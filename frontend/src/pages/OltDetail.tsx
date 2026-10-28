/** Detail OLT (PRD 3.4.7, DESIGN 12). Satu halaman, tab Monitoring / VLANs / Konfigurasi /
 *  Daftar ONU. Role user hanya melihat Monitoring dan Daftar ONU.
 *
 *  Semua tabel/drawer memakai komponen bersama di components/crud.tsx dan data.tsx — jangan
 *  menulis markup tabel atau drawer sendiri di sini, itu yang membuat halaman kehilangan
 *  animasi MOTION 2 (lihat bug UserManagement sebelumnya).
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowClockwise, ArrowLeft } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams, useSearchParams } from "react-router";
import * as z from "zod";
import {
  Confirm, Drawer, Field, JobTrace, MobileCard, TableCard, UsageBar, input,
} from "../components/crud";
import {
  Bar, Empty, ErrorState, Panel, PageTitle, SignalBar, Skeleton, StatusBadge, fmtDateTime, nf,
} from "../components/data";
import { Button } from "../components/ui/button";
import {
  api, qs, type OltDetail as Detail, type OltInterface, type OnuRow, type Page, type Vlan,
} from "../lib/api";
import { OltSyncProgress } from "../components/OltSyncProgress";
import { useAuth } from "../lib/auth";
import { DONE, useJob } from "../lib/jobs";

const TABS = ["Monitoring", "VLANs", "Interfaces", "Konfigurasi", "Daftar ONU"] as const;
type Tab = (typeof TABS)[number];
const MANAGER_ONLY: Tab[] = ["VLANs", "Interfaces", "Konfigurasi"];

const VLAN_TYPES = ["internet", "management", "voip", "iptv", "other"] as const;
const TAG_ACTIONS = ["tag", "transparent", "translate"] as const;
// 10G hanya ada di port xge; port gei ditolak perangkat kalau dipaksa 10000.
const PORT_SPEEDS = ["10", "100", "1000", "10000"] as const;
const DUPLEXES = ["full", "half"] as const;
const isTenGig = (port: string) => port.toLowerCase().startsWith("xgei");

function fmtUptime(seconds: number | null) {
  if (seconds === null) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  // Satuan Indonesia: h=hari, j=jam, m=menit — jangan pakai "h" untuk jam supaya tidak rancu.
  return d > 0 ? `${d} hari ${h} jam` : h > 0 ? `${h} jam ${m} mnt` : `${m} menit`;
}

const pct = (v: number | null) => (v === null ? "—" : `${Number(v).toFixed(0)}%`);

/** Satu angka besar + bar, pola sama dengan sel Dashboard (DESIGN 12.2). */
function Metric({ label, value, fill }: { label: string; value: string; fill?: number | null }) {
  const width = fill === null || fill === undefined ? 0 : Math.min(Math.max(fill, 0), 100);
  const tone = width >= 90 ? "bg-down" : width >= 75 ? "bg-warn" : "bg-fiber";
  return (
    <div className="bg-surface p-3 lg:p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="font-mono text-metric font-semibold">{value}</p>
      {fill !== undefined && (
        <Bar pct={width} tone={tone} className="mt-1 w-full" />
      )}
    </div>
  );
}

