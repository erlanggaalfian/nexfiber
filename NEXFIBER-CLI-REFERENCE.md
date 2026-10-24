# Nexfiber — Referensi CLI OLT

Perintah baca dicek langsung secara read-only ke ZTE C300, ZTE C320, dan CDATA FD1602SB1.
Perintah ubah diambil dari driver yang sudah berjalan di produksi, tidak dijalankan ulang saat pengecekan.

Status:
- ✅ terverifikasi: perintah dijalankan dan menghasilkan data.
- ✅ valid, kosong: perintah diterima OLT, tapi tidak ada data untuk ditampilkan.
- ❌ ditolak: OLT membalas `Invalid input` atau `Unknown command`.
- ⚠️ belum terverifikasi: sintaks dipakai kode, tapi urutannya meragukan.
- 🔧 produksi: perintah ubah yang dipakai driver produksi.

Placeholder:
- ZTE: `<pon>` = `rack/slot/port` (contoh `1/2/4`), `<id>` = ONU ID.
- CDATA: `<frame/slot>` = `0/0`, `<port>` = nomor PON, `<id>` = ONT ID.

---

## ZTE C300 / C320

Sintaks C300 dan C320 sama. Pakai `terminal length 0` sebelum perintah `show` yang panjang.

### Baca — OLT

| Data | Perintah | Status |
|---|---|---|
| Daftar kartu | `show card` | ✅ terverifikasi |
| CPU/RAM | `show processor` | ✅ terverifikasi |
| Versi firmware | `show version-running` | ✅ terverifikasi |
| VLAN | `show vlan summary` | ✅ terverifikasi |
| Interface IP | `show ip interface brief` | ✅ terverifikasi |
| Profile upload (T-CONT) | `show running-config \| include profile tcont` | ✅ terverifikasi |
| Profile download (traffic) | `show running-config \| include profile traffic` | ✅ terverifikasi |
| Profile VLAN ONU | `show gpon onu profile vlan` | ✅ terverifikasi |
| Status satu port uplink | `show interface port-status <ge\|xge>i_<rack>/<slot>/<port>` | ✅ terverifikasi |
| VLAN satu port uplink | `show vlan port <port>` | ✅ terverifikasi |

`show interface port-status` TIDAK punya bentuk massal: tanpa nama port dijawab
`%Error 20203: Incomplete command`, dan `all`, nama slot (`xgei_1/19`) maupun rentang yang
melewati port yang ada (`xgei_1/19/1-4` saat hanya 2 port) ditolak. Satu command per port.
Nama port juga tidak bisa diambil dari `ifDescr` SNMP di semua perangkat — di C300 produksi
seluruh `ifDescr` kosong, jadi nama port ditebak dari `show card` lalu divalidasi lewat
command di atas (port yang tidak ada menjawab `%Error 20202`).

### Baca — PON

| Data | Perintah | Status |
|---|---|---|
| Status semua ONU | `show gpon onu state gpon-olt_<pon>` | ✅ terverifikasi |
| Tipe dan SN ONU | `show gpon onu baseinfo gpon-olt_<pon>` | ✅ terverifikasi |
| ONU belum terdaftar per PON | `show gpon onu uncfg gpon-olt_<pon>` | ✅ valid, kosong |
| ONU belum terdaftar semua PON | `show gpon onu uncfg` | ✅ valid, kosong |
| Rx semua ONU | `show pon power onu-rx gpon-olt_<pon>` | ✅ terverifikasi |
| Rx OLT dari semua ONU | `show pon power olt-rx gpon-olt_<pon>` | ✅ terverifikasi |

Jika tidak ada ONU belum terdaftar, `uncfg` membalas `%Code 62310-GPONSRV : No related information to show`.
Parser harus menganggap ini daftar kosong, bukan error.

### Baca — ONU

