# PRD — Nexfiber (Aplikasi Manajemen OLT/ONU, Greenfield)
## Dokumen Final v3 — Nama Aplikasi Terkunci, Install/Update/Uninstall Jadi Bagian PRD

Status: **FINAL v3** — versi terakhir yang dipakai sebagai acuan development di VS Code. Tidak ada v4 kecuali ada perubahan keputusan produk, bukan sekadar perubahan redaksi.
Disusun oleh: Product Manager, Backend Architect, UI/UX Designer, Database/Infra Specialist, DevOps/QA Engineer (kerja paralel, debat trade-off, disintesis oleh pemilik produk — Erlangga Alfian).
Sifat: aplikasi BARU (greenfield), bukan migrasi/update dari aplikasi lama manapun (termasuk bukan dari SmartOLT). Data mulai kosong.

**Apa yang berubah dari v2 → v3** (v3 ditulis ulang baris per baris, bukan tempel-tambal):
1. Nama aplikasi dikunci: **Nexfiber**. Semua placeholder (`OLT-App`, `Fiberdesk`, `<app>`, `olt-api`/`olt-worker`, `olt_app`) diganti konsisten jadi `Nexfiber` / `nexfiber-api` / `nexfiber-worker` / `nexfiber_db` — di dokumen ini dan di 3 skrip bash pendamping.
2. `install.sh`/`update.sh`/`uninstall.sh`, yang di v2 cuma dijelaskan konsepnya, sekarang **isinya disalin sebagai lampiran PRD** (bukan cuma rujukan ke file terpisah) — lihat Lampiran A di bagian paling bawah dokumen ini.
3. Seluruh isi v2 (produk, arsitektur backend, design system, database/infra, DevOps/QA) tetap dipertahankan — tidak ada keputusan teknis yang dibalik di v3, karena tidak ada trade-off baru yang diajukan sejak v2.

---

## Keputusan Trade-off (Final — Pemilik Produk Mengikuti Semua Rekomendasi Tim)

| # | Trade-off | Keputusan Final |
|---|---|---|
| 1 | MVP ZTE-only, CDATA ditunda ke Phase 2 | **Disetujui.** Interface `OltDriver` tetap ditulis sejak hari 1 untuk menyiapkan tempat CDATA. |
| 2 | Job queue pakai tabel PostgreSQL (`SKIP LOCKED`), bukan Celery+Redis | **Disetujui.** |
| 3 | Status ONU polling **1 menit** via SNMP bulkwalk (dipercepat dari rentang awal 5-15 menit), sinyal optik tetap 15 menit | **Disetujui.** Trap SNMP untuk event LOS/dying-gasp tetap masuk sebagai jaring pengaman seketika. |
| 4 | Tema terang (light) sebagai default, dengan toggle Sistem/Terang/Gelap | **Disetujui.** |
| 5 | 1 server app+DB, tanpa managed DB/DB server terpisah | **Disetujui.** Trigger pindah: CPU>70% sustained / DB>50GB / OLT>80. |
| 6 | Backup cron+pg_dump+WAL archiving sendiri, bukan pgBackRest/replika standby | **Disetujui.** Trigger upgrade: RTO 4 jam tak lagi diterima. |
| 7 | CD otomatis ditolak, deploy manual 1 perintah (`update.sh`) | **Disetujui.** |
| 8 | Tanpa target coverage test %; 6 modul kritis wajib 100% jalur utama, sisanya boleh 0% | **Disetujui.** |
| 9 | TR-069/GenieACS keluar dari MVP, masuk Phase 2 | **Disetujui.** |
| 10 | 3 peran RBAC tetap (Admin/NOC/Teknisi), bukan permission granular | **Disetujui.** Peran disimpan sebagai data agar peran baru bisa ditambah tanpa membongkar model otorisasi. |

**Instruksi tambahan (sesi ini): gunakan versi stabil terbaru dari tiap komponen stack, dan pastikan tampilan UI terasa "bagus" (bukan generik AI-default).**
Diterapkan sebagai update versi (arsitektur/filosofi stack tidak berubah — tetap boring/solo-dev-friendly, cuma dinaikkan ke rilis stabil terkini):

| Komponen | Versi di draft lama | Versi final (stabil terkini) |
|---|---|---|
| PostgreSQL | 16 | **18** (UUIDv7 native, async I/O) |
| FastAPI | 0.11x (generik) | **rilis stabil terbaru**, pin minor (`>=0.120,<0.121`) |
| Frontend build | React + Tailwind (tanpa versi) | **React 19 + Vite 7 + TypeScript + Tailwind CSS v4** |
| Tampilan | — | Tidak berubah arah (tetap karakter `DESIGN.md`, bukan template shadcn default) — hanya naik ke primitif/komponen versi terbaru di atas. |

