"""LIVE traffic per-ONU — pembacaan SNMP read-only, tanpa CLI dan tanpa tulis ke device.

Lingkup sengaja sempit (pengecualian Fase 2 yang user setujui): satu snapshot counter
octet per ONU. Tidak ada tabel histori baru, tidak ada kolom DB baru, tidak ada job —
endpoint ini membaca OLT langsung karena nilainya hanya berguna kalau segar.

Arah trafik & pemetaan field: lihat docstring `app/schemas/onu_traffic.py` (satu tempat).

Aturan yang dipaku di sini:
- **Tidak ada angka palsu.** Kalau OLT tidak membalas atau baris ONU tidak ada di tabel
  performance, endpoint gagal (502/404) — JANGAN pernah mengirim 0 yang akan digambar
  frontend sebagai trafik nol padahal faktanya tidak diketahui.
- **Rate limit 1 pembacaan per ONU per 3 detik**, ditegakkan di backend (bukan hanya UI),
  supaya tab LIVE yang ditinggal terbuka / banyak operator tidak membanjiri SNMP OLT.
- **Scope OLT** (`rbac.scope_olt_ids`): ONU di luar scope = 404, sama seperti endpoint ONU lain.
"""

import time
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, DriverError, NotFoundError
from app.core.rbac import scope_olt_ids
from app.core.security import decrypt_secret
from app.drivers.transport.snmp import SnmpTransport
from app.models.user import User
from app.repositories import onu_repo
from app.schemas.onu_traffic import OnuTrafficSample

# zxAnPonOnuIfCurrPerfTable (NEXFIBER-SNMP-OID.md, ✅ terverifikasi). Nama kolom MIB
# memakai sudut pandang OLT; pemetaan ke arah relatif-ONU dilakukan sekali di bawah.
OID_OLT_RX_OCTETS = "1.3.6.1.4.1.3902.1082.500.4.2.2.2.1.1"   # OLT terima <- ONU = UPLOAD
OID_OLT_TX_OCTETS = "1.3.6.1.4.1.3902.1082.500.4.2.2.2.1.44"  # OLT kirim -> ONU = DOWNLOAD

MIN_INTERVAL_S = 3.0
_MAX_TRACKED = 5000  # batas memori penegak rate limit (proses tunggal, PRD 1 worker/1 API)
_last_read: dict[int, float] = {}


class RateLimitedError(AppError):
    """Satu ONU dibaca lebih cepat dari MIN_INTERVAL_S. 429, bukan data basi palsu."""

    status_code = 429


def encode_perf_ifindex(slot: int, port: int, rack: int = 1, shelf: int = 1) -> int:
    """Kebalikan `zte_c320.decode_optical_ifindex` (skema index KEDUA, keluarga 1082.500):
    ifIndex = (1<<28)|(rack<<24)|(shelf<<16)|(slot<<8)|port.

    ponytail: encoder ditulis di sini, bukan di driver, supaya track ini tidak menyentuh
    `zte_c320.py` yang sedang dipegang agent lain. Dites identik dengan
    `decode_optical_ifindex` (tests/test_onu_traffic.py), pindahkan ke driver saat dua
    track sudah merge.
    """
    return (1 << 28) | (rack << 24) | (shelf << 16) | (slot << 8) | port


def _check_rate_limit(onu_id: int, now: float | None = None) -> None:
    now = time.monotonic() if now is None else now
    previous = _last_read.get(onu_id)
    if previous is not None and now - previous < MIN_INTERVAL_S:
        wait = round(MIN_INTERVAL_S - (now - previous), 1)
        raise RateLimitedError(f"Terlalu cepat; coba lagi dalam {wait} detik")
    if len(_last_read) >= _MAX_TRACKED and onu_id not in _last_read:
        # Buang entri tertua supaya dict tidak tumbuh tanpa batas.
        oldest = min(_last_read.items(), key=lambda kv: kv[1])[0]
        del _last_read[oldest]
    _last_read[onu_id] = now


def counter_bits(value: object) -> Literal[32, 64]:
    """32 vs 64 dari tipe SNMP yang benar-benar dibalas OLT (Counter64 -> 64).

    Frontend butuh ini untuk modulus wrap. Tidak ditebak dari besar nilai: counter
    64-bit yang baru di-reset juga kecil.
    """
    return 64 if "64" in type(value).__name__ else 32


async def _walk_octets(snmp: SnmpTransport, base_oid: str, ifindex: int,
                       onu_index: int) -> tuple[int, Literal[32, 64]]:
    """Satu bulkwalk di `base_oid.ifindex` (semua ONU satu PON), ambil baris ONU ini.

    Walk per-PON, bukan per-ONU: GETBULK pada OID daun persis akan mengembalikan OID
    SESUDAHNYA, jadi `bulkwalk` daun selalu kosong. Satu PON = maksimum 128 baris, jadi
    tetap satu round-trip-ish dan tidak menyentuh PON lain.
    """
    prefix = f"{base_oid}.{ifindex}"
    for oid, value in await snmp.bulkwalk(prefix):
        suffix = oid[len(prefix) + 1:].split(".")
        if suffix and suffix[0].isdigit() and int(suffix[0]) == onu_index:
            try:
                return int(str(value)), counter_bits(value)
            except (TypeError, ValueError) as exc:
                raise DriverError(f"Counter {oid} tidak berupa angka") from exc
    raise DriverError(
        f"OLT tidak melaporkan counter trafik untuk ONU index {onu_index} di {base_oid}"
    )


async def read_sample(db: AsyncSession, serial: str, user: User) -> OnuTrafficSample:
    row = await onu_repo.get_row_by_serial(db, serial, scope_olt_ids(user))
    if row is None:
        raise NotFoundError(f"ONU {serial} not found")
    onu, _olt_name, slot, port = row[0], row[1], row[2], row[3]
    if onu.onu_index is None:
        raise NotFoundError(f"ONU {serial} belum punya index di PON, tidak bisa dibaca")

    _check_rate_limit(onu.id)

    olt = await _get_olt(db, onu.olt_id)
    snmp = SnmpTransport(str(olt.host), decrypt_secret(olt.snmp_community_enc), olt.snmp_port)
    ifindex = encode_perf_ifindex(slot, port)

    upload, up_bits = await _walk_octets(snmp, OID_OLT_RX_OCTETS, ifindex, onu.onu_index)
    download, down_bits = await _walk_octets(snmp, OID_OLT_TX_OCTETS, ifindex, onu.onu_index)

    return OnuTrafficSample(
        serial_number=onu.serial_number,
        sampled_at=datetime.now(UTC),
        in_octets=str(download),   # masuk ke ONU = download pelanggan
        out_octets=str(upload),    # keluar dari ONU = upload pelanggan
        counter_bits=min(up_bits, down_bits),
    )


async def _get_olt(db: AsyncSession, olt_id: int):
    from app.models.olt import Olt

    olt = await db.get(Olt, olt_id)
    if olt is None or olt.deleted_at is not None:
        raise NotFoundError(f"OLT {olt_id} not found")
    return olt