| Data | Perintah | Status |
|---|---|---|
| Detail ONU | `show gpon onu detail-info gpon-onu_<pon>:<id>` | ✅ terverifikasi |
| Redaman | `show pon power attenuation gpon-onu_<pon>:<id>` | ✅ terverifikasi |
| Config interface ONU | `show running-config interface gpon-onu_<pon>:<id>` | ✅ terverifikasi |
| Config OMCI ONU | `show onu running config gpon-onu_<pon>:<id>` | ✅ terverifikasi |
| IP host / WAN | `show gpon remote-onu ip-host gpon-onu_<pon>:<id>` | ✅ terverifikasi |
| Perangkat ONU | `show gpon remote-onu equip gpon-onu_<pon>:<id>` | ✅ terverifikasi |
| Port LAN ONU | `show gpon remote-onu interface eth gpon-onu_<pon>:<id>` | ✅ terverifikasi |
| MAC address ONU | `show mac gpon onu gpon-onu_<pon>:<id>` | ✅ terverifikasi |
| Statistik trafik ONU | `show interface gpon-onu_<pon>:<id>` | ✅ terverifikasi |
| WAN IP ONU | `show gpon remote-onu wan-ip gpon-onu_<pon>:<id>` | ✅ valid, kosong |
| Config ONU per PON | `show running-config interface gpon-olt_<pon>` | 🔧 produksi |
| Kemampuan ONU | `show gpon remote-onu capability gpon-onu_<pon>:<id>` | 🔧 produksi |

Jika ONU tidak punya WAN IP, `wan-ip` membalas `%Code 64040-GPONRM : No relate information to show`.

### Ditolak — jangan dipakai

| Perintah | Pengganti |
|---|---|
| `show gpon remote-onu wan-info gpon-onu_<pon>:<id>` | `show gpon remote-onu ip-host ...` |
| `show gpon remote-onu eth-status gpon-onu_<pon>:<id>` | `show gpon remote-onu interface eth ...` |
| `show gpon onu traffic-info gpon-onu_<pon>:<id>` | `show interface gpon-onu_<pon>:<id>` atau SNMP |
| `show mac gpon-onu_<pon>:<id>` | `show mac gpon onu gpon-onu_<pon>:<id>` |
| `show onu running config all \| include ...` | Baca per ONU |

### Ubah — Otorisasi ONU

Urutan wajib: T-CONT dan gemport dibuat sebelum `service-port`.

```text
configure terminal
interface gpon-olt_<pon>
onu <id> type <onu_type> sn <serial>
exit
interface gpon-onu_<pon>:<id>
name <name>
description <description>
tcont 1 profile <upload_profile>
gemport 1 tcont 1
gemport 1 traffic-limit downstream <download_profile>
service-port 1 vport 1 user-vlan <vlan> vlan <vlan>
exit
pon-onu-mng gpon-onu_<pon>:<id>
flow mode 1 tag-filter vlan-filter untag-filter discard
flow 1 pri 0 vlan <vlan>
gemport 1 flow 1
switchport-bind switch_0/1 iphost 1
switchport-bind switch_0/1 veip 1
vlan-filter-mode iphost 1 tag-filter vlan-filter untag-filter discard
vlan-filter iphost 1 pri 0 vlan <vlan>
dhcp-ip ethuni eth_0/1 from-onu
dhcp-ip ethuni eth_0/2 from-onu
dhcp-ip ethuni eth_0/3 from-onu
dhcp-ip ethuni eth_0/4 from-onu
security-mgmt 998 state enable mode forward ingress-type lan protocol web https
security-mgmt 999 state enable ingress-type lan protocol ftp telnet ssh snmp tr069
exit
exit
write
```

Untuk PPPoE, tambahkan di dalam `pon-onu-mng`:

```text
pppoe 1 nat enable user <username> password <password>
```

Status: 🔧 produksi.

### Ubah — Profile kecepatan

```text
configure terminal
interface gpon-onu_<pon>:<id>
tcont 1 profile <upload_profile>
gemport 1 tcont 1
gemport 1 traffic-limit downstream <download_profile>
exit
exit
write
```

Buat profile baru:

```text
configure terminal
gpon
profile tcont <name> type 5 fixed 64 assured 64 maximum <kbps>
profile traffic <name> sir <kbps> pir <kbps>
exit
exit
write
```

Hapus profile:

```text
configure terminal
gpon
no profile tcont <name>
no profile traffic <name>
exit
exit
write
```

Status: 🔧 produksi.

### Ubah — VLAN ONU

```text
configure terminal
interface gpon-onu_<pon>:<id>
no service-port 1
service-port 1 vport 1 user-vlan <new_vlan> vlan <new_vlan>
exit
pon-onu-mng gpon-onu_<pon>:<id>
no flow 1 pri 0 vlan <old_vlan>
flow 1 pri 0 vlan <new_vlan>
no vlan-filter iphost 1 pri 0 vlan <old_vlan>
vlan-filter iphost 1 pri 0 vlan <new_vlan>
exit
exit
write
```

Status: 🔧 produksi.

### Ubah — VLAN dan uplink