**Pertanyaan tindak lanjut yang masih terbuka** (tidak menghalangi mulai Fase 1, tapi perlu dijawab sebelum Phase 2 direncanakan):
- Berapa % OLT produksi saat ini bermerek CDATA? (menentukan apakah Trade-off #1 perlu ditinjau ulang lebih awal)

---

## Bagian 1 — Produk

## 1. Latar Belakang

ISP fiber kecil-menengah (500–5.000 pelanggan) mengelola OLT GPON merek ZTE (C300/C320) dan CDATA (FD11xx/FD16xx/FD17xx). Realita operasional hari ini:

- **Aktivasi ONU masih manual via telnet/SSH ke OLT.** Teknisi hafal urutan command per vendor, salah ketik VLAN atau profile = pelanggan tidak online, troubleshooting berjam-jam.
- **Pola command tidak seragam antar vendor.** ZTE butuh delete-lalu-recreate untuk ganti VLAN ONU aktif; CDATA pakai `ont modify` in-place dengan argumen flat. Teknisi harus switch mental model tiap pindah OLT.
- **Tidak ada histori sinyal.** Saat pelanggan komplain "internet putus-putus", NOC hanya bisa lihat RX power *sekarang*, bukan tren 7 hari. Redaman yang perlahan memburuk (konektor kotor, bending, splitter degradasi) baru ketahuan setelah ONU benar-benar LOS.
- **Topologi fisik hidup di kepala orang atau spreadsheet.** Pemetaan ODP/splitter → port PON tidak tercatat rapi, sehingga saat satu splitter bermasalah tidak ada yang tahu 16 pelanggan mana yang terdampak.
- **Perubahan tidak terjejak.** Siapa menurunkan speed profile pelanggan X tadi malam? Tidak ada jawabannya.
- **Perangkat CPE tidak terkelola.** Ganti SSID/password WiFi atau reboot router pelanggan = telepon ke pelanggan dan menuntun manual, padahal TR-069 bisa melakukannya.

Produk yang ada di pasar (mis. SmartOLT komersial) menyelesaikan ini tapi berbasis langganan per-ONU yang berat untuk ISP skala ini, dan tidak bisa disesuaikan dengan alur kerja lokal.

**Kendala utama yang membentuk seluruh keputusan scope di dokumen ini: produk ini dibangun dan dirawat oleh 1 developer.** Setiap fitur yang masuk adalah fitur yang harus di-debug sendiri pada jam 2 pagi saat OLT produksi bermasalah. Kompleksitas adalah biaya nyata, bukan abstraksi.

---

## 2. Tujuan

### Tujuan Produk
1. **Aktivasi ONU tanpa CLI.** Teknisi lapangan bisa mengaktifkan pelanggan baru dari browser HP tanpa pernah menyentuh telnet, dan tanpa tahu perbedaan command ZTE vs CDATA.
2. **Satu layar untuk status jaringan.** NOC melihat seluruh ONU (online/offline/LOS/dying-gasp) dan kualitas sinyalnya dalam satu halaman, bukan dari 5 sesi terminal.
3. **Deteksi masalah sebelum pelanggan menelepon.** Histori sinyal + alert ambang batas mengubah troubleshooting dari reaktif menjadi proaktif.
4. **Akuntabilitas operasional.** Setiap perubahan konfigurasi ke OLT tercatat: siapa, kapan, command apa, hasilnya apa.
5. **Aman dirawat satu orang.** Arsitektur boring, dependensi minimal, failure mode jelas. Tidak ada komponen yang pemiliknya tidak sanggup debug sendirian.

### Metrik Keberhasilan (target 3 bulan pasca-rilis MVP)
| Metrik | Baseline | Target |
|---|---|---|
| Waktu aktivasi ONU baru (dari ONU nyala sampai pelanggan online) | ~15 menit (manual CLI) | < 3 menit |
| Aktivasi yang butuh eskalasi ke senior/NOC | ~30% | < 5% |
| Insiden sinyal yang terdeteksi sistem sebelum komplain pelanggan | 0% | > 40% |
| Perubahan konfigurasi OLT yang teraudit | 0% | 100% (lewat aplikasi) |
| MTTR gangguan satu pelanggan | 60–90 menit | < 30 menit |

### Non-Tujuan Strategis
Produk ini **bukan** OSS/BSS. Ia tidak menagih, tidak menerbitkan invoice, tidak mengelola tiket pelanggan. Ia mengelola perangkat jaringan. Integrasi ke sistem billing dilakukan lewat API, bukan dengan menumbuhkan modul billing di dalamnya.

---

## 3. Target User

### Persona Primer

**1. Teknisi Lapangan ("Andi")**
Di lokasi pelanggan, pakai HP, sinyal seluler pas-pasan, tangan kotor. Butuh: cari ONU baru yang belum terdaftar, pilih pelanggan, pilih paket, klik aktifkan, lihat sinyal OK. Tidak paham VLAN tagging dan tidak perlu paham. **Mobile-first bukan nice-to-have untuk persona ini — ini syarat kelayakan.**

**2. Staf NOC / Helpdesk ("Budi")**
Di kantor, dual monitor, menerima telepon komplain. Butuh: cari pelanggan dalam < 5 detik (by nama/serial/ID), lihat status + sinyal + histori, reboot ONU, ganti SSID WiFi, tutup telepon. Tidak diberi hak ubah konfigurasi OLT.

**3. Network Engineer / Admin ("Citra")**
Pemilik teknis jaringan. Butuh: tambah OLT, definisikan VLAN dan speed profile, atur topologi splitter/ODP, lihat utilisasi port PON, audit log, kelola user. Satu-satunya yang boleh menyentuh pengaturan berisiko.

### Persona Sekunder
**Owner ISP** — sesekali membuka dashboard untuk melihat jumlah pelanggan aktif dan kesehatan jaringan. Read-only, tidak perlu fitur khusus di MVP.

### Bukan Target User
Pelanggan akhir. Tidak ada portal pelanggan. Tidak akan pernah ada di roadmap dokumen ini.

### Asumsi Lingkungan
- Aplikasi berjalan di jaringan manajemen ISP (on-premise/VPS dengan akses ke IP manajemen OLT). Tidak di-expose ke internet publik tanpa VPN.
- Skala awal: 1–10 OLT, 500–5.000 ONU. Desain harus tidak runtuh di 10.000 ONU, tapi tidak dioptimalkan untuk 100.000.
- Kredensial OLT dipegang aplikasi, bukan per-user.

---

## 4. Scope Fitur

### 4.1 MVP — "Satu teknisi bisa mengaktifkan pelanggan tanpa CLI"

Definisi selesai MVP: seluruh siklus hidup pelanggan dasar (aktivasi → monitoring → ubah paket → nonaktif) berjalan di aplikasi, untuk OLT ZTE C320.

| # | Fitur | Isi |
|---|---|---|
| M1 | **Manajemen OLT** | CRUD OLT (IP, kredensial telnet/SSH, community SNMP, tipe/vendor). Tes koneksi. Status reachable/unreachable. |
| M2 | **Discovery ONU unconfigured** | Daftar ONU yang terdeteksi OLT tapi belum diotorisasi, dengan serial number, port PON, dan waktu terdeteksi. Auto-refresh. |
| M3 | **Autorisasi ONU** | Satu form: pilih ONU unconfigured → isi data pelanggan (nama, ID, alamat) → pilih VLAN + speed profile + ONU type → eksekusi. Hasil berhasil/gagal dengan pesan yang bisa dibaca manusia, bukan dump CLI mentah. |
| M4 | **Daftar & detail ONU** | Pencarian cepat by nama/serial/ID pelanggan/IP. Status (online, offline, LOS, dying-gasp, power-off), uptime, RX/TX power, jarak, port PON, profile terpasang. |
| M5 | **Monitoring sinyal + histori** | Polling berkala seluruh ONU. Simpan time-series RX power, status, traffic. Grafik 24 jam / 7 hari / 30 hari pada halaman detail ONU. |
| M6 | **Alert dasar** | Ambang batas RX power (warning/critical) dan deteksi ONU offline > N menit. Notifikasi ke Telegram/email. Daftar alert aktif di dashboard. |
| M7 | **Master VLAN & Speed Profile** | Definisi paket layanan (nama, VLAN, upstream/downstream Mbps) yang dipetakan ke profile di OLT. Teknisi memilih "Paket 20 Mbps", bukan mengetik angka. |
| M8 | **Operasi ONU harian** | Reboot ONU, ubah speed profile, ubah VLAN, nonaktifkan/hapus ONU, ganti nama/deskripsi. Semua dengan konfirmasi untuk aksi destruktif. |
| M9 | **User management & RBAC** | 3 peran tetap: Admin (semua), NOC (lihat + reboot + lihat sinyal, tidak boleh ubah konfigurasi OLT), Teknisi (aktivasi + lihat, tidak boleh hapus/ubah master data). Login, ganti password, nonaktifkan user. |
| M10 | **Audit log** | Setiap aksi yang mengubah state OLT tercatat: user, waktu, target ONU, aksi, command yang dikirim, respons OLT, berhasil/gagal. Read-only, tidak bisa dihapus dari UI. |
| M11 | **Dashboard** | Jumlah ONU per status, OLT down, alert aktif, aktivasi hari ini. Satu layar, tanpa scroll di desktop. |
| M12 | **UI mobile-usable** | Halaman aktivasi dan detail ONU harus benar-benar bisa dipakai di layar 390px. Sisanya cukup responsive seadanya. |

### 4.2 Phase 2 — "Dari alat aktivasi menjadi alat operasi jaringan"

| # | Fitur | Isi | Pemicu masuk scope |
|---|---|---|---|
| P1 | **Dukungan OLT CDATA** | Driver kedua + lapisan abstraksi vendor yang sudah terbukti dari driver ZTE. | Setelah driver ZTE stabil di produksi ≥ 1 bulan. |
| P2 | **TR-069 / GenieACS** | Integrasi ke GenieACS yang di-deploy terpisah: lihat parameter CPE, ganti SSID/password WiFi, reboot CPE, lihat perangkat terhubung, firmware upgrade terbatas. | Setelah MVP stabil; butuh GenieACS berjalan sendiri. |
| P3 | **Topologi splitter/ODP** | Pencatatan ODC→ODP→splitter→ONU, kapasitas port terpakai, "siapa saja yang terdampak kalau splitter ini mati". Opsional: titik koordinat di peta. | Saat jumlah ODP > ~50 dan spreadsheet mulai salah. |
| P4 | **Bulk operations** | Aktivasi massal via import CSV, ubah profile banyak ONU sekaligus, reboot per-port PON. | Saat ada migrasi/perubahan paket massal. |
| P5 | **Laporan & ekspor** | Rekap pelanggan aktif, ONU bermasalah berulang, utilisasi port PON, ekspor CSV/PDF. | Permintaan owner/manajemen. |
| P6 | **API publik + webhook** | REST API untuk integrasi billing (suspend/unsuspend otomatis saat tagihan jatuh tempo), webhook event ONU down. | Saat ada sistem billing yang siap diintegrasikan. |
| P7 | **Deteksi anomali sinyal** | Tren memburuk (bukan sekadar ambang batas): "RX power ONU ini turun 3 dB dalam 7 hari". | Setelah data histori ≥ 1 bulan terkumpul. |
| P8 | **Multi-vendor lain** | VSOL, BDCOM, Fiberhome, Huawei — sesuai permintaan pasar, urutan dari yang pola command-nya paling mirip ZTE. | Berbasis permintaan nyata, bukan spekulasi. |

### 4.3 Catatan Arsitektur (usulan, bukan keputusan final)

Prinsip: **boring, sedikit bagian bergerak, bisa di-debug satu orang.**

- **Web app**: satu framework server-rendered dengan komponen interaktif (mis. Laravel + Livewire, atau Django + HTMX). **Hindari SPA terpisah (React/Vue + API)** — dua codebase, dua build pipeline, dua tempat bug untuk satu orang.
- **Worker OLT**: proses terpisah yang berbicara ke OLT via SSH/telnet (ekspektasi: pustaka pexpect/netmiko) dan SNMP. Terpisah dari web agar OLT yang lambat tidak menggantung UI.
- **Database**: satu MySQL/PostgreSQL. Time-series sinyal cukup di tabel biasa dengan retensi bergulir (mis. detail 30 hari, agregat harian 1 tahun). **Jangan tambah InfluxDB/TimescaleDB di MVP** — satu database lagi berarti satu backup, satu monitoring, satu mode kegagalan lagi.
- **Queue & scheduler**: mekanisme antrian sederhana (DB-backed atau Redis) untuk polling dan eksekusi command. Hindari Kafka/RabbitMQ.
- **Deployment**: satu VPS, satu docker-compose, satu perintah deploy. Tidak ada Kubernetes.

Prinsip kerja driver OLT yang wajib dipegang sejak MVP: **setiap command harus idempoten** — coba apply langsung, baru fallback ke delete→create bila OLT menolak. Perbedaan perilaku antar vendor (ZTE butuh recreate untuk ganti VLAN, CDATA bisa in-place) disembunyikan di lapisan driver, tidak bocor ke UI.

---

## 5. User Stories Inti

### Aktivasi (Teknisi)
- **US-01** — Sebagai teknisi, saya ingin melihat daftar ONU yang terdeteksi tapi belum diotorisasi beserta port PON-nya, agar saya tahu ONU mana yang baru saja saya pasang.
  *AC:* daftar menampilkan serial, port PON, waktu deteksi; auto-refresh ≤ 30 detik; bisa difilter per OLT.
- **US-02** — Sebagai teknisi, saya ingin mengaktifkan ONU dengan memilih paket layanan, bukan mengetik VLAN dan profile, agar saya tidak salah konfigurasi.
  *AC:* form berisi pelanggan + paket + tipe ONU; tidak ada input VLAN/profile mentah; validasi sebelum eksekusi.
- **US-03** — Sebagai teknisi, saya ingin melihat hasil aktivasi dalam bahasa manusia dalam < 30 detik, agar saya tahu boleh pulang atau belum.
  *AC:* status sukses/gagal eksplisit; bila gagal, pesan menunjukkan penyebab dan langkah berikutnya; command mentah tetap tersimpan di audit log.
- **US-04** — Sebagai teknisi, saya ingin melihat RX power ONU langsung setelah aktivasi dengan indikator warna, agar saya bisa memperbaiki redaman selagi masih di lokasi.
  *AC:* nilai dBm + kategori baik/waspada/buruk; bisa di-refresh manual.

### Monitoring & Support (NOC)
- **US-05** — Sebagai NOC, saya ingin mencari pelanggan dengan nama, serial, atau ID pelanggan dan mendapat hasil < 5 detik, agar bisa menjawab telepon tanpa membuat penelepon menunggu.
- **US-06** — Sebagai NOC, saya ingin melihat grafik RX power 7 hari terakhir, agar bisa membedakan gangguan sesaat dari degradasi fisik.
- **US-07** — Sebagai NOC, saya ingin mereboot ONU pelanggan dari aplikasi, agar tidak perlu menuntun pelanggan mencabut adaptor.
- **US-08** — Sebagai NOC, saya ingin menerima notifikasi saat ONU LOS atau RX power melewati ambang kritis, agar tahu sebelum pelanggan menelepon.
  *AC:* notifikasi Telegram/email; ada peredaman agar tidak membanjiri saat satu port PON mati bersamaan.
- **US-09** — Sebagai NOC, saya ingin melihat seluruh ONU yang offline saat ini dikelompokkan per port PON, agar bisa membedakan gangguan satu pelanggan dari gangguan satu jalur.

### Administrasi (Admin/Engineer)
- **US-10** — Sebagai admin, saya ingin menambah OLT dan mengetesnya sebelum disimpan, agar salah kredensial ketahuan saat itu juga.
- **US-11** — Sebagai admin, saya ingin mendefinisikan paket layanan (VLAN + speed profile) sekali, agar semua teknisi memakai konfigurasi yang seragam.
- **US-12** — Sebagai admin, saya ingin mengubah speed profile pelanggan saat upgrade paket tanpa memutus layanan lebih dari beberapa detik.
- **US-13** — Sebagai admin, saya ingin menonaktifkan ONU pelanggan yang berhenti berlangganan, dengan konfirmasi eksplisit, agar tidak ada penghapusan tidak sengaja.
  *AC:* dialog konfirmasi menyebut nama pelanggan; aksi tercatat di audit log; ONU bisa diaktifkan kembali.
- **US-14** — Sebagai admin, saya ingin melihat siapa mengubah apa dan kapan, agar bisa menelusuri saat terjadi insiden.
- **US-15** — Sebagai admin, saya ingin memberi peran berbeda ke tiap staf, agar teknisi tidak bisa menghapus master data dan NOC tidak bisa mengubah konfigurasi OLT.
- **US-16** — Sebagai admin, saya ingin melihat utilisasi tiap port PON (jumlah ONU terdaftar vs kapasitas), agar tahu kapan harus menambah kartu atau splitter.

### Phase 2 (ringkas)
- **US-17** — Sebagai NOC, saya ingin mengganti SSID/password WiFi pelanggan dari aplikasi *(butuh TR-069)*.
- **US-18** — Sebagai admin, saya ingin mencatat ODP/splitter dan melihat pelanggan terdampak saat satu splitter bermasalah.
- **US-19** — Sebagai sistem billing, saya ingin memanggil API untuk suspend/unsuspend layanan pelanggan secara otomatis.

---

## 6. Non-Goals (Eksplisit Tidak Dikerjakan)

1. **Billing, invoice, dan pembayaran.** Bukan domain produk ini. Integrasi lewat API di Phase 2 (P6), bukan modul internal. *Alasan: satu modul billing = setengah produk tersendiri; mustahil dirawat bersamaan dengan network management oleh satu orang.*
2. **Portal pelanggan akhir.** Tidak ada login pelanggan, tidak ada aplikasi pelanggan. Selamanya di luar scope dokumen ini.
3. **Ticketing / helpdesk.** Gunakan tool yang sudah ada. Produk ini memberi data, bukan mengelola tiket.
4. **Manajemen perangkat non-GPON.** Switch, router core, mikrotik, radio wireless — di luar scope. Gunakan NMS umum (LibreNMS/Zabbix) untuk itu.
5. **Mendeploy dan mengoperasikan GenieACS.** Phase 2 mengintegrasikan GenieACS sebagai sistem eksternal. Aplikasi ini bukan server ACS dan tidak akan mengimplementasikan protokol TR-069 sendiri.
6. **Multi-tenant / white-label.** Satu instalasi = satu ISP. Tidak ada isolasi data antar-tenant, tidak ada reseller.
7. **Migrasi data dari aplikasi lama.** Data mulai kosong. ONU existing masuk secara alami lewat discovery dari OLT (serial, port, status terbaca otomatis); yang perlu diisi manual hanya metadata pelanggan. *Bila volume pelanggan existing besar, solusinya adalah skrip import CSV sekali pakai yang dibuang setelah dipakai (bagian dari P4) — bukan modul migrasi permanen di dalam produk.*
8. **Konfigurasi OLT tingkat lanjut.** Pengaturan uplink, LAG, routing, OSPF/BGP, firmware upgrade OLT tetap di CLI. Aplikasi ini mengelola siklus hidup ONU, bukan menggantikan konsol OLT.
9. **High availability / clustering.** Satu instans. Downtime aplikasi tidak memutus layanan pelanggan — ONU tetap berjalan tanpa aplikasi. Backup harian cukup.
10. **Monitoring real-time sub-detik.** Polling berkala (interval menit), bukan streaming. Lihat Trade-off #2.
11. **Mobile app native.** Web responsive saja. Tidak ada build Android/iOS untuk dirawat.
12. **Prediksi berbasis AI/ML.** Phase 2 memakai deteksi tren statistik sederhana (P7), bukan model ML.

---

## 7. Trade-off yang Butuh Keputusan Pemilik Produk

### ⚠️ Trade-off #1 (UTAMA, KONTROVERSIAL): MVP hanya mendukung ZTE — CDATA ditunda ke Phase 2

**Usulan:** MVP dirilis dengan driver **ZTE C300/C320 saja**. Dukungan CDATA menyusul setelah driver ZTE terbukti stabil di produksi minimal satu bulan.

**Pro (alasan menunda CDATA):**
- Abstraksi multi-vendor yang dirancang sebelum ada *satu* driver yang matang hampir selalu salah. Membangun driver ZTE sampai benar-benar jalan di lapangan akan menunjukkan di mana batas abstraksi yang sebenarnya; CDATA lalu menjadi validasi, bukan tebakan.
- Pola perintah kedua vendor berbeda secara fundamental (ZTE delete-lalu-recreate untuk ganti VLAN aktif; CDATA argumen flat dengan modify in-place). Mengejar keduanya sekaligus berarti setiap bug butuh dua perangkat uji untuk direproduksi.
- Dokumentasi CDATA lebih tipis dan beberapa perilakunya hanya bisa dipastikan lewat uji di perangkat fisik. Itu kerja riset yang tidak bisa dijadwalkan dengan pasti.
- Waktu rilis MVP diperkirakan lebih cepat ~30–40% tanpa vendor kedua. Nilai bagi bisnis datang dari teknisi berhenti memakai telnet, bukan dari jumlah vendor yang didukung.

**Kontra (alasan tetap memasukkan CDATA di MVP):**
- Bila jaringan produksi hari ini sudah mencampur ZTE dan CDATA, MVP ZTE-only berarti teknisi tetap harus telnet untuk sebagian OLT — sehingga alur kerja lama tidak pernah benar-benar mati dan adopsi aplikasi tersendat.
- Menambahkan vendor kedua *setelah* driver pertama jadi berisiko menimbulkan refaktor besar bila abstraksi awal terlalu condong ke ZTE.
- Secara komersial, "mendukung ZTE dan CDATA" adalah klaim yang jauh lebih kuat bila produk ini kelak dijual ke ISP lain.

**Rekomendasi PM:** **ZTE-only di MVP**, dengan satu syarat pengaman — driver ditulis di balik antarmuka `OltDriver` sejak hari pertama (authorize, deauthorize, get_status, get_optical, set_profile, reboot), walaupun implementasinya baru satu. Biaya tambahannya kecil; biaya menuliskannya belakangan besar.

**Yang perlu diputuskan pemilik produk:** berapa persen OLT produksi saat ini bermerek CDATA? Bila > 40%, keputusan ini layak dibalik dan jadwal rilis MVP perlu dimundurkan secara eksplisit — bukan diam-diam.

---

### Trade-off #2: Polling berkala, bukan monitoring real-time

**Usulan:** status ONU (up/down) di-poll **1 menit** via SNMP bulkwalk (diputuskan sesi ini — dinaikkan dari rentang 5–15 menit awal); sinyal optik tetap 15 menit.

**Pro:** `bulkwalk` 1 round-trip per OLT tetap murah walau interval dipercepat (beban tidak naik linear per-ONU, lihat §3.4); status down/up jadi terasa hampir real-time tanpa kompleksitas streaming/websocket.
**Kontra:** saat gangguan berlangsung, NOC melihat data optik yang bisa jadi 15 menit basi dan mungkin tidak mempercayai dashboard; 1 menit tetap bukan "real-time" — ONU yang flap naik-turun di bawah 1 menit tidak tertangkap.
**Mitigasi:** tombol "refresh sekarang" per-ONU untuk query langsung saat dibutuhkan, plus trap SNMP untuk event LOS/dying-gasp agar kejadian kritis tetap masuk seketika.

---

### Trade-off #3: TR-069/GenieACS keluar dari MVP

**Usulan:** TR-069 masuk Phase 2 (P2).

**Pro:** TR-069 adalah sistem terpisah dengan mode kegagalannya sendiri (sesi CWMP, firewall port 7547, perbedaan WAN management vs internet, inkonsistensi firmware CPE). Menggabungkannya ke MVP berisiko membuat seluruh rilis tersandera urusan CPE, padahal nilai inti MVP — aktivasi tanpa CLI — tidak membutuhkannya sama sekali.
**Kontra:** "ganti password WiFi dari aplikasi" adalah fitur yang paling kasat mata bagi NOC dan paling sering diminta. Tanpa itu, MVP bisa terasa kurang berguna bagi persona NOC.
**Mitigasi:** MVP tetap memberi NOC nilai konkret (pencarian cepat, histori sinyal, reboot ONU). Bila fitur WiFi dianggap wajib sejak awal, konsekuensinya harus diterima terbuka: tambah estimasi dan deploy GenieACS sebagai prasyarat infrastruktur, bukan sebagai bagian dari aplikasi ini.

---

### Trade-off #4: Tiga peran tetap, bukan RBAC granular

**Usulan:** hanya Admin / NOC / Teknisi, hardcoded.

**Pro:** RBAC berbasis permission granular adalah fitur yang terlihat murah tapi menyebar ke seluruh codebase dan menjadi sumber bug otorisasi permanen. Tiga peran menutupi kebutuhan nyata ISP dengan 5–15 staf.
**Kontra:** organisasi yang tumbuh akan menemukan peran yang tidak pas (misal teknisi senior yang boleh hapus ONU).
**Mitigasi:** simpan peran sebagai data, bukan konstanta, sehingga peran keempat bisa ditambah tanpa membongkar model otorisasi.

---

## Bagian 2 — Arsitektur Backend

# 4. Arsitektur Teknologi Backend

> Konteks keras: **1 developer solo maintain, 100% dikerjakan dari VS Code.** Setiap pilihan di bawah dinilai dengan 1 pertanyaan: *kalau jam 2 pagi OLT bermasalah, bisakah 1 orang membaca log, reproduksi, dan memperbaiki tanpa menyalakan 5 service?* Stack yang butuh tim platform ditolak, sekalipun lebih "benar" secara teori.

## 4.1 Pilihan Stack Konkret

| Lapisan | Pilihan | Alasan singkat |
|---|---|---|
| Bahasa | **Python 3.12** (satu bahasa untuk API + driver OLT + worker) | Library otomasi jaringan (netmiko/scrapli/pysnmp) semuanya Python. Pengalaman sebelumnya (app PHP + script Python terpisah) memaksa 2 runtime, 2 set model data, 2 gaya error handling — itu pajak harian untuk solo dev. |
| Framework API | **FastAPI (rilis stabil terbaru, pin `>=0.120,<0.121`) + Uvicorn** | Async native (penting: driver OLT I/O-bound), OpenAPI otomatis (dokumen API gratis, tidak perlu ditulis manual), validasi request pakai **Pydantic v2** (core Rust) — menghilangkan ratusan baris cek input manual. |
| Validasi/DTO | **Pydantic v2** | Satu definisi skema dipakai untuk validasi request, response, dan config driver. |
| ORM | **SQLAlchemy 2.0 (gaya `select()`) + Alembic** | ORM paling matang di Python; Alembic memberi migrasi versioned yang bisa di-`git diff` — wajib untuk solo dev yang deploy sendiri. |
| Database | **PostgreSQL 18** | Lihat trade-off 4.5.B. Versi terbaru stabil; naik dari asumsi awal 16 — fitur `UUIDv7` native dan async I/O (AIO) relevan untuk tabel job/log kita. |
| Background job | **Worker proses terpisah + tabel `jobs` di PostgreSQL (`FOR UPDATE SKIP LOCKED`)** | Lihat trade-off 4.5.A (kontroversial). |
| Scheduler | **APScheduler di dalam proses worker** (bukan proses ketiga) | Scheduler hanya *menulis baris* ke tabel `jobs`; eksekusi tetap milik worker. Satu jalur eksekusi = satu tempat mencari bug. |
| Driver SSH/Telnet | **netmiko** (`cisco_ios`/`generic_termserver` + custom class per vendor) | Sudah menangani paging, prompt detection, timeout, dan `read_until`. Telnet CDATA butuh `\r\n` dan prompt `User name:` (ada spasi) — ditangani lewat subclass, bukan reinvent pexpect. |
| Driver SNMP | **pysnmp (async)** untuk bulk walk status/Rx | Bulk sync 1000+ ONU lewat CLI tidak realistis; SNMP `bulkwalk` 1 round-trip per tabel. |
| TR-069 | **GenieACS 1.2.x (MongoDB 4.4) sebagai service eksternal**, diakses via NBI :7559 | GenieACS TIDAK ditulis ulang. Backend hanya proxy + simpan mapping `onu.serial ↔ genieacs_device_id`. |
| Enkripsi kredensial OLT | `cryptography` Fernet, kunci dari env `APP_SECRET_KEY` | Password OLT tidak boleh plaintext di DB. |
| Auth API | **JWT (PyJWT) + argon2-cffi** untuk hash password user | Stateless, cukup untuk 1 aplikasi internal. |
| Realtime UI | **SSE (Server-Sent Events) `/api/stream/jobs`** | Lihat trade-off 4.5.C. |
| Deploy | systemd 2 unit: `nexfiber-api.service` (uvicorn) + `nexfiber-worker.service`; Nginx reverse proxy | Tanpa Docker/K8s. `journalctl -u nexfiber-worker -f` = satu perintah untuk semua debugging job. |
| Test | pytest + pytest-asyncio; driver diuji dengan **fixture transkrip CLI** (file teks output OLT asli) | Tidak perlu OLT fisik di CI. |

**Yang sengaja TIDAK dipakai (dan kapan baru ditambahkan):**

- **Redis** — belum ada beban yang membutuhkannya. Tambahkan kalau job rate > ~50/detik atau sudah butuh cache lintas-proses.
- **Celery** — lihat 4.5.A.
- **Microservice / gRPC antar modul** — tambahkan kalau sudah ada >1 developer dan >1 jadwal rilis.
- **GraphQL** — tambahkan kalau sudah ada >2 klien UI berbeda dengan kebutuhan field berbeda.
- **Docker** — tambahkan kalau sudah ada lingkungan staging terpisah atau deploy ke >1 server.

## 4.2 Struktur Layer

Monolit modular. Aturan arah dependensi **satu arah, tidak boleh dilanggar**:

```
router  →  service  →  repository  →  database
                 ↘  driver (OLT/ACS)
```

```
app/
  main.py                  # bootstrap FastAPI, mount router, lifespan (pool DB)
  core/
    config.py              # Settings (pydantic-settings, baca .env)
    security.py            # JWT, hash password, enkripsi kredensial OLT
    exceptions.py          # AppError hierarchy → mapper ke HTTP status
    db.py                  # engine + session factory
  routers/                 # HANYA: parsing request, auth/role, panggil service
    auth.py  olts.py  onus.py  vlans.py  splitters.py
    speed_profiles.py  jobs.py  logs.py  stream.py
  schemas/                 # Pydantic request/response (bukan model DB)
  services/                # SEMUA aturan bisnis & orkestrasi
    onu_service.py         # authorize/modify/delete ONU, validasi slot-port-id
    olt_service.py         # CRUD OLT, test koneksi, backup config
    sync_service.py        # logika sinkronisasi (dipanggil worker, bukan router)
    job_service.py         # enqueue, status, retry, cancel
  repositories/            # HANYA query SQLAlchemy; tanpa aturan bisnis
    base.py  onu_repo.py  olt_repo.py  job_repo.py  ...
  drivers/
    base.py                # ABC OltDriver — kontrak seragam
    transport/ssh.py telnet.py snmp.py   # netmiko/pysnmp wrapper + timeout + log raw
    zte_c300.py zte_c320.py cdata_fd1602sb1.py
    registry.py            # vendor+model → kelas driver
    errors.py              # deteksi string error (lihat 4.3)
  acs/genieacs.py          # klien NBI GenieACS
  models/                  # model SQLAlchemy (ORM)
worker/
  main.py                  # loop: klaim job → eksekusi → tulis hasil
  handlers/                # 1 fungsi per job_type
  schedules.py             # APScheduler → enqueue job berkala
alembic/versions/          # migrasi
tests/fixtures/cli/        # transkrip output OLT asli untuk uji parser
```

Aturan tegas:

1. **Router tidak pernah memanggil repository atau driver langsung.** Kalau sebuah endpoint terasa "terlalu sepele untuk butuh service", tetap lewat service — konsistensi lebih murah daripada mengingat pengecualian.
2. **Repository tidak pernah berisi `if` bisnis.** Hanya query dan mapping.
3. **Driver tidak pernah menyentuh database.** Driver menerima parameter primitif dan mengembalikan objek hasil; service yang menyimpan.
4. **Operasi yang menyentuh OLT TIDAK PERNAH dijalankan di dalam request HTTP.** Router hanya `enqueue` job dan langsung balas `202 Accepted` + `job_id`. Alasan: 1 sesi telnet CDATA bisa makan 20–60 detik, dan timeout HTTP akan membuat user menekan tombol dua kali — menghasilkan dua `ont add` pada ONU yang sama.
   *Pengecualian terdaftar:* operasi baca cepat yang sudah di-cache di DB (list ONU, detail) dilayani langsung dari repository.

## 4.3 Kontrak Driver OLT

```python
class OltDriver(ABC):
    vendor: str; model: str
    port_range: tuple[int, int]        # ZTE C320: (1,16) | CDATA FD1602S-B1: (1,2)
    capabilities: set[str]             # {"snmp_rx","cli_rx","tr069_profile","wan_config"}

    async def test_connection(self) -> DriverResult: ...
    async def list_unconfigured(self) -> list[UnconfiguredOnu]: ...
    async def authorize(self, req: AuthorizeRequest) -> DriverResult: ...
    async def modify(self, req: ModifyRequest) -> DriverResult: ...
    async def delete(self, port: int, onu_id: int) -> DriverResult: ...
    async def set_state(self, port: int, onu_id: int, enabled: bool) -> DriverResult: ...
    async def reboot(self, port: int, onu_id: int) -> DriverResult: ...
    async def fetch_inventory(self) -> list[OnuSnapshot]: ...   # status + desc
    async def fetch_optical(self, port: int | None) -> list[OpticalSample]: ...
    async def backup_config(self) -> str: ...
```

Keputusan desain driver yang wajib dipatuhi (hasil pengalaman lapangan, bukan teori):

- **OLT CLI tidak punya exit code. Sukses WAJIB dibuktikan dari isi output,** tidak boleh disimpulkan dari "tidak ada exception". `errors.py` memuat daftar string gagal (`invalid input`, `unknown command`, `operation failed`, `% there is no`, …) **dan** pola "sukses palsu" CDATA seperti `Number of ONTs that can be added: 0, success: 0` dan `Total: 3, online: 2, failed: 1`.
- **Command destruktif bisa meminta konfirmasi `(y/n)` dan akan menggantung selamanya** (`ont delete <port> all`, `firmware switch`). Transport wajib punya auto-answer terdaftar + hard timeout.
- **Satu OLT = satu sesi CLI pada satu waktu.** Worker memegang `asyncio.Lock` per `olt_id` (dan advisory lock Postgres kalau kelak ada >1 worker). Dua sesi paralel ke OLT yang sama menghasilkan output tercampur dan parser salah baca.
- **`sysObjectID` tidak boleh dipakai mendeteksi vendor** (CDATA GPON melapor enterprise EPON `17409`). Vendor/model diambil dari field `olts.vendor`/`olts.model` yang diisi operator, driver dipilih lewat `registry.py`.
- **Sumber data per metrik ditentukan eksplisit per-firmware lewat `capabilities`**, bukan diasumsikan: Rx CDATA V3 andal dari CLI `show ont optical-info`, sedangkan SNMP sering mengembalikan `--`. Probe dulu, jangan hardcode.
- **Setiap perintah tulis menyimpan `raw_command` + `raw_output`** ke `activity_logs`. Ini satu-satunya alat forensik ketika pelanggan protes "internet saya mati setelah Anda utak-atik".

## 4.4 Strategi Background Sync

Tiga jadwal berbeda, karena biayanya berbeda jauh:

| Job | Interval | Transport | Catatan |
|---|---|---|---|
| `sync_onu_status` | **1 menit** | SNMP bulkwalk | Murah (1 round-trip per tabel OID); interval dipercepat dari 3 menit → 1 menit agar ONU drop/up terdeteksi hampir seketika tanpa perlu real-time streaming. Update `status`, `last_seen_at`. |
| `sync_onu_optical` | 15 menit | SNMP kalau `capabilities` mendukung, jika tidak CLI per-PON | Mahal. Simpan Rx/Tx. |
| `sync_unconfigured` | 5 menit | CLI (`show gpon onu uncfg` / `show ont autofind all`) | Untuk layar pendaftaran ONU baru. |
| `backup_olt_config` | harian | CLI | Simpan ke `olt_config_backups`. |

**Catatan beban (`sync_onu_status` @ 1 menit):** satu `bulkwalk` per OLT per menit, bukan per ONU — OLT GPON tetap menjawab satu tabel OID (`ifOperStatus`/vendor-MIB) dalam satu round-trip walaupun isinya ratusan ONU, jadi beban ke OLT tidak bertambah linear dengan jumlah ONU. Yang bertambah adalah tulis-DB: 1000 ONU × 1 baris/menit × 1440 menit/hari ≈ 1,44 juta baris/hari kalau disimpan mentah. **Mitigasi:** `sync_onu_status` hanya menulis baris baru ke `onu_signal_history`/log **saat status berubah** (`UPDATE ... WHERE status IS DISTINCT FROM new_status`), bukan tiap tick — tick yang tidak berubah hanya menyentuh `last_seen_at` di baris ONU itu sendiri (UPSERT 1 baris, bukan INSERT histori).

Aturan anti-penumpukan: scheduler **tidak** membuat job baru bila job sejenis untuk `olt_id` yang sama masih `pending`/`running` (unique partial index di 4.6). OLT yang tidak terjangkau tidak boleh menyumbat antrean OLT lain — eksekusi dikelompokkan per-OLT, kegagalan satu OLT hanya menandai job-nya `failed` dan menaikkan `backoff`.

**Catatan operasional dari insiden nyata:** pada implementasi sebelumnya, satu error format query di OLT pertama mematikan seluruh skrip sync sehingga semua OLT berikutnya kehilangan siklus sinkronisasinya. Karena itu handler wajib `try/except` **per-OLT**, bukan per-batch, dan kegagalan dicatat sebagai hasil job, bukan sebagai crash proses.

## 4.5 Trade-off yang Diputuskan

### A. (KONTROVERSIAL) Antrean job pakai tabel PostgreSQL, bukan Celery + Redis

**Keputusan: tabel `jobs` + `SELECT … FOR UPDATE SKIP LOCKED`, dieksekusi worker asyncio tunggal.**

*Pro:*
- Nol infrastruktur tambahan. Tidak ada Redis untuk di-backup, di-monitor, atau kehabisan memori diam-diam.
- **Antrean ikut transaksi DB.** "Buat ONU + enqueue job provisioning" jadi satu commit; dengan Redis, job bisa terkirim padahal transaksi DB di-rollback — bug paling menyebalkan untuk didiagnosis sendirian.
- Debugging = SQL biasa. `SELECT * FROM jobs WHERE status='failed' ORDER BY id DESC` mengalahkan Flower/`celery inspect`. Histori job otomatis permanen dan bisa di-JOIN ke `onus`/`users` untuk audit.
- Celery + asyncio masih berbau tambal (prefork vs async); di sini semua kode driver sudah `async`, worker asyncio adalah jalur paling lurus.
- Beban nyata kecil: ratusan job/menit, didominasi tunggu I/O jaringan, bukan CPU.

*Kontra (jujur):*
- Polling DB (interval 1 detik) menambah query idle terus-menerus. *Mitigasi:* `LISTEN/NOTIFY` Postgres untuk membangunkan worker saat job baru masuk → polling hanya jadi jaring pengaman.
- Retry/backoff, timeout job gantung, dan dead-letter **ditulis sendiri** (~150 baris). Celery memberi itu gratis.
- Tidak ada UI monitoring siap pakai (Flower). *Mitigasi:* halaman `/jobs` di aplikasi sendiri — toh operator NOC tetap butuh halaman itu.
- Skala horizontal terbatas: pola ini nyaman sampai ~beberapa ribu job/menit. Di atas itu, broker sungguhan menang.

*Kapan keputusan ini dibatalkan:* sudah >2 worker di host berbeda, atau butuh fitur Celery spesifik (chord/chain, rate-limit per-worker, prioritas kompleks). Migrasi relatif murah karena **service tidak pernah tahu antreannya apa** — hanya memanggil `job_service.enqueue(...)`. Yang berubah cuma implementasi di balik fungsi itu.

### B. PostgreSQL, bukan MySQL

*Pro:* `SKIP LOCKED` matang dan merupakan fondasi keputusan A; `JSONB` + GIN index cocok untuk `driver_capabilities`, payload job, dan snapshot TR-069 yang skemanya berubah per-firmware; partial unique index (`WHERE status IN ('pending','running')`) mencegah job ganda di level database, bukan di level kode; `LISTEN/NOTIFY` menghapus kebutuhan Redis pub/sub; tipe `inet` dan range query time-series lebih rapi.

*Kontra:* ekosistem ISP Indonesia lebih akrab MySQL (hosting, DBA lepas, snippet di forum); tooling backup di server lama biasanya sudah MySQL; MySQL 8 sebenarnya juga punya `SKIP LOCKED` dan JSON, jadi argumen ini bukan kemenangan telak. Karena aplikasinya **baru** (bukan migrasi dari basis data lama) dan dipegang satu orang yang menulis sendiri query-nya, ongkos belajar Postgres dibayar sekali di awal dan nol setelahnya.

### C. REST + SSE, bukan WebSocket atau GraphQL

*Pro:* arus data realtime di sini **satu arah** (server → browser: progres job, perubahan status ONU). SSE jalan di atas HTTP biasa, lolos reverse proxy tanpa konfigurasi upgrade, auto-reconnect bawaan browser, dan di sisi server hanya satu generator async. Perintah tetap lewat `POST` REST biasa yang mudah di-`curl` dan dites.

*Kontra:* SSE terbatas ~6 koneksi per domain di HTTP/1.1 (hilang dengan HTTP/2 di Nginx) dan tidak bisa dua arah — kalau nanti ada fitur "terminal CLI interaktif ke OLT di browser", fitur itu **wajib** WebSocket. Keputusan ini diambil karena fitur tersebut tidak ada di scope v1. GraphQL ditolak: satu klien UI, dan biaya N+1 query plus lapisan resolver tidak sebanding untuk solo dev.

## 4.6 Data Model Utama

Konvensi: semua tabel punya `id BIGSERIAL PK`, `created_at`/`updated_at TIMESTAMPTZ`. Soft delete (`deleted_at`) hanya di `olts`, `onus`, `users` — entitas yang punya nilai historis.

### `users`
`id`, `username` UNIQUE, `email` UNIQUE, `password_hash` (argon2), `full_name`, `role` ENUM(`admin`,`noc`,`teknisi`,`viewer`), `is_active`, `last_login_at`, `deleted_at`.
Peran dipakai untuk membatasi aksi destruktif: hanya `admin`/`noc` boleh `delete`/`reboot` ONU.

### `olts`
`id`, `name`, `host` (inet), `vendor` ENUM(`zte`,`cdata`), `model` (`C300`,`C320`,`FD1602S-B1`), `firmware_version`,
`cli_protocol` ENUM(`ssh`,`telnet`), `cli_port`, `cli_username`, `cli_password_enc`, `cli_enable_password_enc`,
`snmp_version`, `snmp_community_enc`, `snmp_port`,
`pon_port_count` (ZTE C320 16 / CDATA FD1602S-B1 **2** — dipakai memvalidasi input port),
`max_onu_per_port`, `capabilities` JSONB, `location`, `latitude`, `longitude`,
`status` ENUM(`online`,`offline`,`unreachable`), `last_sync_at`, `last_error`, `is_active`, `deleted_at`.
Index: UNIQUE(`host`, `cli_port`).

### `pon_ports`
`id`, `olt_id` FK, `slot`, `port`, `ifindex` (SNMP), `description`, `admin_state`, `oper_state`,
`tx_power_dbm`, `rx_power_dbm`, `temperature_c`, `onu_count`, `last_sync_at`.
Index: UNIQUE(`olt_id`,`slot`,`port`). Ada sebagai tabel sendiri supaya splitter dan statistik per-PON punya induk yang jelas.

### `onus` (tabel inti)
`id`, `olt_id` FK, `pon_port_id` FK, `onu_index` (ONU ID di PON, 1–128/256),
`serial_number` (ZTE `ZTEGxxxxxxxx` / CDATA `CDTCxxxxxxxx` / hex-16), `auth_type` ENUM(`sn`,`loid`,`password`), `loid`, `auth_password_enc`,
`name`, `description` (CDATA: maks 64–128 char — divalidasi di service), `customer_name`, `customer_id`, `address`, `phone`,
`onu_type` / `onu_model`, `vendor_id`, `hardware_version`, `software_version`,
`status` ENUM(`online`,`offline`,`los`,`dying_gasp`,`power_off`,`unknown`),
`config_state` ENUM(`success`,`failed`,`configuring`,`initial`), `match_state`,
`admin_state` ENUM(`enabled`,`disabled`),
`rx_power_dbm`, `tx_power_dbm`, `olt_rx_power_dbm`, `temperature_c`, `voltage_v`, `bias_current_ma`,
`distance_m`, `vlan_id` FK→`vlans`, `speed_profile_id` FK, `splitter_id` FK,
`line_profile_id`, `srv_profile_id`, `tr069_profile_id`, `genieacs_device_id` (mapping ke GenieACS),
`mac_address`, `ip_address` (inet),
`last_seen_at`, `last_down_at`, `last_down_reason`, `last_sync_at`,
`registered_at`, `registered_by` FK→`users`, `deleted_at`.
Index: UNIQUE(`olt_id`,`serial_number`) WHERE `deleted_at IS NULL`; UNIQUE(`pon_port_id`,`onu_index`) WHERE `deleted_at IS NULL`; index pada (`status`), (`customer_id`), (`serial_number`).

### `onu_signal_history`
`id`, `onu_id` FK, `rx_power_dbm`, `tx_power_dbm`, `olt_rx_power_dbm`, `status`, `sampled_at`.
Dipisah dari `onus` supaya baris utama tidak di-`UPDATE` ribuan kali sehari dan grafik sinyal punya sumber. Retensi 90 hari, pembersihan oleh job harian. Index: (`onu_id`, `sampled_at DESC`).

### `vlans`
`id`, `olt_id` FK (NULL = VLAN global), `vlan_id` (1–4094), `name`, `type` ENUM(`internet`,`management`,`voip`,`iptv`,`other`),
`description`, `gemport`, `tag_action` ENUM(`transparent`,`translate`,`tag`), `user_vlan`, `is_active`.
Index: UNIQUE(`olt_id`,`vlan_id`).

### `speed_profiles`
`id`, `name`, `download_kbps`, `upload_kbps`, `olt_id` FK (NULL = berlaku untuk semua),
`dba_profile_id`, `dba_type` (type1–4), `line_profile_id`, `srv_profile_id`,
`tcont_id`, `description`, `is_active`.
Catatan penting: ID profil ini adalah **cerminan objek yang sudah ada di OLT**, bukan sumber kebenaran. Aplikasi tidak membuat DBA/line profile otomatis di v1; teknisi memilih dari profil yang terdaftar. (Dibatasi sengaja — otomatisasi pembuatan profil ditambahkan setelah pola penamaan di lapangan stabil.)

### `splitters`
`id`, `parent_id` FK self (splitter bertingkat: ODC → ODP), `olt_id` FK, `pon_port_id` FK,
`name`, `code`, `type` ENUM(`odc`,`odp`), `ratio` (`1:8`,`1:16`,`1:32`,`1:64`),
`capacity`, `used_ports`, `location`, `latitude`, `longitude`, `insertion_loss_db`, `notes`.
Dipakai untuk menjawab "ONU mana saja yang mati karena satu ODP?" — korelasi padam massal.

### `jobs` (antrean + histori, inti keputusan 4.5.A)
`id`, `job_type` (`authorize_onu`,`delete_onu`,`reboot_onu`,`set_state`,`sync_onu_status`,`sync_onu_optical`,`sync_unconfigured`,`backup_olt_config`,`apply_speed_profile`,`tr069_push`),
`status` ENUM(`pending`,`running`,`success`,`failed`,`cancelled`),
`priority` SMALLINT (makin kecil makin dulu), `payload` JSONB, `result` JSONB,
`olt_id` FK, `onu_id` FK, `created_by` FK→`users`,
`attempts`, `max_attempts` (default 3), `run_after` TIMESTAMPTZ (backoff eksponensial), `locked_at`, `locked_by` (nama worker, untuk mendeteksi job gantung), `started_at`, `finished_at`, `duration_ms`, `error_message`, `error_code`.
Index:
- `(status, run_after, priority)` → query klaim job.
- **Partial unique:** `UNIQUE(job_type, olt_id) WHERE status IN ('pending','running') AND job_type LIKE 'sync_%'` → mencegah job sync menumpuk pada OLT yang lambat.
- `(onu_id, created_at DESC)`.

### `activity_logs`
`id`, `user_id` FK (NULL untuk aksi sistem/worker), `job_id` FK, `olt_id` FK, `onu_id` FK,
`action`, `entity_type`, `entity_id`, `before` JSONB, `after` JSONB,
`raw_command` TEXT, `raw_output` TEXT, `success` BOOL, `ip_address` (inet), `user_agent`, `created_at`.
`raw_command`/`raw_output` wajib diisi untuk setiap perintah tulis ke OLT. Retensi 1 tahun.

### `olt_config_backups`
`id`, `olt_id` FK, `config_text`, `checksum` (sha256), `size_bytes`, `taken_at`, `triggered_by`.
Hanya simpan bila `checksum` berbeda dari backup terakhir — menghindari menumpuk salinan identik.

### `settings`
`key` PK, `value` JSONB, `description`, `updated_by`, `updated_at`.
Untuk interval sync, ambang alarm Rx (mis. `-27 dBm`), URL/kredensial GenieACS. Menghindari membuat tabel konfigurasi baru setiap muncul satu nilai yang bisa diatur.

### Relasi ringkas

```
users ─< activity_logs >─ onus
olts ─< pon_ports ─< onus
olts ─< vlans ─< onus
olts ─< splitters ─< onus          (splitters juga self-referencing: ODC → ODP)
speed_profiles ─< onus
jobs >─ olts, onus, users
onus ─< onu_signal_history
olts ─< olt_config_backups
```

## 4.7 Yang Ditunda Secara Sadar

| Ditunda | Tambahkan kalau |
|---|---|
| Redis cache / broker | job > ~50/detik, atau worker sudah lebih dari satu host |
| Multi-worker + advisory lock Postgres | 1 worker tidak lagi menyelesaikan siklus sync dalam interval |
| WebSocket | muncul kebutuhan interaktif dua arah (terminal CLI di browser) |
| Otomatis membuat DBA/line profile di OLT | pola penamaan profil di lapangan sudah stabil |
| Driver vendor lain (Huawei/Fiberhome/VSOL) | ada OLT-nya di jaringan — kontrak `OltDriver` sudah menyiapkan tempatnya |
| Metrics Prometheus / tracing | sudah ada orang khusus yang memantau, bukan developer yang sama |

---

## Bagian 3 — Design System & UI/UX

# PRD Bagian 3: Design System, Navigasi, dan Spesifikasi Layar

Produk: **Nexfiber NOC Console** (manajemen OLT/ONU untuk ISP fiber/GPON)
Peran penulis: UI/UX Designer
Status: draft siap gabung ke PRD utama
Dokumen pendamping: `DESIGN.md` (arah desain, token lengkap) di root repo

## 3.0 Design Read dan dial

> Reading this as: **operational console B2B internal** untuk **operator NOC ISP (shift 24/7)**, dalam bahasa visual **panel instrumen padat, netral hangat, tipografi teknis**, dial **ENERGY 1 / RHYTHM 1 / MOTION 1**.

| Dial | Nilai | Alasan |
|---|---|---|
| ENERGY | 1 | Layar kerja harian; sapaan visual merampok perhatian yang seharusnya milik alarm dan angka sinyal. |
| RHYTHM | 1 | Layar yang sama dipindai ratusan kali per shift; posisi elemen stabil membangun muscle memory. Variasi komposisi hanya antar jenis layar, bukan antar section dalam satu layar. |
| MOTION | 1 | Hover, focus, dan transisi state saja. Gerak abadi di layar monitoring membaca sebagai alarm palsu. |

Karakter produk tidak datang dari energi atau animasi, tapi dari tiga hal: palet netral hangat + hijau optik, pasangan IBM Plex Sans/Mono dengan angka tabular, dan motif **signal bar** yang membawa data (bukan hiasan).

## 3.1 Stack dan rekomendasi

Tetap **React 19 + Vite 7 + TypeScript + Tailwind CSS v4** (naik dari asumsi v3 — engine baru Tailwind v4 lebih cepat dan konfigurasi langsung di CSS via `@theme`, cocok untuk `DESIGN.md` token-based), dengan tambahan:

| Pilihan | Keputusan | Alasan |
|---|---|---|
| Komponen | **shadcn/ui** (copy-in, bukan dependency), hanya primitif: Dialog, Dropdown, Select, Popover, Tooltip, Tabs, Command | Primitif a11y (focus trap, Esc, ARIA) adalah kerja berulang yang tidak menambah nilai produk; token Tailwind di-override penuh dari `DESIGN.md` sehingga look-nya milik kita. |
| Tabel | **TanStack Table + TanStack Virtual**, headless | Tabel 200 s/d 10.000 baris ONU butuh virtualisasi, column pinning, dan server-side sort/filter; komponen tabel siap pakai justru menghalangi. |
| Chart | **uPlot** | Time-series Rx/traffic puluhan ribu titik; library chart umum terlalu berat untuk kebutuhan ini. |
| Ikon | **Phosphor Icons** weight `regular`, dipakai selektif | Dipilih karena bukan set default yang menyeragamkan tampilan AI, dan punya glyph jaringan/perangkat yang relevan. Ikon dipakai hanya di sidebar dan status; tidak di tiap baris atau tiap label. |
| Form | **React Hook Form + Zod** | Form Auth ONU punya validasi berlapis (serial unik, VLAN range, profile cocok dengan OLT) yang harus jalan sebelum request dikirim ke perangkat. |

## 3.2 Design System (ringkas; detail token di `DESIGN.md`)

### Palet

2 warna inti + 1 aksen + netral. Tanpa gradien primer, tanpa glow, tanpa latar radial, tanpa background grid.

| Peran | Token | Light | Dark |
|---|---|---|---|
| Inti 1 | `--ink` | `#1C1B18` | `#E8E6DF` |
| Inti 2 | `--fiber` | `#0F5C4A` | `#4FB79B` |
| Aksen | `--amber` | `#B4540A` | `#E08A3C` |
| Latar app | `--bg-app` | `#F7F6F3` | `#131412` |
| Permukaan | `--bg-surface` | `#FFFFFF` | `#1B1C19` |

Status perangkat (`--st-up/warn/down/idle`) adalah bahasa data, bukan palet dekorasi, dan selalu berpasangan dengan teks.

Alasan per keputusan:
- Latar putih hangat `#F7F6F3`, bukan `#FFFFFF`: mengurangi silau pada shift 8 jam.
- Hijau optik sebagai warna inti kedua: merujuk serat/konektor, dan menghindari biru korporat default.
- Satu aksen amber: satu-satunya warna yang berarti "tindakan ini mengubah jaringan", jadi ia tidak boleh muncul di ikon, link, atau latar.

### Tipografi

| Peran | Font | Alasan |
|---|---|---|
| UI | IBM Plex Sans | Dirancang untuk antarmuka teknis, tinggi-x besar, angka tabular bawaan. |
| Data | IBM Plex Mono | Serial ONU, MAC, PON port, dBm, VLAN butuh lebar tetap agar kolom sejajar dan salah baca `0/O` turun. |

Skala: 11 / 13 / 14 / 16 / 20 / 28px. **Default aplikasi 13px**, karena layar harus menampung 40+ baris tanpa scroll. Uppercase hanya untuk label kolom tabel, tracking maks `0.02em`.

### Spacing

Basis 4px, skala `4 8 12 16 24 32 48`. Sel tabel `8px 12px`; baris 32px (compact) / 40px (comfortable); panel 16px; antar panel 12px; antar grup form 24px. Spasi besar disimpan khusus untuk memisahkan grup form dan batas section, sehingga spasi tetap membawa arti.

### Radius

`0` untuk sel tabel (grid dibaca sebagai matriks), `3px` untuk kontrol (input, tombol, badge), `8px` untuk lapisan (panel, modal, popover). Tanpa pill: bentuk kapsul menghapus perbedaan antara badge, tombol, dan input.

### Shadow

Dua level, hanya untuk elevasi nyata: `shadow-overlay` (dropdown/popover) dan `shadow-modal` (dialog/drawer). Panel, kartu, tabel, dan sidebar **tanpa shadow**; pemisahan memakai border 1px dan perbedaan latar. Alasan: kalau semua melayang, elevasi tidak memberi informasi.

Fokus: `outline: 2px solid var(--fiber)`, offset 1px. Tidak pernah dihapus.

## 3.3 Struktur Menu / Navigasi

Sidebar kiri permanen 208px, tanpa top-bar global penuh. Alasan: navigasi harus selalu terlihat agar operator berpindah antar OLT/ONU tanpa kehilangan konteks, dan baris atas layar lebih berharga untuk filter tabel daripada untuk logo.

```
Nexfiber                    [logo = wordmark teks, placeholder sampai brand final]
─────────────────────────────
Monitor
  Ringkasan                  /
  Alarm                      /alarms            (badge angka alarm aktif)
Perangkat
  OLT                        /olts
  ONU                        /onus
  Otorisasi menunggu         /onus/pending      (badge angka ONU unconfigured)
Konfigurasi
  Profile                    /profiles          (line, service, VLAN)
  Template Provisioning      /templates
Riwayat
  Log Aksi                   /audit
─────────────────────────────
[tema: Sistem/Terang/Gelap]
[nama operator, shift, logout]
```

Aturan navigasi:
- Setiap item punya route nyata. Item yang belum dibangun tidak dipasang; kalau harus terlihat di roadmap, diberi label "Segera" yang tidak bisa diklik.
- Badge angka hanya pada Alarm dan Otorisasi menunggu, karena keduanya adalah antrian kerja. Badge tanpa angka nyata tidak ditampilkan.
- Breadcrumb hanya di layar detail: `OLT / OLT-SBY-01 / PON 1/1/3 / ONU 0021A3...`. Alasan: kedalaman hierarki GPON (OLT > slot/port > ONU) mudah membuat operator kehilangan posisi.
- Context switcher OLT di kiri-atas area konten pada layar ONU/Alarm, karena filter "OLT mana" adalah filter paling sering dipakai.
- Command palette `Ctrl/Cmd+K`: cari serial ONU, nama pelanggan, IP OLT, atau lompat ke route. Alasan: pencarian serial adalah aksi nomor satu operator saat telepon pelanggan masuk; satu shortcut memotong seluruh navigasi.
- Keyboard global: `/` fokus pencarian tabel, `j/k` pindah baris, `Enter` buka detail, `Esc` tutup drawer/modal.

## 3.4 Spesifikasi Layar

### A. Ringkasan (Dashboard): `/`

**Pekerjaan layar**: dalam 5 detik, jawab "ada yang perlu saya tangani sekarang?" dan beri jalan ke objeknya.

Bukan sidebar + 4 stat card + chart + tabel. Hierarki dibalik: antrian kerja di atas, angka agregat sebagai footnote.

```
┌ Sidebar ┬──────────────────────────────────────────────────────────────┐
│         │ Ringkasan            [rentang: 24 jam ▾]  [Perbarui]        │
│         ├──────────────────────────────────────────────────────────────┤
│         │ PERLU TINDAKAN                                              │
│         │ ┌──────────────────────────────────────────────────────────┐ │
│         │ │ 12 ONU LOS lebih dari 15 menit        [Lihat daftar]    │ │
│         │ │ 7 ONU menunggu otorisasi              [Buka antrian]    │ │
│         │ │ 2 OLT gagal dipolling                 [Lihat OLT]       │ │
│         │ └──────────────────────────────────────────────────────────┘ │
│         ├──────────────────────────────────────────────────────────────┤
│         │ ALARM TERBARU (8 baris, bukan feed tanpa batas)              │
│         │ waktu | severity | OLT/PON | objek | pesan | [Tangani]      │
│         ├──────────────────────────────────────────────────────────────┤
│         │ KONDISI SINYAL                     │ KAPASITAS PON          │
│         │ histogram Rx ONU online per bucket │ 6 PON port terpadat:   │
│         │ (normal/waspada/buruk)             │ nama, terpakai/kapasitas│
│         │ "Rx ONU online, 24 jam terakhir"   │ bar isi 1 warna        │
│         ├──────────────────────────────────────────────────────────────┤
│         │ 1.248 ONU online · 37 offline · 12 OLT  (baris teks, 13px)  │
└─────────┴──────────────────────────────────────────────────────────────┘
```

Spesifikasi:
- Blok "Perlu tindakan" adalah focal point tunggal: satu-satunya blok dengan `--bg-surface` di atas `--bg-app` plus tombol aksi. Baris yang hitungannya 0 **hilang**, tidak ditampilkan sebagai "0". Kalau semua 0: "Tidak ada yang perlu ditangani. Polling terakhir 14:32."
- Angka agregat sebagai satu baris teks di bawah, bukan 4 kartu. Alasan: angka itu konteks, bukan keputusan; memberi mereka kartu besar membalik hierarki.
- Tanpa delta "+12% minggu ini" kecuali periode pembanding nyata ada dan disebut namanya.
- Chart punya pertanyaan di judulnya ("Rx ONU online, 24 jam terakhir"), bukan "Overview".
- Setiap angka di layar ini adalah hasil query nyata; sebelum backend tersambung, nilainya `[DATA NYATA]`, bukan angka karangan.
- States: loading = skeleton per blok dengan teks "Menarik ringkasan ..."; error per blok independen (satu blok gagal tidak mengosongkan layar), pesan menyebut penyebab + tombol Coba lagi; stale = teks "Data per 14:32, polling berikutnya 14:37".
- Auto-refresh 60s dengan countdown kecil teks; tanpa animasi loop. Refresh tidak memindahkan posisi scroll.

### B. List ONU: `/onus`

**Pekerjaan layar**: menemukan ONU tertentu, atau menyaring kelompok ONU bermasalah, lalu bertindak.

```
┌────────────────────────────────────────────────────────────────────────┐
│ ONU            [OLT: semua ▾]                      [Export CSV]       │
│ [cari serial / pelanggan / MAC            ]  (fokus: tombol "/")      │
│ Status: Semua | Online | Offline/LOS | Rx waspada | Belum diotorisasi  │
│ [+ filter: PON port ▾] [profile ▾] [kepadatan: compact ▾]             │
├────────────────────────────────────────────────────────────────────────┤
│ ST │ SERIAL       │ PELANGGAN   │ OLT/PON    │ RX ONU    │ UPTIME │ ⋯ │
│ ●  │ 4857544..3A  │ ...         │ SBY-01 1/3 │ ▮▮▮ -21.4 │ 14d    │   │
│ ●  │ ...          │             │            │ ▮▮▯ -26.1 │        │   │
├────────────────────────────────────────────────────────────────────────┤
│ 1.284 ONU · 50 per halaman · ‹ 1 2 3 ›     (3 terpilih: [Reboot] ...) │
└────────────────────────────────────────────────────────────────────────┘
```

Kolom dipilih dari keputusan operator, bukan dari komponen tabel. Kolom penentu (Status, Rx) diletakkan paling awal:

| Kolom | Lebar | Catatan |
|---|---|---|
| Status | 32px | Titik 6px + tooltip teks; kolom sendiri agar bisa dipindai vertikal. |
| Serial | 150px, mono | Klik = buka detail. Serial ditampilkan penuh, tidak dipotong. |
| Pelanggan | fleksibel | Nama + ID layanan; kosong kalau belum dipetakan. |
| OLT / PON | 130px, mono | Format `SBY-01 1/1/3`. |
| Rx ONU | 120px, mono | Signal bar + nilai dBm; sortable. |
| Rx OLT | 110px, mono | Tersembunyi di bawah 1440px. |
| Profile | 120px | |
| Uptime / Last down | 100px | |
| Aksi | 40px | Menu baris: Detail, Reboot, Ubah profile, Deauthorize. Semua punya handler nyata. |

Perilaku:
- Header lengket; kolom Serial lengket di bawah 1280px. Virtualisasi aktif di atas 200 baris.
- Sort dan filter server-side; URL menyimpan state filter supaya operator bisa menempelkan link ke tiket.
- Pilih banyak baris lewat checkbox pada hover/fokus; action bar muncul di footer tabel saat ada yang terpilih (bukan toolbar melayang). Aksi massal wajib dialog konfirmasi yang menyebut jumlah dan nama objek.
- Baris terpilih: latar `--bg-sunken` + garis kiri 2px `--amber`. Garis kiri hanya di baris ini, karena ia menandai state nyata.
- Kepadatan: compact 32px (default) dan comfortable 40px, tersimpan per pengguna.
- States: kosong-pertama = "Belum ada ONU. Tambahkan OLT lalu jalankan discovery."; kosong-filter = "Tidak ada ONU yang cocok." + Hapus filter; error = "Gagal memuat ONU (HTTP 502 dari API). Coba lagi."; partial = banner "3 dari 12 OLT gagal dipolling, data mungkin kedaluwarsa" + daftar OLT.
- Di bawah 768px tabel jadi daftar kartu: serial, status, Rx, OLT/PON, nama pelanggan; aksi via drawer; target sentuh 44px.

### C. Detail ONU: `/onus/:serial`

**Pekerjaan layar**: diagnosa satu ONU saat pelanggan sedang di telepon, lalu eksekusi satu perbaikan.

Dua kolom: kiri = identitas dan metrik (lebar tetap 320px), kanan = tab riwayat/konfigurasi. Panel dibuka sebagai drawer dari list di bawah 1440px, sehingga operator tidak kehilangan konteks tabel.

```
OLT / OLT-SBY-01 / PON 1/1/3 / ONU 4857544...3A        [Reboot] [Ubah ▾]
┌─ IDENTITAS ─────────────┬─ [Sinyal] [Riwayat] [Konfigurasi] [Log] ────┐
│ Status  ● Online 14d    │ Rx ONU, 24 jam terakhir                      │
│ Serial  4857544...3A    │  (line chart uPlot, garis ambang -25/-27     │
│ MAC     ...             │   ditandai, hover = nilai + waktu)           │
│ OLT     OLT-SBY-01      │                                              │
│ PON     1/1/3  ONU 12   │ Rx OLT, 24 jam terakhir                      │
│ Profile res-100M        │                                              │
│ VLAN    102             │ Counter 24 jam: CRC err, dropped, reboot     │
│ Pelanggan / ID layanan  │ (tabel 3 baris, angka mono)                  │
├─ SINYAL SEKARANG ───────┤                                              │
│ Rx ONU  ▮▮▮ -21.4 dBm   │                                              │
│ Rx OLT  ▮▮▯ -24.8 dBm   │                                              │
│ Jarak   1.842 m         │                                              │
│ Terukur 14:32:08        │                                              │
└─────────────────────────┴──────────────────────────────────────────────┘
```

Spesifikasi:
- Focal point: blok "Sinyal sekarang" dengan `text-metric` 28px mono. Alasan: angka ini yang diucapkan operator ke pelanggan dan ditulis ke tiket.
- Signal bar selalu berdampingan dengan nilai dBm, tidak pernah menggantikannya; ambang -25/-27 digambar sebagai garis referensi di chart agar operator melihat posisi relatif, bukan hanya warna.
- Aksi perangkat (Reboot, Ubah profile, Deauthorize) di kanan-atas. Semua memakai dialog konfirmasi yang menyebut serial penuh + nama pelanggan, dan menampilkan hasil nyata dari perangkat (sukses, timeout, ditolak) bukan toast optimistis. Alasan: reboot salah ONU memutus pelanggan yang benar.
- Tab Log menampilkan siapa melakukan apa pada ONU ini, karena pertanyaan "ini kenapa berubah" muncul setiap hari.
- States: loading = skeleton panel + "Mengambil status dari OLT-SBY-01 ..."; data lama = banner "Nilai terakhir 14:32, OLT tidak merespons sejak 14:35"; error = sebab + Coba lagi; ONU tidak ditemukan = "Serial ini tidak terdaftar di OLT mana pun" + tombol ke antrian otorisasi.

### D. Form Auth ONU baru: `/onus/pending` lalu `/onus/authorize/:serial`

**Pekerjaan layar**: mengubah ONU yang terdeteksi tapi belum dikonfigurasi menjadi layanan aktif, tanpa salah serial dan tanpa salah profile.

Alur dua langkah, bukan satu form panjang:

1. **Antrian** (`/onus/pending`): tabel ONU unconfigured, kolom: Serial (mono), OLT/PON, Vendor/model, Rx saat discovery, Terdeteksi sejak, tombol `Otorisasi`. Alasan: memilih objek dulu mencegah operator menyalin serial secara manual, sumber kesalahan paling umum.
2. **Form otorisasi**: satu kolom lebar 560px, bukan grid dua kolom. Alasan: form dengan konsekuensi fisik dibaca berurutan, dan satu kolom menghilangkan ambiguitas urutan.

```
Otorisasi ONU
┌──────────────────────────────────────────────────────────┐
│ PERANGKAT  (read-only, dari discovery)                   │
│ Serial 4857544...3A · OLT-SBY-01 · PON 1/1/3 · -22.1 dBm │
├──────────────────────────────────────────────────────────┤
│ Pelanggan                                                │
│ ID layanan        [                      ]  (wajib)      │
│   Format: SRV-00000. Dicek unik saat kehilangan fokus.   │
│ Nama pelanggan    [                      ]  (wajib)      │
│ Catatan alamat    [                      ]  (opsional)   │
├──────────────────────────────────────────────────────────┤
│ Layanan                                                  │
│ Line profile      [pilih ▾]  (wajib, difilter per OLT)   │
│ Service profile   [pilih ▾]  (wajib)                     │
│ VLAN              [    ]  1 s/d 4094                     │
│ Nama ONU di OLT   [auto: SRV-00000-...]  [ubah]          │
├──────────────────────────────────────────────────────────┤
│ Template          [pilih template ▾]  → mengisi 4 field  │
│                   di atas, nilainya tetap bisa diedit    │
├──────────────────────────────────────────────────────────┤
│ Ringkasan perintah yang akan dikirim ke OLT-SBY-01       │
│  (teks mono read-only, bisa disalin)                     │
├──────────────────────────────────────────────────────────┤
│ [Batal]                        [Otorisasi ONU]  (primer) │
└──────────────────────────────────────────────────────────┘
```

Spesifikasi:
- Panel perangkat read-only di paling atas: operator wajib melihat serial yang akan diotorisasi sebelum mengisi apa pun.
- **Ringkasan perintah** sebelum tombol submit adalah keputusan sengaja: operator NOC terbiasa dengan CLI dan ringkasan ini membuat aksi bisa diverifikasi sebelum menyentuh perangkat produksi. Bukan terminal palsu dekoratif, isinya perintah nyata yang akan dieksekusi.
- Validasi: inline saat blur (bukan saat mengetik), ringkasan error di atas tombol submit kalau submit ditolak. Pesan menyebut field dan alasan: "VLAN 5000 di luar rentang 1 s/d 4094".
- Placeholder jujur: `SRV-00000`, `nama pelanggan`. Tanpa `John Doe` atau `johndoe@example.com`.
- Submit: tombol masuk state loading dengan teks "Mengirim ke OLT-SBY-01 ..." dan tidak bisa diklik dua kali. Hasil: sukses = pindah ke Detail ONU dengan banner "ONU diotorisasi, menunggu status online (maks 90 detik)"; gagal = form tetap terisi + pesan mentah dari OLT ditampilkan utuh di blok mono, karena pesan vendor adalah informasi diagnosa.
- Draft form disimpan di local state sampai submit berhasil, supaya refresh atau telepon masuk tidak menghapus isian.
- Keyboard: `Tab` berurutan, `Enter` di field terakhir tidak auto-submit (aksi destruktif butuh klik atau `Ctrl+Enter` eksplisit).

### E. List OLT: `/olts`

**Pekerjaan layar**: melihat kesehatan tiap OLT dan kapasitas PON-nya, lalu masuk ke OLT yang bermasalah.

Komposisi berbeda dari List ONU secara sengaja: 12 s/d 50 baris, bukan ribuan, dan tiap baris punya sub-struktur (PON port). Jadi ini **daftar baris tinggi dengan ekspansi**, bukan grid padat.

```
OLT                                        [+ Tambah OLT]
┌──────────────────────────────────────────────────────────────────────┐
│ ● OLT-SBY-01   10.20.1.11   ZTE C320   fw V2.1.0                     │
│   Uptime 92d · Polling 14:32 (ok) · Suhu 46°C                        │
│   ONU 312 online · 6 offline · 2 menunggu otorisasi                  │
│   PON: ▮▮▮▮▮▮▮▮▯▯▯▯▯▯▯▯  8/16 port terpakai        [▾ Rincian PON]  │
├──────────────────────────────────────────────────────────────────────┤
│ ● OLT-SBY-02   ...                                                   │
│ ● OLT-MLG-01   10.20.3.11  ⚠ Polling gagal sejak 14:05 (timeout)     │
│   Data ONU di bawah ini per 14:05            [Coba hubungkan]        │
└──────────────────────────────────────────────────────────────────────┘
```

Spesifikasi:
- Satu baris = satu OLT, tinggi ~96px, berisi identitas, kesehatan polling, hitungan ONU, dan kapasitas PON. Alasan: operator memutuskan dari kombinasi empat fakta itu; memaksanya ke kolom-kolom sempit akan memotong semuanya.
- Ekspansi "Rincian PON" membuka tabel kecil di dalam baris: port, ONU terpakai/kapasitas, Tx power, status. Alasan: data PON hanya relevan setelah operator memilih OLT.
- OLT bermasalah tetap di posisi aslinya dengan banner kuning di dalam barisnya, tidak dipindah ke atas. Alasan: urutan daftar yang berubah sendiri membuat operator kehilangan tempat; penandaan visual sudah cukup pada jumlah baris sekecil ini.
- Bar kapasitas PON satu warna (`--fiber`) dengan angka di sebelahnya, bukan donut. Alasan: pertanyaannya "masih ada ruang?", dan bar linier menjawab itu lebih cepat.
- Aksi per OLT: Buka detail, Jalankan polling, Jalankan discovery ONU, Edit kredensial. Kredensial SNMP/CLI tidak pernah ditampilkan, hanya diganti.
- States: kosong = "Belum ada OLT terdaftar. Tambahkan OLT untuk mulai menarik data ONU." + tombol Tambah OLT; loading = skeleton 3 baris; error = "Gagal memuat daftar OLT" + Coba lagi.

## 3.5 Trade-off yang perlu diputuskan pemilik produk

### T1 (kontroversial): Light default + dark toggle, bukan dark-only

**Keputusan yang diusulkan**: tema **terang sebagai default**, dengan toggle Sistem/Terang/Gelap yang berfungsi penuh di kedua mode.

**Kontroversinya**: ekspektasi umum untuk "tool NOC" adalah dark-first, dan sebagian operator akan menganggap default terang sebagai kemunduran.

**Alasan tetap memilih terang sebagai default**: layar ini dipakai juga di siang hari di ruang ber-cahaya, di laptop teknisi di lapangan, dan di-screenshot ke tiket serta WhatsApp grup. Teks tipis di latar gelap kehilangan kontras pada kondisi itu, dan screenshot gelap sulit dibaca di thread tiket. Dark dipilih karena kebutuhan nyata (shift malam di ruang gelap), bukan karena "terlihat teknis", jadi ia layak jadi pilihan tersimpan per pengguna, bukan paksaan.

**Alternatif kalau ditolak**: `tema = Sistem` sebagai default, sehingga OS pengguna yang memutuskan. Ini kompromi yang masih menghormati kedua kelompok, dan biayanya nol karena kedua mode memang harus dibangun.

### T2: Compact 32px sebagai default densitas

Default compact (40+ baris per layar) menang atas comfortable, karena waktu pencarian ONU adalah metrik kerja utama. Risikonya: kesalahan klik baris meningkat. Mitigasi: hover baris terang, dialog konfirmasi untuk semua aksi perangkat, dan toggle comfortable tersimpan per pengguna.

### T3: shadow-in shadcn/ui, bukan full custom

Primitif a11y dipakai dari shadcn/ui (copy-in sehingga bisa diedit, tanpa dependency runtime). Risiko: "bau" visual library. Mitigasi: seluruh token Tailwind di-override dari `DESIGN.md`, radius dan shadow default library dibuang, dan tabel/chart justru headless agar bentuk data sepenuhnya milik kita.

## 3.6 Catatan kepatuhan antislop untuk implementasi

Setiap item di bawah ini adalah syarat terima, bukan saran:

- Tanpa gradien biru-ungu, tanpa glow, tanpa latar radial, tanpa background grid/blueprint.
- Tanpa bento grid. Dashboard disusun dari hierarki keputusan, bukan mosaik kartu.
- Tanpa badge "AI Powered" / "Beta" / eyebrow pill di atas judul. Badge hanya untuk status perangkat nyata dan hitungan antrian nyata.
- Tanpa emoji di teks UI.
- Tanpa panah dekoratif di tombol.
- Tanpa titik berkedip abadi. Titik status menandai state nyata; satu-satunya kedipan adalah alarm kritis baru, 2 detik lalu berhenti.
- Tanpa angka, delta, nama pelanggan, serial, atau feed aktivitas karangan. Sebelum backend tersambung: sel kosong atau `[DATA NYATA]`.
- Tanpa glassmorphism. Pemisahan bidang memakai border dan latar.
- Setiap item nav dan setiap kontrol punya perilaku nyata atau label "Segera" yang tidak bisa diklik.
- Setiap tampilan data punya state kosong, loading, dan error yang menyebut **sebab** dan **tindakan berikutnya**.
- Kontras AA diverifikasi di kedua tema sebelum rilis.
- Seluruh alur bisa dijalankan tanpa mouse, dengan fokus yang terlihat.

---

## Bagian 4 — Database & Infrastruktur

# PRD — Bagian Database & Infrastruktur

Lingkup: aplikasi manajemen OLT/ONU (GPON) untuk ISP lokal, dibangun & dirawat 1 developer solo, deploy di server Linux milik sendiri.

Asumsi volume (dipakai di semua keputusan di bawah):

| Entitas | Perkiraan |
|---|---|
| OLT | 10–50 |
| ONU | 500–5.000 per OLT → ~50.000–250.000 baris total |
| Pelanggan/PPPoE | ~jumlah ONU |
| Log aktivitas | 1–5 juta baris/tahun (~10k–15k/hari) |
| Concurrent user | < 20 (tim NOC/CS) |

---

## 1. Pilihan Database

**Keputusan: PostgreSQL 18, self-hosted, satu instance di server aplikasi.**

Alasan:

1. **Enkripsi data sensitif.** Password OLT (SSH/Telnet) dan kredensial PPPoE dienkripsi di level aplikasi (AES-256-GCM, key dari env/file di luar repo), bukan mengandalkan fitur DB. DB hanya menyimpan `bytea` ciphertext. Postgres punya tipe `bytea` dan `pgcrypto` kalau nanti butuh, tapi default-nya enkripsi di app supaya key tidak pernah masuk query log.
2. **JSONB** untuk menyimpan raw output CLI OLT / hasil parsing SNMP yang bentuknya beda-beda per vendor (ZTE, Huawei, Fiberhome). Tanpa ini harus bikin tabel per vendor.
3. **Partial index & partitioning native** — penting untuk tabel log jutaan baris (lihat §3).
4. **Query analitik** (laporan ONU offline per OLT per periode) jauh lebih enak di Postgres: CTE, window function, `FILTER`.
5. Driver matang di semua bahasa, tooling backup (`pg_dump`, `pg_basebackup`) ada di repo distro.

### Yang ditolak dan alasannya

- **MySQL/MariaDB** — layak, tapi JSON support lebih lemah, partitioning lebih kaku, dan `pg_dump` + partial index Postgres menang untuk kasus log. Bukan keputusan salah kalau tim sudah hafal MySQL; di sini developer solo jadi pilih yang paling kuat fiturnya.
- **SQLite** — cukup untuk tahun pertama, tapi polling ratusan OLT secara paralel = banyak writer bersamaan. SQLite single-writer jadi bottleneck. Tolak.
- **MongoDB** — data OLT/ONU/pelanggan sangat relasional (OLT → PON port → ONU → pelanggan). Tolak.
- **Time-series DB (InfluxDB/Timescale) terpisah** untuk metrik — tambah 1 sistem lagi untuk dirawat solo. Tunda sampai benar-benar butuh (lihat §3.4).

### ⚠️ Trade-off kontroversial #1: self-host Postgres di server yang sama dengan aplikasi, BUKAN managed DB dan BUKAN DB server terpisah

Rekomendasi umum industri: pisahkan DB server, atau pakai managed DB (RDS/Cloud SQL). **Di sini sengaja tidak.**

Alasan:
- Managed DB butuh cloud; data pelanggan dan kredensial OLT ada di infrastruktur ISP sendiri, dan budget terbatas. Managed DB termurah ~$30–50/bln untuk spec yang ternyata di bawah server fisik yang sudah dimiliki.
- DB server terpisah = 2x OS patching, 2x monitoring, 2x backup, + latensi jaringan, untuk < 20 concurrent user. Developer solo tidak punya kapasitas merawat 2 host.
- Postgres di localhost via Unix socket = latensi query ~0,1 ms, tidak ada TLS overhead, tidak ada firewall rule DB yang bisa salah konfigurasi.

Harga yang dibayar (diterima sadar):
- **Single point of failure.** Server mati = semua mati. Dimitigasi dengan backup disiplin (§4) + RTO yang disepakati: **restore ke server cadangan ≤ 4 jam, RPO ≤ 15 menit** (WAL archiving).
- Resource contention app vs DB. Dimitigasi dengan `shared_buffers` dibatasi 25% RAM dan `max_connections` dibatasi + connection pool di app.

**Trigger pindah ke DB server terpisah:** salah satu terpenuhi → CPU server > 70% sustained, ukuran DB > 50 GB, atau jumlah OLT > 80.

---

## 2. Strategi Migrasi Schema

**Keputusan: migration file SQL versioned, forward-only, dijalankan otomatis saat deploy.**

Aturan:

1. **Satu arah (forward-only).** Tidak menulis file `down`. Salah migrasi → perbaiki dengan migrasi baru. Alasan: file `down` hampir tidak pernah diuji, dan rollback destruktif di produksi lebih berbahaya daripada restore dari backup.
2. **Format file:** `migrations/0007_add_onu_last_seen.sql`, nomor urut + deskripsi. Tracking di tabel `schema_migrations(version, applied_at, checksum)`.
3. **Tool:** pakai migrator yang satu binary tanpa dependency (`golang-migrate`, `dbmate`, atau Flyway CLI — pilih sesuai bahasa app). Jangan pakai ORM auto-migrate (`sync`/`db:push`) di produksi: perilakunya tidak deterministik dan bisa drop kolom diam-diam.
4. **Migrasi berjalan sebelum service start**, di script deploy. Deploy gagal kalau migrasi gagal.
5. **Perubahan yang merusak dipecah 3 tahap** (expand → migrate → contract):
   - rilis N: tambah kolom baru nullable, app tulis ke kolom lama + baru;
   - rilis N+1: backfill data, app baca dari kolom baru;
   - rilis N+2: drop kolom lama.
   Ini yang membuat deploy tanpa downtime walau solo.
6. **Operasi berat wajib non-blocking:**
   - `CREATE INDEX CONCURRENTLY` (tidak dalam transaksi) untuk tabel > 100k baris.
   - `ALTER TABLE ... ADD COLUMN ... DEFAULT` aman di PG 11+, tapi `ADD CONSTRAINT` pakai `NOT VALID` lalu `VALIDATE CONSTRAINT` terpisah.
   - `lock_timeout = '5s'` + `statement_timeout` diset di sesi migrasi supaya migrasi yang nge-lock mati sendiri, bukan menggantung aplikasi.
7. **Wajib: `pg_dump` otomatis tepat sebelum migrasi dijalankan.** Ini satu-satunya rollback plan yang nyata.
8. Staging = restore dump produksi terbaru + jalankan migrasi. Tidak ada migrasi yang masuk produksi tanpa dicoba di atas data nyata.

---

## 3. Indexing & Desain Tabel untuk Query Besar

### 3.1 Tabel inti (ONU, ratusan ribu baris)

```sql
-- identitas ONU unik per OLT
CREATE UNIQUE INDEX idx_onu_olt_sn      ON onu (olt_id, serial_number);
CREATE INDEX        idx_onu_olt_pon     ON onu (olt_id, pon_port, onu_index);
CREATE INDEX        idx_onu_customer    ON onu (customer_id) WHERE customer_id IS NOT NULL;

-- pencarian "ONU offline di OLT X" — partial index, hanya baris offline yang masuk index
CREATE INDEX idx_onu_offline ON onu (olt_id, last_status_change DESC)
  WHERE status <> 'online';

-- pencarian teks SN/nama pelanggan dari UI (ketik sebagian)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_onu_sn_trgm ON onu USING gin (serial_number gin_trgm_ops);
```

Catatan: `pg_trgm` dipakai supaya `LIKE '%ABCD%'` tetap pakai index. Tanpa ini pencarian SN jadi seq scan di 250k baris.

### 3.2 Tabel log aktivitas (jutaan baris) — **wajib partisi**

```sql
CREATE TABLE activity_log (
  id          bigserial,
  occurred_at timestamptz NOT NULL,
  olt_id      int,
  onu_id      bigint,
  actor_id    int,
  action      text NOT NULL,
  detail      jsonb,
  PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at);
```

- **Partisi bulanan.** 1 partisi ≈ 300k–450k baris → index kecil, query per periode cuma menyentuh 1–2 partisi.
- Partisi bulan berikutnya dibuat otomatis oleh cron (`pg_partman` opsional; cron + SQL sederhana sudah cukup dan lebih sedikit dependency).
- **Retensi: partisi > 13 bulan di-`DETACH` + dump ke file `.sql.gz` arsip, lalu `DROP`.** `DROP PARTITION` instan; `DELETE FROM ... WHERE occurred_at < ...` di tabel 5 juta baris akan membuat bloat parah dan autovacuum kewalahan. Ini alasan utama partisi dipilih.

Index per partisi (otomatis turun dari parent):
```sql
CREATE INDEX ON activity_log (olt_id, occurred_at DESC);
CREATE INDEX ON activity_log (onu_id, occurred_at DESC) WHERE onu_id IS NOT NULL;
CREATE INDEX ON activity_log (actor_id, occurred_at DESC);
CREATE INDEX ON activity_log USING gin (detail jsonb_path_ops);
```

### 3.3 Aturan umum indexing

- **Semua query list wajib keyset pagination**, bukan `OFFSET`. `OFFSET 50000` memaksa Postgres membaca 50.000 baris terbuang.
  ```sql
  WHERE (occurred_at, id) < ($1, $2) ORDER BY occurred_at DESC, id DESC LIMIT 50;
  ```
- Kolom `ORDER BY` harus ikut masuk index, dengan arah yang sama.
- Jangan bikin index "untuk jaga-jaga" — setiap index memperlambat INSERT log. Tambah index hanya setelah `EXPLAIN (ANALYZE, BUFFERS)` menunjukkan seq scan nyata.
- Cek bulanan: `pg_stat_user_indexes` → index dengan `idx_scan = 0` selama 2 bulan dihapus.
- Aktifkan `pg_stat_statements` sejak hari pertama. Ini sumber kebenaran query lambat, bukan tebakan.
- `log_min_duration_statement = 500ms` → query lambat masuk log Postgres.

### 3.4 Metrik polling (traffic/optical power per ONU)

Data ini tumbuh paling cepat kalau disimpan mentah (5 menit × 250k ONU = 72 juta baris/hari — **tidak layak**).

Keputusan: **jangan simpan sampel mentah.** Simpan:
- status + nilai terakhir di tabel `onu` (di-overwrite),
- agregat per jam (min/avg/max) di tabel terpisah yang juga dipartisi bulanan, retensi 6 bulan.

Kalau nanti ISP butuh grafik resolusi tinggi → baru evaluasi TimescaleDB (extension, bukan server baru) atau VictoriaMetrics. Bukan sekarang.

---

## 4. Backup & Restore

### ⚠️ Trade-off kontroversial #2: cron + `pg_dump` + WAL archiving ke storage lokal & offsite, BUKAN Barman/pgBackRest, dan BUKAN replika standby

Rekomendasi "benar" untuk produksi: pgBackRest + streaming replica. **Ditolak untuk fase awal** karena menambah komponen yang harus dipahami, dipatch, dan di-debug jam 2 pagi oleh satu orang. Backup yang dimengerti pemiliknya lebih bernilai daripada backup canggih yang tidak pernah diuji.

Yang dipakai:

**Lapis 1 — dump logis harian**
```
0 2 * * *  pg_dump -Fc -Z6 nexfiber_db > /var/backups/pg/olt_$(date +\%F).dump
```
- Format custom (`-Fc`) → bisa restore selektif per tabel.
- Retensi lokal 7 hari.

**Lapis 2 — WAL archiving (RPO ≤ 15 menit)**
- `archive_mode = on`, `archive_command` menyalin WAL ke `/var/backups/wal/` + rsync ke offsite.
- `archive_timeout = 900` → walau sepi, WAL tetap ter-archive tiap 15 menit.
- `pg_basebackup` mingguan sebagai base untuk PITR.

**Lapis 3 — offsite (wajib, bukan opsional)**
- `restic` atau `rclone` ke storage terpisah secara fisik (NAS kantor lain / object storage murah / VPS kecil).
- Terenkripsi (restic default). Backup berisi ciphertext kredensial OLT; **encryption key aplikasi TIDAK ikut di backup DB** — disimpan terpisah (password manager + amplop tertutup di brankas). Backup DB yang bocor tanpa key = tidak berguna bagi penyerang.
- Jadwal: harian, retensi 30 harian + 6 bulanan.

**Aturan yang tidak bisa ditawar:**
- **Restore drill tiap bulan**, terjadwal di kalender: ambil dump terbaru, restore ke DB `nexfiber_db_restoretest`, jalankan query sanity (`COUNT(*)` per tabel inti + cek dekripsi 1 kredensial). Backup yang belum pernah di-restore belum tentu backup.
- Cron backup wajib lapor sukses/gagal. Pakai dead-man's switch (healthchecks.io gratis / cron-monitor sendiri): **alert saat ping TIDAK datang**, bukan saat error. Cron yang mati diam-diam adalah mode kegagalan paling umum.
- Backup konfigurasi juga, bukan cuma DB: `/etc/postgresql`, config Nginx/Caddy, unit systemd, file `.env` (terenkripsi terpisah).

**Target yang disepakati:** RPO ≤ 15 menit, RTO ≤ 4 jam.

**Trigger upgrade ke pgBackRest + standby replica:** downtime 4 jam mulai tidak dapat diterima bisnis, atau ukuran DB > 50 GB (dump logis jadi terlalu lambat).

---

## 5. Kebutuhan Infrastruktur Server

### 5.1 Spesifikasi

| Komponen | Minimum | Rekomendasi |
|---|---|---|
| CPU | 4 vCPU | 8 vCPU |
| RAM | 8 GB | 16 GB |
| Disk | 100 GB **SSD/NVMe** | 250 GB NVMe |
| Network | 1 Gbps, IP statis, akses ke management VLAN OLT | sama + jalur redundan |

Catatan:
- **SSD wajib, bukan HDD.** Workload-nya random I/O (index lookup + WAL fsync); HDD akan terasa lambat sejak tahun pertama.
- RAM 8 GB = `shared_buffers` 2 GB, sisanya page cache + aplikasi + worker polling. Di bawah itu, query log mulai sering baca disk.
- Disk: DB ~20–30 GB di tahun pertama; sisanya untuk backup lokal 7 hari + WAL. **Pisahkan mount point `/var/backups`** supaya backup penuh tidak membuat DB berhenti menulis.
- Server cadangan (dingin): boleh VPS kecil yang hanya dinyalakan saat disaster, asal OS & versi Postgres identik. Ini yang membuat RTO 4 jam realistis.

### 5.2 OS

**Debian 12 (Bookworm)** atau **Ubuntu Server 24.04 LTS**. Pilih satu, jangan campur.

- Alasan: LTS panjang, paket Postgres resmi (PGDG repo), dokumentasi melimpah — penting untuk developer solo yang googling jam 2 pagi.
- Pakai **PGDG repo**, bukan Postgres bawaan distro, supaya versi minor update tetap jalan tanpa upgrade OS.
- `unattended-upgrades` aktif untuk security patch saja. Upgrade mayor Postgres selalu manual & terjadwal.
- Firewall `ufw`: hanya 80/443 publik; SSH dibatasi IP kantor/VPN. **Port 5432 tidak pernah terbuka ke publik** (DB diakses via Unix socket).
- SSH: key-only, `PasswordAuthentication no`, root login dimatikan, `fail2ban` aktif.

### 5.3 Reverse Proxy & SSL

**Keputusan: Caddy 2.**

- Alasan: HTTPS + perpanjangan sertifikat Let's Encrypt otomatis tanpa konfigurasi tambahan, HTTP/2 & HTTP/3 default, Caddyfile ~10 baris. Nginx + certbot butuh 3 komponen (nginx, certbot, cron renew) dan renew yang gagal diam-diam adalah penyebab umum outage. Untuk solo maintainer, Caddy menghapus satu kelas kegagalan.
- Kalau tim sudah sangat hafal Nginx, Nginx + certbot tetap sah — tapi renew-nya **wajib dimonitor**, bukan diasumsikan jalan.

Konfigurasi wajib:
- Redirect HTTP → HTTPS, HSTS aktif.
- Security header: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, CSP.
- Rate limit di endpoint login.
- Akses panel admin dibatasi IP kantor/VPN kalau memungkinkan.
- Aplikasi bind ke `127.0.0.1` saja — hanya proxy yang boleh menjangkaunya.

### 5.4 Proses & Deploy

- Aplikasi jalan sebagai **systemd service** (user non-root khusus, `Restart=always`), bukan `screen`/`nohup`.
- Worker polling OLT = service systemd terpisah, supaya restart UI tidak memutus polling.
- Secret di `/etc/olt-app/env`, mode `0600`, owner service user. Tidak pernah masuk git.
- Deploy: script `update.sh` → pull/upload artefak → `pg_dump` → migrasi → `systemctl restart`. Sederhana, bisa dibaca, bisa dijalankan dari SSH. Instalasi awal server baru lewat `install.sh` terpisah; bongkar server lewat `uninstall.sh` (lihat Bagian 5 §X.1).
- **Docker opsional, tidak diwajibkan.** Untuk satu server dan satu developer, systemd + paket distro lebih sedikit lapisan yang bisa rusak. Kalau sudah nyaman Docker Compose, silakan — tapi jangan Kubernetes.

### 5.5 Monitoring Server (monitoring server-nya sendiri, bukan monitoring OLT)

Dua lapis, sengaja dipisah:

**Lapis A — eksternal (wajib, di luar server ini)**
- Uptime check dari luar ke URL `/healthz` tiap 1–5 menit (Uptime Kuma di VPS lain, atau layanan gratis).
- Dead-man's switch untuk cron backup (§4).
- Alasan: kalau server mati total, monitoring yang jalan di server itu ikut mati dan tidak bisa memberi tahu siapa pun. Lapis ini tidak boleh berada di host yang sama.

**Lapis B — lokal (di server)**
- `node_exporter` + `postgres_exporter` + Prometheus + Grafana, **atau** Netdata (satu paket, lebih ringan untuk dipasang solo). Pilih Netdata kalau belum pernah pegang Prometheus.
- Metrik minimum yang dipantau:
  - disk usage per mount (**alert di 75%** — disk penuh adalah penyebab outage DB nomor satu),
  - CPU load, RAM, swap,
  - Postgres: koneksi aktif vs `max_connections`, cache hit ratio, query > 1 detik, replication/WAL lag, ukuran DB, transaksi idle-in-transaction,
  - umur backup terakhir (alert kalau > 26 jam),
  - sisa masa berlaku sertifikat SSL (walau Caddy auto-renew — tetap verifikasi).
- Log terpusat: `journald` dengan `SystemMaxUse=2G`. Loki/ELK **tidak dipakai** di fase ini — satu server, `journalctl` sudah cukup dan tidak menambah RAM terpakai.

**Alerting:** Telegram bot atau email ke 1 tujuan. Jangan lebih dari 2 kanal. Alert yang terlalu banyak akan diabaikan, dan alert yang diabaikan sama dengan tidak ada alert.

---

## 6. Ringkasan Keputusan

| Area | Keputusan | Trigger evaluasi ulang |
|---|---|---|
| DB | PostgreSQL 18 self-host, 1 server bareng app | CPU > 70% sustained / DB > 50 GB / OLT > 80 |
| Migrasi | SQL versioned, forward-only, auto saat deploy | — |
| Log aktivitas | Tabel partisi bulanan, retensi 13 bulan | volume > 10 juta baris/tahun |
| Metrik | Agregat per jam, bukan sampel mentah | butuh grafik resolusi tinggi → TimescaleDB |
| Backup | cron `pg_dump` + WAL archiving + restic offsite | RTO 4 jam tak lagi diterima → pgBackRest + standby |
| OS | Debian 12 / Ubuntu 24.04 LTS | — |
| Proxy/SSL | Caddy 2, TLS otomatis | — |
| Monitoring | Netdata lokal + uptime check eksternal | > 3 server → Prometheus terpusat |

**Dua trade-off kontroversial yang diambil sadar:** (1) satu server untuk app + DB tanpa managed DB, (2) backup cron buatan sendiri tanpa pgBackRest/replika. Keduanya menukar ketahanan teoretis dengan sesuatu yang benar-benar dirawat oleh satu orang — dan masing-masing punya trigger eksplisit kapan harus ditinggalkan.

---

## Bagian 5 — DevOps & QA

# Bagian X — DevOps, Testing & Operasional

Konteks: aplikasi manajemen OLT/ONU, dikembangkan dan di-maintain **1 orang** via VS Code.
Aplikasi mengirim command SSH/Telnet ke OLT produksi ISP. Command salah = pelanggan putus.
Semua keputusan di bawah dioptimalkan untuk **satu orang yang juga jadi on-call**.

---

## X.1 Strategi Deployment — `install.sh` / `update.sh` / `uninstall.sh`

### Prinsip
3 skrip bash di root repo, masing-masing 1 tanggung jawab, dipanggil manual via SSH (bukan CI/CD
otomatis — lihat Trade-off #1). Tidak ada drag-drop FTP/SFTP manual. **Source of truth = git**;
server hanya `git pull`/`git checkout` dari tag, edit file langsung di server dilarang.

### Alur
```
VS Code (laptop)
  └─ git commit + push → origin (GitHub/Gitea private)
        └─ di server, sekali seumur hidup server : bash install.sh
        └─ di server, setiap rilis baru          : bash update.sh
        └─ di server, kalau mau bongkar total     : bash uninstall.sh
```

### `install.sh` — instal kebutuhan dari nol (idempoten, server kosong → siap pakai)
Dipanggil **manual oleh Erlangga**, sekali di server baru. Tugasnya memasang SEMUA kebutuhan via
bash, tanpa langkah manual lain sesudahnya:

1. **Deteksi OS** (`/etc/os-release`) — target Debian 12/Ubuntu 24.04. Keluar dengan pesan jelas
   bila OS tidak didukung (bukan asumsi diam-diam).
2. **Paket sistem** via `apt-get install -y`: `postgresql-18`, `python3.12`, `python3.12-venv`,
   `nodejs` (via NodeSource, untuk build frontend), `caddy`, `git`, `snmp` (untuk `snmpbulkwalk`
   CLI dipakai saat debug manual).
3. **User & direktori**: buat user sistem `nexfiber` (no-login, no-shell) bila belum ada; buat
   `/opt/nexfiber` (kode, milik `nexfiber:nexfiber`), `/etc/nexfiber` (config, `750`), `/var/backups/nexfiber`,
   `/var/log/nexfiber`.
4. **Database**: `sudo -u postgres createuser`/`createdb` idempoten (`IF NOT EXISTS` via cek
   `psql -tc` dulu, bukan asumsi gagal = sudah ada); simpan password yang digenerate random ke
   `/etc/nexfiber/config.ini` (dibuat `640`, owner `nexfiber:nexfiber`) — **tidak pernah** dicetak ke terminal
   atau masuk git.
5. **Python venv** di `/opt/nexfiber/venv`, `pip install -r requirements.txt`.
6. **Frontend build**: `npm ci && npm run build` → hasil statis disajikan Caddy.
7. **Migrasi awal**: `alembic upgrade head` di atas DB yang baru dibuat.
8. **systemd units**: tulis `nexfiber-api.service` dan `nexfiber-worker.service` ke
   `/etc/systemd/system/`, `daemon-reload`, `enable --now` keduanya.
9. **Caddy**: tulis `Caddyfile` minimal (reverse-proxy ke `nexfiber-api`, serve `dist/` statis,
   HTTPS otomatis via domain yang ditanyakan di langkah 10), `systemctl reload caddy`.
10. **Satu pertanyaan interaktif wajib**: domain/hostname untuk HTTPS (Caddy butuh ini untuk
    minta sertifikat). Semua langkah lain tanpa prompt — sesuai pola `install.sh` yang sudah
    dipakai di proyek lain milik Erlangga (manual, tapi 1 jalan tanpa berhenti-henti).
11. **Health check** penutup: curl `/healthz` lokal, cetak ✅/❌ eksplisit + ringkasan port/URL.
    Keluar non-zero kalau gagal, supaya operator tahu instalasi belum benar-benar jalan.
12. **Idempotensi**: jalan ulang `install.sh` di server yang sudah terinstal tidak merusak apa pun
    — tiap langkah cek status dulu (`systemctl is-active`, `psql` existence check, dst) sebelum
    bertindak, bukan `apt-get install` buta yang bisa downgrade/restart service tanpa perlu.

### `update.sh` — rilis versi baru (dipanggil tiap deploy, bukan sekali)
Setara `deploy.sh` di draft sebelumnya, namanya diseragamkan ke konvensi `update.sh` yang sudah
dipakai proyek lain:
1. `git fetch && git checkout <tag>`
2. Snapshot DB: `pg_dump -Fc` ke `/var/backups/nexfiber/<timestamp>.dump` (sebelum migrasi — jaring
   pengaman utama untuk rollback)
3. `alembic upgrade head` — forward-only, idempoten by design
4. `pip install -r requirements.txt` (venv yang sudah ada dari `install.sh`) + `npm ci && npm run build`
5. Fix permission (`chown nexfiber:nexfiber`, `750` dir / `640` file) — ponytail terhadap drift permission
6. `systemctl restart nexfiber-api nexfiber-worker` + health check `/healthz`; keluar non-zero bila gagal
7. **Rollback**: `bash update.sh --rollback <tag_sebelumnya>` → `git checkout` tag lama + restore
   dump kalau migrasi terakhir destruktif. Tag git wajib dibuat tiap rilis (`v2026.10.23-1`).
8. **Tidak menyentuh** hal-hal milik `install.sh` (paket OS, systemd unit file, Caddyfile) kecuali
   memang berubah — `update.sh` mengasumsikan `install.sh` sudah pernah jalan sukses.

### `uninstall.sh` — bongkar bersih (dipanggil manual, sekali, dengan konfirmasi)
Kebalikan `install.sh`, untuk pindah server / abandon total:
1. **Konfirmasi interaktif wajib** (`ketik UNINSTALL untuk lanjut`) — ini destruktif dan tidak
   bisa dibatalkan setengah jalan tanpa risiko state rusak.
2. **Backup wajib sebelum hapus apa pun**: `pg_dump -Fc` ke `/root/nexfiber-final-backup-<timestamp>.dump`,
   dicetak path-nya ke terminal supaya operator tahu ke mana harus menyalin sebelum benar-benar pergi.
3. `systemctl disable --now nexfiber-api nexfiber-worker`, hapus unit file dari `/etc/systemd/system/`,
   `daemon-reload`.
4. Hapus `Caddyfile` entry terkait app, `systemctl reload caddy` (Caddy sendiri **tidak** dihapus
   — bisa dipakai app lain).
5. **Opsional lewat flag** `--drop-db` (default: DB **tidak** dihapus) — menghapus data pelanggan
   secara default adalah kesalahan paling mahal yang bisa dibuat skrip ini; harus sengaja, bukan
   kebetulan ikut-rebuild.
6. Hapus `/opt/nexfiber` (kode+venv), `/etc/nexfiber` (config+secret), biarkan `/var/backups/nexfiber` dan
   `/var/log/nexfiber` tetap ada (bukti forensik/backup jangan ikut lenyap).
7. Cetak ringkasan akhir: apa yang dihapus, apa yang disengaja dipertahankan dan di path mana.

### Checklist pra-`update.sh` (wajib, 5 baris, tempel sebagai konfirmasi interaktif sebelum eksekusi)
- [ ] Migrasi DB sudah ditulis dan idempoten?
- [ ] Ada perubahan command OLT? Sudah diuji ke lab/1 OLT non-kritis?
- [ ] Backup DB otomatis jalan?
- [ ] Tag git dibuat?
- [ ] Rollback step diketahui?

---

## X.2 CI/CD Realistis untuk Solo Developer

### Yang dipakai
Satu workflow GitHub Actions / Gitea Actions, jalan di setiap push:

| Step | Isi | Durasi target |
|---|---|---|
| Lint | `ruff check` + `ruff format --check` (Python) / `eslint` (frontend) | < 20 dtk |
| Unit test | pytest: parser CLI + builder command OLT | < 60 dtk |
| Secret scan | `gitleaks detect` | < 20 dtk |
| Build artefak | `npm run build` (frontend) | < 60 dtk |

Total < 3 menit. Lebih lama dari itu, solo dev akan mulai push dengan `--no-verify` dan CI
jadi dekorasi.

### Yang TIDAK dipakai
- **Tidak ada auto-deploy ke produksi dari CI.** CI berhenti di "hijau". Deploy tetap manual:
  satu perintah SSH yang dipicu manusia yang sadar sedang menyentuh perangkat ISP.
- Tidak ada approval gate / reviewer wajib (tidak ada reviewer kedua).
- Tidak ada matrix build lintas versi PHP/OS. Target produksi satu versi, uji versi itu saja.

### Git hook lokal (pengganti CI cepat)
`.git/hooks/pre-commit`: `ruff check` pada file berubah + `pytest tests/unit` parser. Feedback instan di
VS Code, tanpa menunggu runner.

### ⚠️ Trade-off kontroversial #1 — CD penuh ditolak, deploy tetap manual
Praktik umum menuntut continuous deployment: merge ke `main` → otomatis live. **Kami menolaknya
untuk aplikasi ini.** Alasannya bukan kemalasan, tapi blast radius: bug di web app biasa
menampilkan halaman error; bug di sini mengirim `ont delete` ke OLT dan memutus ratusan
pelanggan. CD mengubah "salah ketik jam 23.00" menjadi "outage jam 23.00" tanpa manusia di
antaranya. Harga yang dibayar nyata: deploy jadi lebih jarang, batch perubahan lebih besar,
dan ada risiko developer lupa deploy. Mitigasinya: `update.sh` dibuat semudah satu perintah,
sehingga hambatan deploy adalah *keputusan*, bukan *usaha*.
Kapan ditinjau ulang: kalau modul yang disentuh murni read-only (dashboard/laporan), modul itu
boleh dipisah path/service tersendiri dan di-CD-kan terpisah.

---

## X.3 Strategi Testing — WAJIB vs OPSIONAL

Prinsip: **uji yang membentuk string command dan yang membaca output perangkat.** Sisanya
diuji oleh mata, karena waktu 1 orang terbatas.

### WAJIB (tanpa ini, jangan merge)

| # | Area | Jenis | Alasan |
|---|---|---|---|
| 1 | **Parser output CLI OLT** (`show gpon onu state`, `show ont info`, dll) | Unit, pakai fixture teks asli dari OLT | Vendor mengubah spasi/kolom antar firmware. Parser rusak = data ONU salah tampil = teknisi ambil keputusan salah. Fixture = file `.txt` hasil copy-paste terminal nyata, satu per vendor/firmware. |
| 2 | **Command builder** (fungsi yang merakit string command sebelum dikirim) | Unit, assert string **persis** | Ini batas tempat kerusakan fisik terjadi. Test membandingkan string output dengan string yang sudah diverifikasi live. Tiap bug command yang pernah terjadi wajib jadi 1 test case baru. |
| 3 | **Guard command destruktif** | Unit | `delete`/`reset`/`no ont` wajib lewat fungsi konfirmasi + whitelist OLT. Test memastikan command destruktif tanpa flag konfirmasi **dilempar exception**, bukan dikirim. |
| 4 | **Validasi input di trust boundary** | Unit | PON port, ONU ID, VLAN, serial number: tolak format tak valid sebelum masuk string command. Cegah injection ke sesi SSH. |
| 5 | **Driver multi-vendor: dispatch ke driver yang benar** | Unit | Kirim sintaks ZTE ke OLT CDATA = command gagal atau, lebih buruk, berarti lain. |
| 6 | **Migrasi DB jalan di atas schema lama** | Integration, satu skrip | Schema drift adalah penyebab 500 paling umum setelah deploy. Jalankan `schema.sql` → migrasi, dan DB-lama → migrasi, bandingkan struktur kolom. |

Target: tes nomor 1–5 adalah **murni fungsi, tanpa jaringan**. Jalan dalam hitungan detik.

### OPSIONAL (kerjakan kalau sempat / saat sudah pernah ada bug di situ)
- Test integrasi SSH ke OLT lab (butuh perangkat; jalankan manual, bukan di CI).
- Test UI/E2E browser.
- Test laporan dan dashboard read-only.
- Coverage CRUD pelanggan/paket.
- Load test.

### ⚠️ Trade-off kontroversial #2 — coverage global ditolak
**Kami tidak menetapkan target coverage persen apa pun** (bukan 80%, bukan 60%). Target
coverage mendorong solo dev menulis test murah untuk getter, controller, dan CRUD — menaikkan
angka tanpa menurunkan risiko — sementara parser multi-firmware yang mahal diuji tetap tipis.
Gantinya: **daftar modul kritis di atas harus 100% jalur-utamanya diuji; modul di luar daftar
boleh 0%.** Konsekuensi yang diterima: bug "receh" di CRUD akan lolos ke produksi dan ditemukan
pengguna. Itu dianggap murah dibanding satu command salah ke OLT.

### Aturan kejujuran test
- Satu bug produksi = satu regression test, ditulis **sebelum** fix.
- Fixture parser berasal dari output perangkat nyata, tidak boleh ditulis dari ingatan.
- Assertion negatif ("command ditolak") hanya sah bila ada assertion positif di test yang sama
  membuktikan jalur normal masih lewat — kalau tidak, exception salah pun lolos.

---

## X.4 Environment (dev / staging / prod)

| Env | Lokasi | Database | OLT | Dipakai untuk |
|---|---|---|---|---|
| **dev** | Laptop, VS Code | PostgreSQL lokal, data dummy | **OLT simulator**: mock SSH yang membalas fixture teks | Coding harian, jalankan unit test |
| **staging** | VPS kecil / LXC di server yang sama | Dump prod yang sudah di-anonimkan (`pg_dump` + restore) | 1 OLT lab **atau** OLT produksi paling sepi, mode read-only | Smoke test sebelum deploy, uji migrasi |
| **prod** | Server ISP | Produksi | Semua OLT | Live |

Catatan penting:
- **Mock OLT wajib ada dan murah**: satu skrip kecil yang menerima command dan mengembalikan
  file fixture. Ini yang membuat dev bisa jalan tanpa perangkat dan membuat test nomor 1–2 mungkin.
- **Flag read-only per environment.** Config punya `ALLOW_WRITE_COMMANDS=false` di staging.
  Aplikasi menolak mengirim command tulis saat flag mati — pertahanan terakhir jika seseorang
  salah menunjuk staging ke OLT produksi.
- **Staging DB wajib dari dump prod** (dianonimkan), karena bug migrasi hanya muncul pada data nyata.

### ⚠️ Trade-off kontroversial #3 — staging TANPA OLT fisik khusus
Praktik ideal: staging punya OLT sendiri. Untuk solo dev, OLT lab berharga puluhan juta dan
sering tidak terpakai. **Keputusan: staging boleh menumpang OLT produksi dalam mode read-only,**
dikunci oleh whitelist IP OLT + flag `ALLOW_WRITE_COMMANDS=false` + user SSH read-only di sisi
OLT (dua lapis, jangan satu). Risiko yang diterima: perubahan jalur tulis tidak pernah diuji
end-to-end sebelum prod — kompensasinya adalah test command-builder yang ketat (X.3 #2, #3)
plus deploy bertahap ke 1 OLT dulu. Kalau anggaran membaik, OLT bekas satu unit adalah
pembelian pertama yang direkomendasikan.

---

## X.5 Monitoring & Error Tracking Pasca-Live

### Lapis 1 — Error aplikasi
- Error tracker self-hosted (mis. GlitchTip/Sentry-compatible) atau, minimal, handler global yang
  menulis JSON ke `/var/log/nexfiber/error.log` + kirim ke Telegram bot.
- Setiap error wajib membawa konteks: `olt_id`, `command`, `user`, `request_id`.
- **Telegram sebagai kanal alert utama** — solo dev memegang HP, bukan dashboard.

### Lapis 2 — Audit trail command OLT (non-negotiable)
Tabel `olt_command_log`: `waktu, user, olt, command, response, durasi, status`.
Setiap command tulis dicatat **sebelum dikirim**, hasil di-update setelahnya.
Ini sumber kebenaran saat pelanggan komplain "internet saya mati sejak jam 3".
Retensi minimal 90 hari.

### Lapis 3 — Kesehatan sistem
- Uptime check eksternal (Uptime Kuma) ke URL login tiap 60 detik.
- Cek reachability tiap OLT (ping/SSH handshake) tiap 5 menit → alert bila OLT tidak terjangkau
  aplikasi (sering jadi gejala awal masalah jaringan, bukan masalah app).
- Cek cron sinkronisasi ONU: alert bila **tidak** jalan dalam N menit (dead-man switch), karena
  cron yang mati diam-diam lebih berbahaya daripada cron yang error keras.
- Disk + ukuran tabel log (log command tumbuh cepat).

### Aturan alert (anti alert-fatigue)
Hanya 3 hal yang boleh membangunkan tengah malam:
1. Aplikasi down.
2. Command OLT gagal beruntun > 3 kali.
3. Cron sinkronisasi mati.
Sisanya masuk digest harian. Alert yang terlalu berisik akan dimatikan oleh satu-satunya
orang yang mendengarnya — dan setelah itu tidak ada yang mendengar apa pun.

### Backup
- `pg_dump -Fc` harian + sebelum tiap deploy, simpan 14 hari, salin ke lokasi off-server (lihat juga §4 bagian Database/Infra: WAL archiving + restic offsite untuk RPO 15 menit).
- **Uji restore 1x per kuartal.** Backup yang belum pernah di-restore belum terbukti ada.

---

## X.6 Ringkasan Keputusan

| Keputusan | Pilihan | Alasan singkat |
|---|---|---|
| Deploy | Manual 1 perintah via `update.sh` (instal awal: `install.sh`, bongkar: `uninstall.sh`), dipicu manusia | Blast radius menyentuh perangkat fisik |
| CI | Lint + unit test + secret scan, < 3 menit | Harus cukup cepat agar tidak dilewati |
| CD otomatis | **Tidak** | Lihat trade-off #1 |
| Target coverage | **Tidak ada**; daftar modul kritis wajib 100% jalur utama | Lihat trade-off #2 |
| Staging | Ada, tanpa OLT fisik khusus, read-only ke OLT prod | Lihat trade-off #3 |
| Monitoring | Telegram alert + audit log command + Uptime Kuma + dead-man switch cron | Satu orang, satu HP |


---


## Lampiran A — Isi Lengkap `install.sh` / `update.sh` / `uninstall.sh`

Ini bukan sekadar deskripsi (§X.1 di atas): isi bash sesungguhnya dilampirkan di sini sebagai
bagian dari dokumen PRD, supaya install/update/uninstall adalah *keputusan produk yang
tertulis*, bukan cuma file terpisah yang bisa diam-diam berubah tanpa jejak di PRD. Versi
hidup/terbaru tetap file `.sh` di root repo — lampiran ini adalah snapshot yang disinkronkan
tiap kali salah satu skrip berubah signifikan.

### A.1 — `install.sh` (instalasi server dari nol)

```bash
#!/bin/bash
# Nexfiber — instalasi server lengkap (konsep & gaya sama dengan install.sh NetBackup)
#
# Usage (dari folder source project, hasil git clone):
#   chmod +x install.sh
#   sudo bash install.sh
#
# Script akan:
#   - Install paket sistem (Python 3.12, PostgreSQL 18, Node.js, Caddy, …)
#   - Buat user sistem, direktori app, venv, build frontend
#   - Buat database + user + migrasi awal (Alembic)
#   - systemd unit (API + worker) + Caddy reverse-proxy & HTTPS
#   - Verifikasi web (health check) dan ringkasan kredensial di akhir

set -e

# =========================================================
# COLOR & PATH
# =========================================================

RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
CYAN='\033[1;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f "$SCRIPT_DIR/VERSION" ]; then
    APP_VERSION="$(tr -d '\r\n' < "$SCRIPT_DIR/VERSION" | head -n1)"
else
    APP_VERSION="1.0.0"
fi

APP_SYSTEM_USER="nexfiber"
LOG_FILE="/var/log/nexfiber_install.log"

# =========================================================
# HELPERS
# =========================================================

error_exit() {
    echo ""
    echo -e "${RED}==================================================${NC}"
    echo -e "${RED} ❌ INSTALLASI GAGAL${NC}"
    echo -e "${RED}==================================================${NC}"
    echo ""
    if [ -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}Detail error (20 baris terakhir):${NC}"
        tail -20 "$LOG_FILE"
        echo ""
        echo -e "${YELLOW}Full log:${NC} $LOG_FILE"
    fi
    echo ""
    exit 1
}

trap error_exit ERR

log() {
    echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $1"
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

success() { echo -e "${GREEN}✔ $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠ $1${NC}"; }

slugify() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9.-]//g'
}

psql_root() {
    sudo -u postgres psql -v ON_ERROR_STOP=1 -tAc "$1" 2>>"$LOG_FILE"
}

db_role_exists() {
    [ "$(psql_root "SELECT 1 FROM pg_roles WHERE rolname='$1'")" = "1" ]
}

db_exists() {
    [ "$(psql_root "SELECT 1 FROM pg_database WHERE datname='$1'")" = "1" ]
}

# =========================================================
# ROOT CHECK & BANNER
# =========================================================

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Installer harus dijalankan dengan root/sudo.${NC}"
    echo -e "Contoh: ${GREEN}sudo bash install.sh${NC}"
    exit 1
fi

if [ ! -f "$SCRIPT_DIR/backend/requirements.txt" ] || [ ! -f "$SCRIPT_DIR/frontend/package.json" ]; then
    echo -e "${RED}Jalankan script dari root folder project (ada backend/requirements.txt dan frontend/package.json).${NC}"
    exit 1
fi

clear
echo -e "${BLUE}"
cat << 'EOF'

  ___  _   _____     _
 / _ \| | |_   _|   / \   ___  _ __
| | | | |   | |    / _ \ / _ \| '_ \
| |_| | |___| |   / ___ \ |_) | |_) |
 \___/|_____|_|  /_/   \_\__/| .__/
    OLT/ONU Management       |_|

EOF
echo -e "${NC}"
echo -e "${GREEN}Nexfiber Server Installer${NC}"
echo -e "${YELLOW}Debian 12 / Ubuntu 24.04 — Python 3.12 + FastAPI + PostgreSQL 18${NC}"
echo -e "${CYAN}Versi: v${APP_VERSION}${NC}"
echo -e "${CYAN}Source: ${SCRIPT_DIR}${NC}"
echo ""

# =========================================================
# [1] OS CHECK
# =========================================================

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE} [1/10] Deteksi Sistem Operasi${NC}"
echo -e "${BLUE}==================================================${NC}"

. /etc/os-release
case "${ID}-${VERSION_ID}" in
    debian-12*|debian-13*|ubuntu-24.*)
        success "OS didukung: ${PRETTY_NAME}"
        ;;
    *)
        echo -e "${RED}OS tidak didukung: ${PRETTY_NAME:-unknown}. Target: Debian 12/13 atau Ubuntu 24.04.${NC}"
        exit 1
        ;;
esac
echo ""

# =========================================================
# [2] KONFIGURASI DOMAIN / HTTPS
# =========================================================

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE} [2/10] Konfigurasi Domain & HTTPS${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "${YELLOW}Caddy mengurus HTTPS otomatis via Let's Encrypt begitu domain mengarah ke server ini.${NC}"
echo -e "${YELLOW}Isi IP server (tanpa domain) jika belum punya domain — Caddy akan jalan HTTP saja.${NC}"
echo ""

DEFAULT_DOMAIN="nexfiber.local"
read -rp "Domain / hostname [${DEFAULT_DOMAIN}]: " SERVER_NAME
SERVER_NAME=${SERVER_NAME:-$DEFAULT_DOMAIN}

APP_DIR="/opt/nexfiber"
CONFIG_DIR="/etc/nexfiber"
BACKUP_DIR="/var/backups/nexfiber"
LOGDIR="/var/log/nexfiber"

echo ""

# =========================================================
# [3] KONFIGURASI DATABASE
# =========================================================

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE} [3/10] Konfigurasi Database${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "${YELLOW}(Tekan Enter untuk nilai default)${NC}"
echo ""

read -rp "Database Name [nexfiber_db]: " DB_NAME
DB_NAME=${DB_NAME:-nexfiber_db}

read -rp "Database User [nexfiber_user]: " DB_USER
DB_USER=${DB_USER:-nexfiber_user}

read -rsp "Password user database (kosong = auto generate): " DB_PASS
echo ""
if [ -z "$DB_PASS" ]; then
    DB_PASS="$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)"
    echo -e "${YELLOW}Password database auto-generated.${NC}"
fi

SECRET_KEY="$(openssl rand -hex 32)"

echo ""
echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN} Memulai instalasi...${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "Domain     : ${CYAN}${SERVER_NAME}${NC}"
echo -e "Install ke : ${CYAN}${APP_DIR}${NC}"
echo -e "Database   : ${CYAN}${DB_NAME}${NC} (user: ${CYAN}${DB_USER}${NC})"
echo ""

read -rp "Lanjutkan instalasi? [y/N]: " CONFIRM
case "$CONFIRM" in
    y|Y|yes|YES) ;;
    *) echo -e "${YELLOW}Instalasi dibatalkan.${NC}"; exit 0 ;;
esac
echo ""

# =========================================================
# [4] PAKET SISTEM
# =========================================================

log "[4/10] Update repository & install paket sistem..."

apt-get update -y >> "$LOG_FILE" 2>&1

# PostgreSQL 18 dari repo resmi PGDG (Debian/Ubuntu stable belum selalu punya 18)
if ! command -v psql &>/dev/null || ! psql --version | grep -q " 18"; then
    install -d /usr/share/postgresql-common/pgdg
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc >> "$LOG_FILE" 2>&1
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list
    apt-get update -y >> "$LOG_FILE" 2>&1
fi

apt-get install -y \
    postgresql-18 postgresql-client-18 \
    python3.12 python3.12-venv python3-pip \
    git curl openssl snmp \
    >> "$LOG_FILE" 2>&1
success "Paket sistem (PostgreSQL 18, Python 3.12, git, snmp) terpasang"

# Node.js (NodeSource) — untuk build frontend
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >> "$LOG_FILE" 2>&1
    apt-get install -y nodejs >> "$LOG_FILE" 2>&1
fi
success "Node.js $(node -v 2>/dev/null) terpasang"

# Caddy (repo resmi)
if ! command -v caddy &>/dev/null; then
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https >> "$LOG_FILE" 2>&1
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
        gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg >> "$LOG_FILE" 2>&1
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        > /etc/apt/sources.list.d/caddy-stable.list 2>>"$LOG_FILE"
    apt-get update -y >> "$LOG_FILE" 2>&1
    apt-get install -y caddy >> "$LOG_FILE" 2>&1
fi
success "Caddy terpasang"

echo ""

# =========================================================
# [5] USER & DIREKTORI
# =========================================================

log "[5/10] Setup user sistem & direktori..."

if ! id "$APP_SYSTEM_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin "$APP_SYSTEM_USER" >> "$LOG_FILE" 2>&1
fi

mkdir -p "$APP_DIR" "$CONFIG_DIR" "$BACKUP_DIR" "$LOGDIR"

# Salin source ke APP_DIR (idempoten, exclude state yang tidak boleh ikut)
if command -v rsync &>/dev/null; then
    rsync -a --exclude '.git/' --exclude 'venv/' --exclude 'node_modules/' --exclude '__pycache__/' \
        "$SCRIPT_DIR/" "$APP_DIR/" >> "$LOG_FILE" 2>&1
else
    cp -a "$SCRIPT_DIR"/. "$APP_DIR"/ 2>>"$LOG_FILE"
fi

chown -R "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$APP_DIR" "$LOGDIR" "$BACKUP_DIR"
chmod 750 "$CONFIG_DIR"
success "Direktori siap: ${APP_DIR}, ${CONFIG_DIR}, ${BACKUP_DIR}"

echo ""

# =========================================================
# [6] DATABASE
# =========================================================

log "[6/10] Setup database PostgreSQL..."

systemctl enable --now postgresql >> "$LOG_FILE" 2>&1

if ! db_role_exists "$DB_USER"; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
        "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASS}';" >> "$LOG_FILE" 2>&1
else
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
        "ALTER ROLE ${DB_USER} PASSWORD '${DB_PASS}';" >> "$LOG_FILE" 2>&1
    warn "Role ${DB_USER} sudah ada — password diperbarui"
fi

if ! db_exists "$DB_NAME"; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c \
        "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};" >> "$LOG_FILE" 2>&1
else
    warn "Database ${DB_NAME} sudah ada — dilewati"
fi
success "Database ${DB_NAME} siap (user: ${DB_USER})"

echo ""

# =========================================================
# [7] CONFIG, VENV, BUILD, MIGRASI
# =========================================================

log "[7/10] Tulis config, siapkan venv, build frontend, migrasi..."

cat > "$CONFIG_DIR/config.ini" << EOF2
[database]
url = postgresql+psycopg://${DB_USER}:${DB_PASS}@localhost:5432/${DB_NAME}

[app]
secret_key = ${SECRET_KEY}
domain = ${SERVER_NAME}
EOF2
chown "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$CONFIG_DIR/config.ini"
chmod 640 "$CONFIG_DIR/config.ini"

python3.12 -m venv "$APP_DIR/venv" >> "$LOG_FILE" 2>&1
"$APP_DIR/venv/bin/pip" install --upgrade pip >> "$LOG_FILE" 2>&1
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" >> "$LOG_FILE" 2>&1
success "Python venv siap"

( cd "$APP_DIR/frontend" && npm ci >> "$LOG_FILE" 2>&1 && npm run build >> "$LOG_FILE" 2>&1 )
success "Frontend ter-build"

( cd "$APP_DIR/backend" && \
  NEXFIBER_CONFIG="$CONFIG_DIR/config.ini" "$APP_DIR/venv/bin/alembic" upgrade head >> "$LOG_FILE" 2>&1 )
success "Migrasi database selesai (alembic upgrade head)"

echo ""

# =========================================================
# [8] SYSTEMD UNITS
# =========================================================

log "[8/10] Tulis systemd unit (API + worker)..."

cat > /etc/systemd/system/nexfiber-api.service << EOF3
[Unit]
Description=Nexfiber API (FastAPI/Uvicorn)
After=network.target postgresql.service

[Service]
User=${APP_SYSTEM_USER}
Group=${APP_SYSTEM_USER}
WorkingDirectory=${APP_DIR}/backend
Environment=NEXFIBER_CONFIG=${CONFIG_DIR}/config.ini
ExecStart=${APP_DIR}/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF3

cat > /etc/systemd/system/nexfiber-worker.service << EOF4
[Unit]
Description=Nexfiber Background Worker (job table poller)
After=network.target postgresql.service nexfiber-api.service

[Service]
User=${APP_SYSTEM_USER}
Group=${APP_SYSTEM_USER}
WorkingDirectory=${APP_DIR}/backend
Environment=NEXFIBER_CONFIG=${CONFIG_DIR}/config.ini
ExecStart=${APP_DIR}/venv/bin/python -m app.worker
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF4

systemctl daemon-reload
systemctl enable --now nexfiber-api.service nexfiber-worker.service >> "$LOG_FILE" 2>&1
success "systemd unit nexfiber-api & nexfiber-worker aktif"

echo ""

# =========================================================
# [9] CADDY (REVERSE PROXY + HTTPS)
# =========================================================

log "[9/10] Konfigurasi Caddy..."

cat > /etc/caddy/Caddyfile << EOF5
${SERVER_NAME} {
    root * ${APP_DIR}/frontend/dist
    encode gzip
    file_server

    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }

    handle /healthz {
        reverse_proxy 127.0.0.1:8000
    }

    try_files {path} /index.html
}
EOF5

systemctl enable --now caddy >> "$LOG_FILE" 2>&1
systemctl reload caddy >> "$LOG_FILE" 2>&1
success "Caddy terkonfigurasi untuk ${SERVER_NAME} (HTTPS otomatis bila domain publik)"

echo ""

# =========================================================
# [10] HEALTH CHECK & RINGKASAN
# =========================================================

log "[10/10] Verifikasi instalasi..."

sleep 2
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "http://127.0.0.1:8000/healthz" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    success "Verifikasi API OK (HTTP ${HTTP_CODE} — http://127.0.0.1:8000/healthz)"
else
    warn "Verifikasi API gagal (HTTP ${HTTP_CODE}) — cek: journalctl -u nexfiber-api -n 50"
fi

echo ""
echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN} ✅ OLT-APP BERHASIL DIINSTALL${NC}"
echo -e "${GREEN}==================================================${NC}"
echo ""
echo -e "${CYAN}URL:${NC} http://${SERVER_NAME}/ (HTTPS otomatis jika domain publik mengarah ke server ini)"
echo ""
echo -e "${CYAN}Instalasi:${NC}"
echo "  Versi   : v${APP_VERSION}"
echo "  Domain  : ${SERVER_NAME}"
echo "  Folder  : ${APP_DIR}"
echo "  Config  : ${CONFIG_DIR}/config.ini"
echo ""
echo -e "${CYAN}Database:${NC}"
echo "  Nama     : ${DB_NAME}"
echo "  User     : ${DB_USER}"
echo "  Password : ${DB_PASS}"
echo ""
echo -e "${CYAN}Service:${NC}"
echo "  systemctl status nexfiber-api"
echo "  systemctl status nexfiber-worker"
echo ""
echo -e "${CYAN}Log instalasi:${NC} ${LOG_FILE}"
echo ""
echo -e "${YELLOW}Langkah berikutnya:${NC}"
echo "  1. Buka URL di browser, login dengan akun admin awal (lihat dokumentasi setup admin)"
echo "  2. Untuk rilis berikutnya pakai: bash update.sh"
echo "  3. Untuk bongkar server: bash uninstall.sh"
echo ""
echo -e "${GREEN}Nexfiber siap digunakan.${NC}"
echo ""
```

### A.2 — `update.sh` (update rilis + rollback)

```bash
#!/bin/bash
# Nexfiber — update ke rilis terbaru (konsep sama dengan update_server.sh NetBackup)
#
# Usage (di server, dari folder /opt/nexfiber):
#   sudo bash update.sh                  # update ke HEAD/tag terbaru di branch saat ini
#   sudo bash update.sh --tag v1.2.0     # update ke tag tertentu
#   sudo bash update.sh --rollback v1.1.0  # rollback ke tag sebelumnya + restore DB

set -e

RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
CYAN='\033[1;36m'
NC='\033[0m'

APP_DIR="/opt/nexfiber"
CONFIG_DIR="/etc/nexfiber"
BACKUP_DIR="/var/backups/nexfiber"
APP_SYSTEM_USER="nexfiber"
LOG_FILE="/var/log/nexfiber_update.log"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"

error_exit() {
    echo ""
    echo -e "${RED}==================================================${NC}"
    echo -e "${RED} ❌ UPDATE GAGAL${NC}"
    echo -e "${RED}==================================================${NC}"
    if [ -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}Detail error (20 baris terakhir):${NC}"
        tail -20 "$LOG_FILE"
        echo -e "${YELLOW}Full log:${NC} $LOG_FILE"
    fi
    echo ""
    echo -e "${YELLOW}Rollback cepat:${NC} sudo bash update.sh --rollback <tag_sebelumnya>"
    exit 1
}
trap error_exit ERR

log()     { echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $1"; echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"; }
success() { echo -e "${GREEN}✔ $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠ $1${NC}"; }

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Jalankan dengan root/sudo: sudo bash update.sh${NC}"
    exit 1
fi

if [ ! -d "$APP_DIR/.git" ]; then
    echo -e "${RED}${APP_DIR} belum berisi git repo. Jalankan install.sh / install.sh dulu.${NC}"
    exit 1
fi

# =========================================================
# ARGUMEN
# =========================================================

MODE="update"
TARGET_TAG=""
case "$1" in
    --rollback)
        MODE="rollback"
        TARGET_TAG="$2"
        if [ -z "$TARGET_TAG" ]; then
            echo -e "${RED}Rollback butuh nama tag: sudo bash update.sh --rollback v1.1.0${NC}"
            exit 1
        fi
        ;;
    --tag)
        TARGET_TAG="$2"
        ;;
esac

clear
echo -e "${BLUE}==================================================${NC}"
if [ "$MODE" = "rollback" ]; then
    echo -e "${BLUE} Nexfiber — ROLLBACK ke ${TARGET_TAG}${NC}"
else
    echo -e "${BLUE} Nexfiber — Update${NC}"
fi
echo -e "${BLUE}==================================================${NC}"
echo ""

# =========================================================
# CHECKLIST KONFIRMASI (sesuai PRD §X.1)
# =========================================================

echo -e "${YELLOW}Checklist sebelum lanjut:${NC}"
echo "  [ ] Migrasi DB (jika ada) sudah ditulis dan idempoten?"
echo "  [ ] Ada perubahan command OLT? Sudah diuji ke lab/1 OLT non-kritis?"
echo "  [ ] Backup DB otomatis jalan (cron harian)?"
echo "  [ ] Tag git sudah dibuat untuk rilis ini?"
echo "  [ ] Tahu cara rollback kalau gagal?"
echo ""
read -rp "Semua sudah dicek, lanjutkan? [y/N]: " CONFIRM
case "$CONFIRM" in
    y|Y|yes|YES) ;;
    *) echo -e "${YELLOW}Dibatalkan.${NC}"; exit 0 ;;
esac
echo ""

# =========================================================
# [1] BACKUP DB SEBELUM MIGRASI
# =========================================================

log "[1/5] Backup database sebelum migrasi..."
mkdir -p "$BACKUP_DIR"
DUMP_FILE="${BACKUP_DIR}/pre-update_${TIMESTAMP}.dump"

DB_URL="$(grep '^url' "$CONFIG_DIR/config.ini" | sed 's/^url\s*=\s*//')"
DB_NAME="$(echo "$DB_URL" | sed -E 's#.*/([a-zA-Z0-9_]+)$#\1#')"
DB_USER="$(echo "$DB_URL" | sed -E 's#.*://([^:]+):.*#\1#')"

PGPASSWORD="$(echo "$DB_URL" | sed -E 's#.*://[^:]+:([^@]+)@.*#\1#')" \
    pg_dump -Fc -U "$DB_USER" -h localhost "$DB_NAME" -f "$DUMP_FILE" >> "$LOG_FILE" 2>&1
success "Backup tersimpan: ${DUMP_FILE}"
echo ""

# =========================================================
# [2] GIT CHECKOUT
# =========================================================

cd "$APP_DIR"
PREVIOUS_TAG="$(git describe --tags --abbrev=0 2>/dev/null || echo 'unknown')"

if [ "$MODE" = "rollback" ]; then
    log "[2/5] Rollback: git checkout ${TARGET_TAG}..."
    git fetch --tags >> "$LOG_FILE" 2>&1
    git checkout "$TARGET_TAG" >> "$LOG_FILE" 2>&1
    success "Checkout ke ${TARGET_TAG} selesai"
else
    log "[2/5] Tarik rilis terbaru..."
    git fetch --tags >> "$LOG_FILE" 2>&1
    if [ -n "$TARGET_TAG" ]; then
        git checkout "$TARGET_TAG" >> "$LOG_FILE" 2>&1
    else
        git checkout main >> "$LOG_FILE" 2>&1
        git pull origin main >> "$LOG_FILE" 2>&1
    fi
    success "Source diperbarui (tag sebelumnya: ${PREVIOUS_TAG})"
fi
echo ""

# =========================================================
# [3] MIGRASI DB
# =========================================================

log "[3/5] Migrasi database (alembic upgrade head)..."
if [ "$MODE" = "rollback" ]; then
    warn "Rollback: migrasi TIDAK dijalankan — restore dari dump jika skema berubah"
    PGPASSWORD="$(echo "$DB_URL" | sed -E 's#.*://[^:]+:([^@]+)@.*#\1#')" \
        pg_restore -c -U "$DB_USER" -h localhost -d "$DB_NAME" "$DUMP_FILE" >> "$LOG_FILE" 2>&1 || true
else
    NEXFIBER_CONFIG="$CONFIG_DIR/config.ini" "$APP_DIR/venv/bin/alembic" upgrade head >> "$LOG_FILE" 2>&1
    success "Migrasi selesai"
fi
echo ""

# =========================================================
# [4] DEPENDENSI & BUILD
# =========================================================

log "[4/5] Update dependensi & build ulang..."
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/backend/requirements.txt" >> "$LOG_FILE" 2>&1
( cd "$APP_DIR/frontend" && npm ci >> "$LOG_FILE" 2>&1 && npm run build >> "$LOG_FILE" 2>&1 )
chown -R "$APP_SYSTEM_USER:$APP_SYSTEM_USER" "$APP_DIR"
success "Dependensi & frontend diperbarui"
echo ""

# =========================================================
# [5] RESTART & HEALTH CHECK
# =========================================================

log "[5/5] Restart service & verifikasi..."
systemctl restart nexfiber-api nexfiber-worker >> "$LOG_FILE" 2>&1
sleep 2

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "http://127.0.0.1:8000/healthz" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" != "200" ]; then
    error_exit
fi
success "Health check OK (HTTP ${HTTP_CODE})"
echo ""

NEW_TAG="$(git describe --tags --abbrev=0 2>/dev/null || echo 'unknown')"
echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN} ✅ UPDATE SELESAI${NC}"
echo -e "${GREEN}==================================================${NC}"
echo "  Tag sebelumnya : ${PREVIOUS_TAG}"
echo "  Tag sekarang   : ${NEW_TAG}"
echo "  Backup DB      : ${DUMP_FILE}"
echo "  Log            : ${LOG_FILE}"
echo ""
echo -e "${YELLOW}Rollback jika ada masalah:${NC} sudo bash update.sh --rollback ${PREVIOUS_TAG}"
echo ""
```

### A.3 — `uninstall.sh` (bongkar bersih, DB dipertahankan default)

```bash
#!/bin/bash
# Nexfiber — bongkar instalasi server (konsep sama dengan uninstall pattern NetBackup)
#
# Usage (di server):
#   sudo bash uninstall.sh              # hapus app, config, service — DB TETAP (default aman)
#   sudo bash uninstall.sh --drop-db    # juga hapus database (ireversibel, perlu konfirmasi ekstra)

set -e

RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
CYAN='\033[1;36m'
NC='\033[0m'

APP_DIR="/opt/nexfiber"
CONFIG_DIR="/etc/nexfiber"
BACKUP_DIR="/var/backups/nexfiber"
LOGDIR="/var/log/nexfiber"
APP_SYSTEM_USER="nexfiber"
LOG_FILE="/var/log/nexfiber_uninstall.log"
TIMESTAMP="$(date '+%Y%m%d_%H%M%S')"
DROP_DB=false

[ "$1" = "--drop-db" ] && DROP_DB=true

log()     { echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $1"; echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"; }
success() { echo -e "${GREEN}✔ $1${NC}"; }
warn()    { echo -e "${YELLOW}⚠ $1${NC}"; }

if [ "$(id -u)" -ne 0 ]; then
    echo -e "${RED}Jalankan dengan root/sudo: sudo bash uninstall.sh${NC}"
    exit 1
fi

clear
echo -e "${RED}==================================================${NC}"
echo -e "${RED} ⚠️  Nexfiber — UNINSTALL${NC}"
echo -e "${RED}==================================================${NC}"
echo ""
echo "Ini akan menghentikan dan menghapus:"
echo "  - systemd service nexfiber-api, nexfiber-worker"
echo "  - Caddy site config untuk app ini"
echo "  - ${APP_DIR} (kode + venv + build frontend)"
echo "  - ${CONFIG_DIR} (config + secret)"
echo ""
echo "Yang TETAP disimpan (tidak dihapus):"
echo "  - ${BACKUP_DIR} (semua backup .dump)"
echo "  - ${LOGDIR} (log aplikasi)"
if [ "$DROP_DB" = true ]; then
    echo -e "  - ${RED}Database AKAN DIHAPUS${NC} (--drop-db aktif)"
else
    echo "  - Database (tidak dihapus — jalankan ulang dengan --drop-db untuk hapus juga)"
fi
echo ""

read -rp "Ketik UNINSTALL untuk lanjut: " CONFIRM
if [ "$CONFIRM" != "UNINSTALL" ]; then
    echo -e "${YELLOW}Dibatalkan.${NC}"
    exit 0
fi
echo ""

# =========================================================
# [1] BACKUP FINAL WAJIB
# =========================================================

log "[1/5] Backup final database sebelum apa pun dihapus..."
mkdir -p "$BACKUP_DIR"
FINAL_DUMP="/root/nexfiber-final-backup_${TIMESTAMP}.dump"

if [ -f "$CONFIG_DIR/config.ini" ]; then
    DB_URL="$(grep '^url' "$CONFIG_DIR/config.ini" | sed 's/^url\s*=\s*//')"
    DB_NAME="$(echo "$DB_URL" | sed -E 's#.*/([a-zA-Z0-9_]+)$#\1#')"
    DB_USER="$(echo "$DB_URL" | sed -E 's#.*://([^:]+):.*#\1#')"
    DB_PASS="$(echo "$DB_URL" | sed -E 's#.*://[^:]+:([^@]+)@.*#\1#')"
    PGPASSWORD="$DB_PASS" pg_dump -Fc -U "$DB_USER" -h localhost "$DB_NAME" -f "$FINAL_DUMP" >> "$LOG_FILE" 2>&1
    success "Backup final tersimpan: ${FINAL_DUMP}"
else
    warn "Config tidak ditemukan, backup final dilewati"
fi
echo ""

# =========================================================
# [2] STOP & HAPUS SERVICE
# =========================================================

log "[2/5] Menghentikan dan menghapus service..."
systemctl disable --now nexfiber-api nexfiber-worker >> "$LOG_FILE" 2>&1 || true
rm -f /etc/systemd/system/nexfiber-api.service /etc/systemd/system/nexfiber-worker.service
systemctl daemon-reload
success "Service nexfiber-api & nexfiber-worker dihentikan dan dihapus"
echo ""

# =========================================================
# [3] HAPUS CADDY SITE (BUKAN CADDY ITU SENDIRI)
# =========================================================

log "[3/5] Membersihkan konfigurasi Caddy..."
if [ -f /etc/caddy/Caddyfile ]; then
    cp /etc/caddy/Caddyfile "${BACKUP_DIR}/Caddyfile.bak_${TIMESTAMP}"
    rm -f /etc/caddy/Caddyfile
    touch /etc/caddy/Caddyfile
    systemctl reload caddy >> "$LOG_FILE" 2>&1 || true
fi
success "Caddyfile dibersihkan (Caddy tetap terpasang untuk app lain)"
echo ""

# =========================================================
# [4] HAPUS KODE & CONFIG (TIDAK HAPUS BACKUP/LOG)
# =========================================================

log "[4/5] Menghapus kode dan config..."
rm -rf "$APP_DIR"
rm -rf "$CONFIG_DIR"
success "${APP_DIR} dan ${CONFIG_DIR} dihapus"
echo ""

# =========================================================
# [5] DATABASE (OPSIONAL)
# =========================================================

log "[5/5] Database..."
if [ "$DROP_DB" = true ] && [ -n "$DB_NAME" ]; then
    echo -e "${RED}Konfirmasi terakhir — database '${DB_NAME}' akan DIHAPUS PERMANEN.${NC}"
    read -rp "Ketik nama database untuk konfirmasi (${DB_NAME}): " DB_CONFIRM
    if [ "$DB_CONFIRM" = "$DB_NAME" ]; then
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${DB_NAME};" >> "$LOG_FILE" 2>&1
        sudo -u postgres psql -c "DROP ROLE IF EXISTS ${DB_USER};" >> "$LOG_FILE" 2>&1
        success "Database ${DB_NAME} dan role ${DB_USER} dihapus"
    else
        warn "Konfirmasi tidak cocok — database TIDAK dihapus"
    fi
else
    warn "Database tidak dihapus (default aman). Backup final: ${FINAL_DUMP}"
fi
echo ""

# =========================================================
# RINGKASAN
# =========================================================

echo -e "${GREEN}==================================================${NC}"
echo -e "${GREEN} ✅ UNINSTALL SELESAI${NC}"
echo -e "${GREEN}==================================================${NC}"
echo ""
echo -e "${CYAN}Dihapus:${NC}"
echo "  - Service nexfiber-api, nexfiber-worker"
echo "  - ${APP_DIR}"
echo "  - ${CONFIG_DIR}"
echo "  - Caddy site config"
if [ "$DROP_DB" = true ]; then
    echo "  - Database (jika konfirmasi cocok)"
fi
echo ""
echo -e "${CYAN}Dipertahankan:${NC}"
echo "  - ${BACKUP_DIR} (semua backup .dump)"
echo "  - ${LOGDIR} (log aplikasi)"
echo "  - ${FINAL_DUMP} (backup final sebelum uninstall)"
if [ "$DROP_DB" != true ]; then
    echo "  - Database (masih ada di PostgreSQL)"
fi
echo ""
echo -e "${CYAN}Log uninstall:${NC} ${LOG_FILE}"
echo ""
```
