"""Satu definisi pembersih nama speed profile (dipakai backend, jangan ulang regex-nya).

Profil hasil impor/sinkron dari OLT yang pernah dikelola SmartOLT membawa token vendor di
namanya (`SMARTOLT-5Mbps`, `5Mbps_SmartOLT`, `SmartOLT 10M`). Token itu bukan bagian paket
pelanggan, jadi dibuang untuk tampilan dan untuk nama baris master yang baru dibuat.

Dipakai di dua titik (DECISIONS: bersih saat DISIMPAN dan saat DITAMPILKAN, supaya data lama
di DB ikut bersih tanpa migrasi data):
  * simpan: speed_profile_service.get_or_create_from_device / sync_from_olt;
  * tampil: speed_profile_service._row, onu_service._row, master_data_service preset out.

`device_profile_id` TIDAK pernah dibersihkan — itu nama profil di perangkat yang dipakai di
command CLI, harus persis.
"""

import re
from typing import overload

# Token `smartolt` sebagai kata utuh. `\b` tidak dipakai karena `_` termasuk word char di
# Python, padahal `5Mbps_SmartOLT` harus ikut terbersihkan.
_SMARTOLT = re.compile(r"(?<![0-9A-Za-z])smartolt(?![0-9A-Za-z])", re.I)
# Pemisah dobel sisa pembuangan token: `A-_B` -> `A-B`.
_DOUBLE_SEP = re.compile(r"[-_\s]{2,}")


@overload
def clean_profile_name(name: str) -> str: ...
@overload
def clean_profile_name(name: None) -> None: ...


def clean_profile_name(name: str | None) -> str | None:
    """`SMARTOLT-5Mbps` -> `5Mbps`. Nama tanpa token (mis. `KhanzaNet`) tidak berubah.

    Hasil kosong (nama yang isinya cuma token, mis. `SMARTOLT`) -> nama asli, supaya tidak
    pernah tampil kosong.
    """
    if not name:
        return name
    out = _DOUBLE_SEP.sub(lambda m: m.group(0)[0], _SMARTOLT.sub("", name)).strip(" -_")
    return out or name
