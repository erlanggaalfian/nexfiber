# Nexfiber — Referensi SNMP OID

Semua OID dicek langsung ke perangkat ZTE C300, ZTE C320, dan CDATA FD1602SB1 secara read-only (`snmpgetnext`).

## Standar (semua vendor)

| Data | OID | Status |
|---|---|---|
| sysDescr | `1.3.6.1.2.1.1.1` | ✅ terverifikasi |
| sysObjectID | `1.3.6.1.2.1.1.2` | ✅ terverifikasi |
| sysUpTime | `1.3.6.1.2.1.1.3` | ✅ terverifikasi |
| sysName | `1.3.6.1.2.1.1.5` | ✅ terverifikasi |
| sysLocation | `1.3.6.1.2.1.1.6` | ✅ terverifikasi |
| ifDescr | `1.3.6.1.2.1.2.2.1.2` | ✅ terverifikasi |
| ifOperStatus | `1.3.6.1.2.1.2.2.1.8` | ✅ terverifikasi |
| ifHCInOctets | `1.3.6.1.2.1.31.1.1.1.6` | ✅ terverifikasi |
| ifHCOutOctets | `1.3.6.1.2.1.31.1.1.1.10` | ✅ terverifikasi |

## ZTE C300/C320 — enterprise 3902

| Data | OID | Status |
|---|---|---|
| ONU type | `1.3.6.1.4.1.3902.1012.3.28.1.1.1` | ✅ terverifikasi |
| ONU name | `1.3.6.1.4.1.3902.1012.3.28.1.1.2` | ✅ terverifikasi |
| ONU description | `1.3.6.1.4.1.3902.1012.3.28.1.1.3` | ✅ terverifikasi |
| ONU serial | `1.3.6.1.4.1.3902.1012.3.28.1.1.5` | ✅ terverifikasi |
| ONU admin state | `1.3.6.1.4.1.3902.1012.3.28.1.1.17` | ✅ terverifikasi |
| ONU phase state | `1.3.6.1.4.1.3902.1012.3.28.2.1.4` | ✅ terverifikasi |
| ONU last down cause | `1.3.6.1.4.1.3902.1012.3.28.2.1.7` | ✅ terverifikasi |
| ONU Rx power | `1.3.6.1.4.1.3902.1012.3.50.12.1.1.10` | ✅ terverifikasi |
| ONU vendor ID | `1.3.6.1.4.1.3902.1012.3.50.11` | ✅ terverifikasi |
| ONU RxOctets | `1.3.6.1.4.1.3902.1082.500.4.2.2.2.1.1` | ✅ terverifikasi |
| ONU RxPackets | `1.3.6.1.4.1.3902.1082.500.4.2.2.2.1.2` | ✅ terverifikasi |
| ONU RxErrPackets | `1.3.6.1.4.1.3902.1082.500.4.2.2.2.1.12` | ✅ terverifikasi |
| ONU TxOctets | `1.3.6.1.4.1.3902.1082.500.4.2.2.2.1.44` | ✅ terverifikasi |
| ONU TxPackets | `1.3.6.1.4.1.3902.1082.500.4.2.2.2.1.45` | ✅ terverifikasi |
| ONU distance | `1.3.6.1.4.1.3902.1082.500.10.2.3.10.1.2` | ✅ terverifikasi |
| Unconfigured ONU SN | `1.3.6.1.4.1.3902.1012.3.13.3.1.2` | ❌ tidak tersedia |
| OLT temperature | `1.3.6.1.4.1.3902.1015.2.1.3.2` | ✅ terverifikasi |
| Board name | `1.3.6.1.4.1.3902.1015.2.1.1.3.1.4` | ✅ terverifikasi |
| Board status | `1.3.6.1.4.1.3902.1015.2.1.1.3.1.5` | ✅ terverifikasi |
| Card type | `1.3.6.1.4.1.3902.1082.10.1.2.4.1.4` | ✅ terverifikasi |
| Card CPU % | `1.3.6.1.4.1.3902.1082.10.1.2.4.1.9` | ✅ terverifikasi |
| Card RAM % | `1.3.6.1.4.1.3902.1082.10.1.2.4.1.11` | ✅ terverifikasi |

