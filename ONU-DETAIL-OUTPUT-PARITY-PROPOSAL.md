# Proposal — output nyata tombol Status / Show running-config / Info SW / LIVE! (Detail ONU)

Status dokumen: **PROPOSAL, belum diimplementasikan.** Tidak ada kode aplikasi yang diubah
oleh dokumen ini. Semua penelusuran dilakukan read-only atas source (repo Nexfiber + aplikasi
referensi PHP milik user di direktori lokalnya); **tidak ada perintah apa pun yang dikirim ke
OLT/ONU**, tidak ada env/DB yang dibuka untuk mengambil password.

Permintaan user: keempat tombol di baris "Status" halaman `/onu/:serial` harus mengeluarkan
**output seperti contoh referensi apa adanya**, bukan ringkasan buatan. Koreksi user terakhir:
**"jangan di samarkan"** — running-config asli harus ditampilkan utuh pada tampilan yang diberi
kewenangan. Itu bertabrakan dengan aturan terkunci; konflik dicatat eksplisit di §6, tidak
ditabrak diam-diam dan tidak juga dipaksa jadi masking otomatis.

**Lingkup dokumen ini = FUNGSI & OUTPUT, bukan layout.** Sumber layout Detail ONU sedang
dipindah user ke desain **Google Stitch** (`stitch.withgoogle.com`); URL project/screen belum
diberikan, jadi tidak ada layout yang dikunci di sini. `ONU-DETAIL-PARITY.md` (layout referensi
lokal) **tidak lagi menjadi acuan tampilan** dan tidak boleh dijadikan prasyarat implementasi
output. Yang dipakai dari referensi lokal hanyalah **isi/urutan blok teks di dalam panel output
CLI** (itu memang kontrak outputnya, bukan desain halaman) dan handler/command read-only-nya.
Penempatan tombol, grid identitas, kartu, dan responsif menunggu desain Stitch. Kredensial/API
key apa pun yang user kirim untuk Stitch tidak disalin ke dokumen, log, atau commit.

## 1. Kondisi sekarang di Nexfiber (fakta dari source)

| Tombol | Yang terjadi sekarang | File |
|---|---|---|
| `Status` | memanggil `POST /api/onus/{sn}/refresh` (job `refresh_onu_detail`) lalu merender ringkasan field (`phase_state`, Rx/Tx, jarak, versi) | `frontend/src/pages/OnuDetail.tsx:289-336`, `app/services/onu_service.py:414` |
| `Show running-config` | tombol yang sama, menampilkan `job.result.running_config` = **hanya** keluaran `show running-config interface gpon-onu_<pon>:<id>` | `app/drivers/zte_c320.py:587-617` |
| `Info SW` | ringkasan 3 field dari `_parse_equip` (`software_version`, `software_version_standby`, `hardware_version`) | sama |
| `LIVE!` | `refetchInterval` 15 s atas `GET /api/onus/{sn}` = **polling DB**, bukan trafik live | `OnuDetail.tsx:36-37,224` |

Jadi ketiga tombol pertama berbagi satu job dan satu perintah set yang sama (4 command), dan
`LIVE!` tidak menyentuh perangkat sama sekali. Tidak ada satu pun blok referensi (CATV, History,
WAN, LAN, VLAN realtime, VoIP, MAC) yang dibaca.

## 2. Peta blok → handler/command read-only nyata

Sumber handler referensi: `backend/python_engine/drivers/zte_c300.py`
(`get_onu_full_status` baris 1524, `get_onu_hw_sw` 2094, `get_onu_running_config` 2149) +
dispatcher `frontend/action/onu-query.php` (map `status|config|hw_sw`).
Kolom "command Nexfiber" = bentuk yang **sudah terverifikasi** di
`NEXFIBER-CLI-REFERENCE.md` §"Baca — ONU" (bukan bentuk referensi, lihat catatan).

### 2.1 Tombol `Status` (9 blok, urutan persis seperti contoh)

