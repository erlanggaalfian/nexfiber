/** Form Otorisasi — PRD 3.4.4, wireframe DESIGN 12.4 (dua kolom: Layanan kiri, Pelanggan kanan).
 *  Mengirim POST /api/onus/authorize lalu memantau job sampai selesai.
 *
 *  Speed profile dipisah jadi 2 dropdown (download/upload, Opsi A) — tiap arah pilih
 *  baris speed_profiles sendiri, bebas dikombinasikan.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useParams } from "react-router";
import * as z from "zod";
import { Field, input } from "../components/crud";
import { ErrorState, PageTitle, Panel, Skeleton } from "../components/data";
import { Button } from "../components/ui/button";
import {
  api, qs, type OnuPreset, type OnuType, type PendingOnu, type SpeedProfile, type Splitter,
  type SplitterDetail, type Vlan, type Zone,
} from "../lib/api";
import { DONE, useJob } from "../lib/jobs";

const ALL = "";
const nullable = (v: string) => (v === "" ? null : v);
// numOrNull lama: input non-numerik ("abc") jadi NaN lalu JSON null diam-diam —
// koordinat/port splitter yang salah ketik hilang tanpa pesan. Sekarang NaN tetap
// null di sini sebagai jaring pengaman, tapi schema di bawah MENOLAK input
// non-numerik sebelum submit, jadi pengguna melihat pesannya.
const numOrNull = (v: string) => {
  if (v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};
const isNumIn = (v: string, min: number, max: number) => {
  if (v === "") return true;
  const n = Number(v);
  return Number.isFinite(n) && n >= min && n <= max;
};

const schema = z.object({
  onu_type_id: z.string().min(1, "Pilih tipe ONU"),
  download_speed_profile_id: z.string().min(1, "Pilih profile download"),
  upload_speed_profile_id: z.string().min(1, "Pilih profile upload"),
  vlan_id: z.string().min(1, "Pilih VLAN"),
  onu_mode: z.enum(["routing", "bridging"]),
  wan_mode: z.enum(["webpage", "dhcp", "static", "pppoe"]),
  pppoe_username: z.string().max(100),
  pppoe_password: z.string().max(100),
  customer_name: z.string().min(1, "Wajib diisi").max(255),
  customer_id: z.string().min(1, "Wajib diisi").max(50),
  contact: z.string().max(100),
  address: z.string().max(500),
  external_id: z.string().max(50),
  zone_id: z.string(),
  splitter_id: z.string(),
  splitter_port: z.string().refine((v) => v === "" || (/^\d+$/.test(v) && Number(v) >= 1), {
    message: "Port splitter harus angka ≥ 1",
  }),
  latitude: z.string().refine((v) => isNumIn(v, -90, 90), {
    message: "Latitude harus angka -90 s.d. 90",
  }),
  longitude: z.string().refine((v) => isNumIn(v, -180, 180), {
    message: "Longitude harus angka -180 s.d. 180",
  }),
}).refine((f) => f.onu_mode !== "routing" || f.wan_mode !== "pppoe" || f.pppoe_username.length > 0, {
  // Mode WAN hanya dirender saat Routing; tanpa cek onu_mode, Bridging gagal validasi di
  // field yang tidak tampak dan tombol Otorisasi diam saja.
  path: ["pppoe_username"], message: "Wajib diisi untuk PPPoE",
});
type Form = z.infer<typeof schema>;

const DEFAULTS: Form = {
  onu_type_id: "", download_speed_profile_id: "", upload_speed_profile_id: "", vlan_id: "",
  onu_mode: "routing", wan_mode: "pppoe",
  pppoe_username: "", pppoe_password: "", customer_name: "", customer_id: "", contact: "",
  address: "", external_id: "", zone_id: "", splitter_id: "", splitter_port: "",
  latitude: "", longitude: "",
};

export function AuthorizeOnu() {
  const { oltId = "", serial = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [jobId, setJobId] = useState<number | null>(null);
  const [presetId, setPresetId] = useState(ALL);
  const [presetName, setPresetName] = useState("");
  const [note, setNote] = useState("");

  const pending = useQuery({
    queryKey: ["pending", oltId],
    queryFn: () => api<PendingOnu[]>(`/api/onus/pending${qs({ olt_id: oltId })}`),
  });
  const onu = (pending.data ?? []).find((p) => p.serial_number === serial);

  const onuTypes = useQuery({ queryKey: ["onu-types"], queryFn: () => api<OnuType[]>("/api/onu-types?active_only=true") });
  const profiles = useQuery({
    queryKey: ["speed-profiles", oltId],
    queryFn: () => api<SpeedProfile[]>(`/api/speed-profiles${qs({ olt_id: oltId })}`),
  });
  const vlans = useQuery({
    queryKey: ["vlans", oltId],
    queryFn: () => api<Vlan[]>(`/api/vlans${qs({ olt_id: oltId })}`),
  });
  const zones = useQuery({ queryKey: ["zones"], queryFn: () => api<Zone[]>("/api/zones") });
  const splitters = useQuery({ queryKey: ["splitters", "all"], queryFn: () => api<Splitter[]>("/api/splitters") });
  const presets = useQuery({ queryKey: ["onu-presets"], queryFn: () => api<OnuPreset[]>("/api/onu-presets") });

  const { register, handleSubmit, watch, reset, getValues, formState } = useForm<Form>({
    resolver: zodResolver(schema), defaultValues: DEFAULTS,
  });
  const wanMode = watch("wan_mode");
  const onuMode = watch("onu_mode");
  const splitterId = watch("splitter_id");
  const zoneId = watch("zone_id");
  // Port splitter yang sudah terpakai tidak boleh dipilih (PRD 3.4.4) — ambil dari detail splitter.
  const splitterDetail = useQuery({
    queryKey: ["splitter", splitterId],
    queryFn: () => api<SplitterDetail>(`/api/splitters/${splitterId}`),
    enabled: !!splitterId,
  });

  // "Gunakan preset": isi otomatis field di bawah (PRD 3.4.4). Profile disimpan per nama,
  // jadi dicocokkan ke baris speed_profiles / vlans OLT ini saat dipakai.
  useEffect(() => {
    const p = (presets.data ?? []).find((x) => String(x.id) === presetId);
    if (!p) return;
    const dn = (profiles.data ?? []).find((s) => s.direction === "download" && s.name === p.download_profile);
    const up = (profiles.data ?? []).find((s) => s.direction === "upload" && s.name === p.upload_profile);
    const vlan = (vlans.data ?? []).find((v) => v.vlan_id === p.vlan);
    reset({
      ...getValues(),
      onu_type_id: String(p.onu_type_id),
      download_speed_profile_id: dn ? String(dn.id) : "",
      upload_speed_profile_id: up ? String(up.id) : "",
      vlan_id: vlan ? String(vlan.id) : "",
      onu_mode: p.onu_mode,
      wan_mode: p.wan_mode,
      zone_id: p.zone_id ? String(p.zone_id) : "",
      splitter_id: p.splitter_id ? String(p.splitter_id) : "",
    });
  }, [presetId, presets.data, profiles.data, vlans.data, reset, getValues]);

  const authorize = useMutation({
    mutationFn: (f: Form) => {
      const dn = (profiles.data ?? []).find((s) => String(s.id) === f.download_speed_profile_id);
      const up = (profiles.data ?? []).find((s) => String(s.id) === f.upload_speed_profile_id);
      const pppoe = f.onu_mode === "routing" && f.wan_mode === "pppoe";
      return api<{ job_id: number }>("/api/onus/authorize", {
        method: "POST",
        json: {
          olt_id: Number(oltId), serial_number: serial,
          customer_name: f.customer_name, customer_id: f.customer_id,
          name: f.customer_name.slice(0, 100),
          contact: nullable(f.contact), address: nullable(f.address),
          external_id: nullable(f.external_id),
          onu_type: onu?.onu_type ?? null, onu_type_id: Number(f.onu_type_id),
          vlan_id: Number(f.vlan_id),
          download_speed_profile_id: Number(f.download_speed_profile_id),
          upload_speed_profile_id: Number(f.upload_speed_profile_id),
          line_profile_id: dn?.device_profile_id ?? null,
          srv_profile_id: up?.device_profile_id ?? null,
          zone_id: numOrNull(f.zone_id), splitter_id: numOrNull(f.splitter_id),
          splitter_port: numOrNull(f.splitter_port),
          preset_id: numOrNull(presetId),
          onu_mode: f.onu_mode,
          wan_mode: f.onu_mode === "routing" ? f.wan_mode : null,
          pppoe_username: pppoe ? nullable(f.pppoe_username) : null,
          pppoe_password: pppoe ? nullable(f.pppoe_password) : null,
          latitude: numOrNull(f.latitude), longitude: numOrNull(f.longitude),
        },
      });
    },
    onSuccess: (r) => setJobId(r.job_id),
  });

  const savePreset = useMutation({
    mutationFn: () => {
      const f = getValues();
      const dn = (profiles.data ?? []).find((s) => String(s.id) === f.download_speed_profile_id);
      const up = (profiles.data ?? []).find((s) => String(s.id) === f.upload_speed_profile_id);
      const vlan = (vlans.data ?? []).find((v) => String(v.id) === f.vlan_id);
      return api<OnuPreset>("/api/onu-presets", {
        method: "POST",
        json: {
          name: presetName, onu_type_id: Number(f.onu_type_id), vlan: vlan?.vlan_id ?? null,
          download_profile: dn?.name ?? null, upload_profile: up?.name ?? null,
          onu_mode: f.onu_mode, wan_mode: f.wan_mode,
          zone_id: numOrNull(f.zone_id), splitter_id: numOrNull(f.splitter_id),
        },
      });
    },
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ["onu-presets"] });
      setPresetName("");
      setNote(`Preset "${p.name}" disimpan.`);
    },
    onError: (e: Error) => setNote(e.message),
  });

  // Resync untuk baris gagal: authorize ulang dari form yang sama PASTI ditolak
  // duplikat serial di backend (baris gagal dari percobaan pertama masih ada),
  // jadi tombol "Coba lagi" lama menyesatkan. Jalur pemulihan yang benar adalah
  // resync job atas baris gagal itu (diizinkan untuk config_state=failed).
  const resync = useMutation({
    mutationFn: () => api<{ job_id: number }>(`/api/onus/${serial}/resync`, { method: "POST" }),
    onSuccess: (r) => setJobId(r.job_id),
    onError: (e: Error) => setNote(e.message),
  });

  const job = useJob(jobId);
  useEffect(() => {
    // URL Detail ONU memakai id internal (bukan serial): id-nya sudah ada di job hasil
    // authorize (`job.onu_id`), jadi tidak perlu request tambahan untuk menukar serial->id.
    const onuId = job.data?.onu_id;
    if (job.data?.status === "success" && onuId != null) navigate(`/onu/${onuId}`);
  }, [job.data?.status, job.data?.onu_id, navigate]);

  if (pending.isPending) return <Skeleton text="Memuat ONU ..." rows={4} />;
  if (pending.isError) {
    return <ErrorState message={pending.error.message} onRetry={() => pending.refetch()} />;
  }
  if (!onu) {
    return (
      <ErrorState message={`${serial} tidak ada di daftar unconfigured OLT ini (mungkin sudah diotorisasi).`} />
    );
  }

  const jobBusy = authorize.isPending || (job.data != null && !DONE.has(job.data.status));
  const jobFailed = job.data?.status === "failed";
  // Dropdown splitter difilter menurut OLT + zone yang dipilih (backend juga
  // menolak splitter OLT/PON/zone lain, jadi dropdown yang menampilkan semuanya
  // hanya menghasilkan submit yang pasti ditolak). Splitter yang sedang
  // terpilih dipertahankan sebagai opsi fallback supaya nilai dari preset
  // tidak hilang diam-diam saat filter berubah.
  const filteredSplitters = (splitters.data ?? []).filter((s) =>
    (s.olt_id == null || s.olt_id === Number(oltId)) &&
    (zoneId === "" || s.zone_id == null || s.zone_id === Number(zoneId)));
  const selectedSplitter = (splitters.data ?? []).find((s) => String(s.id) === splitterId);
  const splitterOptions = selectedSplitter &&
    !filteredSplitters.some((s) => s.id === selectedSplitter.id)
    ? [...filteredSplitters, selectedSplitter] : filteredSplitters;
  const splitter = (splitters.data ?? []).find((s) => String(s.id) === splitterId);
  const usedPorts = new Set(
    (splitterDetail.data?.onus ?? []).map((o) => o.splitter_port).filter((p): p is number => p != null),
  );

  return (
    <>
      <Link to="/unconfigured" className="mb-2 inline-block text-fiber hover:underline">← Unconfigured</Link>
      <PageTitle title="Otorisasi ONU">
        <select value={presetId} onChange={(e) => setPresetId(e.target.value)}
                aria-label="Gunakan preset" className={`${input} w-44`}>
          <option value={ALL}>Tidak ada preset</option>
          {(presets.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <input value={presetName} onChange={(e) => setPresetName(e.target.value)}
               placeholder="Nama preset baru" aria-label="Nama preset baru"
               className={`${input} w-44`} />
        <Button disabled={!presetName || savePreset.isPending} onClick={() => savePreset.mutate()}>
          Simpan sebagai preset
        </Button>
      </PageTitle>

      <p className="mb-3 font-mono text-muted">
        {onu.serial_number} · {onu.olt_name} · {onu.slot}/{onu.port}
        {onu.onu_type ? ` · ${onu.onu_type}` : ""}
      </p>
      {note && <p className="mb-3 text-muted" role="status">{note}</p>}

      <form onSubmit={handleSubmit((f) => authorize.mutate(f))}>
        <div className="entrance grid gap-3 lg:grid-cols-2">
          <Panel title="Layanan" className="p-4">
            <Field label="Tipe ONU *" error={formState.errors.onu_type_id?.message}>
              <select className={input} {...register("onu_type_id")}>
                <option value="">Pilih tipe ONU</option>
                {(onuTypes.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </Field>
            <Field label="Profile download *" error={formState.errors.download_speed_profile_id?.message}>
              <select className={input} {...register("download_speed_profile_id")}>
                <option value="">Pilih profile download</option>
                {(profiles.data ?? []).filter((s) => s.direction === "download").map((s) => (
                  <option key={s.id} value={s.id}>{s.name} · {(s.speed_kbps / 1000).toFixed(0)} Mbps</option>
                ))}
              </select>
            </Field>
            <Field label="Profile upload *" error={formState.errors.upload_speed_profile_id?.message}>
              <select className={input} {...register("upload_speed_profile_id")}>
                <option value="">Pilih profile upload</option>
                {(profiles.data ?? []).filter((s) => s.direction === "upload").map((s) => (
                  <option key={s.id} value={s.id}>{s.name} · {(s.speed_kbps / 1000).toFixed(0)} Mbps</option>
                ))}
              </select>
            </Field>
            <Field label="VLAN *" error={formState.errors.vlan_id?.message}>
              <select className={input} {...register("vlan_id")}>
                <option value="">Pilih VLAN</option>
                {(vlans.data ?? []).map((v) => <option key={v.id} value={v.id}>{v.vlan_id} · {v.name}</option>)}
              </select>
            </Field>
            <Field label="Mode ONU *">
              <select className={input} {...register("onu_mode")}>
                <option value="routing">Routing</option>
                <option value="bridging">Bridging</option>
              </select>
            </Field>
            {onuMode === "routing" && (
              <Field label="Mode WAN *">
                <select className={input} {...register("wan_mode")}>
                  <option value="webpage">Setup via webpage ONU</option>
                  <option value="dhcp">DHCP</option>
                  <option value="static">Static IP</option>
                  <option value="pppoe">PPPoE</option>
                </select>
              </Field>
            )}
            {onuMode === "routing" && wanMode === "pppoe" && (
              <>
                <Field label="PPPoE username *" error={formState.errors.pppoe_username?.message}>
                  <input className={input} autoComplete="off" {...register("pppoe_username")} />
                </Field>
                <Field label="PPPoE password">
                  <input className={input} type="password" autoComplete="new-password"
                         {...register("pppoe_password")} />
                </Field>
              </>
            )}
          </Panel>

          <Panel title="Pelanggan" className="p-4">
            <Field label="Nama pelanggan *" error={formState.errors.customer_name?.message}>
              <input className={input} autoFocus autoComplete="off" {...register("customer_name")} />
            </Field>
            <Field label="Customer ID *" error={formState.errors.customer_id?.message}>
              <input className={input} autoComplete="off" {...register("customer_id")} />
            </Field>
            <Field label="Kontak (HP/WA)"><input className={input} autoComplete="off" {...register("contact")} /></Field>
            <Field label="Alamat"><input className={input} autoComplete="off" {...register("address")} /></Field>
            <Field label="ONU External ID"><input className={input} autoComplete="off" {...register("external_id")} /></Field>
            <Field label="Zone">
              <select className={input} {...register("zone_id")}>
                <option value="">Tanpa zone</option>
                {(zones.data ?? []).map((zn) => <option key={zn.id} value={zn.id}>{zn.name}</option>)}
              </select>
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Splitter (ODB)">
                <select className={input} {...register("splitter_id")}>
                  <option value="">Tanpa splitter</option>
                  {splitterOptions.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </Field>
              <Field label="Port splitter">
                <select className={input} {...register("splitter_port")} disabled={!splitterId}>
                  <option value="">—</option>
                  {Array.from({ length: splitter?.capacity ?? 0 }, (_, i) => i + 1)
                    .filter((p) => !usedPorts.has(p))
                    .map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
              <Field label="Latitude"><input className={input} inputMode="decimal" {...register("latitude")} /></Field>
              <Field label="Longitude"><input className={input} inputMode="decimal" {...register("longitude")} /></Field>
              <Button className="mb-3" onClick={() => navigator.geolocation?.getCurrentPosition((pos) =>
                reset({ ...getValues(), latitude: String(pos.coords.latitude),
                        longitude: String(pos.coords.longitude) }))}>
                Gunakan GPS
              </Button>
            </div>
          </Panel>
        </div>

        {(authorize.error || jobFailed) && (
          <p className="mt-3 text-down" role="alert">
            {authorize.error?.message ?? job.data?.error_message ?? "OLT menolak perintah"}
          </p>
        )}
        {jobFailed && (
          <p className="mt-3 text-muted" role="status">
            Baris ONU gagal ini sudah ada di database, jadi mengirim authorize yang sama
            akan ditolak duplikat serial. Pakai Resync untuk meng-authorize ulang
            baris gagal tersebut, atau hapus barisnya dulu bila ingin mulai dari awal.
          </p>
        )}
        <div className="mt-3 flex justify-end gap-2">
          <Button onClick={() => navigate("/unconfigured")}>Batal</Button>
          {jobFailed ? (
            <Button type="button" variant="primary" disabled={resync.isPending || jobBusy}
                    onClick={() => resync.mutate()}>
              {resync.isPending ? "Mengirim resync ..." : "Resync (perbaiki baris gagal)"}
            </Button>
          ) : (
            <Button type="submit" variant="primary" disabled={jobBusy}>
              {jobBusy ? "Mengirim ke OLT ..." : "Otorisasi"}
            </Button>
          )}
        </div>
      </form>
    </>
  );
}
