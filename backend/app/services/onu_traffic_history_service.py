"""Sampler + histori trafik per ONU (SNMP read-only, satu job per OLT).

Kenapa di worker dan bukan dibaca saat halaman dibuka: grafik 24 jam/7 hari/30 hari butuh
sampel yang dikumpulkan terus-menerus; satu permintaan HTTP tidak bisa mengarang masa lalu.
Panel LIVE (`onu_traffic_service`) tetap jalur terpisah untuk laju detik-demi-detik.

Beban ke OLT: **dua bulkwalk per OLT per siklus** (tabel RX + TX zxAnPonOnuIfCurrPerf),
bukan per ONU. Terukur di OLT WNG (247 baris/tabel): 0,7-0,9 detik per bulkwalk.

Aturan:
- bps dihitung dari dua sampel BERURUTAN milik ONU itu. Sampel pertama -> bps NULL
  (baseline), tidak pernah 0 palsu.
- Counter wrap (delta negatif) dikoreksi dengan modulus; lompatan > setengah ruang
  counter dianggap reset agen SNMP -> bps NULL, bukan angka raksasa.
- OLT tak terjangkau = DriverError dari bulkwalk -> job gagal dan dicoba lagi siklus
  berikutnya; tidak ada baris ditulis, tidak ada lock yang dipegang.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Literal

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import scope_olt_ids
from app.core.security import decrypt_secret
from app.drivers.transport.snmp import SnmpTransport
from app.drivers.zte_c320 import decode_optical_ifindex
from app.models.olt import Olt, PonPort
from app.models.onu import Onu, OnuTrafficHistory
from app.models.user import User
from app.repositories import onu_repo
from app.services.onu_traffic_service import (
    OID_OLT_RX_OCTETS,
    OID_OLT_TX_OCTETS,
    counter_bits,
)

# Interval sampler (schedules.py) — dipakai juga untuk membatasi delta yang masih wajar.
SAMPLE_INTERVAL_MINUTES = 5
# Retensi TIDAK lagi di sini: diatur per jenis data di Settings -> Graph Data
# (`graph_data_service`, job harian `purge_graph_data`), bukan konstanta sampler.
RANGES: dict[str, timedelta] = {
    "24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30),
}
# Delta waktu di atas ini (worker mati lama) tetap dihitung? Tidak: rata-rata lintas jam
# menyamarkan puncak dan menipu operator. Lebih jujur mengosongkan laju.
MAX_DELTA_S = SAMPLE_INTERVAL_MINUTES * 60 * 4


def delta_bps(prev_octets: int, octets: int, seconds: float, bits: int) -> int | None:
    """Laju bit/detik dari dua bacaan counter. `None` = tidak bisa dipercaya.

    Menangani wrap counter unsigned (delta negatif + modulus) dan membedakannya dari
    reset agen SNMP (lompatan > setengah ruang counter -> tidak diketahui).
    """
    if seconds <= 0 or seconds > MAX_DELTA_S:
        return None
    modulus = 1 << bits
    delta = octets - prev_octets
    if delta < 0:
        delta += modulus
    if delta > modulus // 2:
        return None
    return int(delta * 8 / seconds)


async def _walk_table(snmp: SnmpTransport, base_oid: str) -> dict[tuple[int, int, int], tuple[int, int]]:
    """Satu bulkwalk seluruh OLT -> {(slot, port, onu_index): (octets, counter_bits)}.

    Baris yang nilainya bukan angka DILEWATI (bukan menggagalkan seluruh OLT): satu ONU
    aneh tidak boleh menghilangkan sampel 246 ONU lainnya.
    """
    out: dict[tuple[int, int, int], tuple[int, int]] = {}
    for oid, value in await snmp.bulkwalk(base_oid):
        suffix = oid[len(base_oid) + 1:].split(".")
        if len(suffix) != 2 or not all(s.isdigit() for s in suffix):
            continue
        slot, port = decode_optical_ifindex(int(suffix[0]))
        try:
            out[(slot, port, int(suffix[1]))] = (int(str(value)), counter_bits(value))
        except (TypeError, ValueError):
            continue
    return out


async def _previous(db: AsyncSession, onu_ids: list[int]) -> dict[int, OnuTrafficHistory]:
    """Sampel terakhir per ONU. DISTINCT ON = satu baris terbaru per onu_id dalam satu
    query (index (onu_id, sampled_at) dipakai), bukan N query."""
    if not onu_ids:
        return {}
    stmt = (
        select(OnuTrafficHistory)
        .where(OnuTrafficHistory.onu_id.in_(onu_ids))
        .order_by(OnuTrafficHistory.onu_id, OnuTrafficHistory.sampled_at.desc())
        .distinct(OnuTrafficHistory.onu_id)
    )
    return {row.onu_id: row for row in (await db.execute(stmt)).scalars()}


async def sample_olt(db: AsyncSession, olt: Olt) -> dict:
    """Satu siklus sampler untuk satu OLT. Dipanggil handler job `sample_onu_traffic`."""
    now = datetime.now(UTC)
    snmp = SnmpTransport(str(olt.host), decrypt_secret(olt.snmp_community_enc), olt.snmp_port)
    upload = await _walk_table(snmp, OID_OLT_RX_OCTETS)   # OLT terima <- ONU = upload
    download = await _walk_table(snmp, OID_OLT_TX_OCTETS)  # OLT kirim -> ONU = download

    onus = {
        (slot, port, onu.onu_index): onu
        for slot, port, onu in await db.execute(
            select(PonPort.slot, PonPort.port, Onu)
            .join(Onu, Onu.pon_port_id == PonPort.id)
            .where(Onu.olt_id == olt.id, Onu.deleted_at.is_(None))
        )
    }
    previous = await _previous(db, [onu.id for onu in onus.values()])

    # ONU yang hanya muncul di satu tabel (RX saja atau TX saja) sebelumnya dibuang
    # diam-diam: tidak ada baris, tidak ada jejak. Baris null sengaja TIDAK ditulis
    # (akan jadi "sampel sebelumnya" dan merusak delta berikutnya); sebagai gantinya
    # kasusnya dicatat di log worker supaya bisa dibedakan dari sampler yang berhenti.
    partial = sorted(
        (set(upload) | set(download)) & set(onus) - (set(upload) & set(download)))
    if partial:
        logger.warning(
            "sample_onu_traffic OLT %s: %d ONU hanya di satu tabel trafik: %s",
            olt.id, len(partial), [onus[k].serial_number for k in partial[:10]])

    written = with_rate = 0
    # Urut posisi: dua proses menulis dalam urutan sama -> tidak ada deadlock.
    for key in sorted(set(upload) & set(download) & set(onus)):
        onu = onus[key]
        out_octets, out_bits = upload[key]
        in_octets, in_bits = download[key]
        prev = previous.get(onu.id)
        in_bps = out_bps = None
        if prev is not None:
            seconds = (now - prev.sampled_at).total_seconds()
            in_bps = delta_bps(int(prev.in_octets), in_octets, seconds, in_bits)
            out_bps = delta_bps(int(prev.out_octets), out_octets, seconds, out_bits)
        db.add(OnuTrafficHistory(
            onu_id=onu.id, in_octets=in_octets, out_octets=out_octets,
            in_bps=in_bps, out_bps=out_bps, sampled_at=now,
        ))
        written += 1
        if in_bps is not None or out_bps is not None:
            with_rate += 1

    # Sampler trafik TIDAK menulis olt.status/last_error: itu kolom kesehatan
    # OLT (sync/test_connection), bukan bukti dari bulkwalk trafik. Sebelumnya
    # baris ini menandai OLT "online" dan menghapus last_error hanya karena
    # trafik terbaca, menutupi kegagalan CLI/kesehatan.
    return {"onus_on_device": len(upload), "samples_written": written,
            "samples_with_rate": with_rate, "samples_partial_table": len(partial)}


async def history(db: AsyncSession, serial: str, range_: Literal["24h", "7d", "30d"],
                  user: User) -> list[OnuTrafficHistory]:
    """Titik grafik untuk satu ONU. Scope OLT ditegakkan lewat repo yang sama dengan
    endpoint ONU lain: ONU milik Admin lain -> 404."""
    from app.core.exceptions import NotFoundError

    row = await onu_repo.get_row_by_serial(db, serial, scope_olt_ids(user))
    if row is None:
        raise NotFoundError(f"ONU {serial} not found")
    since = datetime.now(UTC) - RANGES[range_]
    stmt = (
        select(OnuTrafficHistory)
        .where(OnuTrafficHistory.onu_id == row[0].id, OnuTrafficHistory.sampled_at >= since)
        .order_by(OnuTrafficHistory.sampled_at)
    )
    return list((await db.execute(stmt)).scalars().all())
