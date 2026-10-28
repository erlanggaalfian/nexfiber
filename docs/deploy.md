# Deploy Nexfiber — LAN-only secara default

## Keputusan (2026-10-28, dari bukti repo)

**Nexfiber berjalan LAN-only, tanpa Caddy, satu port HTTP langsung.**

- `DECISIONS.md` (keputusan terkunci, "hasil setup nyata, bukan rencana"):
  server ini sudah jalan Apache untuk domain lain; Nexfiber **TIDAK** pakai
  Caddy/domain/HTTPS, cukup satu port HTTP langsung; frontend di-build jadi
  statis dan disajikan langsung oleh FastAPI; port aplikasi **8088**.
- Rencana Caddy 2 + HTTPS otomatis di `PRD-FINAL.md` adalah rencana lama
  yang tidak berlaku untuk server ini. `AGENTS.md` yang masih menyebut
  "systemd + Caddy" sudah kedaluwarsa soal ini (belum diperbarui di sini
  karena di luar cakupan perubahan skrip deploy).
- Tidak ada `Caddyfile` di repo dan `install.sh` tidak pernah menginstal
  Caddy — jadi "Caddy vs LAN-only" diselesaikan dengan mengikuti keputusan
  terkunci yang sudah ada, bukan dengan menambah Caddy.

## Default sekarang (setelah perubahan ini)

| Hal | Default |
|---|---|
| Bind API (uvicorn) | IP LAN server yang terdeteksi saat instalasi (`hostname -I`, alamat pertama) — **bukan `0.0.0.0`** |
| Port | `8088` |
| TLS | Tidak ada — HTTP saja, hanya untuk LAN tepercaya |
| Reverse proxy | Tidak ada; FastAPI menyajikan API + frontend statis |
| Autentikasi | Login aplikasi sendiri (akun Superadmin pertama via `/setup`); tidak ada autentikasi tambahan di depan aplikasi |

`0.0.0.0` sebelumnya membuat API mendengarkan **semua** interface,
termasuk interface publik bila server punya IP publik — itu bukan
LAN-only, walau peringatannya sudah ditulis di installer. Sekarang
`0.0.0.0` hanya terjadi bila operator sadar memilihnya saat instalasi.

**Catatan jujur:** bind ke IP LAN bukan firewall. Bila IP pertama server
ternyata IP publik (mis. VPS satu interface), bind itu tidak membatasi
apa-apa — karena itu installer menampilkan IP default dan meminta
operator memeriksanya sebelum lanjut. Jangan port-forward 8088 ke
internet; tidak ada TLS yang melindungi kredensial login di jalur itu.

## Yang dilakukan skrip

- `install.sh`: menanyakan bind address (default IP LAN terdeteksi,
  `127.0.0.1` = hanya dari server itu sendiri, `0.0.0.0` = semua
  interface bila sadar dipilih), menulisnya ke unit
  `nexfiber-api.service` (`ExecStart=... --host <bind> --port 8088`),
  dan health check memakai bind tersebut.
- `update.sh`: **tidak** menulis ulang unit systemd, jadi pilihan bind
  dari instalasi bertahan; health check-nya membaca bind dari unit yang
  terinstal (sebelumnya health check selalu ke `127.0.0.1`, yang akan
  gagal pada instalasi yang mengikat IP LAN).
- `uninstall.sh`: tidak berubah — ia menghapus kedua unit apa pun
  bind-nya, jadi tidak ada yang perlu disesuaikan di sana.

## Mengubah bind pada instalasi yang sudah berjalan

```bash
sudo systemctl edit nexfiber-api   # atau edit langsung unitnya, ubah --host
sudo systemctl daemon-reload
sudo systemctl restart nexfiber-api
```

## Bila suatu hari Nexfiber boleh diakses dari internet (langkah sadar)

Jangan membuka port 8088 ke publik. Urutannya:

1. Bind aplikasi ke `127.0.0.1` (lihat atas).
2. Pasang reverse proxy TLS di depan (mis. Apache yang sudah ada di
   server ini, atau Caddy bila diputuskan saat itu) yang meneruskan ke
   `127.0.0.1:8088` dengan sertifikat yang valid.
3. Pastikan 8088 tidak bisa dijangkau langsung dari luar (firewall /
   tidak ada port-forward ke 8088).
4. Baru setelah itu domain publik boleh diarahkan ke proxy tersebut.

Itu adalah keputusan baru yang butuh persetujuan pemilik — bukan default.

## Yang masih butuh pemilik (di luar cakupan ini)

- Apakah Nexfiber memang boleh diakses dari internet suatu hari, dan
  lewat domain apa — tidak ada pernyataan itu di repo, jadi default
  tetap LAN-only dan pertanyaan ini tetap terbuka.
- Aturan firewall server (tidak dikonfigurasi installer ini).
- Sinkronisasi dokumen: baris "systemd + Caddy" di `AGENTS.md` dan
  rencana Caddy di `PRD-FINAL.md` masih bertentangan dengan keputusan
  ini dan perlu diperbarui di dokumen tersebut (di luar file yang
  boleh diubah untuk tugas deploy ini).
