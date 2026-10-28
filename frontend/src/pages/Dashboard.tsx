import { ArrowClockwise } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { ErrorState, PageTitle, RX_BUCKETS, Skeleton, StatusBadge, fmtAgo, fmtTime, nf, type RxBucket } from "../components/data";
import { Button } from "../components/ui/button";
import { api, type Dashboard as Dash, type OltRow } from "../lib/api";
import { useAuth } from "../lib/auth";
import { LOG_CATEGORIES } from "./Logs";

const sum = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0);

function Cell({ label, value, sub, to }: { label: string; value: number; sub?: ReactNode; to?: string }) {
  const inner = (
    <>
      <p className="text-xs text-muted">{label}</p>
      <p className="font-mono text-metric font-semibold">{nf.format(value)}</p>
      <p className="min-h-4 text-xs text-muted">{sub}</p>
    </>
  );
  // Tanpa `to` = bukan link (dipakai kartu OLT Aktif untuk role user, yang
  // tidak boleh membuka /settings/olts). Sebelumnya kartu itu selalu link ke
  // halaman yang ditolak role user.
  if (!to) return <div className="block bg-surface p-3 lg:p-4">{inner}</div>;
  return (
    <Link to={to} className="hover-lift block bg-surface p-3 hover:bg-sunken lg:p-4">
      {inner}
    </Link>
  );
}

function Strip({ d, isManager }: { d: Dash; isManager: boolean }) {
  const onu = d.onu_by_status;
  const total = sum(onu);
  const online = onu.online ?? 0;
  // "Tidak online" = total - online, termasuk unknown. Link-nya harus memakai
  // SEMUA status itu (filter status backend menerima list), bukan hanya
  // ?status=offline yang dulu hanya menampilkan subset dari angka kartu.
  const notOnline = total - online;
  const notOnlineQuery = ["offline", "los", "dying_gasp", "power_off", "unknown"]
    .map((s) => `status=${s}`).join("&");
  return (
    // gap-px over bg-line draws the 1px dividers for both 4x1 and 2x2.
    <div className="stagger grid grid-cols-2 gap-px overflow-hidden rounded-md border bg-line lg:grid-cols-4">
      {/* olt_by_status dihitung dari OLT aktif saja, sedangkan tabel OLT di bawah
          menampilkan semua OLT non-terhapus — labelnya dibuat jujur, bukan "Total". */}
      <Cell label="OLT Aktif" value={sum(d.olt_by_status)} sub={`${nf.format(d.olt_by_status.online ?? 0)} terhubung`} to={isManager ? "/settings/olts" : undefined} />
      <Cell label="ONU Online" value={online} sub={`dari ${nf.format(total)}`} to="/configured?status=online" />
      <Cell
        label="ONU Tidak Online"
        value={notOnline}
        sub={`LOS ${nf.format(onu.los ?? 0)} · DG ${nf.format(onu.dying_gasp ?? 0)}`}
        to={`/configured?${notOnlineQuery}`}
      />
      <Cell label="Unconfigured" value={d.unconfigured} to="/unconfigured" />
    </div>
  );
}

/** Baris sinyal (PRD 3.4.2 c3): satu bucket per kolom, pakai RX_BUCKETS (sama dengan
 *  SignalBar di Configured.tsx) supaya label+warna tak pernah menyimpang. */
function SignalRow({ onu_by_signal }: { onu_by_signal: Record<string, number> }) {
  const los = onu_by_signal.los ?? 0;
  return (
    <div className="stagger grid grid-cols-2 gap-px overflow-hidden rounded-md border bg-line sm:grid-cols-5">
      {(Object.entries(RX_BUCKETS) as [RxBucket, (typeof RX_BUCKETS)[RxBucket]][]).map(
        ([bucket, { label, color }]) => (
          <Link key={bucket} to={`/configured?signal=${bucket}`} className="hover-lift block bg-surface p-3 hover:bg-sunken">
            <p className="flex items-center gap-1.5 text-xs text-muted"><span className={`size-1.5 shrink-0 ${color}`} aria-hidden />{label}</p>
            <p className="font-mono text-metric font-semibold">{nf.format(onu_by_signal[bucket] ?? 0)}</p>
          </Link>
        ),
      )}
      <Link to="/configured?signal=los" className="hover-lift block bg-surface p-3 hover:bg-sunken">
        <p className="flex items-center gap-1.5 text-xs text-muted"><span className="size-1.5 shrink-0 bg-idle" aria-hidden />LOS</p>
        <p className="font-mono text-metric font-semibold">{nf.format(los)}</p>
      </Link>
    </div>
  );
}

