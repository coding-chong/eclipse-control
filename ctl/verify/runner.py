"""Acceptance-case executor: pre-snapshot -> action -> assert -> post -> rollback.

The tuple shape mirrors `design.md` §10.  Assertions must be computable
predicates (set diff / counter diff / field equality / regex); a PASS without
evidence is treated as a defect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ..client import Client
from ..errors import CtlError, EndpointNotFound, NotFoundError, PrereqNotReady
from ..lifecycle import latest_run_id, run_paths
from ..targets import Config

#: Group vocabulary (`design.md` §10): read|write|errors|resilience|input.
GROUPS = ("read", "write", "errors", "resilience", "input")

#: Exceptions a case body may raise to mean "the environment is not ready".
ENV_NOT_READY = (PrereqNotReady, EndpointNotFound)


class Skip(Exception):
    """Raised *or returned* by ``expect`` when the case cannot be exercised here.

    A skipped case is neither a pass that hides missing coverage nor a failure:
    the reason is recorded verbatim and surfaced as ``SKIP`` (`implement.md`
    P1.1 forbids silent skips).
    """

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass
class Case:
    """One verifiable interaction with a real target."""

    name: str
    group: str
    targets: Tuple[str, ...]
    description: str
    action: Callable[["Ctx"], object]
    expect: Callable[["Ctx", object], Tuple[bool, str]]
    pre: Optional[Callable[["Ctx"], object]] = None
    post: Optional[Callable[["Ctx"], object]] = None
    rollback: Optional[Callable[["Ctx"], object]] = None
    evidence: Tuple[str, ...] = ()
    requires_bridge: bool = True


@dataclass
class CaseResult:
    name: str
    group: str
    passed: bool
    detail: str
    evidence: List[str] = field(default_factory=list)
    skipped: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "group": self.group,
            "passed": self.passed,
            "skipped": self.skipped,
            "detail": self.detail,
            "evidence": self.evidence,
            "error": self.error,
        }


class Ctx:
    """Per-run case context: bridge connection plus evidence collection."""

    def __init__(self, runner: "Runner", case: Case):
        self.runner = runner
        self.case = case
        self.config: Config = runner.config
        self.target = runner.target
        self.run_id = runner.run_id
        self.paths = runner.paths
        self.evidence: List[str] = []
        self._client: Optional[Client] = None

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = self.runner.connect()
        return self._client

    def note(self, line: str) -> None:
        self.evidence.append(str(line))

    def request(self, method: str):
        response = self.client.request(method)
        self.note("raw: %s" % (response.raw.strip() or "<empty>"))
        return response


class Runner:
    """Selects and executes cases against one target instance."""

    def __init__(self, config: Config, target_name: Optional[str] = None,
                 run_id: Optional[str] = None, port: Optional[int] = None,
                 token: str = ""):
        self.config = config
        self.target = config.target(target_name)
        self.port = port
        self.token = token or config.token
        self.run_id = run_id or latest_run_id(config.run_root, self.target.name)
        self.paths = run_paths(config.run_root, self.run_id) if self.run_id else None
        self._client: Optional[Client] = None

    # -- connection -------------------------------------------------------- #

    def connect(self) -> Client:
        if self._client is not None:
            return self._client
        if self.port is not None:
            client = Client(port=int(self.port), token=self.token)
        elif self.run_id:
            client = Client(run_root=self.config.run_root, run_id=self.run_id,
                            token=self.token)
        else:
            raise PrereqNotReady(
                "no run for target %s under %s; retry: python -m ctl install --target %s"
                % (self.target.name, self.config.run_root, self.target.name))
        if not client.ping(timeout=5.0):
            raise PrereqNotReady(
                "bridge not answering for run %s; retry: python -m ctl install --target %s --run-id %s"
                % (self.run_id or "<none>", self.target.name, self.run_id or "<run_id>"))
        self._client = client
        return client

    # -- selection --------------------------------------------------------- #

    def select(self, case: Optional[str] = None, group: Optional[str] = None,
               all_: bool = False) -> List[Case]:
        from .cases import ALL_CASES

        if case:
            for candidate in ALL_CASES:
                if candidate.name == case:
                    return [candidate]
            raise NotFoundError(
                "no such case: %s; retry: python -m ctl verify --case read.ping" % case)
        if group:
            return [c for c in ALL_CASES if c.group == group]
        return list(ALL_CASES)

    # -- execution --------------------------------------------------------- #

    def run_case(self, case: Case) -> CaseResult:
        ctx = Ctx(self, case)
        pre = None
        try:
            if case.requires_bridge:
                self.connect()
            if case.pre is not None:
                pre = case.pre(ctx)
                ctx.note("pre: %s" % _short(pre))
            result = case.action(ctx)
            outcome = case.expect(ctx, result)
            if isinstance(outcome, Skip):
                return CaseResult(case.name, case.group, True,
                                  "skipped: " + outcome.reason, ctx.evidence, skipped=True)
            passed, detail = outcome
            if case.post is not None:
                ctx.note("post: %s" % _short(case.post(ctx)))
        except Skip as skip_exc:
            return CaseResult(case.name, case.group, True,
                              "skipped: " + skip_exc.reason, ctx.evidence, skipped=True)
        except ENV_NOT_READY:
            raise
        except CtlError as exc:
            return CaseResult(case.name, case.group, False,
                              "error: %s" % exc.line(), ctx.evidence, error=exc.line())
        except Exception as exc:  # noqa: BLE001 - a case must never kill the run
            return CaseResult(case.name, case.group, False,
                              "unexpected: %r" % (exc,), ctx.evidence, error=repr(exc))
        if not passed and case.rollback is not None:
            try:
                case.rollback(ctx)
                ctx.note("rollback: applied")
            except Exception as exc:  # noqa: BLE001
                ctx.note("rollback: failed %r" % (exc,))
        return CaseResult(case.name, case.group, bool(passed), detail, ctx.evidence)

    def run(self, cases: Sequence[Case]) -> List[CaseResult]:
        results = []
        for case in cases:
            if case.targets and self.target.name not in case.targets:
                results.append(CaseResult(case.name, case.group, True,
                                          "skipped: not applicable to target %s" % self.target.name,
                                          skipped=True))
                continue
            results.append(self.run_case(case))
        return results


def _short(value: object, limit: int = 120) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "..."