| # | Judul blok di output | Command read-only yang dipakai | Status di CLI-REFERENCE |
|---|---|---|---|
| 1 | `Optical status` (tabel Wavelength/OLT/ONU/Attenuation; 1310 Rx OLT+Tx ONU, 1490 Tx OLT+Rx ONU) | `show pon power attenuation gpon-onu_<pon>:<id>` | ✅ terverifikasi, sudah dipakai driver |
| 2 | `ONU CATV port` (Admin status, State, 1550nm Rx, RF output) | `show gpon remote-onu catv gpon-onu_<pon>:<id>` | ❗ belum tercatat — perlu probe read-only |
| 3 | `ONU details` (Vendor ID, HW Version, Detected ONU type, Name, Type, State, Current channel, Admin state, Phase state, Serial number, Description, ONU Status, ONU Distance, Online Duration) | `show gpon onu detail-info gpon-onu_<pon>:<id>` | ✅ sudah dipakai |
| 4 | `History` (Authpass Time / OfflineTime / Cause) | blok `History:` di keluaran `detail-info` yang sama (tanpa command tambahan) | ✅ (parser belum ada di Nexfiber) |
| 5 | `ONU WAN Interfaces` (WAN ID, MAC address, IPv4/mask/gateway/DNS, blok PPPoE) | `show gpon remote-onu ip-host gpon-onu_<pon>:<id>` | ✅ terverifikasi. **`wan-info` dilarang** (CLI-REFERENCE §"Ditolak") — referensi masih memanggilnya dan selalu kosong |
| 6 | `ONU LAN Interfaces status` (Port/Speed/Admin/Max-frame/Status changes) | `show gpon remote-onu interface eth gpon-onu_<pon>:<id>` | ✅ terverifikasi. **`eth-status` dilarang** (dipakai referensi) |
| 7 | `Realtime VLAN info` (Interface/Mode/VLAN-ID/Def-Prio/Vlan-list) | `show gpon remote-onu vlan gpon-onu_<pon>:<id>` | ❗ belum tercatat — perlu probe |
| 8 | `VoIP status` (Tel line / Service status per pots) | `show gpon remote-onu voip gpon-onu_<pon>:<id>` | ❗ belum tercatat — perlu probe |
| 9 | `MACs on OLT from this ONU` (Mac address/Vlan/Type/Port/Vc) | `show mac gpon onu gpon-onu_<pon>:<id>` | ✅ terverifikasi. **`show mac gpon-onu_...` dilarang** (bentuk yang dipakai referensi) |

Tambahan referensi: setelah blok 1 ia menempel baris `1310nm OLT Rx for this ONU: X (dBm) [SNMP]`
dari `get_onu_rx_power`. Di Nexfiber sumber ekuivalennya sudah ada: `OID_OLT_RX_POWER`
(`1.3.6.1.4.1.3902.1082.500.1.2.4.2.1.2`) + `decode_optical_ifindex` di `zte_c320.py` — pakai itu,
jangan tulis jalur SNMP kedua.

### 2.2 Tombol `Show running-config` (3 blok, dipisah `!`)

| Blok | Command |
|---|---|
| `interface gpon-olt_<pon>` + baris `onu <id> type <T> sn <SN>` | `show running-config interface gpon-olt_<pon>` (🔧 produksi) — referensi memakai `\| include onu <id>`; alternatif tanpa pipe: ambil blok lalu filter baris di parser |
| `interface gpon-onu_<pon>:<id>` (seluruh config) | `show running-config interface gpon-onu_<pon>:<id>` ✅ (satu-satunya yang sudah dipakai sekarang) |
| `pon-onu-mng gpon-onu_<pon>:<id>` (seluruh config) | `show onu running config gpon-onu_<pon>:<id>` ✅ terverifikasi, **belum dipanggil** Nexfiber |

Gap utama: 2 dari 3 blok tidak pernah dibaca → panel "Show running-config" sekarang strukturnya
tidak setara contoh.

### 2.3 Tombol `Info SW`

| Blok | Isi | Command |
|---|---|---|
| `ONU Details` | Vendor ID, HW Version, Serial Number, OMCC version, Model | `show gpon remote-onu equip gpon-onu_<pon>:<id>` ✅ (sudah dipakai, tapi hanya 3 field diambil) |
| `Features reported by ONU` | `Number of ETH ports N (10GE:x GE:y FE:z)`, VoIP, CATV, WIFI | `show gpon remote-onu capability gpon-onu_<pon>:<id>` (🔧 produksi, belum dipanggil) |
| `Software Region 1/2` | version + `Active: yes/no` | **TIDAK TERSEDIA via CLI** pada C300/C320 — docstring referensi sendiri menyatakan field per-region itu OMCI-only (`zte_c300.py:2097-2099`). Nexfiber punya `software_version_standby`, tapi OLT SBI bahkan tidak melaporkan label active/standby (temuan QUEUE 2026-10-24, `_parse_equip`). |

