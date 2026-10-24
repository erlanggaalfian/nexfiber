/** Bentuk data + hitungan progres sinkron OLT, tanpa import apa pun supaya bisa
 *  diuji langsung oleh `node frontend/tests/olt-sync.check.mjs`. Hook React-nya di oltSync.ts.
 *
 *  Mengikuti kontrak backend `OltSyncStatus`/`OltSyncStage` (backend/app/schemas/olt.py)
 *  dan rantai tahap `olt_onboarding.STAGES`.
 */
export type SyncStageStatus = "pending" | "running" | "success" | "failed" | "skipped";
export type SyncState = "pending" | "running" | "success" | "failed";

export type OltSyncStage = {
  key: string;
  label: string;
  status: SyncStageStatus;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  count: number | null;
  job_id: number | null;
};

export type OltSyncStatus = {
  olt_id: number;
  state: SyncState;
  trigger: string | null;
  updated_at: string | null;
  stages: OltSyncStage[];
};

export const ACTIVE_STATES = new Set<SyncState>(["pending", "running"]);
const SETTLED = new Set<SyncStageStatus>(["success", "failed", "skipped"]);
// Jumlah ONU yang dicari user = hasil tahap "Status ONU"; tahap onu_* lain
// (belum terdaftar, metadata) menghitung hal lain dan tidak boleh menggantikannya.
const ONU_COUNT_KEY = "onu_status";

export const isSyncActive = (s: OltSyncStatus) => ACTIVE_STATES.has(s.state);

/** Ringkasan satu baris: "Sinkron 3/6: Status ONU — ONU 246". */
export function syncSummary(s: OltSyncStatus) {
  const done = s.stages.filter((st) => SETTLED.has(st.status)).length;
  const running = s.stages.find((st) => st.status === "running");
  const failed = s.stages.filter((st) => st.status === "failed");
  const onu = s.stages.find((st) => st.key === ONU_COUNT_KEY && st.count !== null)?.count ?? null;
  return {
    done,
    total: s.stages.length,
    pct: s.stages.length === 0 ? 0 : Math.round((done / s.stages.length) * 100),
    running,
    failed,
    onu,
  };
}
