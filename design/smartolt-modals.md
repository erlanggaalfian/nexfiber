# Acuan modal SmartOLT (diekstrak dari "View ONU - Mamura.html" kiriman user)

Hanya struktur/label. Tidak ada data pelanggan, username, atau password di file ini.
Tahap 1: tampilan saja; tombol simpan ke perangkat mati ("Segera"). Layout form: label `col-sm-3` kiri, kontrol kanan.

Daftar modal di halaman acuan: Change ONU type, Update ONU external ID, Configure speed profiles,
Configure ethernet port, Configure WiFi port, Delete, Reboot, Disable ONU, Enable ONU, Stop ONU, Start ONU,
Recreate OLT config for this ONU, Restore to factory defaults, Firmware Upgrade - Reset to defaults,
Update ONU mode, Update Management and VoIP IP, Move ONU, Update GPON channel, Update EPON channel,
Replace ONU by SN, Update attached VLANs, Update location details, Enable VoIP, Disable VoIP, Update IPTV.

## Update ONU mode
- WAN VLAN-ID (select; catatan: "After changing the WAN VLAN-ID, please check the Ethernet ports settings and update VLANs as desired.")
- ONU mode (radio): Routing | Bridging
- WAN mode (radio): Setup via ONU webpage; lalu teks "Settings for compatible ONUs:" DHCP | Static IP | PPPoE
- Config method (radio): OMCI | TR069 - Inactive
- WAN IP source (radio): From IP pool | Manual IP ; WAN IP address (cari IP / select pool)
- (PPPoE) username + password, WAN remote access (select)

## Update attached VLANs
- VLANs (multiselect + Search + Select all; opsi "ID - Nama" atau "ID")
- Teks: "Select from the list all the VLANs that will be used on this ONU. After changing the VLANs list, go to the Ethernet ports settings and assign VLANs as desired."
- Tombol: Close, Update

## Update location details
Zone (select), Splitter (select), Splitter port (select), Sector (select, None), Name, Address or comment,
Contact, Latitude, Longitude, link "Map »", tombol "Get current location", link "Open in Maps". Tombol: Close, Update.

## Configure ethernet port eth_0/N
Link (teks), Status: Enabled | Port shutdown, Mode: LAN | Access | Hybrid | Trunk | Transparent,
VLAN-ID (select), Allowed VLANs list (multiselect, hanya Trunk/Hybrid), DHCP: No control | From ISP | From ONU | Forbidden.
Tombol: Close, Save (hijau).

## Configure WiFi port wifi_0/N
Status: Enabled | Port shutdown, Mode: LAN | Access | Hybrid | Trunk, VLAN-ID, Allowed VLANs list, SSID,
Auth mode: WPA2 | Auto | Open (catatan "Authentication capabilities have not been reported by the ONU."),
Encryption: AES, link "View/Change password", DHCP, tombol "Clear WiFi port settings", Close, Save.
