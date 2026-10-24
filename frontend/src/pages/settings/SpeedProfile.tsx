/** Settings -> Speed Profile (PRD 3.4.12). VLAN hanya dibaca untuk dropdown — tidak ada
 *  create/edit VLAN di halaman ini (DECISIONS: UI VLAN penuh nanti di Detail OLT).
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import * as z from "zod";
import { Confirm, Drawer, Field, TableCard, cell, filterInput, input } from "../../components/crud";
import { PageTitle } from "../../components/data";
import { Button } from "../../components/ui/button";
import { api, qs, type Olt, type SpeedProfileRow, type Vlan } from "../../lib/api";
import { useAuth } from "../../lib/auth";

const ALL = "";
const mbps = (kbps: number) => `${(kbps / 1000).toFixed(kbps % 1000 ? 1 : 0)} Mbps`;
const nullable = (v: string) => (v === "" ? null : v);

const schema = z.object({
  name: z.string().min(1, "Wajib diisi").max(100),
  download_kbps: z.coerce.number().int().min(64).max(10_000_000),
  upload_kbps: z.coerce.number().int().min(64).max(10_000_000),
  olt_id: z.string(),
  vlan_db_id: z.string(),
  description: z.string().max(255),
});
type Form = z.input<typeof schema>;

/** Select kosong = NULL di API (olt_id NULL = semua OLT, vlan_db_id NULL = tanpa VLAN). */
const toPayload = (f: Form) => {
  const v = schema.parse(f);
  return {
    name: v.name,
    download_kbps: v.download_kbps,
    upload_kbps: v.upload_kbps,
    olt_id: nullable(v.olt_id) && Number(v.olt_id),
    vlan_db_id: nullable(v.vlan_db_id) && Number(v.vlan_db_id),
    description: nullable(v.description),
  };
};

function ProfileDrawer({ edit, olts, vlans, onClose }: {
  edit: SpeedProfileRow | null; olts: Olt[]; vlans: Vlan[]; onClose: () => void;
}) {
  const qc = useQueryClient();
  const { register, handleSubmit, formState } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: edit?.name ?? "",
      download_kbps: edit?.download_kbps ?? 20000,
      upload_kbps: edit?.upload_kbps ?? 10000,
      olt_id: edit?.olt_id ? String(edit.olt_id) : ALL,
      vlan_db_id: edit?.vlan_db_id ? String(edit.vlan_db_id) : ALL,
      description: edit?.description ?? "",
    },
  });
  const save = useMutation({
    mutationFn: (f: Form) =>
      edit
        ? api<SpeedProfileRow>(`/api/speed-profiles/${edit.id}`, { method: "PATCH", json: toPayload(f) })
        : api<SpeedProfileRow>("/api/speed-profiles", { method: "POST", json: toPayload(f) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["speed-profiles"] }); onClose(); },
  });

  return (
    <Drawer
      title={edit ? `Edit ${edit.name}` : "Tambah speed profile"}
      onClose={onClose}
      onSubmit={handleSubmit((f) => save.mutate(f))}
      busy={save.isPending}
      error={save.error?.message}
    >
      <Field label="Nama profile" error={formState.errors.name?.message}>
        <input className={input} autoFocus autoComplete="off" {...register("name")} />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Download (kbps)" error={formState.errors.download_kbps?.message}>
          <input className={input} type="number" min={64} {...register("download_kbps")} />
        </Field>
        <Field label="Upload (kbps)" error={formState.errors.upload_kbps?.message}>
          <input className={input} type="number" min={64} {...register("upload_kbps")} />
        </Field>
      </div>
      <Field label="OLT">
        <select className={input} {...register("olt_id")}>
          <option value={ALL}>Semua OLT</option>
          {olts.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </Field>
      <Field label="VLAN">
        <select className={input} {...register("vlan_db_id")}>
          <option value={ALL}>Tanpa VLAN</option>
          {vlans.map((v) => <option key={v.id} value={v.id}>{v.vlan_id} · {v.name}</option>)}
        </select>
      </Field>
      <Field label="Keterangan">
        <input className={input} autoComplete="off" {...register("description")} />
      </Field>
    </Drawer>
  );
}

