import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, getToken, type Job } from "./api";

export const DONE = new Set(["success", "failed", "cancelled"]);

function invalidateFor(qc: QueryClient, job: Job) {
  qc.setQueryData(["jobs", job.id], job);
  if (!DONE.has(job.status)) return;
  qc.invalidateQueries({ queryKey: ["jobs"], exact: true });
  qc.invalidateQueries({ queryKey: ["dashboard"] });
  // Halaman Logs memakai queryKey ["logs", ...], jadi invalidate di sini supaya
  // log job yang selesai tidak menunggu refetch manual.
  qc.invalidateQueries({ queryKey: ["logs"] });
  if (job.onu_id !== null || job.job_type.includes("onu") || job.job_type === "sync_unconfigured"
      || job.job_type === "sync_olt_metrics") {
    qc.invalidateQueries({ queryKey: ["onus"] });
    qc.invalidateQueries({ queryKey: ["onu"] });
    qc.invalidateQueries({ queryKey: ["pending"] });
  }
  if (job.job_type.includes("vlan")) qc.invalidateQueries({ queryKey: ["vlans"] });
  if (job.job_type.includes("speed_profile")) qc.invalidateQueries({ queryKey: ["speed-profiles"] });
  if (job.olt_id !== null) {
    qc.invalidateQueries({ queryKey: ["olts"] });
    qc.invalidateQueries({ queryKey: ["pon-ports", job.olt_id] });
    // Kunci query OltDetail: ["olts", id, "interfaces"] dan ["olts", id, "vlans"].
    // Sebelumnya job VLAN/port selesai tidak me-refresh kedua tab itu.
    qc.invalidateQueries({ queryKey: ["olts", job.olt_id, "interfaces"] });
    qc.invalidateQueries({ queryKey: ["olts", job.olt_id, "vlans"] });
  }
}

/** One SSE connection for the whole app; finished jobs invalidate only related query keys.
 *  Mengembalikan `disconnected` supaya Layout bisa menampilkan indikator putus:
 *  EventSource me-reconnect sendiri, tapi tanpa onerror pengguna tidak tahu
 *  pembaruan job berhenti. Bila token hilang (logout/401), koneksi ditutup. */
export function useJobStream() {
  const qc = useQueryClient();
  const [disconnected, setDisconnected] = useState(false);
  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const es = new EventSource(`/api/stream/jobs?token=${encodeURIComponent(token)}`);
    es.addEventListener("job", (e) => invalidateFor(qc, JSON.parse((e as MessageEvent).data)));
    es.onopen = () => setDisconnected(false);
    es.onerror = () => {
      // Token hilang di tengah jalan = sesi berakhir; jangan reconnect dengan token basi.
      if (!getToken()) { es.close(); return; }
      setDisconnected(true);
    };
    return () => es.close();
  }, [qc]);
  return { disconnected };
}

/** Tracks one job until it finishes. SSE updates the cache; polling every 3s is the fallback.
 *  Polling BERHENTI bila query error (mis. 404/403): sebelumnya polling jalan selamanya
 *  dan menampilkan "menunggu" padahal job tidak akan pernah selesai. */
export function useJob(id: number | null) {
  return useQuery({
    queryKey: ["jobs", id],
    queryFn: () => api<Job>(`/api/jobs/${id}`),
    enabled: id !== null,
    retry: false,
    refetchInterval: (q) =>
      q.state.error || (q.state.data && DONE.has(q.state.data.status)) ? false : 3000,
  });
}
