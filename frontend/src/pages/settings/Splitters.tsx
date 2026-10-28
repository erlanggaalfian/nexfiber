/** Settings -> Splitters & Zone (PRD 3.4.11, DESIGN 12.8: dua tab di bawah judul).
 *  Keduanya milik Admin (owner scope dicek backend); User hanya melihat.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import * as z from "zod";
import {
  Confirm, Drawer, Field, TableCard, UsageBar, cell, filterInput, input,
} from "../../components/crud";
import { PageTitle } from "../../components/data";
import { Button } from "../../components/ui/button";
import {
  api, qs, type OnuPreset, type OnuType, type Splitter, type SplitterDetail, type Zone,
} from "../../lib/api";
import { useAuth } from "../../lib/auth";

const RATIOS = ["1:2", "1:4", "1:8", "1:16", "1:32", "1:64"] as const;
const TYPES = [["odc", "ODC"], ["odp", "ODP"]] as const;
const num = (v: unknown) => (v === "" || v === null || v === undefined ? null : Number(v));
/** Koordinat: kosong = null, selain itu harus angka dalam rentang. Tanpa ini, "abc"
 *  menjadi NaN yang saat di-JSON-kan berubah jadi null dan diam-diam tersimpan kosong. */
const coord = (min: number, max: number) =>
  z.string().refine(
    (v) => v === "" || (!Number.isNaN(Number(v)) && Number(v) >= min && Number(v) <= max),
    "Koordinat tidak valid",
  );

const splitterSchema = z.object({
  name: z.string().min(1, "Wajib diisi").max(100),
  type: z.enum(["odc", "odp"]),
  ratio: z.enum(RATIOS),
  zone_id: z.string().min(1, "Pilih zone"),
  parent_id: z.string(),
  code: z.string().max(50),
  location: z.string().max(255),
  latitude: coord(-90, 90),
  longitude: coord(-180, 180),
  notes: z.string().max(500),
});
type SplitterForm = z.infer<typeof splitterSchema>;

const zoneSchema = z.object({
  name: z.string().min(1, "Wajib diisi").max(100),
  external_id: z.string().max(50),
  latitude: coord(-90, 90),
  longitude: coord(-180, 180),
});
type ZoneForm = z.infer<typeof zoneSchema>;

const useZones = () => useQuery({ queryKey: ["zones"], queryFn: () => api<Zone[]>("/api/zones") });