/** Baris OLT (PRD 3.4.2 c4): satu baris per OLT, data sama dengan OLT Management
 *  (`olt_service.list_rows`) — bukan query terpisah. */
function OltTable({ olts }: { olts: OltRow[] }) {
  if (olts.length === 0) return <p className="p-4 text-muted">Belum ada OLT terdaftar.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-sm">
        <thead className="text-xs text-muted">
          <tr className="border-b">
            {["OLT", "Status", "ONU", "CPU", "RAM", "Suhu"].map((c) => (
              <th key={c} className="px-3 py-2 text-left align-middle">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {olts.map((o) => (
            <tr key={o.id} className="border-b last:border-0 hover:bg-sunken">
              <td className="px-3 py-2"><Link to={`/olt/${o.id}`} className="hover:underline">{o.name}</Link></td>
              <td className="px-3 py-2"><StatusBadge status={o.status} withLabel /></td>
              <td className="px-3 py-2 font-mono">{o.onu_online}/{o.onu_count}</td>
              <td className="px-3 py-2 font-mono">{o.cpu_pct == null ? "—" : `${o.cpu_pct.toFixed(0)}%`}</td>
              <td className="px-3 py-2 font-mono">{o.ram_pct == null ? "—" : `${o.ram_pct.toFixed(0)}%`}</td>
              <td className="px-3 py-2 font-mono">{o.temperature_c == null ? "—" : `${o.temperature_c.toFixed(0)}°C`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Baris aktivitas terbaru (PRD 3.4.2 c5): 10 log terakhir, tiap baris link ke Logs
 *  (difilter serial ONU bila ada). Sebelumnya komentar mengklaim ada link, tetapi
 *  baris tidak dirender sebagai Link sama sekali. */
function ActivityFeed({ items }: { items: Dash["recent_activity"] }) {
  if (items.length === 0) return <p className="p-4 text-muted">Belum ada aktivitas.</p>;
  return (
    <ul className="divide-y">
      {items.map((l) => (
        <li key={l.id}>
          <Link
            to={l.onu_serial ? `/logs?q=${encodeURIComponent(l.onu_serial)}` : "/logs"}
            className="flex items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-sunken"
          >
            <span className="flex items-center gap-1.5 truncate">
              <span className={`size-1.5 shrink-0 ${l.success ? "bg-up" : "bg-down"}`} aria-hidden />
              <span className="text-muted">{l.username ?? "sistem"}</span>
              <span>{LOG_CATEGORIES.find((c) => c.value === l.category)?.label ?? l.category}</span>
              {l.onu_serial && <span className="font-mono text-muted">{l.onu_serial}</span>}
              {l.olt_name && <span className="text-muted">@ {l.olt_name}</span>}
            </span>
            <span className="shrink-0 font-mono text-xs text-muted">{fmtAgo(l.created_at)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function Dashboard() {
  const { isManager } = useAuth();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dash>("/api/dashboard"), refetchInterval: 60_000 });
  return (
    <>
      <PageTitle title="Dashboard">
        <span className="text-xs text-muted">Diperbarui {q.dataUpdatedAt ? fmtTime(new Date(q.dataUpdatedAt).toISOString()) : "—"}</span>
        <Button onClick={() => q.refetch()} disabled={q.isFetching}>
          <ArrowClockwise size={16} /> Refresh
        </Button>
      </PageTitle>
      {q.isPending ? (
        <Skeleton rows={2} text="Menarik data dari OLT ..." />
      ) : q.isError ? (
        <ErrorState message={`Gagal memuat Dashboard: ${q.error.message}`} onRetry={() => q.refetch()} />
      ) : (
        <div className="stagger flex flex-col gap-4">
          <Strip d={q.data} isManager={isManager} />
          <SignalRow onu_by_signal={q.data.onu_by_signal} />
          <section className="rounded-md border bg-surface">
            <h2 className="border-b px-3 py-2 text-sm font-medium">OLT</h2>
            <OltTable olts={q.data.olts} />
          </section>
          <section className="rounded-md border bg-surface">
            <h2 className="border-b px-3 py-2 text-sm font-medium">Aktivitas terbaru</h2>
            <ActivityFeed items={q.data.recent_activity} />
          </section>
        </div>
      )}
    </>
  );
}
