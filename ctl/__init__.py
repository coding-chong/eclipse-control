"""eclipse-ctl -- external control channel for Eclipse-family IDEs.

Layout (see `design.md` §2)::

    ctl/targets.py    per-IDE facts (Eclipse / JRE / source level / port)
    ctl/client.py     line-protocol client (connect / send / parse / timeout)
    ctl/console.py    Gogo (Equinox) console driver -- NOT the IDE Console view
    ctl/lifecycle.py  run-id discipline, launch / ping / clean / endpoint.json
    ctl/verify/       acceptance-case runner

Only the Python standard library is used, by design (`design-project.md` §15.3).
"""

# Project version == bridge `Bundle-Version` (`design-project.md` §15.2).
__version__ = "0.1.0"

# Protocol version is numbered independently of the project version and only
# moves when the line protocol itself changes (`design-project.md` §15.2).
PROTOCOL_VERSION = 1

# Bridge identity, frozen (`design-project.md` §15.1): OSGi symbolic name may
# contain '-', the Java package name may not.
BUNDLE_SYMBOLIC_NAME = "eclipse-ctl.bridge"
