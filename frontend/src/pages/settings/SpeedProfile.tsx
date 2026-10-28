/** Settings -> Speed Profile (PRD 3.4.12). VLAN hanya dibaca untuk dropdown — tidak ada
 *  create/edit VLAN di halaman ini (DECISIONS: UI VLAN penuh nanti di Detail OLT).
 *  Opsi A: satu baris = satu arah. Tab Download/Upload (pola sama dengan Splitter & Zone)
 *  — dua master data terpisah, bukan satu list dengan kolom arah.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import * as z from "zod";
import { Confirm, Drawer, Field, JobTrace, MobileCard, TableCard, cell, filterInput, input } from "../../components/crud";
import { PageTitle } from "../../components/data";
import { Button } from "../../components/ui/button";
import { api, qs, type Olt, type SpeedProfileRow, type Vlan } from "../../lib/api";
import { useAuth } from "../../lib/auth";

const ALL = "";
const mbps = (kbps: number) => `${(kbps / 1000).toFixed(kbps % 1000 ? 1 : 0)} Mbps`;
const nullable = (v: string) => (v === "" ? null : v);

const schema = z.object({
  name: z.string().min(1, "Wajib diisi").max(100),
  speed_kbps: z.coerce.number().int().min(64).max(10_000_000),
  olt_id: z.string(),
  vlan_db_id: z.string(),
  description: z.string().max(255),
  is_active: z.string().default("true"),
});
type Form = z.input<typeof schema>;

/** Select kosong = NULL di API (olt_id NULL = semua OLT, vlan_db_id NULL = tanpa VLAN).
 *  is_active hanya dikirim saat edit (create tidak punya field itu di backend). */
const toPayload = (f: Form, direction: "download" | "upload", edit: boolean) => {
  const v = schema.parse(f);
  return {
    name: v.name,
    direction,
    speed_kbps: v.speed_kbps,
    olt_id: nullable(v.olt_id) && Number(v.olt_id),
    vlan_db_id: nullable(v.vlan_db_id) && Number(v.vlan_db_id),
    description: nullable(v.description),
    ...(edit ? { is_active: v.is_active === "true" } : {}),
  };
};

