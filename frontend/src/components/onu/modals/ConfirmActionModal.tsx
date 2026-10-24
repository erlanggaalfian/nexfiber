/** Modal konfirmasi aksi perangkat: Reboot, Disable/Enable ONU, Recreate OLT config,
 *  Restore to factory defaults, Delete.
 *
 *  Peringatan satu baris (selera pemilik: tanpa paragraf panjang) + Batal/Ya. Dua aksi tak
 *  bisa dibatalkan — Delete dan Restore to factory defaults — WAJIB mengetik serial number
 *  lebih dulu; tombolnya mati sampai teksnya cocok persis. */
import { useState } from "react";
import type { ActionKind } from "../../../lib/onuActions";
import { ModalShell, field } from "./ModalShell";

export type ConfirmKind = "reboot" | "disable" | "enable" | "resync-config" | "restore-factory" | "delete";

const TEXT: Record<ConfirmKind, { title: string; body: string; action: string; danger?: boolean }> = {
  reboot: {
    title: "Reboot", action: "Ya, reboot",
    body: "ONU mati sekitar satu menit lalu hidup kembali.",
  },
  disable: {
    title: "Disable ONU", action: "Ya, nonaktifkan",
    body: "Semua layanan ONU ini dimatikan di OLT.",
  },
  enable: {
    title: "Enable ONU", action: "Ya, aktifkan",
    body: "Layanan ONU ini dihidupkan kembali.",
  },
  "resync-config": {
    title: "Recreate OLT config", action: "Ya, resync",
    body: "Konfigurasi ONU di OLT dibuat ulang dari database Nexfiber (sekitar 30 detik).",
  },
  "restore-factory": {
    title: "Restore to factory defaults", action: "Ya, reset", danger: true,
    body: "Semua setelan pelanggan di perangkat hilang, termasuk SSID dan sandi WiFi.",
  },
  delete: {
    title: "Delete", action: "Ya, hapus", danger: true,
    body: "ONU dihapus dari OLT dan dari daftar Nexfiber. Riwayat sinyal tetap tersimpan.",
  },
};

/** Hanya dua aksi ini yang butuh ketik ulang serial number. */
const NEEDS_TYPED: ConfirmKind[] = ["delete", "restore-factory"];

export function ConfirmActionModal(
  { kind, serial, supported, note, busy, error, onClose, onConfirm }:
  {
    kind: ConfirmKind;
    serial: string;
    supported: boolean | null;
    note?: string | null;
    busy?: boolean;
    error?: string | null;
    onClose: () => void;
    onConfirm: (kind: ActionKind) => void;
  },
) {
  const t = TEXT[kind];
  const needsTyped = NEEDS_TYPED.includes(kind);
  const [typed, setTyped] = useState("");
  const ok = !needsTyped || typed === serial;
  return (
    <ModalShell title={t.title} action={t.action} danger={t.danger} supported={supported} note={note}
                busy={busy} error={error} disabled={!ok} onClose={onClose}
                onSubmit={() => ok && onConfirm(kind)}>
      <p className={`text-sm ${t.danger ? "text-down" : "text-muted"}`}>{t.body}</p>
      {needsTyped && (
        <label className="mt-3 block">
          <span className="mb-1 block text-xs text-muted">Ketik serial number: {serial}</span>
          <input className={field} value={typed} autoComplete="off" placeholder={serial}
                 aria-label="Konfirmasi serial number"
                 onChange={(e) => setTyped(e.target.value.trim())} />
          {typed !== "" && typed !== serial && (
            <span className="mt-1 block text-xs text-down">Serial number belum cocok.</span>
          )}
        </label>
      )}
    </ModalShell>
  );
}
