import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, getToken, type Job } from "./api";

export const DONE = new Set(["success", "failed", "cancelled"]);

function invalidateFor(qc: QueryClient, job: Job) {
  qc.setQueryData(["jobs", job.id], job);
  if (!DONE.has(job.status)) return;
  qc.invalidateQueries({ queryKey: ["jobs"], exact: true });
  qc.invalidateQueries({ queryKey: ["dashboard"] });
  if (job.onu_id !== null || job.job_type.includes("onu") || job.job_type === "sync_unconfigured") {
    qc.invalidateQueries({ queryKey: ["onus"] });
    qc.invalidateQueries({ queryKey: ["onu"] });
    qc.invalidateQueries({ queryKey: ["pending"] });
  }
  if (job.olt_id !== null) {
    qc.invalidateQueries({ queryKey: ["olts"] });
    qc.invalidateQueries({ queryKey: ["pon-ports", job.olt_id] });
  }
}

/** One SSE connection for the whole app; finished jobs invalidate only related query keys. */
export function useJobStream() {
  const qc = useQueryClient();
  useEffect(() => {
    const es = new EventSource(`/api/stream/jobs?token=${encodeURIComponent(getToken() ?? "")}`);
    es.addEventListener("job", (e) => invalidateFor(qc, JSON.parse((e as MessageEvent).data)));
    return () => es.close();
  }, [qc]);
}

/** Tracks one job until it finishes. SSE updates the cache; polling every 3s is the fallback. */
export function useJob(id: number | null) {
  return useQuery({
    queryKey: ["jobs", id],
    queryFn: () => api<Job>(`/api/jobs/${id}`),
    enabled: id !== null,
    refetchInterval: (q) => (q.state.data && DONE.has(q.state.data.status) ? false : 3000),
  });
}