function ProfileDrawer({ edit, direction, olts, onClose }: {
  edit: SpeedProfileRow | null; direction: "download" | "upload";
  olts: Olt[]; onClose: () => void;
}) {
  const qc = useQueryClient();
  const { register, handleSubmit, watch, formState } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: edit?.name ?? "",
      speed_kbps: edit?.speed_kbps ?? 20000,
      olt_id: edit?.olt_id ? String(edit.olt_id) : ALL,
      vlan_db_id: edit?.vlan_db_id ? String(edit.vlan_db_id) : ALL,
      description: edit?.description ?? "",
      is_active: edit ? String(edit.is_active) : "true",
    },
  });
  // VLAN difilter OLT yang dipilih DI DRAWER ini, bukan filter halaman — kalau
  // tidak, ganti OLT di drawer tidak mengubah opsi VLAN.
  const watchedOlt = watch("olt_id");
  const vlans = useQuery({
    queryKey: ["vlans", watchedOlt],
    queryFn: () => api<Vlan[]>(`/api/vlans${qs({ olt_id: watchedOlt })}`),
  });
  const vlanRows = vlans.data ?? [];
  // Opsi fallback: nilai lama yang tidak ada di daftar (mis. OLT/VLAN dihapus
  // dari scope) tetap ditampilkan, supaya simpan tidak diam-diam men-null-kan.
  const oltFallback = edit?.olt_id != null && !olts.some((o) => o.id === edit.olt_id);
  const vlanFallback = edit?.vlan_db_id != null && !vlanRows.some((v) => v.id === edit.vlan_db_id);
  const save = useMutation({
    mutationFn: (f: Form) =>
      edit
        ? api<SpeedProfileRow>(`/api/speed-profiles/${edit.id}`, { method: "PATCH", json: toPayload(f, direction, true) })
        : api<SpeedProfileRow>("/api/speed-profiles", { method: "POST", json: toPayload(f, direction, false) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["speed-profiles"] }); onClose(); },
  });

  return (
    <Drawer
      title={edit ? `Edit ${edit.name}` : `Tambah profile ${direction === "download" ? "download" : "upload"}`}
      onClose={onClose}
      dirty={formState.isDirty}
      onSubmit={handleSubmit((f) => save.mutate(f))}
      busy={save.isPending}
      error={save.error?.message}
    >
      <Field label="Nama profile" error={formState.errors.name?.message}>
        <input className={input} autoFocus autoComplete="off" {...register("name")} />
      </Field>
      <Field label="Speed (kbps)" error={formState.errors.speed_kbps?.message}>
        <input className={input} type="number" min={64} {...register("speed_kbps")} />
      </Field>
      <Field label="OLT">
        <select className={input} {...register("olt_id")}>
          <option value={ALL}>Semua OLT</option>
          {oltFallback && <option value={String(edit!.olt_id)}>OLT tidak tersedia (id {edit!.olt_id})</option>}
          {olts.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
        </select>
      </Field>
      <Field label="VLAN">
        <select className={input} {...register("vlan_db_id")}>
          <option value={ALL}>Tanpa VLAN</option>
          {vlanFallback && <option value={String(edit!.vlan_db_id)}>VLAN tidak tersedia (id {edit!.vlan_db_id})</option>}
          {vlanRows.map((v) => <option key={v.id} value={v.id}>{v.vlan_id} · {v.name}</option>)}
        </select>
      </Field>
      <Field label="Keterangan">
        <input className={input} autoComplete="off" {...register("description")} />
      </Field>
      {edit && (
        <Field label="Status">
          <select className={input} {...register("is_active")}>
            <option value="true">Aktif</option>
            <option value="false">Nonaktif</option>
          </select>
        </Field>
      )}
    </Drawer>
  );
}

