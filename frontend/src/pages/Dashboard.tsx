import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { Button, buttonClass } from "../components/ui/button";
import { ErrorState, Panel, Skeleton, fmtTime, nf } from "../components/data";
import { api, type Dashboard as Dash } from "../lib/api";

const REFRESH = 60_000;

function useCountdown(from: number) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return Math.max(0, Math.ceil((from + REFRESH - now) / 1000));
}

function ActionBlock({ d }: { d: Dash }) {
  const rows: [number, string, string, string][] = [
    [d.action.los_over_15m, "ONU LOS lebih dari 15 menit", "Lihat daftar", "/onus?state=down&sort=-last_seen"],
    [d.action.pending_authorization, "ONU menunggu otorisasi", "Buka antrian", "/onus/pending"],
    [d.action.olt_poll_failed, "OLT gagal dipolling", "Lihat OLT", "/olts"],
  ];
  const shown = rows.filter(([n]) => n > 0);
  if (!shown.length)
    return <p className="p-4 text-muted">Tidak ada yang perlu ditangani. Polling terakhir {fmtTime(d.last_poll_at)}.</p>;
  return (
    <ul className="divide-y">
      {shown.map(([n, label, cta, to]) => (
        <li key={label} className="flex items-center justify-between gap-3 px-4 py-2">
          <span><span className="font-mono font-semibold">{nf.format(n)}</span> {label}</span>
          <Link to={to} className={buttonClass("secondary", "sm")}>{cta}</Link>
        </li>
      ))}
    </ul>
  );
}

const BUCKETS = [
  ["normal", "Normal", "bg-up"],
  ["warn", "Waspada", "bg-warn"],
  ["bad", "Buruk", "bg-down"],
] as const;

function RxHistogram({ d }: { d: Dash }) {
  const total = BUCKETS.reduce((s, [k]) => s + (d.rx_histogram[k] ?? 0), 0);
  const t = d.rx_threshold;
  const range = { normal: `≥ ${t.warn} dBm`, warn: `${t.warn} s/d ${t.crit} dBm`, bad: `< ${t.crit} dBm` };
  if (!total) return <p className="p-4 text-muted">Belum ada data Rx ONU online.</p>;
  return (
    <ul className="space-y-2 p-4">
      {BUCKETS.map(([k, label, color]) => {
        const n = d.rx_histogram[k] ?? 0;
        return (
          <li key={k} className="grid grid-cols-[6rem_1fr_4rem] items-center gap-2">
            <span>{label} <span className="block text-xs text-muted">{range[k]}</span></span>
            <span className="h-2 bg-sunken"><span className={`block h-full ${color}`} style={{ width: `${(n / total) * 100}%` }} /></span>
            <span className="text-right font-mono">{nf.format(n)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function PonCapacity({ d }: { d: Dash }) {
  if (!d.busiest_pon_ports.length) return <p className="p-4 text-muted">Belum ada PON port.</p>;
  return (
    <ul className="space-y-2 p-4">
      {d.busiest_pon_ports.map((p) => (
        <li key={p.pon_port_id} className="grid grid-cols-[1fr_5rem] items-center gap-x-2">
          <span className="truncate">{p.olt_name} <span className="font-mono text-muted">{p.slot}/{p.port}</span></span>
          <span className="text-right font-mono">{p.used}/{p.capacity}</span>
          <span className="col-span-2 mt-1 h-1.5 bg-sunken">
            <span className="block h-full bg-fiber" style={{ width: `${Math.min(100, (p.used / p.capacity) * 100)}%` }} />
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Dashboard() {
  const q = useQuery({ queryKey: ["dashboard"], queryFn: () => api<Dash>("/api/dashboard"), refetchInterval: REFRESH });
  const left = useCountdown(q.dataUpdatedAt);
  const d = q.data;
  const s = d?.onu_by_status ?? {};
  const offline = Object.entries(s).reduce((n, [k, v]) => (k === "online" ? n : n + v), 0);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Ringkasan</h1>
        <div className="flex items-center gap-3 text-xs text-muted">
          {d && <span>Data per {fmtTime(new Date(q.dataUpdatedAt).toISOString())}, perbarui dalam {left} dtk</span>}
          <Button size="sm" variant="quiet" onClick={() => q.refetch()} disabled={q.isFetching}>Perbarui</Button>
        </div>
      </header>

      {q.isPending ? (
        <Panel><Skeleton text="Menarik ringkasan ..." /></Panel>
      ) : q.isError ? (
        <Panel><ErrorState message={`Ringkasan gagal dimuat: ${q.error.message}`} onRetry={() => q.refetch()} /></Panel>
      ) : (
        <>
          <Panel title="Perlu tindakan"><ActionBlock d={d!} /></Panel>
          <div className="grid gap-4 md:grid-cols-2">
            <section className="rounded-md border">
              <h2 className="border-b px-4 py-2 text-xs font-medium uppercase tracking-[0.02em] text-muted">Rx ONU online, saat ini</h2>
              <RxHistogram d={d!} />
            </section>
            <section className="rounded-md border">
              <h2 className="border-b px-4 py-2 text-xs font-medium uppercase tracking-[0.02em] text-muted">PON port terpadat</h2>
              <PonCapacity d={d!} />
            </section>
          </div>
          <p className="text-muted">
            {nf.format(s.online ?? 0)} ONU online · {nf.format(offline)} tidak online · {nf.format(d!.olt_count)} OLT ·{" "}
            {nf.format(d!.activated_today)} diaktivasi hari ini · polling terakhir {fmtTime(d!.last_poll_at)}
          </p>
        </>
      )}
    </div>
  );
}
