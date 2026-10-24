/** Update attached VLANs — acuan `updateVlans`: satu multiselect VLAN layanan.
 *  VLAN management tidak muncul (disaring `serviceVlanOptions`). */
import { useState } from "react";
import { serviceVlanOptions, type OnuConfigOptions } from "../../../lib/onuActions";
import { Help, HelpPanel, ModalShell, Row, VlanMulti } from "./ModalShell";

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
      <Row label="VLANs">
        <VlanMulti label="VLANs" options={serviceVlanOptions(options)} value={vlans} onChange={setVlans} />
      </Row>
      {/* Acuan: dua catatan di panel penuh lebar di bawah multiselect, bukan hint kecil. */}
      <HelpPanel>
        <Help>Pilih semua VLAN yang akan dipakai pada ONU ini.</Help>
        <Help warn>
          Setelah daftar VLAN diubah, buka setelan port Ethernet dan tetapkan VLAN sesuai kebutuhan.
        </Help>
      </HelpPanel>
    </ModalShell>
  );
}