Buat VLAN:

```text
configure terminal
vlan <vlan>
description <description>
exit
exit
write
```

Tagged di uplink:

```text
configure terminal
interface <uplink>
switchport mode trunk
switchport vlan <vlan> tag
exit
exit
write
```

`switchport mode trunk` hanya perlu jika port masih `access`.

Untagged di uplink:

```text
configure terminal
interface <uplink>
switchport mode hybrid
switchport default vlan <vlan>
exit
exit
write
```

Jika VLAN sudah anggota port, pakai `switchport vlan <vlan> untag` sebagai ganti `switchport default vlan`.

Lepas VLAN dari uplink:

```text
no switchport vlan <vlan>
```

Jika VLAN itu masih PVID, kirim `no switchport default vlan` lebih dulu.

Kode penolakan yang harus ditangani:
- `%Code 60584`: `untag` ditolak karena port masih `trunk`. Ubah ke `hybrid` dulu.
- `%Code 60550`: VLAN sudah ada di port.
- `%Code 60591`: VLAN masih PVID, jadi tidak bisa dilepas.
- `%Code 60551`: `switchport default vlan 1` ditolak. Pakai `no switchport default vlan`.

Status: 🔧 produksi.

### Ubah — Port uplink (auto-negotiation, speed, duplex)

```text
configure terminal
interface <port>
negotiation auto
exit
```

Manual (auto-negotiation dimatikan dulu, kalau tidak speed/duplex diabaikan perangkat):

```text
configure terminal
interface <port>
no negotiation auto
speed <10|100|1000|10000>
duplex <full|half>
exit
```

Port `gei_*` maksimal 1000 Mbps; `10000` hanya untuk port `xgei_*`.

### Ubah — TR-069 (Phase 2)

```text
configure terminal
pon-onu-mng gpon-onu_<pon>:<id>
tr069-mgmt 1 state unlock
tr069-mgmt 1 acs <acs_url> validate basic username <username> password <password>
tr069-mgmt 1 tag pri <priority> vlan <vlan>
veip 1 port udp 1232 host <host>
exit
exit
write
```

Nonaktifkan:

```text
configure terminal
pon-onu-mng gpon-onu_<pon>:<id>
tr069-mgmt 1 state lock
no tr069-mgmt 1 acs
exit
exit
write
```

Status: 🔧 produksi. Tidak masuk MVP Nexfiber.

### Ubah — Reboot dan hapus ONU

Reboot:

```text
pon-onu-mng gpon-onu_<pon>:<id>
reboot
exit
```

Status: ⚠️ belum terverifikasi. Ini urutan yang dikirim driver produksi, tanpa `configure terminal`. Uji di ONU test sebelum dipakai Nexfiber.

Hapus:

```text
configure terminal
interface gpon-olt_<pon>
no onu <id>
exit
exit
write
```

Status: 🔧 produksi.

---

## CDATA FD1602SB1

Jangan kirim `enable` jika sesi sudah berada di mode privileged. OLT akan membalas `% Unknown command`.
Perintah ONT dijalankan di dalam `config` lalu `interface gpon <frame/slot>`.

### Baca — OLT

| Data | Perintah | Status |
|---|---|---|
| CPU | `show cpu` | ✅ terverifikasi |
| Memory | `show memory` | ✅ terverifikasi |
| Suhu | `show temperature` | ✅ terverifikasi |
| Versi | `show version` | ✅ terverifikasi |
| Perangkat | `show device` | ✅ terverifikasi |
| Uptime | `show uptime` | ✅ terverifikasi |
| Jumlah status ONT | `show ont status-count` | ✅ terverifikasi |
| ONT belum terdaftar | `show ont autofind all` | ✅ terverifikasi |
| VLAN | `show vlan all` | ✅ terverifikasi |
| Interface management | `show interface mgmt` | ✅ terverifikasi |
| Profile upload (DBA) | `show dba-profile all` | ✅ terverifikasi |
| Profile download (traffic) | `show traffic-profile all` | ✅ terverifikasi |
| Fan | `show fan` | 🔧 produksi |

### Baca — ONT

Jalankan setelah:

```text
config
interface gpon <frame/slot>
```

