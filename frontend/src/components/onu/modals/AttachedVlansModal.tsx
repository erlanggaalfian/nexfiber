/** Update attached VLANs — acuan `updateVlans`: satu multiselect VLAN layanan.
 *  VLAN management tidak muncul (disaring `serviceVlanOptions`). */
import { useState } from "react";
import { serviceVlanOptions, type OnuConfigOptions } from "../../../lib/onuActions";
import { ModalShell, Row, VlanMulti } from "./ModalShell";

export function AttachedVlansModal(
  { options, current, supported, note, busy, error, onClose, onSubmit }:
  {
    options: OnuConfigOptions | undefined;
    current: number[];
    supported: boolean | null;
    note?: string | null;
    busy?: boolean;
    error?: string | null;
    onClose: () => void;
    onSubmit: (vlans: number[]) => void;
  },
) {
  const [vlans, setVlans] = useState<number[]>(current);
  return (
    <ModalShell title="Update attached VLANs" action="Update" supported={supported} note={note}
                busy={busy} error={error} onClose={onClose} onSubmit={() => onSubmit(vlans)}>
      <Row label="VLANs" hint="Setelah diubah, cek VLAN pada port Ethernet.">
        <VlanMulti label="VLANs" options={serviceVlanOptions(options)} value={vlans} onChange={setVlans} />
      </Row>
    </ModalShell>
  );
}
