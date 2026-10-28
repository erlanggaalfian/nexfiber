"""Logs — PRD 3.4.15. Satu kategori = prefix `action` sebelum titik (onu/olt/user/vlan/...)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

LogCategory = Literal["authorize", "reboot", "service", "delete", "olt", "user", "login"]

# Prefix action -> kategori filter UI. Beberapa action onu masuk kategori lebih spesifik
# daripada entity_type-nya (mis. onu.delete -> "delete", bukan "onu").
_CATEGORY_BY_ACTION: dict[str, LogCategory] = {
    "onu.authorize": "authorize",
    "onu.reboot": "reboot",
    "onu.delete": "delete",
    "onu.restore_factory": "delete",
    "onu.apply_speed_profile": "service",
    "onu.set_vlan": "service",
    "onu.set_state": "service",
    "user.login": "login",
}


def category_of(action: str) -> LogCategory:
    if action in _CATEGORY_BY_ACTION:
        return _CATEGORY_BY_ACTION[action]
    # Konsisten dengan kondisi SQL di activity_log_repo: semua penghapusan
    # (apa pun prefix-nya) adalah kategori "delete", dan user.login adalah
    # "login", bukan "user". Sebelumnya keduanya jatuh ke kategori prefix
    # sehingga filter Hapus menyembunyikan sebagian besar penghapusan.
    if action.endswith(".delete") or action == "onu.restore_factory":
        return "delete"  # type: ignore[return-value]
    if action == "user.login":
        return "login"  # type: ignore[return-value]
    entity = action.split(".", 1)[0]
    return "olt" if entity == "olt" else "user" if entity == "user" else "service"  # type: ignore[return-value]


# Dipakai service buat filter kategori -> daftar action persis, karena category_of() tidak
# invertible 1:1 (mis. semua "entity.xxx" generik jatuh ke "service"/"olt"/"user" by default).
_KNOWN_ACTIONS = [
    "onu.authorize", "onu.reboot", "onu.delete", "onu.restore_factory",
    "onu.apply_speed_profile", "onu.set_vlan", "onu.set_state", "onu.refresh_detail",
    "user.login", "user.create", "user.update", "user.delete", "user.reset_password",
    "olt.delete",
    "olt.create", "olt.update", "olt.delete", "olt.test_connection",
    "vlan.create", "vlan.update", "vlan.set_ports", "vlan.delete",
    "speed_profile.create", "speed_profile.update", "speed_profile.delete", "speed_profile.push",
    "zone.create", "zone.update", "zone.delete",
    "splitter.create", "splitter.update", "splitter.delete",
    "onu_type.create", "onu_type.update", "onu_type.delete",
    "onu_preset.create", "onu_preset.delete",
]


def actions_for_category(category: LogCategory) -> list[str]:
    # LEGACY, hanya untuk test: filter DB sekarang memakai kondisi SQL di
    # activity_log_repo._category_condition supaya aksi baru tidak pernah hilang
    # dari filter hanya karena belum ditambahkan ke daftar ini.
    return [a for a in _KNOWN_ACTIONS if category_of(a) == category]


class LogRow(BaseModel):
    id: int
    created_at: datetime
    username: str | None
    action: str
    category: LogCategory
    olt_id: int | None
    olt_name: str | None
    onu_id: int | None
    onu_serial: str | None
    entity_type: str
    entity_id: str | None
    success: bool
    raw_command: str | None
    raw_output: str | None


class LogPage(BaseModel):
    items: list[LogRow]
    total: int
    page: int
    size: int