Keputusan yang diusulkan untuk Region 1/2: render dua baris dengan nilai apa adanya bila
`equip` memuatnya, dan "tidak dilaporkan perangkat" bila tidak — **bukan** angka tebakan.
Ini perbedaan isi yang tidak bisa ditutup tanpa jalur OMCI/TR-069 (Phase 2).

### 2.4 Tombol `LIVE!` — grafik trafik realtime

Referensi: `LIVE!` hanya memperpendek interval `fetchRealtimeData()` dari 15 s → **3 s**, dan yang
digambar adalah **delta counter octets antar sample** (`lastTraffic = {t, rx, tx}` →
Mbps = `delta_bytes*8/delta_t/1e6`), sumbernya `action/onu-data.php?mode=snmp` → SNMP-only,
nol SSH. OID counter per ONU sudah tercatat terverifikasi di `NEXFIBER-SNMP-OID.md`:

- RxOctets `1.3.6.1.4.1.3902.1082.500.4.2.2.2.1.1`
- TxOctets `…4.2.2.2.1.44`
- RxPackets `…4.2.2.2.1.2`, TxPackets `…4.2.2.2.1.45`

Index = ifIndex PON + `.onu_id` — encoder yang benar sudah ada di Nexfiber
(`encode_pon_ifindex` / `decode_optical_ifindex` keluarga `1082.500`, hasil perbaikan bug
inventory 2026-10-24). Jadi data mentahnya **tersedia tanpa fitur baru di perangkat**, yang
belum ada hanya endpoint + perhitungan delta di Nexfiber.

Catatan izin: trafik per-ONU saat ini berstatus "Phase 2" di `ONU-DETAIL-PARITY.md`.
Proposal ini **tidak mengasumsikan izin itu sudah dibuka** — §7 menaruhnya di tahap terpisah
yang butuh "lanjut" eksplisit.

## 3. Desain yang diusulkan (backend)

Prinsip: satu halaman existing, satu job, **tanpa duplikasi parser** (AGENTS.md DRY).

1. **Satu job baru per tombol, bukan satu job gemuk.** `refresh_onu_detail` tetap seperti
   sekarang (dipakai kartu Sinyal/Perangkat dan sync). Tambah job type:
   `read_onu_status` (9 blok), `read_onu_running_config` (3 blok), `read_onu_software`
   (2 blok). Alasan: `Status` butuh ~8 command CLI ~10–20 s; menumpuknya ke job yang juga
   dipakai polling akan memperlambat semua pemakai lain, dan user menekan tombol secara
   terpisah.
2. **Driver**: tiga method baru di `OltDriver` + `ZteC320Driver`:
   `fetch_onu_status_report()`, `fetch_onu_running_config()`, `fetch_onu_software_report()`.
   Masing-masing **satu sesi CLI** untuk semua command-nya (PRD 4.3), mengembalikan dataclass
   dengan field per blok (`optical`, `catv`, `details`, `history`, `wan`, `lan`, `vlan`, `voip`,
   `macs`) + `raw_command`. Parser dipisah per blok di modul yang sama supaya bisa diuji
   fixture-per-blok.
