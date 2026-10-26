"""Schema LIVE traffic per-ONU (Fase 2, pengecualian sempit yang disetujui user).

ARAH TRAFIK — kontrak dengan frontend, dibaca relatif terhadap **ONU**, bukan OLT:

| field | arti relatif ONU | istilah pelanggan | OID ZTE |
|---|---|---|---|
| `in_octets`  | MASUK ke ONU (OLT -> ONU)  | DOWNLOAD | `…4.2.2.2.1.44` (TxOctets) |
| `out_octets` | KELUAR dari ONU (ONU -> OLT) | UPLOAD | `…4.2.2.2.1.1` (RxOctets) |

Tabel `zxAnPonOnuIfCurrPerfTable` menulis Rx/Tx dari **sudut OLT**: "Rx" = yang OLT
terima dari ONU (= upload pelanggan), "Tx" = yang OLT kirim ke ONU (= download
pelanggan). Jadi pemetaannya SENGAJA bertukar nama supaya field API konsisten
"relatif ONU". Aplikasi referensi memakai konvensi yang sama
(`rx_octets` -> upSpeed, `tx_octets` -> downSpeed, `onu-detail.php:1088-1089`).

Nilai adalah **counter kumulatif** sejak OLT boot (bukan kecepatan). Mbps dihitung di
frontend dari 2 sample: `delta_octets * 8 / delta_detik / 1e6`. Sample pertama hanya
baseline. Octet dikirim sebagai **string desimal** karena Counter64 melewati
Number.MAX_SAFE_INTEGER di JavaScript — frontend mem-parse ke BigInt.

`counter_bits` (32 atau 64) dibutuhkan frontend untuk menangani wrap counter:
modulus = 2**counter_bits. Kalau delta negatif -> wrap/reset, jangan gambar angka.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OnuTrafficSample(BaseModel):
    serial_number: str
    sampled_at: datetime = Field(description="Waktu backend membaca counter, ISO-8601 UTC")
    in_octets: str = Field(description="Desimal string; octet MASUK ke ONU = download")
    out_octets: str = Field(description="Desimal string; octet KELUAR dari ONU = upload")
    counter_bits: Literal[32, 64] = Field(description="Lebar counter: modulus wrap = 2**bits")


class OnuTrafficPoint(BaseModel):
    """Satu titik grafik `Traffic history` (sampel tersimpan, interval ±5 menit).

    Berbeda dari `OnuTrafficSample`: laju sudah DIHITUNG backend dari sampel sebelumnya
    (hanya backend yang menyimpan masa lalu). `null` = laju tidak diketahui (sampel
    pertama, counter wrap, atau sampler sempat berhenti) — frontend harus memutus garis
    di titik itu, bukan menggambar nol.
    """

    sampled_at: datetime
    in_bps: int | None = Field(description="bit/detik MASUK ke ONU = download pelanggan")
    out_bps: int | None = Field(description="bit/detik KELUAR dari ONU = upload pelanggan")
