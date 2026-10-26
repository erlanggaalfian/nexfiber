from types import SimpleNamespace
from typing import Any, cast

from app.schemas.onu import DEFAULT_ONU_MODE, DEFAULT_WAN_MODE
from app.services.onu_service import _apply_mode_defaults, pick_free_onu_index


def test_pick_free_onu_index_fills_first_gap_and_reports_full():
    assert pick_free_onu_index([], 128) == 1
    assert pick_free_onu_index([1, 2, 4], 128) == 3
    assert pick_free_onu_index(list(range(1, 129)), 128) is None


def _detail(onu_mode, wan_mode) -> Any:
    """Pengganti OnuDetail: hanya empat field yang disentuh _apply_mode_defaults."""
    return SimpleNamespace(onu_mode=onu_mode, wan_mode=wan_mode,
                           onu_mode_source="cli", wan_mode_source="cli")


def test_mode_defaults_only_fill_what_cli_did_not_read():
    # Terbaca di CLI: nilainya dipakai apa adanya, sumber tetap "cli".
    d = _detail("bridging", "pppoe")
    _apply_mode_defaults(cast(Any, d))
    assert (d.onu_mode, d.onu_mode_source) == ("bridging", "cli")
    assert (d.wan_mode, d.wan_mode_source) == ("pppoe", "cli")

    # Tidak ada di CLI (NULL atau string kosong): default pemilik + sumber "default".
    for empty in (None, ""):
        d = _detail(empty, empty)
        _apply_mode_defaults(cast(Any, d))
        assert (d.onu_mode, d.onu_mode_source) == (DEFAULT_ONU_MODE, "default")
        assert (d.wan_mode, d.wan_mode_source) == (DEFAULT_WAN_MODE, "default")

    # Default yang dipaku pemilik: Routing + Setup via ONU webpage.
    assert (DEFAULT_ONU_MODE, DEFAULT_WAN_MODE) == ("routing", "webpage")

    # Satu sisi terbaca, satu sisi tidak: masing-masing dinilai sendiri.
    d = _detail(None, "dhcp")
    _apply_mode_defaults(cast(Any, d))
    assert (d.onu_mode_source, d.wan_mode_source) == ("default", "cli")