3. **Tidak ada fabrikasi.** Referensi punya kebiasaan buruk: bila parse gagal ia mengisi
   **data demo hardcoded** (MAC `ec6c.b532.be20`, gateway palsu, `eth_0/1 auto unlock 1632 0`,
   `pots_0/1 none`) — lihat `zte_c300.py:1745-1746,1814,1830,1839`. Nexfiber **tidak** menirunya:
   blok yang tidak dijawab perangkat ditulis apa adanya (`%Error …` / "tidak dilaporkan
   perangkat"). Ini satu-satunya titik di mana output sengaja beda dari contoh, dan ini sesuai
   aturan repo (jangan tampilkan angka palsu).
4. **Presentasi teks final dirakit di backend**, satu tempat (mis. `onu_report_service`), karena
   tombol harus menghasilkan blok teks persis; frontend hanya menampilkan string per blok.
   Mencegah dua versi formatter (backend + TSX) menyimpang.
5. **Hasil tidak disimpan permanen.** Referensi menulis seluruh output ke kolom
   `onus.last_status_cli` / `last_running_config` (`onu-query.php:111-116`). Usul: **jangan**
   tambah kolom itu di Nexfiber — hasil hidup di `job.result` saja (retensi job), karena
   running-config memuat nilai konfigurasi sensitif (§6) dan kolom DB = salinan permanen yang
   ikut ke backup.

## 4. RBAC akses output sensitif

Yang sudah ada: scope OLT per user (`core/rbac.py scope_olt_ids`, termasuk `olt_access`),
`isManager` untuk aksi berisiko di `OnuDetail.tsx`. Usul tambahan — **minimal, tanpa tabel baru**:

| Output | Boleh | Alasan |
|---|---|---|
| `Status` (9 blok) | semua role dalam scope OLT (termasuk `user`) | tidak memuat kredensial |
| `Info SW` | sama | sama |
| `LIVE!` trafik | sama | counter saja |
| `Show running-config` **utuh/tanpa penyamaran** | hanya `superadmin` + `admin` (`isManager`), dan hanya untuk OLT dalam scope-nya | blok `pon-onu-mng`/`interface` memuat PPPoE, ACS, SNMP, WiFi key |

Pengecekan di **backend pada endpoint dan pada job** (AGENTS.md: cek di setiap endpoint, di luar
scope = 404), bukan sekadar disembunyikan di UI. Role `user` yang menekan tombol itu → 403 dengan
pesan jelas, tombol tidak dirender.

Anti-jejak (sesuai permintaan "no persistent browser cache/log"):
- response `Cache-Control: no-store`, tidak masuk TanStack Query cache persisten
  (`gcTime: 0`, tanpa `persistQueryClient`), tidak ditulis ke `localStorage`/`sessionStorage`;
- panel output dibuang saat unmount/logout; tombol "Salin" tetap manual (clipboard = aksi user);
- `activity_logs` untuk `read_onu_running_config`: tulis `raw_command` + **ringkasan/jumlah baris**,
  **jangan** tulis `raw_output` penuh (kolom itu nullable dan hari ini memang dipakai menyimpan
  `running_config` di `refresh_onu_detail`, `onu_service.py:436-440` — itu perlu diubah);
- log aplikasi/worker tidak pernah memuat isi blok config.

## 5. Sumber live traffic + poll/stream/rate limit

- **Sumber**: SNMP counter `1082.500.4.2.2.2.1.{1,2,44,45}` (lihat §2.4). **Tanpa CLI** sama sekali
  di jalur LIVE.
- **Bentuk endpoint**: `GET /api/onus/{serial}/traffic` → satu sample
  `{t, rx_octets, tx_octets, rx_packets, tx_packets}`. Delta → Mbps dihitung **di frontend**
  (butuh 2 sample; sample pertama hanya menetapkan baseline), persis pola referensi, dan
  menghindari tabel histori baru (DECISIONS.md: jangan buat tabel histori yang ditunda).
- **Polling, bukan stream**: SSE `/api/stream/jobs` yang ada dipakai untuk event job, bukan time
  series; menambah stream kedua tidak sepadan. Interval: **5 s saat LIVE aktif** (referensi 3 s;
  5 s menjaga beban SNMP OLT lebih aman), kembali ke 15 s/off saat LIVE dimatikan, dan polling
  **berhenti saat tab tidak terlihat** (`document.hidden`).
- **Rate limit**: maksimum 1 pembacaan per ONU per 3 s (ditegakkan di backend, bukan hanya UI),
  dan LIVE otomatis mati setelah 10 menit tanpa interaksi supaya tab yang ditinggal terbuka tidak
  memolling OLT selamanya.
- Tombol `Status` / `Show running-config` / `Info SW` (CLI, mahal): debounce + tolak job kedua
  bila masih ada job tipe sama `pending/running` untuk ONU yang sama.

## 6. KONFLIK KEPUTUSAN TERKUNCI — wajib diputuskan user sebelum implementasi

**K1 — "jangan di samarkan" vs aturan kredensial tidak boleh keluar.**
Permintaan terbaru user: running-config ditampilkan **asli, termasuk nilai konfigurasi
sensitif**, pada tampilan yang diberi kewenangan. Aturan terkunci yang bertabrakan:

- `AGENTS.md` baris 27: kredensial "tidak pernah dikirim balik ke frontend, tidak pernah masuk log
  (`[REDACTED]`)" — ditulis untuk kredensial OLT, **tidak** secara eksplisit mengatur isi
  running-config ONU, tapi bunyinya dipakai sebagai aturan umum sampai sekarang.
- `PRD-FINAL.md` §925: kredensial PPPoE dienkripsi di level aplikasi.
- `ONU-DETAIL-PARITY.md`: "password ONU … tidak pernah dikirim ke frontend; menampilkannya =
  regresi keamanan".
- Regresi yang akan **gagal** bila output ditampilkan utuh:
  `backend/tests/test_onu_detail_layout.py::test_pppoe_password_never_rendered`.

Keluaran `show running-config interface …` / `show onu running config …` pada ZTE memuat, antara
lain: username/password PPPoE, URL+username+password ACS/TR-069, SSID + WiFi key, community SNMP
ONU. Jadi ini bukan soal gaya tampilan — ini perubahan kebijakan keamanan.

**Usul resolusi (pilih satu, butuh keputusan eksplisit user, jangan diasumsikan):**

- **O1 (direkomendasikan).** Tambah keputusan baru di `DECISIONS.md`: *"Output `Show
  running-config` ONU ditampilkan utuh tanpa penyamaran, khusus role `superadmin`/`admin` pada OLT
  dalam scope-nya"*, dengan pagar: tidak disimpan ke kolom DB, tidak masuk `activity_logs.raw_output`,
  tidak masuk cache browser/log server, dicatat sebagai akses ("siapa membuka config ONU X kapan")
  tanpa isinya. Test `test_pppoe_password_never_rendered` **diubah lingkupnya**: tetap melarang
  field PPPoE password dirender dari kolom DB/`OnuDetail`, tapi mengizinkan blok config live
  milik role manager. AGENTS.md baris 27 diberi klausa: aturan `[REDACTED]` berlaku untuk
  kredensial **OLT** dan untuk **log**, bukan untuk tampilan config live ke role berwenang.
- **O2.** Status quo keamanan: tampilkan utuh kecuali nilai kredensial. Ini **menolak** permintaan
  user "jangan di samarkan" → tidak diusulkan, dicatat hanya sebagai alternatif.
- **O3.** Utuh untuk semua role dalam scope (termasuk `user`). **Tidak direkomendasikan**: role
  `user` adalah teknisi/CS di bawah Admin; memberi semua PPPoE/ACS pelanggan ke role itu
  memperluas dampak satu akun bocor.

Catatan disiplin yang tetap berlaku di semua opsi, tidak dinegosiasikan di sini: contoh output
milik user (yang memuat kredensial ACS nyata) **tidak disalin** ke kode, fixture test, dokumen,
maupun chat. Fixture test memakai nilai sintetis (`SECRET-NOT-REAL`-style), dan secret tetap tidak
pernah ditulis ke log.

**K2 — command referensi yang statusnya "Ditolak" di Nexfiber.** `wan-info`, `eth-status`,
`show mac gpon-onu_<pon>:<id>`, `traffic-info` dipakai referensi tapi terdaftar ditolak di
`NEXFIBER-CLI-REFERENCE.md`. Proposal memakai penggantinya (`ip-host`, `interface eth`,
`show mac gpon onu`, `show interface`/SNMP). Konsekuensi: **format kolom bisa berbeda** dari
contoh user di blok 5/6/9 — perlu transkrip read-only nyata sebelum parser dipaku.

**K3 — blok yang belum tercatat sama sekali** (`remote-onu catv`, `remote-onu vlan`,
`remote-onu voip`): tidak ada entri di CLI-REFERENCE dan tidak ada fixture. Harus diprobe
read-only lebih dulu di OLT yang user izinkan; sampai itu ada, 3 blok ini **tidak bisa**
dijanjikan setara contoh.

**K4 — Software Region 1/2** tidak tersedia via CLI (§2.3). Tidak ada resolusi teknis di MVP.

**K5 — trafik per-ONU** masih ditandai Phase 2 di `ONU-DETAIL-PARITY.md`; mengerjakan LIVE! grafik
berarti mengubah status itu. Butuh "lanjut" eksplisit, tidak diambil sendiri oleh agent.

**K6 — sumber layout berpindah ke Google Stitch.** `ONU-DETAIL-PARITY.md` + commit `abb8fe0`/
`155f85d` mengunci layout Detail ONU ke referensi lokal, dan `DESIGN.md` §12.6 (tab horizontal +
dropdown "Aksi") sudah sengaja ditinggalkan demi referensi itu. Keputusan baru user = layout dari
Stitch. Konsekuensi: (a) `ONU-DETAIL-PARITY.md` perlu diturunkan statusnya jadi catatan historis
untuk layout (bagian inventaris blok/command tetap berguna), (b) `test_onu_detail_layout.py`
memaku urutan `<Section label=…>` dan urutan `DRow` — test itu akan gagal begitu layout Stitch
masuk, jadi harus **diganti** menjadi regresi fungsi (endpoint yang dipanggil, RBAC, tidak ada
halaman kedua, tidak ada angka palsu) bukan regresi posisi, (c) penyimpangan dari DESIGN §12.6
perlu diputuskan ulang: ikut Stitch atau kembali ke DESIGN. **Blocker:** URL project/screen
Stitch belum ada — tanpa itu layout tidak bisa dianalisis, dan tombol/panel output tidak punya
tempat yang pasti. Fungsi/output (§2–§5) tidak tergantung ini dan bisa jalan lebih dulu.

## 7. Tahap implementasi yang diusulkan (satu tahap per giliran, AGENTS.md)

| Tahap | Isi | Prasyarat |
|---|---|---|
| T0 | Keputusan K1 (pilih O1/O2/O3) + izin probe read-only command K3 di OLT nyata | user |
| T1 | Probe read-only: kumpulkan transkrip asli 12 command (§2) dari satu ONU yang user tunjuk; simpan sebagai fixture **tersanitasi** (tanpa secret nyata) | T0 |
| T2 | Driver + parser `fetch_onu_status_report` (9 blok) + job `read_onu_status` + unit test fixture per blok | T1 |
| T3 | `fetch_onu_running_config` 3 blok + job + RBAC manager-only + no-store/no-log | T1, K1 |
| T4 | `fetch_onu_software_report` (equip + capability) + job | T1 |
| T5 | Frontend: tiga tombol → tiga job terpisah, panel output per blok (satu panel, judul blok seperti contoh). **Penempatan/tampilan mengikuti desain Google Stitch — menunggu URL project/screen dari user**; tetap satu halaman existing, tanpa halaman baru | T2–T4 + desain Stitch |
| T6 | `LIVE!`: endpoint `GET /api/onus/{serial}/traffic` (SNMP) + delta Mbps + grafik, rate limit, auto-off | izin K5 |

Tiap tahap: `pytest` backend + `tsc -b` + `npm run build`, lapor file yang diubah dan output
nyatanya; tidak ada deploy tanpa permintaan.

## 8. Regression test yang diusulkan

- **Parser per blok** (fixture teks, PRD Bagian 5 wajib): 9 blok Status, 3 blok running-config,
  2 blok Info SW; termasuk kasus `%Error`/kosong → blok bertanda "tidak dilaporkan", **bukan**
  data demo (anti-regresi atas kebiasaan referensi).
- **Anti-fabrikasi**: assert bahwa string hardcoded khas referensi (`eth_0/1 auto unlock 1632 0`,
  `pots_0/1`, MAC demo) tidak muncul di output ketika perangkat tidak menjawab.
- **Urutan & judul blok** persis seperti contoh (output tombol = kontrak), di backend.
- **RBAC**: `user` → 403 untuk `read_onu_running_config`; manager OLT lain → 404; manager dalam
  scope → 200.
- **Tidak ada persistensi**: assert `activity_logs.raw_output` kosong untuk job running-config,
  assert tidak ada kolom `last_status_cli`/`last_running_config` baru, assert header `no-store`.
- **Penyesuaian** `test_pppoe_password_never_rendered` sesuai keputusan K1 (tetap melarang
  rendering dari `OnuDetail`/DB; lingkup dipersempit, tidak dihapus).
- **LIVE!**: rate limit ditegakkan backend (request ke-2 dalam 3 s ditolak), polling berhenti saat
  `document.hidden`.
- **Fixture bebas secret**: test yang memindai folder fixture memastikan tidak ada pola
  credential nyata (ACS/PPPoE/SNMP) ikut masuk repo.

## 9. Koordinasi sibling / file yang tidak disentuh

- Metadata ONU & `StatusBadge` bersama (commit `80480a8`, `985e3bf`) — **tidak diubah**.
- `06b98b2` (TR-069 status disembunyikan) tetap: proposal ini tidak menghidupkan tombol TR-069.
- Perubahan yang menyentuh kontrak lintas track bila dikerjakan: `job_type` ENUM (migrasi
  Alembic), `OltDriver` (interface), `app/schemas/onu.py`. Harus diumumkan sebelum T2 supaya tidak
  bentrok dengan track yang memakai ENUM/driver yang sama.
- Tidak ada perubahan skema `onus` yang diusulkan.
