from engine.api import DumpAnalyzer
from products.test_suite.config import SUM_CHECK_GROUPS

# ── Analyzers ──────────────────────────────────────────────────────────────────
#
# "Sum of all dwords in region 'dummy' equals the value of the dword at
# location Z" -- a running-total/checksum register kept alongside raw
# per-slot data, a common real-world firmware pattern.
#
# Every key in SUM_CHECK_GROUPS is guaranteed present in every scenario_*
# fixture (see config.py) -- no defensive missing-region check before use.


def run(analyzer: DumpAnalyzer) -> None:
    print("\n=== Sum-check regions vs stored totals ===")
    for region, total in SUM_CHECK_GROUPS:
        region_sum   = sum(dw for _, dw in analyzer.iter_dwords(region))
        stored_total = analyzer.get_dword(total)
        print(f"  sum({region}) = {region_sum}   {total} = {stored_total}")
        analyzer.assert_equal(f"sum({region}) == {total}", region_sum, stored_total)
