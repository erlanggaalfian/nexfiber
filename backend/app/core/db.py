from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Pool dinaikkan karena setiap job CLI memegang satu koneksi tambahan untuk kunci
# per-OLT (olt_cli_lock) selain koneksi sesi kerjanya.
engine = create_async_engine(settings.database_url, pool_size=20, max_overflow=10)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# Namespace tetap advisory lock per OLT; harus sama di semua proses.
CLI_LOCK_NAMESPACE = 0x6E78  # 'nx'


@asynccontextmanager
async def olt_cli_lock(olt_id: int) -> AsyncIterator[bool]:
    """Kunci "satu OLT = satu sesi CLI" lintas proses/worker (PRD 4.3).

    Pakai pg_try_advisory_lock LEVEL SESI pada koneksi khusus, bukan level transaksi:
    handler job (onu_service._record, vlan_service) commit di tengah job, dan kunci
    level transaksi akan ikut terlepas di situ — sesi CLI OLT jadi bisa dobel.
    `try_` (tanpa menunggu) = tidak mungkin deadlock; kalau proses mati, Postgres
    melepas kunci saat koneksinya tutup. Hasil False berarti OLT sedang dipakai.
    """
    key = olt_id % 2**31
    async with engine.connect() as conn:
        got = bool(await conn.scalar(
            text("SELECT pg_try_advisory_lock(:ns, :key)"),
            {"ns": CLI_LOCK_NAMESPACE, "key": key},
        ))
        try:
            yield got
        finally:
            if got:
                # Wajib: koneksi kembali ke pool, kunci sesi tidak lepas sendiri.
                await conn.exec_driver_sql(
                    f"SELECT pg_advisory_unlock({CLI_LOCK_NAMESPACE}, {key})"
                )


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