export function SpeedProfile() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const canWrite = me.role !== "user";
  const [oltId, setOltId] = useState(ALL);
  const [q, setQ] = useState("");
  const [drawer, setDrawer] = useState<{ edit: SpeedProfileRow | null } | null>(null);
  const [del, setDel] = useState<SpeedProfileRow | null>(null);
  const [note, setNote] = useState("");

  const olts = useQuery({ queryKey: ["olts"], queryFn: () => api<Olt[]>("/api/olts") });
  const vlans = useQuery({
    queryKey: ["vlans", oltId],
    queryFn: () => api<Vlan[]>(`/api/vlans${qs({ olt_id: oltId })}`),
  });
  const profiles = useQuery({
    queryKey: ["speed-profiles", oltId],
    queryFn: () => api<SpeedProfileRow[]>(`/api/speed-profiles${qs({ olt_id: oltId })}`),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["speed-profiles"] });
  const remove = useMutation({
    mutationFn: (p: SpeedProfileRow) => api<void>(`/api/speed-profiles/${p.id}`, { method: "DELETE" }),
    onSuccess: () => { invalidate(); setDel(null); },
  });
  const push = useMutation({
    mutationFn: (p: SpeedProfileRow) =>
      api<{ job_id: number }>(`/api/speed-profiles/${p.id}/push`, { method: "POST" }),
    onSuccess: (r) => setNote(`Job simpan ke OLT #${r.job_id} dibuat.`),
    onError: (e: Error) => setNote(e.message),
  });
  const sync = useMutation({
    mutationFn: () => api<{ job_id: number }>(`/api/speed-profiles/sync${qs({ olt_id: oltId })}`, { method: "POST" }),
    onSuccess: (r) => { invalidate(); setNote(`Job baca dari OLT #${r.job_id} dibuat.`); },
    onError: (e: Error) => setNote(e.message),
  });

  const needle = q.toLowerCase();
  const rows = (profiles.data ?? []).filter((p) => !needle || p.name.toLowerCase().includes(needle));

  return (
    <>
      <PageTitle title="Speed Profile">
        {canWrite && <Button variant="fiber" onClick={() => setDrawer({ edit: null })}>Tambah profile</Button>}
      </PageTitle>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select value={oltId} onChange={(e) => { setOltId(e.target.value); setNote(""); }}
                aria-label="Pilih OLT" className={filterInput}>
          <option value={ALL}>Semua OLT</option>
          {(olts.data ?? []).map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)}
               placeholder="Cari profile" className={`${filterInput} w-60`} />
        {canWrite && (
          <Button onClick={() => sync.mutate()} disabled={!oltId || sync.isPending}>
            {sync.isPending ? "Membaca ..." : "Baca dari OLT"}
          </Button>
        )}
        {note && <span className="text-muted" role="status">{note}</span>}
      </div>

      <TableCard
        query={{ ...profiles, data: rows }}
        loadingText="Memuat speed profile ..."
        empty="Belum ada speed profile."
        columns={["Nama", "Download", "Upload", "OLT", "VLAN", "ONU", "Status", "Aksi"]}
        row={(p: SpeedProfileRow) => (
          <tr key={p.id} className="border-b last:border-0">
            <td className={cell}>{p.name}</td>
            <td className={`${cell} font-mono`}>{mbps(p.download_kbps)}</td>
            <td className={`${cell} font-mono`}>{mbps(p.upload_kbps)}</td>
            <td className={cell}>{p.olt_name ?? "Semua OLT"}</td>
            <td className={`${cell} font-mono`}>{p.vlan_id ?? "—"}</td>
            <td className={`${cell} font-mono`}>{p.onu_count}</td>
            <td className={cell}>
              <span className="inline-flex items-center gap-1.5">
                <span className={`size-1.5 shrink-0 ${p.is_active ? "bg-up" : "bg-idle"}`} aria-hidden />
                {p.is_active ? "Aktif" : "Nonaktif"}
              </span>
            </td>
            <td className={cell}>
              {canWrite ? (
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => setDrawer({ edit: p })}>Edit</Button>
                  <Button size="sm" disabled={!p.olt_id || push.isPending}
                          onClick={() => push.mutate(p)}>Simpan ke OLT</Button>
                  <Button size="sm" variant="danger" onClick={() => setDel(p)}>Hapus</Button>
                </div>
              ) : "—"}
            </td>
          </tr>
        )}
      />

      {drawer && (
        <ProfileDrawer edit={drawer.edit} olts={olts.data ?? []} vlans={vlans.data ?? []}
                       onClose={() => setDrawer(null)} />
      )}
      {del && (
        <Confirm
          title={`Hapus ${del.name}?`}
          body={del.onu_count > 0
            ? `Profile ini dipakai ${del.onu_count} ONU, penghapusan akan ditolak.`
            : "Speed profile dihapus permanen."}
          action="Hapus"
          busy={remove.isPending}
          error={remove.error?.message}
          onConfirm={() => remove.mutate(del)}
          onClose={() => { remove.reset(); setDel(null); }}
        />
      )}
    </>
  );
}
