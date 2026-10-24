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
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router";
import * as z from "zod";
import { Confirm, Drawer, Field, TableCard, UsageBar, cell, input } from "../components/crud";
import {
  Empty, ErrorState, Panel, PageTitle, Skeleton, StatusBadge, fmtDateTime, nf,
} from "../components/data";
import { Button } from "../components/ui/button";
import { api, qs, type OltDetail as Detail, type OnuRow, type Page, type Vlan } from "../lib/api";
import { useAuth } from "../lib/auth";

const TABS = ["Monitoring", "VLANs", "Konfigurasi", "Daftar ONU"] as const;
type Tab = (typeof TABS)[number];
const MANAGER_ONLY: Tab[] = ["VLANs", "Konfigurasi"];

const VLAN_TYPES = ["internet", "management", "voip", "iptv", "other"] as const;
const TAG_ACTIONS = ["tag", "transparent", "translate"] as const;

function fmtUptime(seconds: number | null) {
  if (seconds === null) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return d > 0 ? `${d}h ${h}j` : h > 0 ? `${h}j ${m}m` : `${m}m`;
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
      <span className="mt-1 flex h-1 w-full bg-sunken" aria-hidden>
        <span className={`h-1 ${tone}`} style={{ width: `${width}%` }} />
      </span>
    </div>
  );
}

function Monitoring({ d, oltId }: { d: Detail; oltId: number }) {
  const { isManager } = useAuth();
  const qc = useQueryClient();
  const refresh = useMutation({
    mutationFn: () => api<{ job_id: number }>(`/api/olts/${oltId}/refresh-metrics`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["olts", oltId] }),
  });
  const pon = {
    isPending: false, isError: false, error: null, data: d.pon_ports, refetch: () => {},
  };
  return (
    <>
      <div className="stagger mb-3 grid grid-cols-2 gap-px overflow-hidden rounded-md border bg-line lg:grid-cols-4">
        <Metric label="CPU" value={pct(d.cpu_pct)} fill={d.cpu_pct} />
        <Metric label="RAM" value={pct(d.ram_pct)} fill={d.ram_pct} />
        <Metric
          label="Suhu"
          value={d.temperature_c === null ? "—" : `${Number(d.temperature_c).toFixed(0)}°C`}
          fill={d.temperature_c}
        />
        <Metric label="Uptime" value={fmtUptime(d.uptime_seconds)} />
      </div>
      <Panel
        title="Port PON"
        className="mb-3"
        action={
          isManager && (
            <Button size="sm" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              <ArrowClockwise size={14} /> Refresh
            </Button>
          )
        }
      >
        <div className="p-0">
          <TableCard
            query={pon}
            columns={["PON", "Status", "ONU", "Sinkron terakhir"]}
            empty="Belum ada port PON tersinkron. Jalankan Refresh untuk memindai OLT."
            loadingText="Memuat port PON ..."
            row={(p) => (
              <tr key={p.id} className="border-b last:border-0">
                <td className={`${cell} font-mono`}>{p.slot}/{p.port}</td>
                <td className={cell}><StatusBadge status={p.oper_state === "up" ? "online" : "offline"} /></td>
                <td className={cell}><UsageBar used={p.onu_count} capacity={p.capacity} /></td>
                <td className={`${cell} text-muted`}>{fmtDateTime(p.last_sync_at)}</td>
              </tr>
            )}
          />
        </div>
      </Panel>
      {d.last_error && (
        <Panel title="Kesalahan terakhir">
          <p className="p-4 text-down">{d.last_error}</p>
        </Panel>
      )}
    </>
  );
}

type VlanForm = z.infer<typeof vlanSchema>;
const vlanSchema = z.object({
  vlan_id: z.string().regex(/^\d+$/, "Angka 1-4094"),
  name: z.string().min(1).max(100),
  type: z.enum(VLAN_TYPES),
  description: z.string().max(255),
  gemport: z.string().regex(/^\d*$/, "Angka"),
  tag_action: z.enum(TAG_ACTIONS),
  user_vlan: z.string().regex(/^\d*$/, "Angka"),
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
        : api<Vlan>("/api/vlans", {
            method: "POST",
            json: { ...common, olt_id: oltId, vlan_id: Number(f.vlan_id) },
          });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["olts", oltId, "vlans"] });
      onClose();
    },
  });

  return (
    <Drawer
      title={edit ? `Edit VLAN ${edit.vlan_id}` : "Tambah VLAN"}
      onClose={onClose}
      onSubmit={handleSubmit((f) => save.mutate(f))}
      busy={save.isPending}
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
      {!edit && (
        <p className="text-xs text-muted">
          Menyimpan akan mengantre job pembuatan VLAN di OLT; status bisa dilihat di Logs.
        </p>
      )}
    </Drawer>
  );
}

