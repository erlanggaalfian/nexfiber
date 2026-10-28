from abc import ABC, abstractmethod

from app.drivers.types import (
    AuthorizeRequest,
    ConnectionCheck,
    DriverResult,
    InterfaceStatus,
    ModifyRequest,
    OltHealth,
    OltInventory,
    OltProvisioning,
    OnuLiveDetail,
    OnuReport,
    OnuStatusSample,
    OpticalSample,
    PonPortInfo,
    TrafficProfile,
    UnconfiguredOnu,
)


class OltDriver(ABC):
    """Vendor-agnostic contract (PRD 4.3). MVP ships a ZTE implementation only; CDATA/TR-069
    are Phase 2 and must not be added here.
    """

    vendor: str
    model: str
    port_range: tuple[int, int]
    capabilities: set[str]  # e.g. {"snmp_rx", "cli_rx", "tr069_profile", "wan_config"}

    @abstractmethod
    async def test_connection(self) -> ConnectionCheck:
        """CLI dan SNMP diuji terpisah; satu boolean per protokol (lihat ConnectionCheck)."""

    @abstractmethod
    async def fetch_health(self) -> OltHealth:
        """CPU/RAM/suhu/uptime/versi/kartu untuk tab Monitoring (PRD 3.4.7)."""

    @abstractmethod
    async def set_vlan_ports(self, vlan_id: int, ports: dict[str, str]) -> DriverResult:
        """{nama_port: "tagged"|"untagged"} di port uplink."""

    @abstractmethod
    async def fetch_interfaces(self) -> list[InterfaceStatus]:
        """Status live tiap port uplink fisik untuk tab Interfaces (PRD 3.4.7)."""

    @abstractmethod
    async def set_port_config(self, port: str, auto_nego: str, speed: str | None,
                              duplex: str | None) -> DriverResult:
        """Auto-negotiation/speed/duplex satu port uplink. auto_nego="enable" mengabaikan
        speed/duplex (perangkat yang menentukan).
        """

    @abstractmethod
    async def list_unconfigured(self) -> list[UnconfiguredOnu]: ...

    @abstractmethod
    async def authorize(self, req: AuthorizeRequest) -> DriverResult: ...

    @abstractmethod
    async def modify(self, req: ModifyRequest) -> DriverResult: ...

    @abstractmethod
    async def delete(self, slot: int, port: int, onu_id: int) -> DriverResult: ...

    @abstractmethod
    async def set_state(self, slot: int, port: int, onu_id: int, enabled: bool) -> DriverResult: ...

    @abstractmethod
    async def reboot(self, slot: int, port: int, onu_id: int) -> DriverResult: ...

    @abstractmethod
    async def fetch_inventory(self) -> OltInventory: ...

    @abstractmethod
    async def fetch_onu_status(self) -> list[OnuStatusSample]: ...

    @abstractmethod
    async def fetch_optical(self, slot: int | None, port: int | None) -> list[OpticalSample]: ...

    @abstractmethod
    async def fetch_provisioning(self) -> OltProvisioning:
        """Profil kecepatan terpakai + VLAN service-port + jarak SETIAP ONU, satu kali baca
        untuk seluruh OLT (SNMP-first; jangan per-PON/per-ONU). Dipakai onboarding_sync.
        """

    @abstractmethod
    async def backup_config(self) -> str: ...

    @abstractmethod
    async def list_pon_ports(self) -> list[PonPortInfo]: ...

    async def fetch_pon_oper_states(self) -> dict[tuple[int, int], str]:
        """ifOperStatus per PON {(slot, port): "up"|"down"}.

        Non-abstrak (default {}) supaya FakeDriver di tes lama tidak wajib mengisi;
        implementasi ZTE ada di zte_c320. sync_service tetap memanggil lewat getattr
        sebagai jaring pengaman untuk driver/fake yang lebih lama lagi.
        """
        return {}

    @abstractmethod
    async def list_onu_ids(self, slot: int, port: int) -> list[int]:
        """ONU IDs currently configured on one PON, read live (authorize picks a free one)."""

    @abstractmethod
    async def fetch_onu_detail(self, slot: int, port: int, onu_id: int) -> OnuLiveDetail:
        """Baca live satu ONU untuk halaman Detail ONU (PRD 3.4.6): optical, jarak,
        versi software/hardware dan running-config read-only.
        """

    @abstractmethod
    async def fetch_onu_status_report(self, slot: int, port: int, onu_id: int) -> OnuReport:
        """Laporan read-only 9 blok untuk tombol `Status` di Detail ONU."""

    async def fetch_onu_ip_host(self, slot: int, port: int, onu_id: int) -> tuple[str, str]:
        """Pasangan (laporan `show gpon remote-onu ip-host`, `show onu running config`),
        read-only, satu sesi CLI: laporan memuat IP per blok `Host ID`, running-config
        memuat pemetaan `ip-host N` -> VLAN untuk verifikasi (lihat `parse_current_ip`).
        # ponytail: default non-abstrak supaya FakeDriver di tes tidak wajib mengisi;
        # naikkan jadi @abstractmethod saat vendor selain ZTE muncul."""
        raise NotImplementedError

    @abstractmethod
    async def fetch_onu_running_config(self, slot: int, port: int, onu_id: int) -> OnuReport:
        """Running-config ONU 3 blok (registrasi + interface + pon-onu-mng), read-only.

        Isi bisa memuat kredensial pelanggan: pemanggil wajib sudah memeriksa role.
        """

    @abstractmethod
    async def fetch_onu_software_report(self, slot: int, port: int, onu_id: int) -> OnuReport:
        """Info hardware/software + kemampuan ONU untuk tombol `Info SW`, read-only."""

    @abstractmethod
    async def set_onu_vlan(self, slot: int, port: int, onu_id: int, old_vlan: int | None,
                           new_vlan: int) -> DriverResult:
        """Pindahkan ONU ke VLAN lain; old_vlan dibutuhkan untuk mencabut flow yang lama."""

    @abstractmethod
    async def restore_factory(self, slot: int, port: int, onu_id: int) -> DriverResult:
        """Reset ONU ke setelan pabrik (aksi destruktif, selalu lewat job + konfirmasi UI)."""

    async def run_onu_commands(self, commands: list[str]) -> DriverResult:
        """Kirim satu blok perintah config ONU yang sudah dibangun pemanggil.

        Dipakai aksi/konfigurasi ONU (modal SmartOLT) supaya setiap kind tidak perlu
        method driver sendiri: pembangun perintahnya per-vendor, pengirimannya satu pintu.
        Driver yang belum mendukung menolaknya.
        """
        raise NotImplementedError(f"{self.vendor} {self.model} belum mendukung aksi ONU ini")


    @abstractmethod
    async def create_vlan(self, vlan_id: int, description: str | None) -> DriverResult: ...

    @abstractmethod
    async def delete_vlan(self, vlan_id: int) -> DriverResult: ...

    @abstractmethod
    async def create_traffic_profile(
        self, name: str, direction: str, kbps: int
    ) -> DriverResult:
        """Satu profile T-CONT (upload) atau traffic (download) di device, per arah."""

    @abstractmethod
    async def list_traffic_profiles(self) -> list[TrafficProfile]: ...