## CDATA FD1602SB1 — enterprise 34592 + NSCRTV 17409

| Data | OID | Status |
|---|---|---|
| CPU % | `1.3.6.1.4.1.34592.1.3.100.1.8.1` | ✅ terverifikasi |
| Memory | `1.3.6.1.4.1.34592.1.3.100.1.8.2` | ✅ terverifikasi |
| Flash total | `1.3.6.1.4.1.34592.1.3.100.1.8.3` | ✅ terverifikasi |
| Flash free | `1.3.6.1.4.1.34592.1.3.100.1.8.4` | ✅ terverifikasi |
| Temperature | `1.3.6.1.4.1.34592.1.3.100.1.8.6` | ✅ terverifikasi |
| Temp threshold | `1.3.6.1.4.1.34592.1.3.100.1.8.7` | ✅ terverifikasi |
| ONU OutPkts | `1.3.6.1.4.1.34592.1.3.100.12.7.1.2` | ✅ terverifikasi |
| ONU InPkts | `1.3.6.1.4.1.34592.1.3.100.12.7.1.3` | ✅ terverifikasi |
| ONU OutBytes | `1.3.6.1.4.1.34592.1.3.100.12.7.1.4` | ✅ terverifikasi |
| ONU InBytes | `1.3.6.1.4.1.34592.1.3.100.12.7.1.5` | ✅ terverifikasi |
| ONU info table (NSCRTV) | `1.3.6.1.4.1.17409.2.8.4.1.1` | ✅ terverifikasi |
| ONU distance (NSCRTV) | `1.3.6.1.4.1.17409.2.8.4.1.1.9` | ✅ terverifikasi |
| ONU optical (NSCRTV) | `1.3.6.1.4.1.17409.2.8.4.4.1` | ✅ terverifikasi |

## Index ZTE

Ada dua skema index. Jangan dipakai bergantian.

1. Tabel identitas, status, dan Rx power (`1012.3.28.*`, `1012.3.50.12.*`):
   `ifIndex = 268435456 + slot*65536 + port*256`, lalu `.onu_id`.
2. Tabel trafik dan jarak (`1082.500.*`):
   `ifIndex = (1<<28) | (rack<<24) | (shelf<<16) | (slot<<8) | port`, lalu `.onu_id`.
   Rack dan shelf biasanya `1`.

## Nilai phase state ZTE (`1012.3.28.2.1.4`)

| Nilai | Arti |
|---|---|
| 0 | logging |
| 1 | los |
| 2 | syncMib |
| **3** | **working / online** |
| 4 | dyingGasp |
| 5 | authFailed |
| 6 | offline |

Terverifikasi: jumlah ONU bernilai `3` sama persis dengan jumlah ONU online. Hanya `3` yang dianggap online.

## Index CDATA

Trafik dan jarak: `index = 0x480000 | ((port-1) << 12) | onu_id`.

## Catatan

- `Unconfigured ONU SN` (`1012.3.13.3.1.2`) tidak tersedia. `sync_unconfigured` tetap memakai CLI.
- Tabel optical `1082.500.*` memakai index skema 2 dan melaporkan **dBm x 1000 bertanda**
  (raw `-23768` = `-23.768` dBm). Jangan pakai `decode_pon_ifindex` (skema 1) untuk tabel ini:
  index nyata `285279745` = PON 1/6/1, kalau salah skema terbaca slot 257 dan Rx jadi NULL.
  Terverifikasi di OLT SBI 2026-10-24 (silang `show pon power onu-rx|olt-rx`).
- Kalau seluruh `ifDescr` kosong (C300 produksi), ifIndex PON dihitung
  (`encode_pon_ifindex`), bukan dibaca dari SNMP.
