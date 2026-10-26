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
        self._auth = CommunityData(community, mpModel=1 if version == "2c" else 0)
        self._host = host
        self._port = port

    async def bulkwalk(self, base_oid: str) -> list[tuple[str, object]]:
        """Walk every OID under base_oid, returning (oid_string, value) pairs.

        BUG NYATA (worker produksi, 26-10-2026): SnmpEngine dibuat sekali di __init__ dan
        membuka satu socket UDP yang TIDAK PERNAH ditutup. build_driver() memanggil
        SnmpTransport() untuk SETIAP job, jadi tiap job sync (≥2 per menit) membocorkan 1 fd.
        Setelah ~1 hari proses worker menyentuh batas 1024 fd (terukur: 1021 fd, 1012 socket
        UDP) dan SEJAK ITU setiap job gagal: SnmpEngine() tidak bisa lagi membuka file MIB
        -> "No module __SNMP-FRAMEWORK-MIB loaded". Dampak ke UI: job diagnostik Detail ONU
        gagal, pesan 409 "Pembacaan untuk ONU ini masih berjalan" bertahan lama karena job
        menggantung di retry/backoff.
        Karena itu engine dibuat PER walk dan dispatcher-nya ditutup di `finally` — socket
        dilepas walau walk gagal/di-cancel. Engine tidak bisa dipakai ulang setelah
        closeDispatcher() (pysnmp: "No suitable transport domain"), jadi jangan di-cache.
        """
        engine = SnmpEngine()
        try:
            target = UdpTransportTarget((self._host, self._port))
            results: list[tuple[str, object]] = []
            obj = ObjectType(ObjectIdentity(base_oid))
            while True:
                error_indication, error_status, _error_index, var_binds = await bulkCmd(
                    engine,
                    self._auth,
                    target,
                    ContextData(),
                    0,
                    25,
                    obj,
                    lexicographicMode=False,
                )
                if error_indication or error_status:
                    # Raise, not break: an unreachable OLT must fail the job, not look like
                    # "0 ONUs".
                    reason = error_indication or error_status
                    raise DriverError(f"SNMP walk {base_oid} failed: {reason}")
                if not var_binds:
                    break
                # pysnmp 6.x bulkCmd: var_binds = list baris, tiap baris list berisi 1 tuple
                # (oid, value). Pakai SEMUA baris balasan (25 per round-trip), bukan hanya baris
                # pertama -- tabel besar (WNG, 32 PON) jadi ratusan kali lebih cepat.
                last = None
                done = False
                for row in var_binds:
                    if not row:
                        continue
                    oid, value = row[0]
                    if not str(oid).startswith(base_oid):
                        done = True
                        break
                    results.append((str(oid), value))
                    last = oid
                if done or last is None:
                    break
                obj = ObjectType(ObjectIdentity(last))
            return results
        finally:
            dispatcher = engine.transportDispatcher
            if dispatcher is not None:
                dispatcher.closeDispatcher()
