"""pysnmp async bulkwalk wrapper (PRD 4.3, 4.4). One bulkwalk = one round-trip per OID
table regardless of ONU count, which is why sync_onu_status can run every 1 minute.
"""

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    bulkCmd,
)

from app.core.exceptions import DriverError


class SnmpTransport:
    def __init__(self, host: str, community: str, port: int = 161, version: str = "2c") -> None:
        self._engine = SnmpEngine()
        self._auth = CommunityData(community, mpModel=1 if version == "2c" else 0)
        self._host = host
        self._port = port

    async def bulkwalk(self, base_oid: str) -> list[tuple[str, object]]:
        """Walk every OID under base_oid, returning (oid_string, value) pairs."""
        target = UdpTransportTarget((self._host, self._port))
        results: list[tuple[str, object]] = []
        obj = ObjectType(ObjectIdentity(base_oid))
        while True:
            error_indication, error_status, _error_index, var_binds = await bulkCmd(
                self._engine,
                self._auth,
                target,
                ContextData(),
                0,
                25,
                obj,
                lexicographicMode=False,
            )
            if error_indication or error_status:
                # Raise, not break: an unreachable OLT must fail the job, not look like "0 ONUs".
                reason = error_indication or error_status
                raise DriverError(f"SNMP walk {base_oid} failed: {reason}")
            if not var_binds:
                break
            oid, value = var_binds[0]
            if not str(oid).startswith(base_oid):
                break
            results.append((str(oid), value))
            obj = ObjectType(ObjectIdentity(oid))
        return results
