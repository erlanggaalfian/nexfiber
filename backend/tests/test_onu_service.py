from app.services.onu_service import pick_free_onu_index


def test_pick_free_onu_index_fills_first_gap_and_reports_full():
    assert pick_free_onu_index([], 128) == 1
    assert pick_free_onu_index([1, 2, 4], 128) == 3
    assert pick_free_onu_index(list(range(1, 129)), 128) is None
