/** Pembersih nama/label speed profile untuk tampilan. Kembaran dari
 *  `backend/app/core/profile_name.py` — satu-satunya salinan di frontend, jangan tulis
 *  regex ini lagi di komponen.
 *
 *  Nama profile yang datang dari API (`speed_profiles.name`, `download_profile_name`,
 *  preset) SUDAH dibersihkan backend. Helper ini dipakai untuk label yang isinya nama
 *  profil di PERANGKAT (`line_profile_id` / `srv_profile_id`), yang sengaja dikirim apa
 *  adanya karena dipakai di command CLI.
 */

// `\b` tidak cukup: `_` adalah word char, padahal `5Mbps_SmartOLT` harus ikut bersih.
const SMARTOLT = /(?<![0-9A-Za-z])smartolt(?![0-9A-Za-z])/gi;
const DOUBLE_SEP = /[-_\s]{2,}/g;

/** `SMARTOLT-5Mbps` -> `5Mbps`. `KhanzaNet` tidak berubah. Hasil kosong -> nama asli. */
export function cleanProfileName(name: string | null | undefined): string | null {
  if (!name) return name ?? null;
  const out = name
    .replace(SMARTOLT, "")
    .replace(DOUBLE_SEP, (m) => m[0])
    .replace(/^[-_\s]+|[-_\s]+$/g, "");
  return out || name;
}
