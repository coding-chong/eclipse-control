"""read.env -- identity / protocol handshake.

`design.md` §6: `sys.env` payload must carry ``java.version`` / ``os.name`` /
``bundle`` / ``id`` / ``state`` / ``thread``, with ``state=32`` (ACTIVE);
`design-project.md` §16.3 adds the ``protocol`` field the client compares.
"""

from __future__ import annotations

import re
from typing import Tuple

from ... import BUNDLE_SYMBOLIC_NAME, PROTOCOL_VERSION
from ..runner import Case
from ._util import kv, verdict

_REQUIRED = ("java.version", "os.name", "protocol", "bundle", "port", "thread")


def _action(ctx):
    return ctx.request("sys.env")


def _expect(ctx, response) -> Tuple[bool, str]:
    fields = kv(response.text)
    bundle_line = None
    for line in response.text.splitlines():
        if line.startswith("bundle="):
            bundle_line = line.strip()
            break
    match = re.match(r"^bundle=(\S+) version=(\S+) id=(\d+) state=(\d+)$", bundle_line or "")

    problems = []
    if not response.ok:
        problems.append("expected OK, got %r" % response.status_line)
    missing = [key for key in _REQUIRED if key not in fields]
    if missing:
        problems.append("missing field(s): %s" % ",".join(missing))
    if not match:
        problems.append("bundle line not in '<bsn> version=<v> id=<n> state=<n>' form: %r" % bundle_line)
    else:
        if match.group(1) != BUNDLE_SYMBOLIC_NAME:
            problems.append("bundle symbolic name %r != %r" % (match.group(1), BUNDLE_SYMBOLIC_NAME))
        if match.group(4) != "32":
            problems.append("bundle state %s != 32 (ACTIVE)" % match.group(4))
    protocol = fields.get("protocol")
    if protocol is not None and str(protocol) != str(PROTOCOL_VERSION):
        problems.append("protocol %s != client %s" % (protocol, PROTOCOL_VERSION))
    return verdict(problems, "status=%r bundle=%r protocol=%r java=%r"
                   % (response.status_line, bundle_line, protocol, fields.get("java.version")))


CASE = Case(
    name="read.env",
    group="read",
    targets=("gs32", "ccs12"),
    description="sys.env reports java/os/protocol/bundle(id,state=32)/port/thread",
    action=_action,
    expect=_expect,
    evidence=("raw:action",),
)
