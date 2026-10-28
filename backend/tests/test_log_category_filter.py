"""Filter kategori Logs: kondisi SQL di repo harus mencerminkan `category_of`
tanpa bergantung pada daftar aksi statis (regression test untuk bug filter
yang menyembunyikan `onu.action.*`, `onu.read_ip_host`, `graph_data.*`, dll).

Tidak butuh Postgres: kondisi dievaluasi lewat SQLite in-memory pada tabel
minimal yang kolom `action`-nya sama dengan `ActivityLog.action`.
"""
from sqlalchemy import create_engine, select, text

from app.models.activity_log import ActivityLog
from app.repositories.activity_log_repo import _category_condition
from app.schemas.activity_log import category_of


def _actions_for(category: str) -> set[str]:
    """Aksi yang lolos kondisi SQL kategori ini, dievaluasi di SQLite."""
    engine = create_engine("sqlite://")
    # Tabel minimal bernama activity_logs (sama dengan ActivityLog.__tablename__)
    # supaya kondisi SQL yang merujuk ActivityLog.action bisa dievaluasi.
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE activity_logs (action VARCHAR(100))"))
    actions = [
        "onu.authorize", "onu.reboot", "onu.delete", "onu.restore_factory",
        "onu.action.speed-profile", "onu.action.replace-sn", "onu.read_ip_host",
        "onu.update_info", "onu.read_status", "olt.create", "olt.push_port_config",
        "olt.sync_all", "user.create", "user.delete", "graph_data.delete",
        "graph_data.set_retention", "vlan.create", "speed_profile.create",
    ]
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO activity_logs (action) VALUES (:a)"),
            [{"a": a} for a in actions],
        )
        rows = conn.execute(
            select(ActivityLog.action).where(_category_condition(category))
        ).scalars().all()
    return set(rows)


def test_category_sql_matches_category_of():
    for category in ("authorize", "reboot", "delete", "olt", "user", "service"):
        got = _actions_for(category)
        # Semua aksi yang category_of-nya = kategori ini harus lolos filter itu.
        expected = {
            a for a in [
                "onu.authorize", "onu.reboot", "onu.delete", "onu.restore_factory",
                "onu.action.speed-profile", "onu.action.replace-sn", "onu.read_ip_host",
                "onu.update_info", "onu.read_status", "olt.create", "olt.push_port_config",
                "olt.sync_all", "user.create", "user.delete", "graph_data.delete",
                "graph_data.set_retention", "vlan.create", "speed_profile.create",
            ] if category_of(a) == category
        }
        assert expected <= got, f"{category}: hilang {expected - got}"
        # Dan tidak ada aksi kategori lain yang bocor ke kategori ini.
        assert got == expected, f"{category}: got {got}, expected {expected}"
