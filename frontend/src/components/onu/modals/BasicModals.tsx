/** Modal satu/dua field: Change ONU type, Update ONU external ID, Configure speed profiles,
 *  Replace ONU by SN. Semuanya memakai `ModalShell` yang sama. */
import { useState } from "react";
import type { OnuConfigOptions } from "../../../lib/onuActions";
import { ModalShell, Row, Select, field } from "./ModalShell";

type Common = {
  supported: boolean | null;
  note?: string | null;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
};

export function OnuTypeModal(
  { options, current, onSubmit, ...c }:
  Common & {
    options: OnuConfigOptions | undefined;
    current: number | null;
    onSubmit: (body: { onu_type_id: number }) => void;
  },
) {
  const [id, setId] = useState(current === null ? "" : String(current));
  // Tipe nonaktif tidak ada di opsi (backend memfilter is_active): nilai awal seperti
  // itu tidak boleh bisa dikirim ulang — Save mati sampai tipe aktif dipilih.
  const idInList = (options?.onu_types ?? []).some((t) => String(t.id) === id);
  return (
    <ModalShell title="Change ONU type" action="Change" {...c} disabled={id === "" || !idInList}
                onSubmit={() => id !== "" && idInList && onSubmit({ onu_type_id: Number(id) })}>
      <Row label="ONU type">
        <Select value={id} onChange={setId} placeholder="Pilih tipe ..." label="ONU type">
          {(options?.onu_types ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </Select>
      </Row>
    </ModalShell>
  );
}

export function ExternalIdModal(
  { current, onSubmit, ...c }:
  Common & { current: string | null; onSubmit: (body: { external_id: string | null }) => void },
) {
  const [v, setV] = useState(current ?? "");
  // Backend max_length 50: batasi di input supaya kesalahan tertangkap sebelum submit.
  return (
    <ModalShell title="Update ONU external ID" action="Update" {...c}
                disabled={v.trim().length > 50}
                onSubmit={() => onSubmit({ external_id: v.trim() === "" ? null : v.trim() })}>
      <Row label="ONU external ID">
        <input className={field} value={v} autoComplete="off" aria-label="ONU external ID"
               maxLength={50} onChange={(e) => setV(e.target.value)} />
      </Row>
    </ModalShell>
  );
}

export function SpeedProfileModal(
  { options, current, currentName, onSubmit, ...c }:
  Common & {
    options: OnuConfigOptions | undefined;
    current: { download: number | null; upload: number | null };
    /** Nama profil saat ini, hanya untuk menampilkan nilai lama yang tidak ada di daftar aktif. */
    currentName?: { download: string | null; upload: string | null };
    onSubmit: (body: { upload_profile: number | null; download_profile: number | null }) => void;
  },
) {
  const [dn, setDn] = useState(current.download === null ? "" : String(current.download));
  const [up, setUp] = useState(current.upload === null ? "" : String(current.upload));
  const list = options?.speed_profiles ?? [];
  const byDir = (dir: string) =>
    list.filter((p) => !p.direction || p.direction === dir);
  // Nilai lama yang tidak ada di daftar (mis. profil nonaktif) tetap ditampilkan
  // sebagai info, supaya select tidak kosong padahal state masih menyimpan nilai itu
  // — tetapi TIDAK boleh dikirim ulang: Save mati selama arah yang terpilih adalah
  // nilai fallback di luar daftar aktif.
  const fallback = (value: string, name: string | null | undefined) =>
    value !== "" && !list.some((p) => String(p.id) === value) && name
      ? <option key={value} value={value}>{name}</option>
      : null;
  const dnStale = dn !== "" && !list.some((p) => String(p.id) === dn);
  const upStale = up !== "" && !list.some((p) => String(p.id) === up);
  // Placeholder kosong = lewati arah itu (backend hanya mengubah arah yang terisi),
  // jadi labelnya mengikuti ada tidaknya nilai awal: "Jangan ubah" bila sudah ada,
  // "Pilih profil ..." bila memang masih kosong. Save mati bila kedua arah kosong,
  // sama seperti validasi backend "Pilih minimal satu profile".
  return (
    <ModalShell title="Configure speed profiles" action="Save" {...c}
                disabled={(dn === "" && up === "") || dnStale || upStale}
                onSubmit={() => onSubmit({
                  download_profile: dn === "" ? null : Number(dn),
                  upload_profile: up === "" ? null : Number(up),
                })}>
      <Row label="Download speed">
        <Select value={dn} onChange={setDn}
                placeholder={current.download === null ? "Pilih profil ..." : "Jangan ubah"}
                label="Download speed">
          {fallback(dn, currentName?.download)}
          {byDir("download").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      </Row>
      <Row label="Upload speed">
        <Select value={up} onChange={setUp}
                placeholder={current.upload === null ? "Pilih profil ..." : "Jangan ubah"}
                label="Upload speed">
          {fallback(up, currentName?.upload)}
          {byDir("upload").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      </Row>
    </ModalShell>
  );
}

export function ReplaceSnModal(
  { currentSn, onSubmit, ...c }:
  Common & { currentSn: string; onSubmit: (body: { new_sn: string }) => void },
) {
  const [sn, setSn] = useState("");
  // Samakan dengan backend: ^[A-Z0-9]{8,20}$ setelah upper (bukan sekadar >= 4).
  const ok = /^[A-Z0-9]{8,20}$/.test(sn) && sn !== currentSn.toUpperCase();
  return (
    <ModalShell title="Replace ONU by SN" action="Replace" {...c} disabled={!ok}
                onSubmit={() => ok && onSubmit({ new_sn: sn })}>
      <Row label="SN saat ini">
        <input className={field} value={currentSn} readOnly disabled aria-label="SN sekarang" />
      </Row>
      <Row label="SN">
        <input className={field} value={sn} autoComplete="off" aria-label="SN baru"
               onChange={(e) => setSn(e.target.value.trim().toUpperCase())} />
      </Row>
    </ModalShell>
  );
}
