# Detail ONU — VLAN / Splitter / Zone kosong: bukti sumber data + kontrak API

Status: **analisis read-only + helper parser (sudah ada test), BELUM diintegrasikan** ke
sync/schema/endpoint. Integrasi minimal dilakukan parent/agent pemilik file terkait.
Tidak ada perintah tulis ke OLT/ONU, tidak ada data pelanggan diubah, tidak ada baris
master dibuat.

QUEUE: item "pada Detail ONU, kolom VLAN, Splitter, Zone masih kosong".

## 1. Mengapa ketiga kolom kosong

| Kolom UI | Sumber payload sekarang | Isi nyata DB (OLT SBI id=31, 39 ONU) |
|---|---|---|
| `Zone` | `OnuDetail.zone_name` ← `onus.zone_id` → `zones.name` | `zone_id` NULL **39/39**, tabel `zones` **0 baris** |
| `Splitter` | `OnuDetail.splitter_name` ← `onus.splitter_id` → `splitters.name` | `splitter_id` NULL **39/39**, `splitter_port` NULL 39/39, tabel `splitters` **0 baris** |
| `VLAN terpasang` | `OnuDetail.vlan_number` ← `onus.vlan_id` → `vlans.vlan_id` | `onus.vlan_id` NULL **39/39** (padahal `vlans` punya 6 baris untuk OLT 31: 1, 15, 19, 68, 100, 3045) |

Jadi **bukan bug render**: join-nya benar (`repositories/onu_repo._onu_rows()` sudah
`outerjoin` Vlan/Zone/Splitter dan service mengirim `vlan_number`/`zone_name`/
`splitter_name`), tapi ketiga foreign key memang NULL dan dua tabel master kosong.
Yang hilang adalah **jalur pengisian**, bukan tampilan.

## 2. Data yang ternyata ADA di perangkat (bukti read-only, 2026-10-24)

### 2.1 VLAN per-ONU — ada, lengkap, belum pernah dibaca

`show running-config` OLT SBI (83 KB, 39 stanza `interface gpon-onu_…`):

```
interface gpon-onu_1/6/2:15
  service-port 1 vport 1 user-vlan 15 vlan 15
  service-port 2 vport 2 user-vlan 100 vlan 100
```

Hitungan nyata 39 ONU:

| Set VLAN per ONU | Jumlah ONU |
|---|---|
| `[15, 100]` | 37 |
| `[15]` | 1 |
| `[15, 100, 3045]` | 1 |

- 78 baris `service-port` total; **`user-vlan` == `vlan` pada 78/78 baris** di OLT ini,
  jadi perbedaan inner/outer belum pernah muncul di produksi — helper tetap menyimpan
  keduanya dan memakai angka setelah keyword `vlan` untuk display (sesuai instruksi).
- Aplikasi referensi hanya mengambil **service-port pertama** (`zte_c320.py:2037`,
  komentar "Skip subsequent (management)") lalu menyimpannya ke satu kolom
  `onus.vlan` → di referensi pun ONU multi-layanan kehilangan VLAN keduanya. Nexfiber
  tidak mengulangi itu: daftar, bukan satu angka.
- `vlan-filter iphost … vlan <n>` (77 baris) sengaja TIDAK dipakai sebagai sumber VLAN
  layanan — itu filter IP host manajemen ONU.

### 2.2 Metadata zone/alamat/ODP/tanggal otorisasi — formatnya nyata, isinya tipis di OLT ini

Format terstruktur `name_…_zone_…_descr_…_odb_…_authd_YYYYMMDD` adalah kontrak
**eksplisit operator**: ditulis oleh aplikasi referensi
(`frontend/action/auth-onu.php`, `replace-onu.php`, `update-onu-mode.php`) dan dibaca
balik oleh `backend/db.php::parse_structured_description`.

Isi `description` nyata OLT SBI (39/39 ONU punya `name` dan `description`):