function Monitoring({ d, oltId }: { d: Detail; oltId: number }) {
  const { isManager } = useAuth();
  const qc = useQueryClient();
  // Pola sama dengan PortsDrawer: simpan job_id, tampilkan JobTrace, dan
  // refresh detail HANYA saat job SELESAI — sebelumnya job_id dibuang di
  // onSuccess dan refresh.error tidak pernah dirender, jadi gagal refresh
  // tidak terlihat di tab ini.
  const [jobId, setJobId] = useState<number | null>(null);
  const refresh = useMutation({
    mutationFn: () => api<{ job_id: number }>(`/api/olts/${oltId}/refresh-metrics`, { method: "POST" }),
    onSuccess: (r) => setJobId(r.job_id),
  });
  const job = useJob(jobId);
  useEffect(() => {
    if (jobId !== null && job.data && DONE.has(job.data.status)) {
      qc.invalidateQueries({ queryKey: ["olts", oltId, "detail"] });
    }
  }, [job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const pon = {
    isPending: false, isError: false, error: null, data: d.pon_ports, refetch: () => {},
  };
  return (
    <>
      <div className="stagger mb-3 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line/60 bg-line lg:grid-cols-4">
        <Metric label="CPU" value={pct(d.cpu_pct)} fill={d.cpu_pct} />
        <Metric label="RAM" value={pct(d.ram_pct)} fill={d.ram_pct} />
        <Metric
          label="Suhu"
          value={d.temperature_c === null ? "—" : `${Number(d.temperature_c).toFixed(0)}°C`}
        />
        <Metric label="Uptime" value={fmtUptime(d.uptime_seconds)} />
      </div>
      {/* Panel lama dihapus bingkainya: isinya HANYA tabel, dan kartu tabel
          baru dari TableCard akan menjadi bingkai ganda bila Panel dipertahankan.
          Judul + tombol Refresh dipertahankan apa adanya di kepala polos. */}
      <section className="entrance mb-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h2 className="text-xs font-medium uppercase tracking-[0.02em] text-muted">Port PON</h2>
          {isManager && (
            <Button size="sm" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              <ArrowClockwise size={14} /> Refresh
            </Button>
          )}
        </div>
        <TableCard
            query={pon}
            columns={["PON", "Status", "ONU", "Sinkron terakhir"]}
            card={(p) => (
              <MobileCard key={p.id}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono font-medium">{p.slot}/{p.port}</span>
                  <StatusBadge status={p.oper_state === "up" ? "online" : "offline"} withLabel />
                </div>
                <p className="text-xs text-muted"><UsageBar used={p.onu_count} capacity={p.capacity} /></p>
                <p className="font-mono text-xs text-muted">{fmtDateTime(p.last_sync_at)}</p>
              </MobileCard>
            )}
            empty="Belum ada port PON tersinkron. Jalankan Refresh untuk memindai OLT."
            loadingText="Memuat port PON ..."
            row={(p) => (
              <tr key={p.id}>
                <td className="font-mono font-semibold">{p.slot}/{p.port}</td>
                <td><StatusBadge status={p.oper_state === "up" ? "online" : "offline"} withLabel /></td>
                <td><UsageBar used={p.onu_count} capacity={p.capacity} /></td>
                <td className="text-muted">{fmtDateTime(p.last_sync_at)}</td>
              </tr>
            )}
        />
      </section>
      {refresh.isError && (
        <Panel title="Refresh gagal">
          <p className="text-down">{refresh.error.message}</p>
        </Panel>
      )}
      <JobTrace jobId={jobId} />
      {d.last_error && (
        <Panel title="Kesalahan terakhir">
          <p className="text-down">{d.last_error}</p>
        </Panel>
      )}
    </>
  );
}

type VlanForm = z.infer<typeof vlanSchema>;
const vlanNum = (min: number, max: number, label: string) =>
  z.string().refine(
    (v) => v === "" || (/^\d+$/.test(v) && Number(v) >= min && Number(v) <= max),
    `${label} harus ${min}-${max}`,
  );
const vlanSchema = z.object({
  vlan_id: z.string().refine(
    (v) => /^\d+$/.test(v) && Number(v) >= 1 && Number(v) <= 4094, "Angka 1-4094"),
  name: z.string().min(1).max(100),
  type: z.enum(VLAN_TYPES),
  description: z.string().max(255),
  gemport: z.string().refine(
    (v) => v === "" || (/^\d+$/.test(v) && Number(v) >= 1), "GEM port harus >= 1"),
  tag_action: z.enum(TAG_ACTIONS),
  user_vlan: vlanNum(1, 4094, "User VLAN"),
});

function VlanDrawer({ oltId, edit, onClose }: { oltId: number; edit: Vlan | null; onClose: () => void }) {
  const qc = useQueryClient();
  const { register, handleSubmit, formState } = useForm<VlanForm>({
    resolver: zodResolver(vlanSchema),
    defaultValues: {
      vlan_id: edit ? String(edit.vlan_id) : "",
      name: edit?.name ?? "",
      type: (edit?.type ?? "internet") as VlanForm["type"],
      description: edit?.description ?? "",
      gemport: edit?.gemport ? String(edit.gemport) : "",
      tag_action: (edit?.tag_action ?? "tag") as VlanForm["tag_action"],
      user_vlan: edit?.user_vlan ? String(edit.user_vlan) : "",
    },
  });

  // Buat VLAN OLT mengembalikan job_id (VlanCreated) — sebelumnya dibuang
  // karena respons diketik sebagai Vlan, jadi drawer menutup dan tabel
  // di-refresh padahal perangkat belum tentu membuat VLAN. Sekarang drawer
  // tetap terbuka dengan JobTrace sampai job selesai; hanya job sukses yang
  // menutup drawer. Edit (PATCH, tanpa job) dan VLAN global (job_id null)
  // tetap menutup langsung seperti dulu.
  const [jobId, setJobId] = useState<number | null>(null);
  const save = useMutation({
    mutationFn: (f: VlanForm) => {
      const common = {
        name: f.name, type: f.type, description: f.description || null,
        gemport: f.gemport ? Number(f.gemport) : null, tag_action: f.tag_action,
        user_vlan: f.user_vlan ? Number(f.user_vlan) : null,
      };
      // vlan_id tidak bisa diubah: itu identitas objek di perangkat (backend menolaknya).
      return edit
        ? api<Vlan>(`/api/vlans/${edit.id}`, { method: "PATCH", json: common })
        : api<Vlan & { job_id: number | null }>("/api/vlans", {
            method: "POST",
            json: { ...common, olt_id: oltId, vlan_id: Number(f.vlan_id) },
          });
    },
    onSuccess: (r) => {
      // Cabang edit mengembalikan Vlan tanpa job_id; TS tidak bisa menyempitkan
      // union lewat `in` di sini, jadi baca lewat cast eksplisit.
      const jid = (r as Vlan & { job_id?: number | null }).job_id;
      if (!edit && jid !== undefined && jid !== null) {
        setJobId(jid);
      } else {
        qc.invalidateQueries({ queryKey: ["olts", oltId, "vlans"] });
        onClose();
      }
    },
  });
  const job = useJob(jobId);
  useEffect(() => {
    if (jobId !== null && job.data && DONE.has(job.data.status)) {
      qc.invalidateQueries({ queryKey: ["olts", oltId, "vlans"] });
      if (job.data.status === "success") onClose();
    }
  }, [job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Drawer
      title={edit ? `Edit VLAN ${edit.vlan_id}` : "Tambah VLAN"}
      onClose={onClose}
      onSubmit={handleSubmit((f) => save.mutate(f))}
      busy={save.isPending || jobId !== null}
      error={save.error?.message}
    >
      <Field label="Nomor VLAN (1-4094)" error={formState.errors.vlan_id?.message}>
        <input className={input} {...register("vlan_id")} disabled={!!edit} inputMode="numeric" />
      </Field>
      <Field label="Nama" error={formState.errors.name?.message}>
        <input className={input} {...register("name")} />
      </Field>
      <Field label="Tipe">
        <select className={input} {...register("type")}>
          {VLAN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </Field>
      <Field label="Tag action">
        <select className={input} {...register("tag_action")}>
          {TAG_ACTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </Field>
      <Field label="GEM port (opsional)" error={formState.errors.gemport?.message}>
        <input className={input} {...register("gemport")} inputMode="numeric" />
      </Field>
      <Field label="User VLAN (opsional)" error={formState.errors.user_vlan?.message}>
        <input className={input} {...register("user_vlan")} inputMode="numeric" />
      </Field>
      <Field label="Deskripsi" error={formState.errors.description?.message}>
        <input className={input} {...register("description")} />
      </Field>
      {edit && (
        <>
          <p className="text-xs text-muted">
            Deskripsi, GEM port, tag action, dan user VLAN hanya tersimpan di database
            untuk VLAN yang sudah ada; tidak dikirim ulang ke perangkat.
          </p>
          <p className="text-xs text-muted">
            Mengubah tipe VLAN yang masih dirujuk ONU, speed profile, atau preset
            ditolak backend — lepas dulu rujukannya, atau hapus dan buat ulang VLAN.
          </p>
        </>
      )}
      {!edit && (
        <p className="text-xs text-muted">
          Menyimpan akan mengantre job pembuatan VLAN di OLT. VLAN baru tampil
          tidak aktif sampai job pembuatan sukses di perangkat.
        </p>
      )}
      <JobTrace jobId={jobId} />
    </Drawer>
  );
}

/** Tagged/untagged per port uplink. Simpan = job push ke OLT, bukan panggilan langsung. */
function PortsDrawer({ oltId, vlan, ports, onClose }: {
  oltId: number; vlan: Vlan; ports: string[]; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [value, setValue] = useState<Record<string, string>>(() => ({ ...vlan.uplink_ports }));
  const [jobId, setJobId] = useState<number | null>(null);
  // Port yang tersimpan di DB tapi tidak ada di daftar sinkron tetap dirender:
  // kalau tidak, penugasan lama tidak terlihat dan tidak bisa diubah.
  const allPorts = [...new Set([...ports, ...Object.keys(vlan.uplink_ports ?? {})])];
  const removed = Object.keys(vlan.uplink_ports ?? {})
    .filter((p) => (value[p] ?? "") === "");
  const save = useMutation({
    mutationFn: () => {
      const picked = Object.fromEntries(Object.entries(value).filter(([, v]) => v !== ""));
      return api<{ job_id: number }>(`/api/vlans/${vlan.id}/ports`, {
        method: "PUT", json: { ports: picked },
      });
    },
    // Drawer dibiarkan terbuka supaya jejak CLI job-nya terbaca di tempat.
    // Tabel baru di-refresh saat job SELESAI, bukan saat antrean dibuat — kalau
    // tidak, tabel menampilkan konfigurasi yang belum tentu sampai ke perangkat.
    onSuccess: (r) => setJobId(r.job_id),
  });
  const job = useJob(jobId);
  useEffect(() => {
    if (jobId !== null && job.data && DONE.has(job.data.status)) {
      qc.invalidateQueries({ queryKey: ["olts", oltId, "vlans"] });
    }
  }, [job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Drawer
      title={`Port uplink VLAN ${vlan.vlan_id}`}
      onClose={onClose}
      onSubmit={() => save.mutate()}
      busy={save.isPending}
      error={save.error?.message}
    >
      {allPorts.length === 0 ? (
        <p className="text-muted">
          Daftar port uplink belum tersinkron. Jalankan Refresh di tab Monitoring dulu.
        </p>
      ) : (
        allPorts.map((port) => (
          <Field key={port} label={ports.includes(port) ? port : `${port} (tersimpan)`}>
            <select
              className={input}
              value={value[port] ?? ""}
              onChange={(e) => setValue((v) => ({ ...v, [port]: e.target.value }))}
            >
              <option value="">Tidak dikonfigurasi</option>
              <option value="tagged">Tagged</option>
              <option value="untagged">Untagged</option>
            </select>
          </Field>
        ))
      )}
      {removed.length > 0 && (
        <p className="text-xs text-down">
          Port {removed.join(", ")} yang diubah ke "Tidak dikonfigurasi" tidak akan
          dihapus dari perangkat pada versi ini (driver belum mendukung perintah
          hapus); nilai tersimpannya dipertahankan.
        </p>
      )}
      <p className="text-xs text-muted">
        Menyimpan mengantre job push ke OLT. Untagged otomatis mengubah port ke mode hybrid.
      </p>
      <JobTrace jobId={jobId} />
    </Drawer>
  );
}

function Vlans({ oltId, uplinkPorts }: { oltId: number; uplinkPorts: string[] }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<Vlan | null>(null);
  const [adding, setAdding] = useState(false);
  const [ports, setPorts] = useState<Vlan | null>(null);
  const [remove, setRemove] = useState<Vlan | null>(null);
  const [delJob, setDelJob] = useState<number | null>(null);

  const q = useQuery({
    queryKey: ["olts", oltId, "vlans"],
    queryFn: () => api<Vlan[]>(`/api/vlans${qs({ olt_id: oltId })}`),
  });

  const del = useMutation({
    mutationFn: (v: Vlan) => api<{ job_id: number | null }>(`/api/vlans/${v.id}`, { method: "DELETE" }),
    onSuccess: (r) => {
      // VLAN global dihapus langsung tanpa job: tutup dialog dan refresh.
      // VLAN OLT: dialog dibiarkan terbuka sampai job selesai (lihat effect di
      // bawah); tabel TIDAK di-refresh saat antrean dibuat, supaya baris tidak
      // hilang seolah perangkat sudah menghapus VLAN.
      if (r.job_id === null) {
        setRemove(null);
        qc.invalidateQueries({ queryKey: ["olts", oltId, "vlans"] });
      } else {
        setDelJob(r.job_id);
      }
    },
  });
  const delJobData = useJob(delJob);
  useEffect(() => {
    if (delJob !== null && delJobData.data && DONE.has(delJobData.data.status)) {
      qc.invalidateQueries({ queryKey: ["olts", oltId, "vlans"] });
      if (delJobData.data.status === "success") setRemove(null);
    }
  }, [delJobData.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const uplinkEntries = (v: Vlan) => Object.entries(v.uplink_ports ?? {});
  const portCountLabel = (v: Vlan) => {
    const n = uplinkEntries(v).length;
    return n === 0 ? "—" : `${n} port uplink`;
  };

  return (
    <>
      <div className="mb-3 flex justify-end">
        <Button variant="fiber" onClick={() => setAdding(true)}>Tambah VLAN</Button>
      </div>
      <TableCard
        query={q}
        columns={["VLAN", "Nama", "Tipe", "Tag", "Port uplink", "Cakupan", ""]}
        card={(v) => (
          <MobileCard key={v.id}>
            <div className="flex items-center justify-between gap-2">
              <span className="min-w-0 truncate font-medium">{v.name}</span>
              <span className="shrink-0 font-mono text-xs text-muted">VLAN {v.vlan_id}</span>
            </div>
            <p className="truncate font-mono text-xs text-muted">
              {v.type} · {v.tag_action} · {v.olt_id === null ? "Global" : "OLT"} · {portCountLabel(v)}
            </p>
            <div className="mt-1 flex flex-wrap gap-2">
              <Button size="sm" variant="quiet" disabled={v.olt_id === null} onClick={() => setPorts(v)}>Port</Button>
              <Button size="sm" variant="quiet" onClick={() => setEdit(v)}>Edit</Button>
              <Button size="sm" variant="quiet" onClick={() => setRemove(v)}>Hapus</Button>
            </div>
          </MobileCard>
        )}
        empty="Belum ada VLAN untuk OLT ini."
        loadingText="Memuat VLAN ..."
        row={(v) => (
          <tr key={v.id}>
            <td className="font-mono">{v.vlan_id}</td>
            <td className="font-semibold">{v.name}</td>
            <td>{v.type}</td>
            <td>{v.tag_action}</td>
            <td className="font-mono text-xs">
              {uplinkEntries(v).length === 0 ? "—" : uplinkEntries(v).map(([p, m]) => (
                <span key={p} className="mr-2 whitespace-nowrap">
                  {p}: {m === "tagged" ? "Tagged" : "Untagged"}
                </span>
              ))}
            </td>
            <td>{v.olt_id === null ? "Global" : "OLT"}</td>
            <td className="text-right whitespace-nowrap">
              <Button size="sm" variant="quiet" disabled={v.olt_id === null}
                      title={v.olt_id === null ? "VLAN global tidak punya port uplink" : undefined}
                      onClick={() => setPorts(v)}>Port</Button>
              <Button size="sm" variant="quiet" onClick={() => setEdit(v)}>Edit</Button>
              <Button size="sm" variant="quiet" onClick={() => setRemove(v)}>Hapus</Button>
            </td>
          </tr>
        )}
      />
      {(adding || edit) && (
        <VlanDrawer oltId={oltId} edit={edit} onClose={() => { setAdding(false); setEdit(null); }} />
      )}
      {ports && (
        <PortsDrawer oltId={oltId} vlan={ports} ports={uplinkPorts} onClose={() => setPorts(null)} />
      )}
      {remove && (
        <Confirm
          title={`Hapus VLAN ${remove.vlan_id}?`}
          body={remove.olt_id === null
            ? "VLAN global akan dihapus langsung (tanpa job) dan berdampak ke semua OLT. ONU yang masih memakainya akan kehilangan layanan."
            : "VLAN akan dihapus dari OLT lewat job. ONU yang masih memakainya akan kehilangan layanan."}
          action="Hapus"
          busy={del.isPending}
          error={del.error?.message}
          onConfirm={() => del.mutate(remove)}
          onClose={() => { setRemove(null); setDelJob(null); }}
        >
          <JobTrace jobId={delJob} />
        </Confirm>
      )}
    </>
  );
}

/** Edit auto-nego/speed/duplex satu port uplink. Simpan = job push, jejak CLI-nya
 *  ditampilkan di tempat (JobTrace) supaya tidak perlu buka Logs untuk lihat perintahnya. */
function PortConfigDrawer({ oltId, port, onClose }: {
  oltId: number; port: OltInterface; onClose: () => void;
}) {
  const qc = useQueryClient();
  // Nilai live null/tidak dikenal TIDAK dipaksa jadi disable/1000/full: itu akan
  // mengirim perubahan yang tidak pernah dipilih operator saat Simpan ditekan.
  // "unknown" memblokir Simpan sampai operator memilih nilai yang sebenarnya.
  const [autoNego, setAutoNego] = useState(
    port.auto_nego === "enable" ? "enable" : port.auto_nego === "disable" ? "disable" : "unknown",
  );
  const [speed, setSpeed] = useState(
    PORT_SPEEDS.includes(port.speed as (typeof PORT_SPEEDS)[number]) ? port.speed! : "",
  );
  const [duplex, setDuplex] = useState(
    port.duplex === "half" ? "half" : port.duplex === "full" ? "full" : "",
  );
  const [jobId, setJobId] = useState<number | null>(null);
  const canSave = autoNego !== "unknown"
    && (autoNego === "enable" || (speed !== "" && duplex !== ""));

  const save = useMutation({
    mutationFn: () =>
      api<{ job_id: number }>(
        `/api/olts/${oltId}/interfaces/${encodeURIComponent(port.name)}/config`,
        { method: "POST", json: autoNego === "enable"
            ? { auto_nego: "enable" }
            : { auto_nego: "disable", speed, duplex } },
      ),
    // Drawer tetap terbuka: jejak CLI job baru berguna setelah job jalan.
    // Interfaces baru di-refresh saat job SELESAI, bukan saat antrean dibuat.
    onSuccess: (r) => setJobId(r.job_id),
  });
  const job = useJob(jobId);
  useEffect(() => {
    if (jobId !== null && job.data && DONE.has(job.data.status)) {
      qc.invalidateQueries({ queryKey: ["olts", oltId, "interfaces"] });
    }
  }, [job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const speeds = PORT_SPEEDS.filter((s) => s !== "10000" || isTenGig(port.name));
  return (
    <Drawer
      title={`Konfigurasi ${port.name}`}
      onClose={onClose}
      onSubmit={() => { if (canSave) save.mutate(); }}
      busy={save.isPending}
      error={!canSave ? "Status live port ini tidak diketahui; pilih nilai auto nego/kecepatan/duplex yang sebenarnya sebelum menyimpan." : save.error?.message}
    >
      <Field label="Auto negotiation">
        <select className={input} value={autoNego} onChange={(e) => setAutoNego(e.target.value)}>
          <option value="unknown" disabled>Tidak diketahui</option>
          <option value="enable">Enable</option>
          <option value="disable">Disable</option>
        </select>
      </Field>
      {autoNego === "disable" && (
        <>
          <Field label="Speed (Mbps)">
            <select className={input} value={speed} onChange={(e) => setSpeed(e.target.value)}>
              <option value="" disabled>Tidak diketahui</option>
              {speeds.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <Field label="Duplex">
            <select className={input} value={duplex} onChange={(e) => setDuplex(e.target.value)}>
              <option value="" disabled>Tidak diketahui</option>
              {DUPLEXES.map((dx) => <option key={dx} value={dx}>{dx}</option>)}
            </select>
          </Field>
        </>
      )}
      <p className="text-xs text-muted">
        {autoNego === "enable"
          ? "Speed dan duplex ditentukan perangkat saat auto negotiation aktif."
          : "Menyimpan mengantre job push ke OLT; port akan putus sesaat saat berubah."}
      </p>
      <JobTrace jobId={jobId} />
    </Drawer>
  );
}

function Interfaces({ oltId }: { oltId: number }) {
  const [edit, setEdit] = useState<OltInterface | null>(null);
  // Dibaca live tiap tab dibuka (bukan dari DB): butuh satu sesi CLI ke OLT, jadi
  // sengaja tidak auto-refetch.
  const q = useQuery({
    queryKey: ["olts", oltId, "interfaces"],
    queryFn: () => api<OltInterface[]>(`/api/olts/${oltId}/interfaces`),
    staleTime: 30_000,
  });

  return (
    <>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="min-w-0 text-xs text-muted">
          Dibaca langsung dari OLT saat tab dibuka, bukan dari database.
        </p>
        <Button size="sm" className="shrink-0" onClick={() => q.refetch()} disabled={q.isFetching}>
          <ArrowClockwise size={14} /> {q.isFetching ? "Membaca ..." : "Baca ulang"}
        </Button>
      </div>
      <TableCard
        query={q}
        columns={["Port", { label: "Media", className: "hidden lg:table-cell" }, { label: "PVID", className: "text-right" }, "Auto nego", "Speed", { label: "Duplex", className: "hidden lg:table-cell" }, "Admin", "Link", ""]}
        card={(p) => (
          <MobileCard key={p.name}>
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono font-medium">{p.name}</span>
              <StatusBadge status={p.link === "up" ? "online" : "offline"} withLabel />
            </div>
            <p className="font-mono text-xs text-muted">
              {p.media ?? "—"} · PVID {p.pvid ?? "—"} · {p.speed ?? "—"} · {p.duplex ?? "—"}
            </p>
            <p className="text-xs text-muted">Admin {p.admin_status ?? "—"} · Auto nego {p.auto_nego ?? "—"}</p>
            <Button size="sm" variant="quiet" className="mt-1" onClick={() => setEdit(p)}>Edit</Button>
          </MobileCard>
        )}
        empty="Tidak ada port uplink terbaca di OLT ini."
        loadingText="Membaca port uplink dari OLT ..."
        row={(p) => (
          <tr key={p.name}>
            <td className="font-mono font-semibold">{p.name}</td>
            <td className="hidden lg:table-cell">{p.media ?? "—"}</td>
            <td className="font-mono text-right">{p.pvid ?? "—"}</td>
            <td>{p.auto_nego ?? "—"}</td>
            <td className="font-mono">{p.speed ?? "—"}</td>
            <td className="hidden lg:table-cell">{p.duplex ?? "—"}</td>
            <td>{p.admin_status ?? "—"}</td>
            <td>
              <StatusBadge status={p.link === "up" ? "online" : "offline"} withLabel />
            </td>
            <td className="text-right">
              <Button size="sm" variant="quiet" onClick={() => setEdit(p)}>Edit</Button>
            </td>
          </tr>
        )}
      />
      {edit && <PortConfigDrawer oltId={oltId} port={edit} onClose={() => setEdit(null)} />}
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  // Tanpa px-4: Panel sudah p-4, jadi px-4 di sini = padding ganda 32px.
  // Nilai break-all: string CLI/SNMP panjang tidak punya titik patah alami
  // dan meluber di 390px.
  return (
    <div className="flex justify-between gap-3 border-b py-2 last:border-0">
      <span className="shrink-0 text-muted">{label}</span>
      <span className="min-w-0 break-all font-mono text-right">{value}</span>
    </div>
  );
}

function Konfigurasi({ d }: { d: Detail }) {
  const cards = {
    isPending: false, isError: false, error: null, data: d.cards, refetch: () => {},
  };
  return (
    <>
      <Panel title="Identitas" className="mb-3">
        <Row label="Host" value={d.host} />
        <Row label="Vendor / model" value={`${d.vendor} ${d.model}`} />
        <Row label="Versi software" value={d.software_version ?? "—"} />
        <Row label="Nama sistem (sysName)" value={d.sys_name ?? "—"} />
        <Row label="Lokasi (sysLocation)" value={d.sys_location ?? "—"} />
        <Row label="Pemilik" value={d.owner_name} />
        <Row label="CLI" value={`${d.cli_protocol}://${d.cli_username}@${d.host}:${d.cli_port}`} />
        <Row label="SNMP port" value={String(d.snmp_port)} />
        <Row label="Kapasitas" value={`${d.pon_port_count} PON x ${d.max_onu_per_port} ONU`} />
        <Row label="Lokasi" value={d.location ?? "—"} />
        <Row label="Sinkron terakhir" value={fmtDateTime(d.last_sync_at)} />
      </Panel>
      {/* Sama seperti Port PON: Panel hanya membungkus tabel, bingkainya dihapus
          supaya tidak ganda dengan kartu TableCard; judul dipertahankan polos. */}
      <section className="entrance mb-3">
        <div className="mb-2">
          <h2 className="text-xs font-medium uppercase tracking-[0.02em] text-muted">Kartu</h2>
        </div>
        <TableCard
          query={cards}
            columns={["Slot", "Tipe", { label: "Port", className: "text-right" }, { label: "HW", className: "hidden lg:table-cell" }, { label: "SW", className: "hidden lg:table-cell" }, { label: "CPU", className: "text-right" }, { label: "RAM", className: "text-right" }, "Status"]}
            card={(c) => (
              <MobileCard key={c.slot}>
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono font-medium">Slot {c.slot}</span>
                  <span className="text-xs text-muted">{c.status ?? "—"}</span>
                </div>
                <p className="truncate text-xs text-muted">{c.real_type ?? c.cfg_type ?? "—"}</p>
                <p className="font-mono text-xs text-muted">
                  Port {c.port_count ?? "—"} · CPU {pct(c.cpu_pct)} · RAM {pct(c.ram_pct)}
                </p>
              </MobileCard>
            )}
            empty="Data kartu belum tersinkron."
            loadingText="Memuat kartu ..."
            row={(c) => (
              <tr key={c.slot}>
                <td className="font-mono font-semibold">{c.slot}</td>
                <td>{c.real_type ?? c.cfg_type ?? "—"}</td>
                <td className="font-mono text-right">{c.port_count ?? "—"}</td>
                <td className="hidden lg:table-cell">{c.hardware_version ?? "—"}</td>
                <td className="hidden lg:table-cell">{c.software_version ?? "—"}</td>
                <td className="font-mono text-right">{pct(c.cpu_pct)}</td>
                <td className="font-mono text-right">{pct(c.ram_pct)}</td>
                <td>{c.status ?? "—"}</td>
              </tr>
            )}
        />
      </section>
      <Panel title="Port uplink">
        {d.uplink_ports.length === 0 ? (
          <Empty>Belum tersinkron.</Empty>
        ) : (
          <p className="break-all font-mono text-sm">{d.uplink_ports.join(", ")}</p>
        )}
      </Panel>
    </>
  );
}

function DaftarOnu({ oltId }: { oltId: number }) {
  // Sebelumnya size=200 tanpa page dan tanpa label total: OLT dengan >200 ONU
  // diam-diam terpotong. Sekarang paginasi penuh (page/total dari endpoint)
  // dengan ukuran 50 per halaman — halaman lain tetap bisa dibuka.
  const [page, setPage] = useState(1);
  const q = useQuery({
    queryKey: ["onus", { olt_id: oltId, page }],
    queryFn: () => api<Page<OnuRow>>(`/api/onus${qs({ olt_id: oltId, page, size: 50 })}`),
  });
  const rows = { ...q, data: q.data?.items };
  const total = q.data?.total ?? 0;
  const size = q.data?.size ?? 50;
  const pages = total === 0 ? 1 : Math.ceil(total / size);
  const from = total === 0 ? 0 : (page - 1) * size + 1;
  const to = Math.min(page * size, total);
  return (
    <>
      <TableCard
        query={rows}
        columns={["Serial", "Pelanggan", "PON", "Status", "Rx"]}
        card={(o) => (
          <MobileCard key={o.id}>
            <div className="flex items-center justify-between gap-2">
              <Link to={`/onu/${o.id}`} className="min-w-0 truncate font-medium text-fiber hover:underline">
                {o.customer_name ?? o.name ?? "—"}
              </Link>
              <StatusBadge status={o.status} reason={o.last_down_reason} withLabel />
            </div>
            <p className="truncate font-mono text-xs text-muted">
              {o.serial_number} · {o.slot}/{o.port}:{o.onu_index ?? "—"}
            </p>
            {/* PON sudah tampil di baris serial di atas — tidak diulang lagi. */}
            <p className="text-xs">
              <SignalBar dbm={o.rx_power_dbm} />
            </p>
          </MobileCard>
        )}
        empty="Belum ada ONU terdaftar di OLT ini."
        emptyAction={(
          <Link to={`/configured?olt_id=${oltId}`} className="text-fiber hover:underline">
            Buka di Configured
          </Link>
        )}
        loadingText="Memuat ONU ..."
        row={(o) => (
          <tr key={o.id}>
            <td className="font-mono">
              <Link to={`/onu/${o.id}`} className="text-fiber hover:underline">{o.serial_number}</Link>
            </td>
            <td className="font-semibold">{o.customer_name ?? o.name ?? "—"}</td>
            <td className="font-mono">{o.slot}/{o.port}:{o.onu_index ?? "—"}</td>
            <td><StatusBadge status={o.status} reason={o.last_down_reason} withLabel /></td>
            <td><SignalBar dbm={o.rx_power_dbm} /></td>
          </tr>
        )}
      />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-muted">
          Menampilkan {from}–{to} dari {total} ONU
          {total > 200 ? " — daftar ini dipaginasi, halaman lain bisa dibuka." : ""}
        </p>
        <div className="flex gap-2">
          <Button size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Sebelumnya
          </Button>
          <span className="text-xs text-muted self-center">{page} / {pages}</span>
          <Button size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
            Selanjutnya
          </Button>
        </div>
      </div>
    </>
  );
}

export function OltDetail() {
  const { id } = useParams();
  const oltId = Number(id);
  const { isManager } = useAuth();
  const tabs = isManager ? TABS : TABS.filter((t) => !MANAGER_ONLY.includes(t));
  const [params, setParams] = useSearchParams();
  const tabParam = params.get("tab") as Tab | null;
  const tab: Tab = tabParam !== null && tabs.includes(tabParam) ? tabParam : "Monitoring";
  const setTab = (t: Tab) => {
    const p = new URLSearchParams(params);
    if (t === "Monitoring") p.delete("tab"); else p.set("tab", t);
    setParams(p, { replace: true });
  };

  const q = useQuery({
    queryKey: ["olts", oltId, "detail"],
    queryFn: () => api<Detail>(`/api/olts/${oltId}/detail`),
    enabled: Number.isFinite(oltId),
  });

  if (q.isPending) return <Skeleton rows={4} text="Memuat Detail OLT ..." />;
  if (q.isError) {
    return <ErrorState message={`Gagal memuat Detail OLT: ${q.error.message}`} onRetry={() => q.refetch()} />;
  }
  const d = q.data;
  const online = d.onu_by_status.online ?? 0;

  return (
    <>
      <PageTitle title={d.name}>
        <Link to="/settings/olts" className="text-fiber hover:underline">
          <ArrowLeft size={16} className="inline" /> OLT
        </Link>
      </PageTitle>
      <div className="entrance mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-line/60 bg-surface px-4 py-3">
        <StatusBadge status={d.status} withLabel />
        <span className="min-w-0 break-all font-mono text-sm">{d.host}</span>
        <span className="text-sm text-muted">{d.vendor} {d.model}</span>
        <span className="ml-auto text-sm">
          <span className="font-mono font-semibold">{nf.format(online)}</span>
          <span className="text-muted"> / {nf.format(d.onu_count)} ONU online</span>
        </span>
        {/* Progres sinkron otomatis; satu baris penuh di mobile maupun desktop. */}
        <OltSyncProgress oltId={oltId} showIdle />
      </div>

      {/* z-20 di bawah header aplikasi z-40. thead tabel sudah tidak sticky
          (putusan user 2026-10-29), jadi bar tab ini tidak mungkin bersaing
          offset dengan header tabel. */}
      <div className="sticky top-14 z-20 mb-3 flex gap-1 overflow-x-auto border-b bg-surface" role="tablist">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors duration-150 ease-out motion-reduce:transition-none max-lg:min-h-12 ${
              tab === t ? "border-fiber font-semibold text-fiber" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t === "Daftar ONU" ? `Daftar ONU · ${nf.format(d.onu_count)}` : t}
          </button>
        ))}
      </div>

      {tab === "Monitoring" && <Monitoring d={d} oltId={oltId} />}
      {tab === "VLANs" && <Vlans oltId={oltId} uplinkPorts={d.uplink_ports} />}
      {tab === "Interfaces" && <Interfaces oltId={oltId} />}
      {tab === "Konfigurasi" && <Konfigurasi d={d} />}
      {tab === "Daftar ONU" && <DaftarOnu oltId={oltId} />}
    </>
  );
}
