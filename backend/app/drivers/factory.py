"""Builds a driver instance from an `olts` row: resolves the class via registry.py and
decrypts the stored CLI/SNMP credentials. Kept out of the worker/service layer so nothing
else needs to know how an Olt model maps to a driver constructor.
"""

from app.core.security import decrypt_secret
from app.drivers.base import OltDriver
from app.drivers.registry import get_driver_class
from app.models.olt import Olt


def build_driver(olt: Olt) -> OltDriver:
    driver_cls = get_driver_class(olt.vendor, olt.model)
    return driver_cls(
        host=str(olt.host),
        cli_username=olt.cli_username,
        cli_password=decrypt_secret(olt.cli_password_enc),
        cli_protocol=olt.cli_protocol,
        cli_port=olt.cli_port,
        snmp_community=decrypt_secret(olt.snmp_community_enc),
        snmp_port=olt.snmp_port,
        cli_enable_password=decrypt_secret(olt.cli_enable_password_enc)
        if olt.cli_enable_password_enc
        else None,
    )
