/** Pindah ONU ke PON lain (kind `move`, sudah didukung backend: pre-check PON tujuan
 *  ada di DB OLT ini dan bentrok onu_index di PON tujuan ditolak sebelum perintah).
 *  Daftar PON diambil dari endpoint pon-ports OLT; PON asal tidak ditawarkan. */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type PonPort } from "../../../lib/api";
import { ModalShell, Row, Select } from "./ModalShell";

export function MoveModal(
  { oltId, currentSlot, currentPort, supported, note, busy, error, onClose, onSubmit }:
  {
    oltId: number;
    currentSlot: number;
    currentPort: number;
    supported: boolean | null;
    note?: string | null;
    busy?: boolean;
    error?: string | null;
    onClose: () => void;
    onSubmit: (body: { board: number; port: number }) => void;
  },
) {
  const [target, setTarget] = useState("");
  const ponPorts = useQuery({
    queryKey: ["pon-ports", oltId],
    queryFn: () => api<PonPort[]>(`/api/olts/${oltId}/pon-ports`),
  });
  const ports = (ponPorts.data ?? [])
    .filter((p) => !(p.slot === currentSlot && p.port === currentPort))
    .sort((a, b) => a.slot - b.slot || a.port - b.port);
  const picked = ports.find((p) => `${p.slot}/${p.port}` === target);
  return (
    <ModalShell title="Pindah PON" action="Pindah" warn {...{ supported, note, busy, error, onClose }}
                disabled={picked === undefined}
                onSubmit={() => picked && onSubmit({ board: picked.slot, port: picked.port })}>
      <Row label="PON saat ini">
        <span className="font-mono text-sm text-muted">{currentSlot}/{currentPort}</span>
      </Row>
      <Row label="PON tujuan">
        <Select value={target} onChange={setTarget} placeholder="Pilih PON ..." label="PON tujuan">
          {ports.map((p) => (
            <option key={p.id} value={`${p.slot}/${p.port}`}>
              {p.slot}/{p.port} ({p.onu_count}/{p.capacity} ONU)
            </option>
          ))}
        </Select>
      </Row>
      {ponPorts.isError && (
        <p className="text-sm text-down">Daftar PON gagal dimuat.</p>
      )}
    </ModalShell>
  );
}
