"""vendor+model -> driver class (PRD 4.3). sysObjectID must never be used to pick a
driver (CDATA reports a GPON device under an EPON enterprise OID) — always keyed off the
operator-entered olts.vendor/olts.model fields.
"""

from app.drivers.base import OltDriver
from app.drivers.zte_c320 import ZteC320Driver

_REGISTRY: dict[tuple[str, str], type[OltDriver]] = {
    ("zte", "C320"): ZteC320Driver,
    ("zte", "C300"): ZteC320Driver,  # same command set per PRD; split out if C300 diverges
}

def get_driver_class(vendor: str, model: str) -> type[OltDriver]:
    try:
        return _REGISTRY[(vendor, model)]
    except KeyError:
        raise ValueError(f"No driver registered for vendor={vendor!r} model={model!r}") from None
