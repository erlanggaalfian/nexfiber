"""Satu-satunya definisi bucket sinyal di sisi backend (DECISIONS.md "Sinyal / RX").

4 bucket + LOS, dipakai filter tabel Configured dan export CSV. Batasnya WAJIB sama persis
dengan `rxBucket()` di frontend/src/components/data.tsx — kalau salah satu diubah, ubah
keduanya. Jangan tulis ulang perbandingan dBm di repository/service/router manapun; panggil
`rx_bucket()` atau `bucket_filter()` dari sini.

  Good     : -25 .. -8 dBm
  Fair     : -27 .. -25
  Weak     : -28 .. -27
  Critical : <= -28, ATAU > -8 (kelewat kuat)
  LOS      : tanpa nilai
"""

from sqlalchemy import ColumnElement

STRONG_DBM = -8.0
FAIR_DBM = -25.0
WEAK_DBM = -27.0
CRITICAL_DBM = -28.0

BUCKETS = ("good", "fair", "weak", "critical", "los")


def rx_bucket(dbm: float | None) -> str:
    if dbm is None:
        return "los"
    if dbm > STRONG_DBM or dbm <= CRITICAL_DBM:
        return "critical"
    if dbm < WEAK_DBM:
        return "weak"
    if dbm < FAIR_DBM:
        return "fair"
    return "good"


def bucket_filter(col: ColumnElement, bucket: str) -> ColumnElement:
    """Predikat SQL untuk satu bucket — bayangan `rx_bucket()` di atas."""
    if bucket == "los":
        return col.is_(None)
    if bucket == "critical":
        return col.isnot(None) & ((col > STRONG_DBM) | (col <= CRITICAL_DBM))
    if bucket == "weak":
        return (col > CRITICAL_DBM) & (col < WEAK_DBM)
    if bucket == "fair":
        return (col >= WEAK_DBM) & (col < FAIR_DBM)
    if bucket == "good":
        return (col >= FAIR_DBM) & (col <= STRONG_DBM)
    raise ValueError(f"Unknown rx bucket '{bucket}'")