function SplitterDrawer({ edit, zones, onClose }: {
  edit: Splitter | null; zones: Zone[]; onClose: () => void;
}) {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ["splitter", edit?.id],
    queryFn: () => api<SplitterDetail>(`/api/splitters/${edit!.id}`),
    enabled: !!edit,
  });
  const siblings = useQuery({
    queryKey: ["splitters", "all"],
    queryFn: () => api<Splitter[]>("/api/splitters"),
  });
  const { register, handleSubmit, watch, formState } = useForm<SplitterForm>({
    resolver: zodResolver(splitterSchema),
    defaultValues: {
      name: edit?.name ?? "",
      type: (edit?.type ?? "odp") as SplitterForm["type"],
      ratio: (edit?.ratio ?? "1:8") as SplitterForm["ratio"],
      zone_id: edit?.zone_id ? String(edit.zone_id) : "",
      parent_id: edit?.parent_id ? String(edit.parent_id) : "",
      code: edit?.code ?? "",
      location: edit?.location ?? "",
      latitude: edit?.latitude != null ? String(edit.latitude) : "",
      longitude: edit?.longitude != null ? String(edit.longitude) : "",
      notes: edit?.notes ?? "",
    },
  });
  const save = useMutation({
    mutationFn: (f: SplitterForm) => {
      const body = {
        name: f.name, type: f.type, ratio: f.ratio, zone_id: Number(f.zone_id),
        parent_id: num(f.parent_id), code: f.code || null, location: f.location || null,
        latitude: num(f.latitude), longitude: num(f.longitude), notes: f.notes || null,
      };
      return edit
        ? api<SplitterDetail>(`/api/splitters/${edit.id}`, { method: "PATCH", json: body })
        : api<SplitterDetail>("/api/splitters", { method: "POST", json: body });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["splitters"] });
      qc.invalidateQueries({ queryKey: ["zones"] });
      onClose();
    },
  });
  // Induk hanya ODC dan satu zone dengan splitter ini (invariant produk, juga
  // divalidasi backend). Induk lama yang tidak lolos filter tetap ditampilkan
  // sebagai opsi fallback supaya baris legacy tetap bisa disimpan tanpa diubah.
  const watchedZone = watch("zone_id");
  const allSiblings = siblings.data ?? [];
  const parents = allSiblings.filter((s) =>
    s.id !== edit?.id && s.type === "odc" && String(s.zone_id) === watchedZone);
  const parentFallback = edit?.parent_id != null
    && !parents.some((s) => s.id === edit.parent_id)
    ? allSiblings.find((s) => s.id === edit.parent_id) : undefined;

  return (
    <Drawer
      title={edit ? `Edit ${edit.name}` : "Tambah splitter"}
      onClose={onClose}
      onSubmit={handleSubmit((f) => save.mutate(f))}
      busy={save.isPending}
      error={save.error?.message}
    >
      <Field label="Nama" error={formState.errors.name?.message}>
        <input className={input} autoFocus autoComplete="off" {...register("name")} />
      </Field>
      <Field label="External ID"><input className={input} autoComplete="off" {...register("code")} /></Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Tipe">
          <select className={input} {...register("type")}>
            {TYPES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}
          </select>
        </Field>
        <Field label="Ratio">
          <select className={input} {...register("ratio")}>
            {RATIOS.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </Field>
      </div>
      <Field label="Zone" error={formState.errors.zone_id?.message}>
        <select className={input} {...register("zone_id")}>
          <option value="">Pilih zone</option>
          {zones.map((zn) => <option key={zn.id} value={zn.id}>{zn.name}</option>)}
        </select>
      </Field>
      <Field label="Induk (ODC)">
        <select className={input} {...register("parent_id")}>
          <option value="">Tanpa induk</option>
          {parentFallback && (
            <option value={parentFallback.id}>{parentFallback.name} (induk lama)</option>
          )}
          {parents.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </Field>
      <Field label="Lokasi"><input className={input} autoComplete="off" {...register("location")} /></Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Latitude" error={formState.errors.latitude?.message}><input className={input} inputMode="decimal" {...register("latitude")} /></Field>
        <Field label="Longitude" error={formState.errors.longitude?.message}><input className={input} inputMode="decimal" {...register("longitude")} /></Field>
      </div>
      <Field label="Catatan"><input className={input} {...register("notes")} /></Field>

      {edit && (
        <div className="mt-2">
          <p className="mb-1 text-xs uppercase tracking-[0.02em] text-muted">ONU terpasang</p>
          {detail.data?.onus.length ? (
            <table className="w-full border-collapse text-sm">
              <tbody>
                {detail.data.onus.map((o) => (
                  <tr key={o.id} className="border-b last:border-0">
                    <td className={`${cell} font-mono`}>{o.splitter_port ?? "—"}</td>
                    <td className={`${cell} font-mono`}>{o.serial_number}</td>
                    <td className={cell}>{o.customer_name ?? o.name ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="text-muted">Belum ada ONU.</p>}
        </div>
      )}
    </Drawer>
  );
}

function ZoneDrawer({ edit, onClose }: { edit: Zone | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { register, handleSubmit, formState } = useForm<ZoneForm>({
    resolver: zodResolver(zoneSchema),
    defaultValues: {
      name: edit?.name ?? "",
      external_id: edit?.external_id ?? "",
      latitude: edit?.latitude != null ? String(edit.latitude) : "",
      longitude: edit?.longitude != null ? String(edit.longitude) : "",
    },
  });
  const save = useMutation({
    mutationFn: (f: ZoneForm) => {
      const body = {
        name: f.name, external_id: f.external_id || null,
        latitude: num(f.latitude), longitude: num(f.longitude),
      };
      return edit
        ? api<Zone>(`/api/zones/${edit.id}`, { method: "PATCH", json: body })
        : api<Zone>("/api/zones", { method: "POST", json: body });
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["zones"] }); onClose(); },
  });

  return (
    <Drawer
      title={edit ? `Edit ${edit.name}` : "Tambah zone"}
      onClose={onClose}
      onSubmit={handleSubmit((f) => save.mutate(f))}
      busy={save.isPending}
      error={save.error?.message}
    >
      <Field label="Nama" error={formState.errors.name?.message}>
        <input className={input} autoFocus autoComplete="off" {...register("name")} />
      </Field>
      <Field label="External ID"><input className={input} autoComplete="off" {...register("external_id")} /></Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="Latitude" error={formState.errors.latitude?.message}><input className={input} inputMode="decimal" {...register("latitude")} /></Field>
        <Field label="Longitude" error={formState.errors.longitude?.message}><input className={input} inputMode="decimal" {...register("longitude")} /></Field>
      </div>
    </Drawer>
  );
}

const presetSchema = z.object({
  name: z.string().min(1, "Wajib diisi").max(100),
  onu_type_id: z.string().min(1, "Pilih tipe ONU"),
  vlan: z.string().refine(
    (v) => v === "" || (/^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= 4094),
    "VLAN harus 1-4094"),
  download_profile: z.string().max(50),
  upload_profile: z.string().max(50),
  onu_mode: z.enum(["routing", "bridging"]),
  wan_mode: z.enum(["webpage", "dhcp", "static", "pppoe"]),
  zone_id: z.string(),
  splitter_id: z.string(),
});
type PresetForm = z.infer<typeof presetSchema>;

/** Drawer edit/tambah preset. Tidak ada halaman preset khusus di router
 *  (main.tsx di luar cakupan area ini), jadi manajemen preset tinggal di tab
 *  ketiga halaman ini — preset terikat zone/splitter, jadi ini tempatnya yang
 *  paling masuk akal tanpa menambah route baru. */
function PresetDrawer({ edit, zones, splitters, types, onClose }: {
  edit: OnuPreset | null; zones: Zone[]; splitters: Splitter[]; types: OnuType[];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { register, handleSubmit, formState } = useForm<PresetForm>({
    resolver: zodResolver(presetSchema),
    defaultValues: {
      name: edit?.name ?? "",
      onu_type_id: edit?.onu_type_id ? String(edit.onu_type_id) : "",
      vlan: edit?.vlan ? String(edit.vlan) : "",
      download_profile: edit?.download_profile ?? "",
      upload_profile: edit?.upload_profile ?? "",
      onu_mode: (edit?.onu_mode ?? "routing") as PresetForm["onu_mode"],
      wan_mode: (edit?.wan_mode ?? "dhcp") as PresetForm["wan_mode"],
      zone_id: edit?.zone_id ? String(edit.zone_id) : "",
      splitter_id: edit?.splitter_id ? String(edit.splitter_id) : "",
    },
  });
  const save = useMutation({
    mutationFn: (f: PresetForm) => {
      const body = {
        name: f.name, onu_type_id: Number(f.onu_type_id),
        vlan: f.vlan ? Number(f.vlan) : null,
        download_profile: f.download_profile || null,
        upload_profile: f.upload_profile || null,
        onu_mode: f.onu_mode, wan_mode: f.wan_mode,
        zone_id: f.zone_id ? Number(f.zone_id) : null,
        splitter_id: f.splitter_id ? Number(f.splitter_id) : null,
      };
      return edit
        ? api<OnuPreset>(`/api/onu-presets/${edit.id}`, { method: "PATCH", json: body })
        : api<OnuPreset>("/api/onu-presets", { method: "POST", json: body });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["onu-presets"] });
      onClose();
    },
  });
  return (
    <Drawer
      title={edit ? `Edit ${edit.name}` : "Tambah preset"}
      onClose={onClose}
      onSubmit={handleSubmit((f) => save.mutate(f))}
      busy={save.isPending}
      error={save.error?.message}
    >
      <Field label="Nama" error={formState.errors.name?.message}>
        <input className={input} autoFocus autoComplete="off" {...register("name")} />
      </Field>
      <Field label="Tipe ONU" error={formState.errors.onu_type_id?.message}>
        <select className={input} {...register("onu_type_id")}>
          <option value="">Pilih tipe</option>
          {types.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
      </Field>
      <Field label="VLAN (opsional)" error={formState.errors.vlan?.message}>
        <input className={input} inputMode="numeric" {...register("vlan")} />
      </Field>
      <Field label="Profile download (opsional)">
        <input className={input} autoComplete="off" {...register("download_profile")} />
      </Field>
      <Field label="Profile upload (opsional)">
        <input className={input} autoComplete="off" {...register("upload_profile")} />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Mode ONU">
          <select className={input} {...register("onu_mode")}>
            <option value="routing">routing</option>
            <option value="bridging">bridging</option>
          </select>
        </Field>
        <Field label="Mode WAN">
          <select className={input} {...register("wan_mode")}>
            <option value="webpage">webpage</option>
            <option value="dhcp">dhcp</option>
            <option value="static">static</option>
            <option value="pppoe">pppoe</option>
          </select>
        </Field>
        <Field label="Zone (opsional)">
          <select className={input} {...register("zone_id")}>
            <option value="">Tanpa zone</option>
            {zones.map((zn) => <option key={zn.id} value={zn.id}>{zn.name}</option>)}
          </select>
        </Field>
        <Field label="Splitter (opsional)">
          <select className={input} {...register("splitter_id")}>
            <option value="">Tanpa splitter</option>
            {splitters.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
      </div>
      <p className="text-xs text-muted">
        Splitter harus berada di zone yang dipilih; backend menolak pasangan
        zone/splitter yang tidak cocok.
      </p>
    </Drawer>
  );
}

export function Splitters() {
  const { isManager } = useAuth();
  const qc = useQueryClient();
  const [tab, setTab] = useState<"splitter" | "zone" | "preset">("splitter");
  const [q, setQ] = useState("");
  const [zoneId, setZoneId] = useState("");
  const [splitterDrawer, setSplitterDrawer] = useState<{ edit: Splitter | null } | null>(null);
  const [zoneDrawer, setZoneDrawer] = useState<{ edit: Zone | null } | null>(null);
  const [presetDrawer, setPresetDrawer] = useState<{ edit: OnuPreset | null } | null>(null);
  const [delSplitter, setDelSplitter] = useState<Splitter | null>(null);
  const [delZone, setDelZone] = useState<Zone | null>(null);
  const [delPreset, setDelPreset] = useState<OnuPreset | null>(null);

  const zones = useZones();
  const splitters = useQuery({
    queryKey: ["splitters", q, zoneId],
    queryFn: () => api<Splitter[]>(`/api/splitters${qs({ q, zone_id: zoneId })}`),
  });
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["splitters"] });
    qc.invalidateQueries({ queryKey: ["zones"] });
  };
  const removeSplitter = useMutation({
    mutationFn: (s: Splitter) => api<void>(`/api/splitters/${s.id}`, { method: "DELETE" }),
    onSuccess: () => { invalidate(); setDelSplitter(null); },
  });
  const removeZone = useMutation({
    mutationFn: (zn: Zone) => api<void>(`/api/zones/${zn.id}`, { method: "DELETE" }),
    onSuccess: () => { invalidate(); setDelZone(null); },
  });
  const presets = useQuery({
    queryKey: ["onu-presets"],
    queryFn: () => api<OnuPreset[]>("/api/onu-presets"),
  });
  const onuTypes = useQuery({
    queryKey: ["onu-types"],
    queryFn: () => api<OnuType[]>("/api/onu-types"),
  });
  const removePreset = useMutation({
    mutationFn: (p: OnuPreset) => api<void>(`/api/onu-presets/${p.id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["onu-presets"] });
      setDelPreset(null);
    },
  });

  const tabClass = (t: string) =>
    `h-8 px-3 text-sm ${tab === t ? "border-b-2 border-fiber font-medium" : "text-muted"}`;

  return (
    <>
      <PageTitle title="Splitters & Zone">
        {isManager && (
          tab === "splitter"
            ? <Button variant="fiber" onClick={() => setSplitterDrawer({ edit: null })}>Tambah splitter</Button>
            : tab === "zone"
              ? <Button variant="fiber" onClick={() => setZoneDrawer({ edit: null })}>Tambah zone</Button>
              : <Button variant="fiber" onClick={() => setPresetDrawer({ edit: null })}>Tambah preset</Button>
        )}
      </PageTitle>

      <div className="mb-3 flex gap-1 border-b">
        <button type="button" className={tabClass("splitter")} onClick={() => setTab("splitter")}>Splitter</button>
        <button type="button" className={tabClass("zone")} onClick={() => setTab("zone")}>Zone</button>
        <button type="button" className={tabClass("preset")} onClick={() => setTab("preset")}>Preset</button>
      </div>

      {tab === "preset" ? (
        <TableCard
          query={presets}
          loadingText="Memuat preset ..."
          empty="Belum ada preset."
          columns={["Nama", "Tipe", "VLAN", "Download", "Upload", "Mode", "Aksi"]}
          row={(p) => (
            <tr key={p.id} className="border-b last:border-0">
              <td className={cell}>{p.name}</td>
              <td className={cell}>{onuTypes.data?.find((t) => t.id === p.onu_type_id)?.name ?? p.onu_type_id}</td>
              <td className={`${cell} font-mono`}>{p.vlan ?? "—"}</td>
              <td className={cell}>{p.download_profile ?? "—"}</td>
              <td className={cell}>{p.upload_profile ?? "—"}</td>
              <td className={cell}>{p.onu_mode}/{p.wan_mode}</td>
              <td className={cell}>
                {isManager ? (
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => setPresetDrawer({ edit: p })}>Edit</Button>
                    <Button size="sm" variant="danger" onClick={() => setDelPreset(p)}>Hapus</Button>
                  </div>
                ) : "—"}
              </td>
            </tr>
          )}
        />
      ) : tab === "splitter" ? (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="Cari splitter" className={`${filterInput} w-60`} />
            <select value={zoneId} onChange={(e) => setZoneId(e.target.value)}
                    aria-label="Filter zone" className={filterInput}>
              <option value="">Semua zone</option>
              {(zones.data ?? []).map((zn) => <option key={zn.id} value={zn.id}>{zn.name}</option>)}
            </select>
          </div>
          <TableCard
            query={splitters}
            loadingText="Memuat splitter ..."
            empty="Belum ada splitter."
            columns={["Nama", "External ID", "Tipe", "Induk", "Koordinat", "Penggunaan", "Zone", "Aksi"]}
            row={(s: Splitter) => (
              <tr key={s.id} className="border-b last:border-0">
                <td className={cell}>{s.name}</td>
                <td className={`${cell} font-mono`}>{s.code ?? "—"}</td>
                <td className={cell}>{s.type.toUpperCase()}</td>
                <td className={cell}>{s.parent_name ?? "—"}</td>
                <td className={`${cell} font-mono`}>
                  {s.latitude != null && s.longitude != null ? `${s.latitude}, ${s.longitude}` : "—"}
                </td>
                <td className={cell}>
                  <UsageBar used={s.onu_count} capacity={s.capacity} />
                  {s.capacity === null && (
                    <span className="ml-2 text-xs text-down">Kapasitas belum diisi</span>
                  )}
                </td>
                <td className={cell}>{s.zone_name ?? "—"}</td>
                <td className={cell}>
                  {isManager ? (
                    <div className="flex gap-2">
                      <Button size="sm" onClick={() => setSplitterDrawer({ edit: s })}>Edit</Button>
                      <Button size="sm" variant="danger" onClick={() => setDelSplitter(s)}>Hapus</Button>
                    </div>
                  ) : "—"}
                </td>
              </tr>
            )}
          />
        </>
      ) : (
        <TableCard
          query={zones}
          loadingText="Memuat zone ..."
          empty="Belum ada zone."
          columns={["Nama", "External ID", "Splitter", "ONU", "Koordinat", "Aksi"]}
          row={(zn: Zone) => (
            <tr key={zn.id} className="border-b last:border-0">
              <td className={cell}>{zn.name}</td>
              <td className={`${cell} font-mono`}>{zn.external_id ?? "—"}</td>
              <td className={`${cell} font-mono`}>{zn.splitter_count}</td>
              <td className={`${cell} font-mono`}>{zn.onu_count}</td>
              <td className={`${cell} font-mono`}>
                {zn.latitude != null && zn.longitude != null ? `${zn.latitude}, ${zn.longitude}` : "—"}
              </td>
              <td className={cell}>
                {isManager ? (
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => setZoneDrawer({ edit: zn })}>Edit</Button>
                    <Button size="sm" variant="danger" onClick={() => setDelZone(zn)}>Hapus</Button>
                  </div>
                ) : "—"}
              </td>
            </tr>
          )}
        />
      )}

      {splitterDrawer && (
        <SplitterDrawer edit={splitterDrawer.edit} zones={zones.data ?? []}
                        onClose={() => setSplitterDrawer(null)} />
      )}
      {zoneDrawer && <ZoneDrawer edit={zoneDrawer.edit} onClose={() => setZoneDrawer(null)} />}
      {presetDrawer && (
        <PresetDrawer edit={presetDrawer.edit} zones={zones.data ?? []}
                      splitters={splitters.data ?? []} types={onuTypes.data ?? []}
                      onClose={() => setPresetDrawer(null)} />
      )}
      {delPreset && (
        <Confirm
          title={`Hapus ${delPreset.name}?`}
          body="Preset dihapus permanen. Penghapusan ditolak bila preset masih dipakai ONU."
          action="Hapus"
          busy={removePreset.isPending}
          error={removePreset.error?.message}
          onConfirm={() => removePreset.mutate(delPreset)}
          onClose={() => { removePreset.reset(); setDelPreset(null); }}
        />
      )}
      {delSplitter && (
        <Confirm
          title={`Hapus ${delSplitter.name}?`}
          body={delSplitter.onu_count > 0
            ? `Splitter dipakai ${delSplitter.onu_count} ONU, penghapusan akan ditolak.`
            : "Splitter dihapus permanen. Penghapusan juga ditolak bila splitter masih dipakai preset atau masih punya splitter turunan."}
          action="Hapus"
          busy={removeSplitter.isPending}
          error={removeSplitter.error?.message}
          onConfirm={() => removeSplitter.mutate(delSplitter)}
          onClose={() => { removeSplitter.reset(); setDelSplitter(null); }}
        />
      )}
      {delZone && (
        <Confirm
          title={`Hapus ${delZone.name}?`}
          body={delZone.splitter_count + delZone.onu_count > 0
            ? "Zone masih dipakai splitter atau ONU, penghapusan akan ditolak."
            : "Zone dihapus permanen. Penghapusan juga ditolak bila zone masih dipakai preset."}
          action="Hapus"
          busy={removeZone.isPending}
          error={removeZone.error?.message}
          onConfirm={() => removeZone.mutate(delZone)}
          onClose={() => { removeZone.reset(); setDelZone(null); }}
        />
      )}
    </>
  );
}
