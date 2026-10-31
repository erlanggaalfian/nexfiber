import { ArrowClockwise, CaretDown } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { ErrorState, PageTitle, RX_BUCKETS, StatusBadge, fmtAgo, fmtTime, nf, type RxBucket } from "../components/data";
import { Button } from "../components/ui/button";
import { api, type Dashboard as Dash, type OltRow } from "../lib/api";
import { useAuth } from "../lib/auth";
import { LOG_CATEGORIES } from "./Logs";

const sum = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0);

/** Aksen atas 2px (h-0.5) hanya untuk sel urgent; `changed` = garis atas 2px
 *  --teal-glow sekali saat nilainya berubah di auto-refresh, lalu hilang (timer di
 *  Dashboard, bukan loop). --teal-glow tidak punya utilitas Tailwind (tidak ada
 *  --color-teal-glow di @theme), jadi warnanya lewat var() inline, bukan kelas. */
function Cell({ label, value, sub, to, accent, dot, changed, tint }: {
  label: string; value: number; sub?: ReactNode; to?: string;
  accent?: string; dot?: string; changed?: boolean;
  /** Latar tipis untuk sel urgent — hanya aktif bila value > 0, supaya mata
   *  tertarik ke angka yang butuh tindakan; saat 0 sel tetap netral. */
  tint?: string;
}) {
  // Strip pertama yang dirender yang menempel ke tepi atas sel (padding ditarik
  // balik dengan margin negatif); strip kedua menempel tepat di bawahnya.
  const strips = (
    <>
      {changed && (
        <span aria-hidden className="-mx-3 -mt-3 mb-0 block h-0.5 lg:-mx-4 lg:-mt-4"
              style={{ backgroundColor: "var(--teal-glow)" }} />
      )}
      {accent && (
        <span aria-hidden
              className={`-mx-3 block h-0.5 lg:-mx-4 ${changed ? "" : "-mt-3 lg:-mt-4"} ${accent}`} />
      )}
    </>
  );
  const bg = tint && value > 0 ? tint : "bg-surface";
  const inner = (
    <>
      {strips}
      <p className="flex items-center gap-1.5 text-xs text-muted">
        {dot && <span className={`size-1.5 shrink-0 ${dot}`} aria-hidden />}
        {label}
      </p>
      <p className="font-mono text-metric font-semibold tabular-nums">{nf.format(value)}</p>
      <p className="min-h-4 text-xs text-muted">{sub}</p>
    </>
  );
  // Tanpa `to` = bukan link (dipakai kartu OLT Aktif untuk role user, yang
  // tidak boleh membuka /settings/olts). Sebelumnya kartu itu selalu link ke
  // halaman yang ditolak role user.
  if (!to) return <div className={`block ${bg} p-3 lg:p-4`}>{inner}</div>;
  return (
    <Link to={to} className={`hover-lift block ${bg} p-3 hover:bg-sunken lg:p-4`}>
      {inner}
    </Link>
  );
}

function Strip({ d, isManager, changed }: { d: Dash; isManager: boolean; changed: ReadonlySet<string> }) {
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
    <div className="stagger grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line/60 bg-line lg:grid-cols-4">
      {/* olt_by_status dihitung dari OLT aktif saja, sedangkan tabel OLT di bawah
          menampilkan semua OLT non-terhapus — labelnya dibuat jujur, bukan "Total". */}
      <Cell label="OLT Aktif" value={sum(d.olt_by_status)} sub={`${nf.format(d.olt_by_status.online ?? 0)} terhubung`} to={isManager ? "/settings/olts" : undefined} changed={changed.has("olt")} />
      <Cell label="ONU Online" value={online} sub={`dari ${nf.format(total)}`} to="/configured?status=online" changed={changed.has("online")} />
      <Cell
        label="ONU Tidak Online"
        value={notOnline}
        sub={`LOS ${nf.format(onu.los ?? 0)} · DG ${nf.format(onu.dying_gasp ?? 0)}`}
        to={`/configured?${notOnlineQuery}`}
        accent="bg-down" dot="bg-down" tint="bg-down/5" changed={changed.has("notOnline")}
      />
      <Cell label="Unconfigured" value={d.unconfigured} to="/unconfigured"
            accent="bg-amber" dot="bg-amber" tint="bg-amber/5" changed={changed.has("unconfigured")} />
    </div>
  );
}

