/** Update Management and VoIP IP, Enable/Disable VoIP, Update IPTV.
 *
 *  Body `mgmt-ip` {mode,ip} dan `iptv` {enabled} persis kontrak backend
 *  (`build_mgmt_ip`: pool/manual/release; perintah `mgmt-ip` tidak memakai VLAN).
 *  Body `voip-enable` HANYA {port}: backend hanya mengirim `voip protocol sip`
 *  (satu-satunya sintaks VoIP yang terbukti di perangkat) dan MENOLAK eksplisit
 *  bila dikirimi nomor/sandi SIP — akun SIP tidak diprovisi lewat CLI OLT karena
 *  tidak ada sintaksnya yang terbukti, jadi modal ini tidak lagi menampilkan
 *  field nomor/sandi yang dulu dikirim lalu dibuang diam-diam.
 */
import { useState } from "react";
import { ModalShell, Help, Radios, Row, field } from "./ModalShell";

type Common = {
  supported: boolean | null;
  note?: string | null;
  busy?: boolean;
  error?: string | null;
  onClose: () => void;
};

export function MgmtIpModal(
  { current, onSubmit, ...c }:
  Common & {
    // Mode tampilan perangkat (inactive/static/dhcp) dipetakan ke mode perintah
    // backend: static -> manual, inactive -> release. Mode dhcp tidak punya padanan
    // perintah `mgmt-ip`, jadi dibiarkan kosong sampai operator memilih aksi.
    current: { mode: string | null; ip: string | null };
    onSubmit: (body: { mode: string; ip: string | null; netmask?: string }) => void;
  },
) {
  const initMode = ((): "" | "pool" | "manual" | "release" => {
    const v = (current.mode ?? "").toLowerCase();
    return v === "static" ? "manual" : v === "inactive" ? "release" : "";
  })();
  const [mode, setMode] = useState<"" | "pool" | "manual" | "release">(initMode);
  const [ip, setIp] = useState(current.ip ?? "");
  // Sebelumnya manual selalu memakai /24 tanpa field: jaringan management yang bukan
  // /24 tidak bisa diisi dengan benar. Default tetap 255.255.255.0.
  const [netmask, setNetmask] = useState("255.255.255.0");
  const netmaskOk = /^(\d{1,3}\.){3}\d{1,3}$/.test(netmask)
    && netmask.split(".").every((o) => Number(o) <= 255);
  return (
    <ModalShell title="Perbarui IP Management dan VoIP" action="Simpan" {...c} dirty={mode !== initMode || ip !== (current.ip ?? "") || netmask !== "255.255.255.0"}
                disabled={mode === "" || (mode === "manual" && (ip.trim() === "" || !netmaskOk))}
                onSubmit={() => onSubmit({
                  mode,
                  ip: mode === "manual" ? ip.trim() : null,
                  netmask: mode === "manual" ? netmask.trim() : undefined,
                })}>
      <Row label="Mgmt IP mode" hint={mode === "" ? "Pilih aksi: mode perangkat saat ini tidak bisa dipetakan ke perintah ini" : undefined}>
        <Radios name="mgmt-mode" value={mode} onChange={setMode} autoFocus
                options={[
                  { value: "pool", label: "Auto-assign (pool)" },
                  { value: "manual", label: "Static IP" },
                  { value: "release", label: "Release" },
                ]} />
      </Row>
      {mode === "manual" && (
        <>
          <Row label="Management IP address">
            <input className={field} value={ip} autoComplete="off" aria-label="Management IP address"
                   onChange={(e) => setIp(e.target.value.trim())} />
          </Row>
          <Row label="Netmask" hint="Isi sesuai jaringan management bila bukan /24.">
            <input className={field} value={netmask} autoComplete="off" aria-label="Netmask"
                   onChange={(e) => setNetmask(e.target.value.trim())} />
          </Row>
        </>
      )}
    </ModalShell>
  );
}

export function VoipEnableModal(
  { port, onSubmit, ...c }:
  Common & {
    port: number;
    onSubmit: (body: { port: number }) => void;
  },
) {
  return (
    <ModalShell title="Aktifkan VoIP" action="Aktifkan" {...c}
                onSubmit={() => onSubmit({ port })}>
      <Row label="Port">
        <span className="font-mono text-sm text-muted">pots_0/{port}</span>
      </Row>
      <Help>
        Hanya protokol VoIP yang diatur dari OLT (`voip protocol sip`). Akun SIP
        (nomor dan sandi) tidak diprovisi lewat CLI OLT — tidak ada sintaksnya
        yang terbukti, jadi field itu sengaja tidak ditampilkan.
      </Help>
    </ModalShell>
  );
}

export function IptvModal(
  { current, onSubmit, ...c }:
  Common & { current: boolean; onSubmit: (body: { enabled: boolean }) => void },
) {
  const [on, setOn] = useState<"on" | "off">(current ? "on" : "off");
  return (
    <ModalShell title="Perbarui IPTV" action="Simpan" {...c} dirty={(on === "on") !== current}
                onSubmit={() => onSubmit({ enabled: on === "on" })}>
      <Row label="IPTV status">
        <Radios name="iptv-status" value={on} onChange={setOn} autoFocus
                options={[{ value: "off", label: "Inactive" }, { value: "on", label: "Active" }]} />
      </Row>
    </ModalShell>
  );
}