/** Tagged/untagged per port uplink. Simpan = job push ke OLT, bukan panggilan langsung. */
function PortsDrawer({ oltId, vlan, ports, onClose }: {
  oltId: number; vlan: Vlan; ports: string[]; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [value, setValue] = useState<Record<string, string>>(() => ({ ...vlan.uplink_ports }));
  const save = useMutation({
    mutationFn: () => {
      const picked = Object.fromEntries(Object.entries(value).filter(([, v]) => v !== ""));
      return api<{ job_id: number }>(`/api/vlans/${vlan.id}/ports`, {
        method: "PUT", json: { ports: picked },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["olts", oltId, "vlans"] });
      onClose();
    },
  });

  return (
    <Drawer
      title={`Port uplink VLAN ${vlan.vlan_id}`}
      onClose={onClose}
      onSubmit={() => save.mutate()}
      busy={save.isPending}
      error={save.error?.message}
    >
      {ports.length === 0 ? (
        <p className="text-muted">
          Daftar port uplink belum tersinkron. Jalankan Refresh di tab Monitoring dulu.
        </p>
      ) : (
        ports.map((port) => (
          <Field key={port} label={port}>
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
      <p className="text-xs text-muted">
        Menyimpan mengantre job push ke OLT. Untagged otomatis mengubah port ke mode hybrid.
      </p>
    </Drawer>
  );
}

function Vlans({ oltId, uplinkPorts }: { oltId: number; uplinkPorts: string[] }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<Vlan | null>(null);
  const [adding, setAdding] = useState(false);
  const [ports, setPorts] = useState<Vlan | null>(null);
  const [remove, setRemove] = useState<Vlan | null>(null);

  const q = useQuery({
    queryKey: ["olts", oltId, "vlans"],
    queryFn: () => api<Vlan[]>(`/api/vlans${qs({ olt_id: oltId })}`),
  });

  const del = useMutation({
    mutationFn: (v: Vlan) => api<{ job_id: number }>(`/api/vlans/${v.id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["olts", oltId, "vlans"] });
      setRemove(null);
    },
  });

  const portLabel = (v: Vlan) => {
    const entries = Object.entries(v.uplink_ports ?? {});
    return entries.length === 0 ? "—" : entries.map(([p, m]) => `${p}:${m === "tagged" ? "T" : "U"}`).join(", ");
  };

  return (
    <>
      <div className="mb-3 flex justify-end">
        <Button variant="fiber" onClick={() => setAdding(true)}>Tambah VLAN</Button>
      </div>
      <TableCard
        query={q}
        columns={["VLAN", "Nama", "Tipe", "Tag", "Port uplink", ""]}
        empty="Belum ada VLAN untuk OLT ini."
        loadingText="Memuat VLAN ..."
        row={(v) => (
          <tr key={v.id} className="border-b last:border-0">
            <td className={`${cell} font-mono`}>{v.vlan_id}</td>
            <td className={cell}>{v.name}</td>
            <td className={cell}>{v.type}</td>
            <td className={cell}>{v.tag_action}</td>
            <td className={`${cell} font-mono text-xs`}>{portLabel(v)}</td>
            <td className={`${cell} text-right whitespace-nowrap`}>
              <Button size="sm" variant="quiet" onClick={() => setPorts(v)}>Port</Button>
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
          body="VLAN akan dihapus dari OLT lewat job. ONU yang masih memakainya akan kehilangan layanan."
          action="Hapus"
          busy={del.isPending}
          error={del.error?.message}
          onConfirm={() => del.mutate(remove)}
          onClose={() => setRemove(null)}
        />
      )}
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 border-b px-4 py-2 last:border-0">
      <span className="text-muted">{label}</span>
      <span className="font-mono text-right">{value}</span>
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
        <Row label="Pemilik" value={d.owner_name} />
        <Row label="CLI" value={`${d.cli_protocol}://${d.cli_username}@:${d.cli_port}`} />
        <Row label="SNMP port" value={String(d.snmp_port)} />
        <Row label="Kapasitas" value={`${d.pon_port_count} PON x ${d.max_onu_per_port} ONU`} />
        <Row label="Lokasi" value={d.location ?? "—"} />
        <Row label="Sinkron terakhir" value={fmtDateTime(d.last_sync_at)} />
      </Panel>
      <Panel title="Kartu" className="mb-3">
        <div className="p-0">
          <TableCard
            query={cards}
            columns={["Slot", "Tipe", "Port", "HW", "SW", "CPU", "RAM", "Status"]}
            empty="Data kartu belum tersinkron."
            loadingText="Memuat kartu ..."
            row={(c) => (
              <tr key={c.slot} className="border-b last:border-0">
                <td className={`${cell} font-mono`}>{c.slot}</td>
                <td className={cell}>{c.real_type ?? c.cfg_type ?? "—"}</td>
                <td className={`${cell} font-mono`}>{c.port_count ?? "—"}</td>
                <td className={cell}>{c.hardware_version ?? "—"}</td>
                <td className={cell}>{c.software_version ?? "—"}</td>
                <td className={`${cell} font-mono`}>{pct(c.cpu_pct)}</td>
                <td className={`${cell} font-mono`}>{pct(c.ram_pct)}</td>
                <td className={cell}>{c.status ?? "—"}</td>
              </tr>
            )}
          />
        </div>
      </Panel>
      <Panel title="Port uplink">
        {d.uplink_ports.length === 0 ? (
          <Empty>Belum tersinkron.</Empty>
        ) : (
          <p className="p-4 font-mono text-sm">{d.uplink_ports.join(", ")}</p>
        )}
      </Panel>
    </>
  );
}

function DaftarOnu({ oltId }: { oltId: number }) {
  const q = useQuery({
    queryKey: ["onus", { olt_id: oltId }],
    queryFn: () => api<Page<OnuRow>>(`/api/onus${qs({ olt_id: oltId, size: 200 })}`),
  });
  const rows = { ...q, data: q.data?.items };
  return (
    <TableCard
      query={rows}
      columns={["Serial", "Pelanggan", "PON", "Status", "Rx"]}
      empty="Belum ada ONU terdaftar di OLT ini."
      loadingText="Memuat ONU ..."
      row={(o) => (
        <tr key={o.id} className="border-b last:border-0">
          <td className={`${cell} font-mono`}>
            <Link to={`/onu/${o.id}`} className="text-fiber hover:underline">{o.serial_number}</Link>
          </td>
          <td className={cell}>{o.customer_name ?? o.name ?? "—"}</td>
          <td className={`${cell} font-mono`}>{o.slot}/{o.port}:{o.onu_index ?? "—"}</td>
          <td className={cell}><StatusBadge status={o.status} /></td>
          <td className={`${cell} font-mono`}>{o.rx_power_dbm === null ? "LOS" : o.rx_power_dbm.toFixed(1)}</td>
        </tr>
      )}
    />
  );
}

export function OltDetail() {
  const { id } = useParams();
  const oltId = Number(id);
  const { isManager } = useAuth();
  const tabs = isManager ? TABS : TABS.filter((t) => !MANAGER_ONLY.includes(t));
  const [tab, setTab] = useState<Tab>("Monitoring");

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
      <div className="entrance mb-3 flex flex-wrap items-center gap-3 rounded-md border bg-surface px-4 py-3">
        <StatusBadge status={d.status} />
        <span className="font-mono text-sm">{d.host}</span>
        <span className="text-sm text-muted">{d.vendor} {d.model}</span>
        <span className="ml-auto text-sm">
          <span className="font-mono font-semibold">{nf.format(online)}</span>
          <span className="text-muted"> / {nf.format(d.onu_count)} ONU online</span>
        </span>
      </div>

      <div className="mb-3 flex gap-1 overflow-x-auto border-b" role="tablist">
        {tabs.map((t) => (
          <button
            key={t}
            type="button"
            role="tab"
            aria-selected={tab === t}
            onClick={() => setTab(t)}
            className={`-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
              tab === t ? "border-fiber font-semibold text-fiber" : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Monitoring" && <Monitoring d={d} oltId={oltId} />}
      {tab === "VLANs" && <Vlans oltId={oltId} uplinkPorts={d.uplink_ports} />}
      {tab === "Konfigurasi" && <Konfigurasi d={d} />}
      {tab === "Daftar ONU" && <DaftarOnu oltId={oltId} />}
    </>
  );
}