/** Baris sinyal (PRD 3.4.2 c3, DESIGN §12.2): SATU BARIS, bukan kartu — label
 *  "Kualitas sinyal" + segmen klikabel (label + angka + mini-bar proporsional).
 *  Memakai RX_BUCKETS (sama dengan SignalBar di Configured) supaya label+warna
 *  tak pernah menyimpang. Titik teal-glow kecil menandai segmen yang berubah
 *  di auto-refresh (2 detik, timer di Dashboard — sama seperti strip). */
function SignalRow({ onu_by_signal, changed }: { onu_by_signal: Record<string, number>; changed: ReadonlySet<string> }) {
  const los = onu_by_signal.los ?? 0;
  // Total = semua bucket + LOS (dihitung eksplisit, bukan sum() atas record, supaya
  // kunci lain yang mungkin dikirim backend tidak ikut terhitung ganda).
  const total = (onu_by_signal.good ?? 0) + (onu_by_signal.fair ?? 0)
    + (onu_by_signal.weak ?? 0) + (onu_by_signal.critical ?? 0) + los;
  const seg = (key: string, label: string, color: string, value: number, to: string) => {
    const pct = total > 0 ? Math.min(value / total, 1) * 100 : 0;
    return (
      <Link key={key} to={to}
            className="flex items-center gap-2 rounded-md px-2.5 py-1.5 hover:bg-sunken">
        {changed.has(key) && (
          <span aria-hidden className="size-1.5 shrink-0 rounded-full"
                style={{ backgroundColor: "var(--teal-glow)" }} />
        )}
        <span className="text-xs text-muted">{label}</span>
        <span className="font-mono text-sm font-semibold tabular-nums">{nf.format(value)}</span>
        <span className="flex h-1 w-10 bg-sunken" aria-hidden>
          <span className={`h-1 transition-[width] duration-300 ease-out motion-reduce:transition-none ${color}`}
                style={{ width: `${pct}%` }} />
        </span>
      </Link>
    );
  };
  return (
    <div className="flex flex-wrap items-center gap-x-1 gap-y-1">
      <span className="mr-1 text-xs font-semibold uppercase tracking-wider text-muted">Kualitas sinyal</span>
      {(Object.entries(RX_BUCKETS) as [RxBucket, (typeof RX_BUCKETS)[RxBucket]][]).map(
        ([bucket, { label, color }]) => seg(
          bucket, label, color,
          onu_by_signal[bucket] ?? 0, `/configured?signal=${bucket}`,
        ),
      )}
      {seg("los", "LOS", "bg-down", los, "/configured?signal=los")}
      <span className="ml-1 text-xs text-muted">dari {nf.format(total)} ONU</span>
    </div>
  );
}

/** Baris OLT (PRD 3.4.2 c4): satu baris per OLT, data sama dengan OLT Management
 *  (`olt_service.list_rows`) — bukan query terpisah. Di bawah 768px jadi kartu
 *  DESIGN §12.10 (nama+status, ONU on/total, CPU/RAM/suhu). */
/** Bar rasio ONU online, geometri UsageBar (48x4, transisi lebar 300ms) — tapi
 *  tonenya DIBALIK dari UsageBar: di UsageBar 100% = penuh = merah (kapasitas),
 *  di sini 100% = semua ONU online = hijau. Karena itu tidak memakai UsageBar
 *  langsung (akan mewarnai OLT yang sepenuhnya online menjadi merah). CPU/RAM/Suhu
 *  sengaja TIDAK diwarnai: tidak ada ambang buatan untuknya. */
