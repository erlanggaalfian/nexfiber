from abc import ABC, abstractmethod

from app.drivers.types import (
    AuthorizeRequest,
    DriverResult,
    ModifyRequest,
    OnuSnapshot,
    OnuStatusSample,
    OpticalSample,
    PonPortInfo,
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
    async def test_connection(self) -> DriverResult: ...

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
    async def fetch_inventory(self) -> list[OnuSnapshot]: ...

    @abstractmethod
    async def fetch_onu_status(self) -> list[OnuStatusSample]: ...

    @abstractmethod
    async def fetch_optical(self, slot: int | None, port: int | None) -> list[OpticalSample]: ...

    @abstractmethod
    async def backup_config(self) -> str: ...

    @abstractmethod
    async def list_pon_ports(self) -> list[PonPortInfo]: ...

    @abstractmethod
    async def list_onu_ids(self, slot: int, port: int) -> list[int]:
        """ONU IDs currently configured on one PON, read live (authorize picks a free one)."""