| Token | Jumlah ONU (dari 39) |
|---|---|
| `zone_` | 3 |
| `_descr_` | 1 |
| `_odb_` | **0** |
| `_authd_` | 2 |
| teks bebas tanpa token (alamat saja) | 35 |

Panjang `description` maksimum di OLT ini **58 karakter**, jadi di OLT SBI tidak ada
pemotongan. Tapi di korpus referensi (6.677 description terstruktur, dump read-only
`/home/kamal/smartolt`): panjang maksimum **246**, dan **14 melebihi 128**. Diuji: kalau
string itu dipotong di 128, `_odb_` dan `_authd_` **hilang total pada 14/14**. Kolom
`onus.description` Nexfiber saat ini `varchar(128)` → **prasyarat migrasi** sebelum
import metadata, lihat §5.

Parse korpus referensi dengan helper baru (6.677 string): zone 6.661, splitter 6.483,
auth date 6.076, alamat 6.597 — tidak ada exception.

### 2.3 SNMP-first: metadata ONU tidak perlu CLI

Probe read-only bulkwalk OLT SBI (OID sudah tercatat "terverifikasi" di
`NEXFIBER-SNMP-OID.md` baris 24-25):

| OID | Hasil |
|---|---|
| `1.3.6.1.4.1.3902.1012.3.28.1.1.2` (ONU name) | 39 baris, panjang maks 37 |
| `1.3.6.1.4.1.3902.1012.3.28.1.1.3` (ONU description) | 39 baris, panjang maks 58 |

Dibandingkan field hasil parse `show running-config` per (slot, port, onu_id):
**keyset identik, 0 selisih nilai (39/39)**. Index = skema 1
(`268435456 + slot*65536 + port*256`, lalu `.onu_id`) → `decode_pon_ifindex` yang sudah
ada cocok tanpa perubahan.

Konsekuensi: polling metadata boleh pindah ke SNMP (cepat, tanpa sesi CLI 11 detik /
83 KB). **Pengecualian:** output tombol `Status` / `Show running-config` / `Info SW`
tetap WAJIB CLI (instruksi user); dan **VLAN layanan tetap dari CLI `service-port`** —
belum ada OID terverifikasi untuk service-port, jadi tidak boleh diklaim SNMP.

## 3. Helper baru (file sendiri, parser sibling tidak disentuh)

`backend/app/services/onu_device_metadata.py` — pure, tanpa DB/perangkat:

- `parse_device_description(desc) -> DeviceMetadata{zone, address, splitter, contact,
  external_id, authorized_on: date|None, free_text, structured}`
  Delimiter robust: nilai boleh memuat spasi/`/`/`.`/underscore; tiap field berhenti di
  delimiter berikutnya yang dikenal (`zone|descr|odb|authd|contact|name|extid`), bukan di
  underscore pertama. `None`/kosong → None. `_authd_` tidak valid → None, **tidak pernah
  diturunkan dari timestamp sync/registrasi**. Teks bebas tetap teks bebas (tidak dipaksa
  jadi zone/ODP). Hard-wrap OLT disatukan sebelum parse.
- `parse_service_ports(cfg)` / `service_vlan_ids(cfg)` → daftar VLAN dedupe, urutan
  stabil sesuai urutan perangkat.
- `classify_service_vlans(ids, master)` → `ServiceVlan{vlan_id, name, is_management,
  in_master}`; `is_management` **hanya** dari `vlans.type == "management"` (tidak ada
  angka di-hardcode). VLAN yang belum ada di master tetap tampil (`in_master=False`).
- `display_service_vlans(rows)` → buang yang management. Kalau semuanya management,
  hasilnya **list kosong** — ditampilkan apa adanya, tanpa fallback.

Test: `backend/tests/test_onu_device_metadata.py`, 16 test (contoh eksplisit user,
nilai berspasi/underscore, token `None`, teks bebas, token parsial, tanggal invalid,
hard-wrap, ODP+GPS, multi-VLAN 15+100, dedupe, inner≠outer, filter management via flag,
semua-management → kosong, VLAN tak dikenal master tetap nyata, tanpa service-port →
kosong).

