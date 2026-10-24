/** Hook progres sinkron otomatis satu OLT (ONU, speed, zone, ODP, VLAN, kesehatan).
 *  Bentuk data + hitungannya ada di oltSyncStages.ts (bisa diuji tanpa React).
 *
 *  Kontrak backend: `GET /api/olts/{id}/sync-status` dan `POST /api/olts/{id}/sync-all`
 *  (keduanya menjawab OltSyncStatus). Kalau endpoint belum ada / di luar hak akses
 *  (404/403), hook memberi `unavailable` dan UI bilang "belum tersedia" — tidak ada
 *  data karangan.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { ApiError, api } from "./api";
import { ACTIVE_STATES, isSyncActive, type OltSyncStatus, type SyncState } from "./oltSyncStages";

export { isSyncActive, syncSummary } from "./oltSyncStages";
export type { OltSyncStage, OltSyncStatus, SyncStageStatus, SyncState } from "./oltSyncStages";

const key = (oltId: number) => ["olts", oltId, "sync-status"];

/** Polling 3 dtk selama pending/running, berhenti saat selesai. */
export function useOltSync(oltId: number, enabled = true) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: key(oltId),
    queryFn: () => api<OltSyncStatus>(`/api/olts/${oltId}/sync-status`),
    enabled: enabled && Number.isFinite(oltId),
    // 404 = endpoint belum ada, 403 = di luar cakupan user; jangan diulang.
    retry: (count, e) => !(e instanceof ApiError && (e.status === 404 || e.status === 403)) && count < 2,
    refetchInterval: (query) => (query.state.data && isSyncActive(query.state.data) ? 3000 : false),
  });

  const unavailable = q.error instanceof ApiError && (q.error.status === 404 || q.error.status === 403);

  // Begitu sinkron selesai, daftar OLT/ONU dimuat ulang sendiri — user tidak klik apa pun.
  const prev = useRef<SyncState | null>(null);
  const state = q.data?.state ?? null;
  useEffect(() => {
    if (state && prev.current && ACTIVE_STATES.has(prev.current) && !ACTIVE_STATES.has(state)) {
      for (const key of [["olts"], ["onus"], ["onu"], ["pending"], ["dashboard"]]) {
        qc.invalidateQueries({ queryKey: key });
      }
    }
    prev.current = state;
  }, [state, qc]);

  return { ...q, unavailable };
}

/** Sinkron ulang semua (tombol "Coba lagi"). Jawabannya OltSyncStatus, jadi langsung
 *  dipasang ke cache — polling 3 dtk lanjut sendiri tanpa satu putaran kosong. */
export function useSyncAll(oltId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<OltSyncStatus>(`/api/olts/${oltId}/sync-all`, { method: "POST" }),
    onSuccess: (s) => qc.setQueryData(key(oltId), s),
  });
}
