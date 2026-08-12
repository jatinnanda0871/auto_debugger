from engine.api import DumpAnalyzer
from products.test_suite.config import MIRROR_PAIRS

# ── Analyzers ──────────────────────────────────────────────────────────────────
#
# "Value at dword X identical to value at dword Y" -- a common real-world
# check for redundant/backup register pairs. Each pair should read
# identically; a mismatch means the primary and shadow copies drifted apart.
#
# Every key in MIRROR_PAIRS is guaranteed present in every scenario_*
# fixture (see config.py) -- no defensive missing-region check before use.


def run(analyzer: DumpAnalyzer) -> None:
    print("\n=== Mirror pair consistency ===")
    for primary, shadow in MIRROR_PAIRS:
        primary_val = analyzer.get_dword(primary)
        shadow_val  = analyzer.get_dword(shadow)
        print(f"  {primary} = 0x{primary_val:08X}   {shadow} = 0x{shadow_val:08X}")
        analyzer.assert_equal(f"{primary} == {shadow}", primary_val, shadow_val)