- CPU/RAM ZTE dibaca per kartu dengan index `.1.1.<slot>`. Main control bertipe `SCXN`.
- Rx/Tx dilihat dari sisi OLT: Rx = upload pelanggan, Tx = download pelanggan.
- Port SNMP bisa bukan 161. Selalu baca port dari config OLT.
- Community, IP, dan port disimpan di DB/config, bukan di repo.

## SNMP RO dan RW

Setiap OLT punya dua community:
- **RO (read-only):** dipakai untuk semua polling (status, optik, trafik, health).
- **RW (read-write):** hanya dipakai worker untuk aksi tulis yang tercantum di bawah.

Uji tulis dilakukan di ONU test. Semua nilai sudah dikembalikan seperti semula.

### Hasil uji

| Uji | Hasil |
|---|---|
| SET memakai community RO (ZTE) | ❌ timeout. RO benar-benar tidak bisa menulis |
| SET memakai community RW (ZTE) | ✅ diterima |
| GET memakai community RW | ✅ bisa, tapi polling tetap pakai RO |
| Community RW di CDATA | ⚠️ aktif di sebagian OLT. Di OLT lain RW timeout |

### OID yang bisa ditulis (ZTE C300/C320)

Index: `<ifIndex>.<onu_id>`, dengan `ifIndex = 268435456 + slot*65536 + port*256`.

| Aksi | OID | Tipe | Nilai | Status |
|---|---|---|---|---|
| Ganti nama ONU | `1.3.6.1.4.1.3902.1012.3.28.1.1.2` | `s` | teks | ✅ terverifikasi, nilai terbaca kembali |
| Ganti deskripsi ONU | `1.3.6.1.4.1.3902.1012.3.28.1.1.3` | `s` | teks | ✅ terverifikasi |
| Enable / disable ONU | `1.3.6.1.4.1.3902.1012.3.28.1.1.17` | `i` | `1` = enable, `2` = disable | ✅ terverifikasi, nilai terbaca kembali |

Contoh:

```bash
snmpset -v2c -c <community_rw> <ip>:<port> 1.3.6.1.4.1.3902.1012.3.28.1.1.17.<ifIndex>.<onu_id> i 2
```

### CDATA FD1602SB1

Belum ada OID tulis ONU yang terverifikasi. Semua aksi tulis CDATA tetap lewat CLI.

### Yang tetap lewat CLI

Auth ONU, hapus ONU, profile kecepatan, VLAN, service-port, PPPoE, TR-069, dan reboot.
Belum ada OID tulis yang terverifikasi untuk aksi-aksi ini.

### Aturan untuk Nexfiber

1. Simpan `snmp_community_ro` dan `snmp_community_rw` sebagai kolom terpisah dan terenkripsi.
2. Polling hanya boleh memakai RO. Community RW hanya dibaca oleh worker saat menjalankan aksi tulis.
3. Setelah SET, baca ulang OID-nya memakai RO. Jika nilainya tidak berubah, job dianggap gagal.
4. Jika SET gagal atau timeout, jalankan aksi yang sama lewat CLI. Catat jalur yang dipakai di log job.
5. SET SNMP hanya mengubah running-config. Untuk menyimpan perubahan, jalankan `write` lewat CLI. Satukan dalam satu job `write` yang di-debounce per OLT.
6. Community RW tidak boleh muncul di UI, log, atau response API.
7. SNMPv2c tidak terenkripsi. Batasi akses SNMP di OLT hanya dari IP server Nexfiber.
8. Saat menambah OLT, tes RO dan RW secara terpisah. Jika RW gagal, OLT tetap bisa dipakai, tapi semua aksi tulis lewat CLI.
9. Jangan memakai community `public`/`private`. Generate community acak saat menambah OLT.

### Konfigurasi community di OLT

ZTE:

```text
configure terminal
snmp-server community <community_ro> view allview ro
snmp-server community <community_rw> view allview rw
exit
write
```

CDATA:

```text
config
snmp-agent community read <community_ro>
snmp-agent community write <community_rw>
exit
write
```

Status: 🔧 produksi.
