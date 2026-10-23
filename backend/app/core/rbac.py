"""Per-role permission checks (PRD decision: role is a Postgres ENUM, permissions hardcoded here
— not a data-driven permissions table). Adding a 5th role later means adding it to the ENUM
migration and to the sets below; no other model changes needed.
"""

# PRD M9 / Trade-off #4: admin = semua; noc = lihat + reboot + lihat sinyal, tidak ubah konfigurasi
# OLT; teknisi = aktivasi + lihat, tidak boleh hapus/ubah master data; viewer = read-only.
CAN_MANAGE_OLTS = {"admin"}
CAN_MANAGE_MASTER_DATA = {"admin"}  # VLAN, speed profile, splitter CRUD
CAN_AUTHORIZE_ONU = {"admin", "teknisi"}
CAN_REBOOT_ONU = {"admin", "noc"}
CAN_MODIFY_ONU = {"admin", "noc"}
CAN_DELETE_ONU = {"admin", "noc"}  # PRD 4.6: "hanya admin/noc boleh delete/reboot ONU"
CAN_MANAGE_USERS = {"admin"}


class PermissionDenied(Exception):
    pass


def require_role(role: str, allowed: set[str]) -> None:
    if role not in allowed:
        raise PermissionDenied(f"role '{role}' is not permitted to perform this action")

def permissions_for(role: str) -> list[str]:
    """Names like 'authorize_onu' (CAN_ prefix stripped) so the UI can hide forbidden actions."""
    return sorted(k[4:].lower() for k, v in globals().items() if k.startswith("CAN_") and role in v)
