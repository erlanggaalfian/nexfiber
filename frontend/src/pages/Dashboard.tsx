import { ArrowClockwise } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { Link } from "react-router";
import { ErrorState, PageTitle, Skeleton, fmtTime, nf } from "../components/data";
import { Button } from "../components/ui/button";
import { api, type Dashboard as Dash } from "../lib/api";

const sum = (r: Record<string, number>) => Object.values(r).reduce((a, b) => a + b, 0);

function Cell({ label, value, sub, to }: { label: string; value: number; sub?: ReactNode; to: string }) {
  return (
    <Link to={to} className="hover-lift block bg-surface p-3 hover:bg-sunken lg:p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="font-mono text-metric font-semibold">{nf.format(value)}</p>
      <p className="min-h-4 text-xs text-muted">{sub}</p>
    </Link>
  );
}

function Strip({ d }: { d: Dash }) {
  const onu = d.onu_by_status;
  const total = sum(onu);
  const online = onu.online ?? 0;
  return (
    // gap-px over bg-line draws the 1px dividers for both 4x1 and 2x2.
    <div className="stagger grid grid-cols-2 gap-px overflow-hidden rounded-md border bg-line lg:grid-cols-4">
      <Cell label="Total OLT" value={sum(d.olt_by_status)} sub={`${nf.format(d.olt_by_status.online ?? 0)} terhubung`} to="/settings/olts" />
      <Cell label="ONU Online" value={online} sub={`dari ${nf.format(total)}`} to="/configured?status=online" />
      <Cell
        label="ONU Offline"
        value={total - online}
        sub={`LOS ${nf.format(onu.los ?? 0)} · DG ${nf.format(onu.dying_gasp ?? 0)}`}
        to="/configured?status=offline"
      />
      <Cell label="Unconfigured" value={d.unconfigured} to="/unconfigured" />
    </div>
  );
}

export function Dashboard() {
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
        <Strip d={q.data} />
      )}
    </>
  );
}
