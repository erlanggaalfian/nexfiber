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
  return (
    <ModalShell title="Change ONU type" action="Change" {...c} disabled={id === ""}
                onSubmit={() => id !== "" && onSubmit({ onu_type_id: Number(id) })}>
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
  return (
    <ModalShell title="Update ONU external ID" action="Update" {...c}
                onSubmit={() => onSubmit({ external_id: v.trim() === "" ? null : v.trim() })}>
      <Row label="ONU external ID">
        <input className={field} value={v} autoComplete="off" aria-label="ONU external ID"
               onChange={(e) => setV(e.target.value)} />
      </Row>
    </ModalShell>
  );
}

export function SpeedProfileModal(
  { options, current, onSubmit, ...c }:
  Common & {
    options: OnuConfigOptions | undefined;
    current: { download: string | null; upload: string | null };
    onSubmit: (body: { upload_profile: string | null; download_profile: string | null }) => void;
  },
) {
  const [dn, setDn] = useState(current.download ?? "");
  const [up, setUp] = useState(current.upload ?? "");
  const list = options?.speed_profiles ?? [];
  const byDir = (dir: string) =>
    list.filter((p) => !p.direction || p.direction === dir);
  return (
    <ModalShell title="Configure speed profiles" action="Save" {...c}
                onSubmit={() => onSubmit({
                  download_profile: dn === "" ? null : dn,
                  upload_profile: up === "" ? null : up,
                })}>
      <Row label="Download speed">
        <Select value={dn} onChange={setDn} placeholder="Jangan ubah" label="Download speed">
          {byDir("download").map((p) => <option key={p.id} value={p.name}>{p.name}</option>)}
        </Select>
      </Row>
      <Row label="Upload speed">
        <Select value={up} onChange={setUp} placeholder="Jangan ubah" label="Upload speed">
          {byDir("upload").map((p) => <option key={p.id} value={p.name}>{p.name}</option>)}
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
  const ok = sn.length >= 4 && sn !== currentSn;
  return (
    <ModalShell title="Replace ONU by SN" action="Replace" {...c} disabled={!ok}
                onSubmit={() => ok && onSubmit({ new_sn: sn })}>
      <Row label="SN saat ini">
        <input className={field} value={currentSn} readOnly disabled aria-label="SN sekarang" />
      </Row>
      <Row label="SN">
        <input className={field} value={sn} autoComplete="off" aria-label="SN baru"
               onChange={(e) => setSn(e.target.value.trim())} />
      </Row>
    </ModalShell>
  );
}
