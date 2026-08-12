from engine.api import DumpAnalyzer
from products.test_suite.config import OCCUPIED_TAGS_ADDR, PENDING_KEYS, FCC_COUNTERS_ADDR, FCC_COUNTER_SIZE

# ── Analyzers ──────────────────────────────────────────────────────────────────
#
# Domain-level cross-region invariants for the TagManager/FccManager keys,
# same pattern as products/epdc but reused here against the test_suite
# fixtures (products/test_suite/sample_dumps/scenario_*).
#
# Every key here is guaranteed present in every scenario_* fixture (see
# config.py) -- no defensive key_exists/is_region_in_dump/get_missing_regions
# check before use. A key that's actually missing is a bug the underlying
# engine.api call should surface on its own.


def check_fcc_counters_match_occupied_tags(analyzer: DumpAnalyzer) -> None:
    print("\n=== FCC counters vs occupied tags ===")

    total_fcc      = analyzer.sum_bitfield_across_region(FCC_COUNTERS_ADDR, bit_offset=0, bit_width=FCC_COUNTER_SIZE)
    occupied_count = analyzer.count_set_tags(OCCUPIED_TAGS_ADDR)
    print(f"  fcc total = {total_fcc}, occupied tag count = {occupied_count}")
    analyzer.assert_equal("FCC counter total vs occupied tag count", total_fcc, occupied_count)


def check_pending_tags_are_subset_of_occupied(analyzer: DumpAnalyzer) -> None:
    print("\n=== Pending tags subset of occupied ===")

    occupied = set(analyzer.get_set_bits(OCCUPIED_TAGS_ADDR))
    pending  = set(analyzer.get_tags_in_any(*PENDING_KEYS))
    leaked   = sorted(pending - occupied)

    print(f"  occupied={len(occupied)} pending_union={len(pending)} leaked={leaked}")
    analyzer.assert_equal("Pending tags not present in occupied_tags", len(leaked), 0)


# ── Module entry point — called by product.py ──────────────────────────────────

def run(analyzer: DumpAnalyzer) -> None:
    check_fcc_counters_match_occupied_tags(analyzer)
    check_pending_tags_are_subset_of_occupied(analyzer)
