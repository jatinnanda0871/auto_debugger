from engine.api import DumpAnalyzer
from products.test_suite.config import RESERVED_KEYS

# ── Analyzers ──────────────────────────────────────────────────────────────────
#
# "Is any field/dword/byte in this region set" -- most of a real firmware
# dump is unused/reserved memory that must stay zero. Any bit set there
# usually means either memory corruption or an undocumented write.
#
# Every key in RESERVED_KEYS is guaranteed present in every scenario_*
# fixture (see config.py) -- no defensive key_exists/is_region_in_dump
# check before use.


def run(analyzer: DumpAnalyzer) -> None:
    print("\n=== Reserved region zero-check ===")
    unexpectedly_set = [key for key in RESERVED_KEYS if analyzer.any_nonzero(key)]

    print(f"  checked {len(RESERVED_KEYS)} reserved key(s); {len(unexpectedly_set)} unexpectedly nonzero")
    if unexpectedly_set:
        print(f"  nonzero reserved key(s): {unexpectedly_set}")
    analyzer.assert_equal("Reserved key(s) unexpectedly nonzero", len(unexpectedly_set), 0)