export function SpeedProfile() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const canWrite = me.role !== "user";
  const [direction, setDirection] = useState<"download" | "upload">("download");
  const [oltId, setOltId] = useState(ALL);
  const [q, setQ] = useState("");
  const [drawer, setDrawer] = useState<{ edit: SpeedProfileRow | null } | null>(null);
  const [del, setDel] = useState<SpeedProfileRow | null>(null);
  const [note, setNote] = useState("");
  const [pushJob, setPushJob] = useState<number | null>(null);

  const olts = useQuery({ queryKey: ["olts"], queryFn: () => api<Olt[]>("/api/olts") });
  const profiles = useQuery({
    // include_inactive: profile nonaktif tetap tampil dengan badge Nonaktif dan
    // bisa diaktifkan lagi lewat drawer; kalau tidak, reaktivasi lewat UI mustahil.
    queryKey: ["speed-profiles", oltId],
    queryFn: () => api<SpeedProfileRow[]>(`/api/speed-profiles${qs({ olt_id: oltId, include_inactive: "true" })}`),
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["speed-profiles"] });
  const remove = useMutation({
    mutationFn: (p: SpeedProfileRow) => api<void>(`/api/speed-profiles/${p.id}`, { method: "DELETE" }),
    onSuccess: () => { invalidate(); setDel(null); },
  });
  // Baris yang diklik disimpan supaya label tombolnya saja yang berubah
  // menjadi "Mengirim …" — tombol baris lain tetap mati selama mutasi bersama
  // berjalan (mencegah dua push bersamaan), tapi tidak lagi mati tanpa penjelasan.
  // JobTrace di atas halaman tetap ada sebagai pelengkap, bukan satu-satunya umpan balik.
  const [pushTarget, setPushTarget] = useState<number | null>(null);
  const push = useMutation({
    mutationFn: (p: SpeedProfileRow) =>
      api<{ job_id: number }>(`/api/speed-profiles/${p.id}/push`, { method: "POST" }),
    onSuccess: (r) => { setPushTarget(null); setPushJob(r.job_id); setNote(`Job simpan ke OLT #${r.job_id} dibuat.`); },
    onError: (e: Error) => { setPushTarget(null); setNote(e.message); },
  });
  const pushLabel = (p: SpeedProfileRow) =>
    pushTarget === p.id && push.isPending ? "Mengirim …" : "Simpan ke OLT";
  const sync = useMutation({
    mutationFn: () => api<{ job_id: number }>(`/api/speed-profiles/sync${qs({ olt_id: oltId })}`, { method: "POST" }),
    onSuccess: (r) => { invalidate(); setNote(`Job baca dari OLT #${r.job_id} dibuat.`); },
    onError: (e: Error) => setNote(e.message),
  });

  const needle = q.toLowerCase();
  const rows = (profiles.data ?? [])
    .filter((p) => p.direction === direction)
    .filter((p) => !needle || p.name.toLowerCase().includes(needle));

  const tabClass = (t: string) =>
    `h-8 px-3 text-sm ${direction === t ? "border-b-2 border-fiber font-medium" : "text-muted"}`;

  return (
    <>
      <PageTitle title="Speed Profile">
        {canWrite && (
          <Button variant="fiber" onClick={() => setDrawer({ edit: null })}>
            Tambah profile {direction === "download" ? "download" : "upload"}
          </Button>
        )}
      </PageTitle>

      <div className="mb-3 flex gap-1 border-b">
        <button type="button" className={tabClass("download")} onClick={() => setDirection("download")}>
          Download
        </button>
        <button type="button" className={tabClass("upload")} onClick={() => setDirection("upload")}>
          Upload
        </button>
      </div>

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
      <JobTrace jobId={pushJob} />

      <TableCard
        query={{ ...profiles, data: rows }}
        loadingText="Memuat speed profile ..."
        empty={`Belum ada speed profile ${direction === "download" ? "download" : "upload"}.`}
        columns={["Nama", "Speed", "OLT", "VLAN", "ONU", "Status", "Aksi"]}
        card={(p: SpeedProfileRow) => (
          <MobileCard key={p.id}>
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate font-medium">{p.name}</span>
              <span className="inline-flex shrink-0 items-center gap-1.5 text-xs">
                <span className={`size-1.5 shrink-0 ${p.is_active ? "bg-up" : "bg-idle"}`} aria-hidden />
                {p.is_active ? "Aktif" : "Nonaktif"}
              </span>
            </div>
            <p className="font-mono text-xs text-muted">
              {mbps(p.speed_kbps)} · {p.olt_name ?? "Semua OLT"} · VLAN {p.vlan_id ?? "—"} · ONU {p.onu_count}
            </p>
            {canWrite && (
              <div className="mt-1 flex flex-wrap gap-2">
                <Button size="sm" onClick={() => setDrawer({ edit: p })}>Edit</Button>
                <Button size="sm" disabled={!p.olt_id || push.isPending} onClick={() => { setPushTarget(p.id); push.mutate(p); }}>{pushLabel(p)}</Button>
                <Button size="sm" variant="danger" onClick={() => setDel(p)}>Hapus</Button>
              </div>
            )}
          </MobileCard>
        )}
        row={(p: SpeedProfileRow) => (
          <tr key={p.id} className="border-b last:border-0">
            <td className={cell}>{p.name}</td>
            <td className={`${cell} font-mono`}>{mbps(p.speed_kbps)}</td>
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
                          onClick={() => { setPushTarget(p.id); push.mutate(p); }}>{pushLabel(p)}</Button>
                  <Button size="sm" variant="danger" onClick={() => setDel(p)}>Hapus</Button>
                </div>
              ) : "—"}
            </td>
          </tr>
        )}
      />

      {drawer && (
        <ProfileDrawer edit={drawer.edit} direction={direction} olts={olts.data ?? []}
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
