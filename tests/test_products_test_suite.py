"""
End-to-end tests for the products/test_suite product itself (api_smoke_test +
tag_consistency_check + mirror_consistency_check + sum_check +
reserved_region_check) against every fixture under
products/test_suite/sample_dumps/.
"""

import importlib.util

import pytest

from products.test_suite import fixture_schema as schema
from tests.conftest import TEST_SUITE_DUMPS, build_analyzer

PRODUCT_PATH = TEST_SUITE_DUMPS.parent / "product.py"


def load_test_suite_product():
    spec   = importlib.util.spec_from_file_location("products.test_suite.product", PRODUCT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_test_suite_product_runs_without_raising_on_every_fixture(test_suite_scenario):
    analyzer = build_analyzer(test_suite_scenario)
    product  = load_test_suite_product()
    product.run(analyzer)  # must not raise for any fixture, error or clean


# ── scenario_* — identical 50-key layout ────────────────────────────────────

def test_identical_scenarios_share_the_same_map(identical_layout_scenario):
    """Every scenario_* fixture must declare the exact same 50 keys at the
    exact same addresses/sizes -- only the dump *values* should differ."""
    from engine.loader import load_map
    regions = load_map(str(identical_layout_scenario / "memory.map"))
    assert len(regions) == len(schema.LAYOUT) == 50
    for name, addr, size in schema.LAYOUT:
        assert regions[name].base_addr == addr
        assert regions[name].size_bytes == size


def test_baseline_scenario_has_no_assertion_failures(baseline_analyzer):
    load_test_suite_product().run(baseline_analyzer)
    assert baseline_analyzer._error_found is False


def test_baseline_scenario_has_expected_scale(baseline_analyzer):
    assert baseline_analyzer.count_set_tags("TagManager::occupied_tags") == schema.N_OCCUPIED
    assert baseline_analyzer.sum_bitfield_across_region(
        "FccManager::counters", bit_offset=0, bit_width=8
    ) == schema.N_OCCUPIED


def test_fcc_counter_value_error_is_isolated_to_the_fcc_check(fcc_counter_error_analyzer):
    load_test_suite_product().run(fcc_counter_error_analyzer)
    assert fcc_counter_error_analyzer._error_found is True
    # occupied count itself is untouched by this mutation
    assert fcc_counter_error_analyzer.count_set_tags("TagManager::occupied_tags") == schema.N_OCCUPIED
    # the fcc sum is the one that moved
    assert fcc_counter_error_analyzer.sum_bitfield_across_region(
        "FccManager::counters", bit_offset=0, bit_width=8
    ) == schema.N_OCCUPIED - 1


def test_occupied_tag_count_error_is_isolated_to_the_tag_count(occupied_tag_count_error_analyzer):
    load_test_suite_product().run(occupied_tag_count_error_analyzer)
    assert occupied_tag_count_error_analyzer._error_found is True
    assert occupied_tag_count_error_analyzer.count_set_tags("TagManager::occupied_tags") == schema.N_OCCUPIED + 1
    # fcc sum itself is untouched by this mutation
    assert occupied_tag_count_error_analyzer.sum_bitfield_across_region(
        "FccManager::counters", bit_offset=0, bit_width=8
    ) == schema.N_OCCUPIED


def test_pending_tag_leak_detected_without_breaking_fcc_tag_count_match(pending_tag_leak_analyzer):
    load_test_suite_product().run(pending_tag_leak_analyzer)
    assert pending_tag_leak_analyzer._error_found is True
    # counts still match -- only the pending-subset invariant is broken
    occupied = pending_tag_leak_analyzer.count_set_tags("TagManager::occupied_tags")
    fcc_sum  = pending_tag_leak_analyzer.sum_bitfield_across_region(
        "FccManager::counters", bit_offset=0, bit_width=8
    )
    assert occupied == fcc_sum == schema.N_OCCUPIED
    assert pending_tag_leak_analyzer.is_tag_set_in_region("TagManager::commit_pending", 450) is True
    assert pending_tag_leak_analyzer.is_tag_set_in_region("TagManager::occupied_tags", 450) is False


def test_mirror_mismatch_is_isolated_to_one_pair(mirror_mismatch_analyzer):
    load_test_suite_product().run(mirror_mismatch_analyzer)
    assert mirror_mismatch_analyzer._error_found is True
    # only pair 0 was touched -- every other mirror pair still matches
    for primary, shadow in schema.MIRROR_PAIRS[1:]:
        assert mirror_mismatch_analyzer.get_dword(primary) == mirror_mismatch_analyzer.get_dword(shadow)
    primary0, shadow0 = schema.MIRROR_PAIRS[0]
    assert mirror_mismatch_analyzer.get_dword(primary0) != mirror_mismatch_analyzer.get_dword(shadow0)
    # domain (Tag/Fcc) invariants remain untouched by this mutation
    occupied = mirror_mismatch_analyzer.count_set_tags("TagManager::occupied_tags")
    fcc_sum  = mirror_mismatch_analyzer.sum_bitfield_across_region(
        "FccManager::counters", bit_offset=0, bit_width=8
    )
    assert occupied == fcc_sum == schema.N_OCCUPIED


def test_sum_check_mismatch_is_isolated_to_one_group(sum_check_mismatch_analyzer):
    load_test_suite_product().run(sum_check_mismatch_analyzer)
    assert sum_check_mismatch_analyzer._error_found is True
    for region, total in schema.SUM_CHECK_GROUPS[1:]:
        region_sum = sum(dw for _, dw in sum_check_mismatch_analyzer.iter_dwords(region))
        assert region_sum == sum_check_mismatch_analyzer.get_dword(total)
    region0, total0 = schema.SUM_CHECK_GROUPS[0]
    region0_sum = sum(dw for _, dw in sum_check_mismatch_analyzer.iter_dwords(region0))
    assert region0_sum != sum_check_mismatch_analyzer.get_dword(total0)


def test_reserved_region_set_is_isolated_to_one_key(reserved_region_set_analyzer):
    load_test_suite_product().run(reserved_region_set_analyzer)
    assert reserved_region_set_analyzer._error_found is True
    flagged = [k for k in schema.RESERVED_KEY_NAMES if reserved_region_set_analyzer.any_nonzero(k)]
    assert flagged == [schema.RESERVED_KEY_NAMES[0]]


@pytest.mark.parametrize("scenario,expected_error", [
    ("scenario_01_baseline_no_errors", False),
    ("scenario_02_fcc_counter_value_error", True),
    ("scenario_03_occupied_tag_count_error", True),
    ("scenario_04_pending_tag_leak", True),
    ("scenario_05_mirror_mismatch", True),
    ("scenario_06_sum_check_mismatch", True),
    ("scenario_07_reserved_region_set", True),
])
def test_scenario_error_state_matches_recorded_expectation(scenario, expected_error):
    """Pins the pass/fail outcome of every scenario_* fixture."""
    analyzer = build_analyzer(TEST_SUITE_DUMPS / scenario)
    load_test_suite_product().run(analyzer)
    assert analyzer._error_found is expected_error