| Data | Perintah | Status |
|---|---|---|
| Semua ONT | `show ont info all` | ✅ terverifikasi |
| Optical ONT | `show ont optical-info <port> <id>` | ✅ terverifikasi |
| Optical semua ONT di PON | `show ont optical-info <port> all` | 🔧 produksi |
| Versi ONT | `show ont version <port> <id>` | ✅ terverifikasi |
| Kemampuan ONT | `show ont capability <port> <id>` | ✅ terverifikasi |
| IP config ONT | `show ont ipconfig <port> <id>` | ✅ terverifikasi |
| Statistik ONT | `show statistics ont <port> <id>` | ✅ terverifikasi |

Config ONT dibaca di level `config`, bukan di dalam `interface gpon`:

```text
config
show current-config section ont <frame/slot> <port> <id>
exit
```

Status: ✅ terverifikasi. Perintah yang sama di dalam `interface gpon` ditolak.

### Ubah — Otorisasi ONT

```text
config
interface gpon <frame/slot>
ont add <port> <id> sn-auth "<serial>"
ont description <port> <id> "<description>"
ont ont-port <port> <id> eth adaptive pots adaptive catv adaptive iphost adaptive wifi adaptive
ont native-vlan <port> <id> concern
ont tcont <port> <id> 0 dba-profile-id 0
ont tcont <port> <id> 1 dba-profile-id <dba_id>
ont mapping-mode <port> <id> vlan
ont gemport <port> <id> 1 tcont 1 gem-car-upstream <traffic_id> gem-car-downstream <traffic_id> encrypt disable
ont gemport mapping <port> <id> 1 1 vlan <vlan>
exit
write
```

PPPoE:

```text
no ont ipconfig <port> <id> ip-index 0
ont ipconfig <port> <id> ip-index 0 pppoe username <username> password <password> vlan <vlan> priority 0
ont ipconfig <port> <id> ip-index 0 connection-type route
```

DHCP:

```text
no ont ipconfig <port> <id> ip-index 0
ont ipconfig <port> <id> ip-index 0 dhcp vlan <vlan> priority 0
```

Status: 🔧 produksi.

### Ubah — Enable, disable, reboot, reset, hapus ONT

```text
config
interface gpon <frame/slot>
ont enable <port> <id>
ont disable <port> <id>
ont reboot <port> <id>
ont restore-factory <port> <id>
ont delete <port> <id>
exit
write
```

Pilih satu perintah sesuai aksi. Status: 🔧 produksi.

### Ubah — VLAN dan uplink

Buat VLAN:

```text
config
vlan <vlan>
vlan description <vlan> <description>
exit
write
```

Uplink memakai `interface ge 0/0` atau `interface xge 0/0`.

Access:

```text
config
interface <ge|xge> 0/0
vlan mode <port> access
vlan access <port> <pvid>
exit
write
```

Trunk:

```text
config
interface <ge|xge> 0/0
vlan mode <port> trunk
vlan trunk <port> <vlan_list>
exit
write
```

Hybrid:

```text
config
interface <ge|xge> 0/0
vlan mode <port> hybrid
vlan hybrid <port> tagged <vlan_list>
vlan hybrid <port> untagged <pvid>
exit
write
```

Setelah membuat VLAN, verifikasi ulang dengan `show vlan all`. Jangan menganggap sukses hanya dari output perintah.

Status: 🔧 produksi.

### Ubah — TR-069 (Phase 2)

```text
config
interface gpon <frame/slot>
ont tr069 <port> <id> tr069-management enable
ont tr069 <port> <id> acs-url <acs_url> acs-username <username> acs-password <password>
ont tr069 <port> <id> inform enable
ont tr069 <port> <id> ip-index <0_or_1>
exit
save
```

Nonaktifkan:

```text
config
interface gpon <frame/slot>
ont tr069 <port> <id> tr069-management disable
exit
save
```

Status: 🔧 produksi. Tidak masuk MVP Nexfiber.

---

## Aturan untuk driver Nexfiber

- Satu operasi OLT = satu job worker, bukan request HTTP langsung.
- Satu OLT hanya boleh punya satu sesi CLI tulis aktif.
- Sanitasi semua input sebelum disisipkan ke CLI. Tolak newline dan karakter kontrol.
- Jangan simpan password PPPoE atau kredensial OLT di log CLI.
- Anggap `%Code 62310` dan `%Code 64040` sebagai hasil kosong, bukan error.
- Anggap `Invalid input`, `Unknown command`, dan `Incomplete command` sebagai error.
- Simpan output mentah CLI di log job untuk debug, setelah data sensitif disamarkan.
- Status ONU periodik tetap memakai SNMP. CLI dipakai untuk aksi dan data yang tidak tersedia di SNMP.
