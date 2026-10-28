/** Update attached VLANs — acuan `updateVlans`: satu multiselect VLAN layanan.
 *  VLAN management tidak muncul (disaring `serviceVlanOptions`). */
import { useState } from "react";
import { serviceVlanOptions, type OnuConfigOptions } from "../../../lib/onuActions";
import { Help, HelpPanel, ModalShell, Row, VlanMulti } from "./ModalShell";

export function AttachedVlansModal(
  { options, current, supported, note, busy, error, onClose, onSubmit }:
  {
    options: OnuConfigOptions | undefined;
    /** VLAN yang SUDAH terpasang di ONU (nomor perangkat, dari `service_vlans` backend).
     *  Dipakai sebagai centang awal; lihat `attachedVlanNumbers` di OnuDetail. */
    current: number[];
    supported: boolean | null;
    note?: string | null;
    busy?: boolean;
    error?: string | null;
    onClose: () => void;
    onSubmit: (vlans: number[]) => void;
  },
) {
  /** `current` dibaca sekali saat modal mount. Modal hanya dirender setelah detail ONU
   *  ada (halaman menampilkan skeleton sebelum itu), jadi nilainya sudah final — dan
   *  menyinkronkan ulang dari prop akan membuang centang yang sedang diubah operator
   *  setiap kali query detail refetch di latar. */
  const [vlans, setVlans] = useState<number[]>(current);
  /** VLAN terpasang yang TIDAK ada di daftar pilihan (management, atau belum terdaftar di
   *  master VLAN OLT). Tidak bisa dicentang/di-uncheck di sini, tapi tetap dikirim utuh:
   *  perintah backend menulis ulang seluruh `service-port`, jadi menghilangkannya = ikut
   *  menghapus layanan yang tidak pernah ditampilkan ke operator. */
  const shown = serviceVlanOptions(options);
  const hidden = vlans.filter((v) => !shown.some((o) => o.number === v));
  return (
    <ModalShell title="Perbarui VLAN terpasang" action="Simpan" supported={supported} note={note} dirty={vlans.join(",") !== current.join(",")}
                busy={busy} error={error} onClose={onClose} onSubmit={() => onSubmit(vlans)}>
      <Row label="VLANs">
        <VlanMulti label="VLANs" options={shown} value={vlans} onChange={setVlans} autoFocus />
      </Row>
      {/* Acuan: catatan di panel penuh lebar di bawah multiselect, bukan hint kecil. */}
      <HelpPanel>
        <Help>Pilih semua VLAN yang akan dipakai pada ONU ini.</Help>
        {hidden.length > 0 && (
          <Help>
            VLAN {hidden.join(", ")} tetap terpasang pada ONU dan akan dipertahankan
            (tidak bisa diubah di sini).
          </Help>
        )}
      </HelpPanel>
    </ModalShell>
  );
}