Catatan kondisi master OLT 31 hari ini: VLAN 100 ber-`type='internet'`, jadi filter
management **belum** menyembunyikan apa pun (39/39 ONU punya VLAN tampil). Kalau operator
menandai 100 sebagai management, display jadi `[15]` untuk 38 ONU dan `[15, 3045]` untuk 1.

## 4. Kontrak API yang diusulkan ke parent (untuk frontend yang sedang rewrite)

Tambahan field di `OnuDetail` (tidak ada endpoint baru, tidak menghapus field lama):

```jsonc
{
  // VLAN: daftar, bukan satu angka. Sumber: service-port running-config per ONU.
  "service_vlans": [
    { "vlan_id": 15,  "name": "VLAN15",  "is_management": false, "in_master": true },
    { "vlan_id": 100, "name": "VLAN100", "is_management": false, "in_master": true }
  ],
  // Kolom "VLAN" Detail ONU merender service_vlans yang is_management == false.
  // Array kosong = jujur kosong (semua management / tidak ada service-port). Jangan fallback.

  // Metadata hasil parse description perangkat (read-only, belum tentu = kolom operator)
  "device_metadata": {
    "zone": "Nawangan",
    "address": "Grandring Pucung RT 03/ 05 kec Kismantoro",
    "splitter": "LGD-01B0214-Gandring",
    "authorized_on": "2026-10-22",
    "structured": true
  }
}
```

Aturan render yang disarankan:
- `vlan_number`/`vlan_id` lama **tetap** (dipakai dialog "Ubah VLAN" yang menulis satu
  VLAN primer); `service_vlans` adalah tampilan nyata perangkat.
- `Zone`/`Splitter`: tampilkan `zone_name`/`splitter_name` (relasi master) kalau ada;
  kalau NULL dan `device_metadata.zone`/`.splitter` ada, tampilkan nilai perangkat dengan
  penanda "dari perangkat (belum terhubung master)". Jangan menampilkan keduanya sebagai
  hal yang sama.
- `authorized_on` hanya dari `_authd_`. Kalau None → "—", **jangan** pakai
  `registered_at`/`last_sync_at`.

## 5. Gap & prasyarat (bukan bug yang bisa "ditutup" hari ini)

1. **Kolom `onus.description` `varchar(128)`** memotong description terstruktur panjang
   (14 kasus terbukti di korpus referensi, `_odb_`+`_authd_` hilang). Prasyarat sebelum
   import metadata: migrasi lebar kolom (atau simpan hasil parse ke kolom tersendiri dan
   jangan clip sebelum parse). Belum dilakukan — butuh izin migrasi.
2. **Master `zones` / `splitters` 0 baris.** Import metadata hanya memberi *teks* zone/ODP.
   Untuk mengisi `onus.zone_id`/`splitter_id` perlu baris master. Usulan aman (belum
   dijalankan, menunggu izin): upsert per `owner_id` scope + per `olt_id`, dedupe
   case-insensitive pada nama yang sudah dinormalisasi, hanya untuk nilai yang muncul di
   perangkat, dengan laporan "akan dibuat N zone / M splitter" sebelum eksekusi. **Tanpa
   bulk-create tanpa validasi dedupe**, dan `splitter.capacity`/`ratio`/`pon_port_id`
   tidak boleh ditebak. Di OLT SBI: 3 nilai zone unik, **0** nilai ODP → praktis belum ada
   yang bisa dipetakan ke `splitters`.
3. **`splitter_port`** tidak ada di description perangkat (token `_odb_` hanya nama ODP).
   Tetap isian operator.
4. **Isian operator tidak boleh ditimpa**: import hanya mengisi kolom yang masih NULL
   (pola yang sudah dipakai `_adopt_inventory` untuk `name`/`description`).
5. **VLAN**: belum ada OID SNMP terverifikasi untuk service-port → tetap CLI.