function OnuRatioBar({ online, count }: { online: number; count: number }) {
  const pct = count > 0 ? Math.min(online / count, 1) * 100 : 0;
  return (
    <span className="inline-flex items-center gap-2 font-mono">
      <span className="flex h-1 w-12 bg-sunken" aria-hidden>
        <span className="h-1 bg-fiber transition-[width] duration-300 ease-out motion-reduce:transition-none"
              style={{ width: `${pct}%` }} />
      </span>
      {online}/{count}
    </span>
  );
}

function OltTable({ olts }: { olts: OltRow[] }) {
  const navigate = useNavigate();
  if (olts.length === 0) return <p className="p-4 text-muted">Belum ada OLT terdaftar.</p>;
  // Urutan: OLT tidak online dulu, lalu rasio ONU online terendah. OLT tanpa ONU
  // (count 0) dianggap rasio 1 supaya tidak tampil sebagai yang terburuk.
  const sorted = [...olts].sort((a, b) => {
    const aOff = a.status !== "online" ? 0 : 1;
    const bOff = b.status !== "online" ? 0 : 1;
    if (aOff !== bOff) return aOff - bOff;
    const ra = a.onu_count > 0 ? a.onu_online / a.onu_count : 1;
    const rb = b.onu_count > 0 ? b.onu_online / b.onu_count : 1;
    return ra - rb;
  });
  return (
    <>
    <div className="grid divide-y divide-line/60 md:hidden">
      {sorted.map((o) => (
        <Link key={o.id} to={`/olt/${o.id}`} className="block px-3 py-3">
          <div className="flex items-center justify-between gap-2">
            <span className="min-w-0 truncate font-semibold">{o.name}</span>
            <StatusBadge status={o.status} withLabel />
          </div>
          <p className="font-mono text-xs text-muted">
            ONU <OnuRatioBar online={o.onu_online} count={o.onu_count} />
          </p>
          <p className="font-mono text-xs text-muted">
            CPU {o.cpu_pct == null ? "—" : `${o.cpu_pct.toFixed(0)}%`} · RAM {o.ram_pct == null ? "—" : `${o.ram_pct.toFixed(0)}%`} · Suhu {o.temperature_c == null ? "—" : `${o.temperature_c.toFixed(0)}°C`}
          </p>
        </Link>
      ))}
    </div>
    <div className="hidden overflow-x-auto md:block">
      <table className="tbl">
        <thead>
          <tr>
            {[
              { label: "OLT" }, { label: "Status" }, { label: "ONU" },
              { label: "CPU", className: "text-right" },
              { label: "RAM", className: "text-right" },
              { label: "Suhu", className: "text-right" },
            ].map((c) => (
              <th key={c.label} className={c.className ?? ""}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((o) => (
            <tr key={o.id} onClick={() => navigate(`/olt/${o.id}`)}
                className="cursor-pointer">
              <td><Link to={`/olt/${o.id}`} className="block max-w-60 truncate font-semibold hover:underline" title={o.name}>{o.name}</Link></td>
              <td><StatusBadge status={o.status} withLabel /></td>
              <td><OnuRatioBar online={o.onu_online} count={o.onu_count} /></td>
              <td className="font-mono text-right">{o.cpu_pct == null ? "—" : `${o.cpu_pct.toFixed(0)}%`}</td>
              <td className="font-mono text-right">{o.ram_pct == null ? "—" : `${o.ram_pct.toFixed(0)}%`}</td>
              <td className="font-mono text-right">{o.temperature_c == null ? "—" : `${o.temperature_c.toFixed(0)}°C`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
    </>
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
            className="flex min-h-11 items-center justify-between gap-3 px-3 py-2 text-sm hover:bg-sunken"
          >
            <span className="flex min-w-0 items-center gap-1.5 truncate">
              <span className={`size-1.5 shrink-0 ${l.success ? "bg-up" : "bg-down"}`} aria-hidden />
              <span className="shrink-0 text-muted">{l.username ?? "sistem"}</span>
              <span className="truncate">{LOG_CATEGORIES.find((c) => c.value === l.category)?.label ?? l.category}</span>
              {l.onu_serial && <span className="min-w-0 truncate font-mono text-muted">{l.onu_serial}</span>}
              {l.olt_name && <span className="text-muted">@ {l.olt_name}</span>}
            </span>
            <span className="shrink-0 font-mono text-xs text-muted">{fmtAgo(l.created_at)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** Skeleton berbentuk Dashboard (strip 4 sel + baris sinyal 5 sel + baris tabel),
 *  bg-sunken, tanpa shimmer/animasi looping. Skeleton generik lama tidak dipakai lagi. */
function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-4" aria-busy>
      <p className="text-muted">Menarik data dari OLT ...</p>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line/60 bg-line lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="bg-surface p-3 lg:p-4">
            <div className="h-4 bg-sunken" />
            <div className="mt-2 h-7 bg-sunken" />
            <div className="mt-1 h-4 bg-sunken" />
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-1 gap-y-1" aria-hidden>
        <div className="mr-1 h-4 w-24 bg-sunken" />
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="h-7 w-28 rounded-md bg-sunken" />
        ))}
      </div>
      <div className="rounded-lg border border-line/60 bg-surface p-3">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className="mb-1 h-8 bg-sunken last:mb-0" />
        ))}
      </div>
    </div>
  );
}

/** Snapshot angka strip + sinyal untuk mendeteksi sel yang berubah di auto-refresh. */
function dashboardSnapshot(d: Dash): Record<string, number> {
  const onu = d.onu_by_status;
  const total = sum(onu);
  return {
    olt: sum(d.olt_by_status),
    online: onu.online ?? 0,
    notOnline: total - (onu.online ?? 0),
    unconfigured: d.unconfigured,
    good: d.onu_by_signal.good ?? 0,
    fair: d.onu_by_signal.fair ?? 0,
    weak: d.onu_by_signal.weak ?? 0,
    critical: d.onu_by_signal.critical ?? 0,
    los: d.onu_by_signal.los ?? 0,
  };
}

export function Dashboard() {
  const { isManager } = useAuth();
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dash>("/api/dashboard"), refetchInterval: 60_000 });
  // Sel yang berubah: dibandingkan dengan snapshot sebelumnya, ditandai 2 detik
  // lalu dibersihkan (timer, bukan loop). Muat pertama tidak ditandai (prev null).
  const prevRef = useRef<Record<string, number> | null>(null);
  const [changed, setChanged] = useState<ReadonlySet<string>>(new Set());
  /* Judul diketuk di mobile (adopsi vibekoding §3.5): info "Diperbarui …" /
   * "Poll OLT terakhir …" disembunyikan di <768px dan muncul saat judul
   * diketuk. Desktop tidak berubah. */
  const [infoOpen, setInfoOpen] = useState(false);
  // Ditarik ke variabel supaya teks yang sama tidak ditulis dua kali (DRY):
  // dipakai di baris judul desktop dan di panel lipat mobile.
  const updatedLabel = q.dataUpdatedAt ? fmtTime(new Date(q.dataUpdatedAt).toISOString()) : "—";
  const pollLabel = q.data?.last_poll_at ? fmtTime(q.data.last_poll_at) : "—";
  // OLT yang status poll terakhirnya bukan online — untuk banner "sebagian gagal"
  // (§8 State data). Dihitung dari data yang sudah ada; tanpa mengarang.
  const oltsGagal = (q.data?.olts ?? []).filter((o) => o.status !== "online");
  useEffect(() => {
    if (!q.data) return;
    const cur = dashboardSnapshot(q.data);
    const prev = prevRef.current;
    prevRef.current = cur;
    if (!prev) return;
    const diff = Object.keys(cur).filter((k) => prev[k] !== cur[k]);
    if (diff.length === 0) return;
    setChanged(new Set(diff));
    const id = setTimeout(() => setChanged(new Set()), 2000);
    return () => clearTimeout(id);
  }, [q.data]);
  return (
    <>
      <PageTitle title="Dashboard">
        {/* max-md:hidden: di mobile info ini pindah ke panel lipat di bawah judul
            (collapsed-first), bukan hilang — desktop tidak berubah. */}
        <span className="text-xs text-muted max-md:hidden">Diperbarui {updatedLabel}</span>
        <span className="text-xs text-muted max-md:hidden">Poll OLT terakhir {pollLabel}</span>
        <Button onClick={() => q.refetch()} disabled={q.isFetching}>
          <ArrowClockwise size={16} /> Refresh
        </Button>
      </PageTitle>
      {/* Mobile (<768px) saja: ketuk judul men-toggle baris info. Bukan <h1>
          kedua — h1 PageTitle sudah sr-only di bawah lg, jadi ini <button>
          teks biasa + chevron. Strip metrik, tabel OLT, dan activity feed di
          bawahnya tidak disentuh. */}
      <div className="mb-2 md:hidden">
        <button
          type="button"
          onClick={() => setInfoOpen((v) => !v)}
          aria-expanded={infoOpen}
          className="flex min-h-12 w-full items-center justify-between gap-2 text-left"
        >
          <span className="text-xl font-semibold">Dashboard</span>
          <CaretDown
            size={16}
            aria-hidden
            className={`shrink-0 text-muted transition-transform duration-150 ease-out motion-reduce:transition-none ${infoOpen ? "rotate-180" : ""}`}
          />
        </button>
        {infoOpen && (
          <div className="space-y-0.5 pb-1 text-xs text-muted">
            <p>Diperbarui {updatedLabel}</p>
            <p>Poll OLT terakhir {pollLabel}</p>
          </div>
        )}
      </div>
      {q.isPending ? (
        <DashboardSkeleton />
      ) : q.isError ? (
        <ErrorState message={`Gagal memuat Dashboard: ${q.error.message}`} onRetry={() => q.refetch()} />
      ) : (
        // Tanpa stagger di parent (sebelumnya stagger bersarang: parent + Strip/
        // SignalRow, sehingga sel naik dua kali). Stagger hanya di dalam grid,
        // section memakai entrance biasa seperti TableCard/Panel.
        <div className="flex flex-col gap-3">
          <Strip d={q.data} isManager={isManager} changed={changed} />
          <SignalRow onu_by_signal={q.data.onu_by_signal} changed={changed} />
          {oltsGagal.length > 0 && (
            <div role="alert" className="rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-sm">
              <p className="font-semibold text-warn">
                {oltsGagal.length} dari {q.data.olts.length} OLT gagal dipolling. Data di bawah mungkin kedaluwarsa.
              </p>
              <p className="mt-0.5 text-xs text-muted">{oltsGagal.map((o) => o.name).join(" · ")}</p>
            </div>
          )}
          <section className="entrance overflow-hidden rounded-lg border border-line bg-surface shadow-xs">
            <h2 className="border-b border-line-strong bg-sunken px-6 py-4 text-xs font-semibold uppercase tracking-wider text-muted">OLT</h2>
            <OltTable olts={q.data.olts} />
          </section>
          <section className="entrance rounded-lg border border-line/60 bg-surface shadow-xs">
            <div className="flex items-center justify-between gap-2 border-b px-3 py-2">
              <h2 className="text-sm font-medium">Aktivitas terbaru</h2>
              <Link to="/logs" className="text-sm text-fiber hover:underline">Lihat semua</Link>
            </div>
            <ActivityFeed items={q.data.recent_activity} />
          </section>
        </div>
      )}
    </>
  );
}
