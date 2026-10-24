# Antrian Permintaan — Nexfiber

Log tiap permintaan Erlangga ke proyek Nexfiber, urut dari paling lama. Status: `selesai` / `jalan` / `antri`.

## Format
`[tanggal] status — permintaan singkat → hasil/commit (kalau ada)`

## Log

- [2026-10-24] selesai — resolusi 3 decision point pasca Fase C (Rx column, verifikasi parser CLI, review diff shared-file) → Rx: tidak ditambah (limitasi device, didokumentasikan); diff: bersih tanpa duplikasi; parser: diperbaiki pakai driver pembanding SmartOLT (commit `92f51ee`)
- [2026-10-24] selesai — tambah OLT nyata "SBI" (id=31) untuk verifikasi read-only → ditest, CLI awalnya gagal auth
- [2026-10-24] selesai — "ambil olt sbi dari smartolt saja" (ambil kredensial dari record SmartOLT produksi id=12) → password diperbarui di DB, 6 bug nyata ditemukan & diperbaiki (parser card/processor/version-running, netmiko device_type, command show version, SNMP var_binds unpack) → commit `fc46175`, deployed, test_connection real: cli_ok=True snmp_ok=True
- [2026-10-24] selesai — tarik transkrip `show gpon remote-onu equip` dari OLT SBI (read-only) untuk menutup sisa decision point 2 → ONU 1/6/1:1, parser `_parse_equip` diperbaiki (OLT ini tidak punya label active/standby software version, cuma "Version"+"Model"), fixture+test ditambah, 89 test lulus
- [2026-10-24] selesai — Speed Profile: pisahkan UI-nya jadi 2 section/halaman terpisah (Download & Upload), ikut konsep Zone/Splitter (master data terpisah), bukan 1 list dengan field direction → tab Download/Upload (pola sama Splitters.tsx), form tanpa dropdown arah (terkunci ke tab aktif), tsc+build bersih
- [2026-10-24] selesai — buat file antrian permintaan ini (QUEUE.md)
- [2026-10-24] selesai — fitur: pisah Speed Profile jadi profil Download dan Upload independen (lihat `DECISIONS.md` § "TODO — Speed Profile pisah Download/Upload") → migrasi `b7c8d9e0f1a2`, backend+frontend diperbarui, 88 test lulus, deploy via update.sh (commit `99ab441`)
- [2026-10-24] selesai — "lanjut sampai jadi" (gap Fase D): halaman Logs (PRD 3.4.15) → tabel `activity_logs` sudah ada (insert-only), ditambah query baca+scope OLT (`activity_log_repo.search`), service, router `/api/logs`, halaman frontend `Logs.tsx` (filter kategori/OLT/teks, paginasi, dialog detail command/response), terhubung di nav header. 91 test lulus, tsc+build bersih
