from api import DumpAnalyzer
from products.epdc.config import PENDING_TAG_ADDR, FCC_COUNTERS_ADDR, FCC_COUNTER_SIZE


# ── Analyzers ──────────────────────────────────────────────────────────────────

def analyze_fcc_counter(analyzer: DumpAnalyzer) -> None:
    print("\n=== FCC Counter Analysis ===")

    # FCC_COUNTER_SIZE is a literal value in the map (not a dump address),
    # so check only dump-backed regions for coverage.
    missing = analyzer.get_missing_regions(FCC_COUNTERS_ADDR, PENDING_TAG_ADDR)
    if missing:
        print(f"  [SKIP] Missing regions: {missing}")
        return
    if not analyzer.key_exists(FCC_COUNTER_SIZE):
        print(f"  [SKIP] '{FCC_COUNTER_SIZE}' not in map")
        return

    fcc_counter_size = analyzer.get_value(FCC_COUNTER_SIZE, is_address=False)
    fcc_mask         = (1 << fcc_counter_size) - 1
    print(f"  fcc_count_field_size : {fcc_counter_size} bits  (mask=0x{fcc_mask:08X})")

    func_count = analyzer.get_region_size_dwords(FCC_COUNTERS_ADDR)
    print(f"  Total Functions      : {func_count}  (derived from region size)")

    print(f"\n  {'Function':<12} {'Raw Dword':<12} {'FCC Counter':<12}")
    print(f"  {'-'*36}")

    total_fcc = analyzer.sum_bitfield_across_region(
        FCC_COUNTERS_ADDR, bit_offset=0, bit_width=fcc_counter_size
    )

    for i, dw in analyzer.iter_dwords(FCC_COUNTERS_ADDR):
        fcc_val = dw & fcc_mask
        print(f"  Func[{i:<2}]     0x{dw:08X}      {fcc_val}")

    pending_count = analyzer.count_set_tags(PENDING_TAG_ADDR)

    print()
    analyzer.assert_equal("FCC count vs pending tags", total_fcc, pending_count)


# ── Module entry point — called by product.py ──────────────────────────────────

def run(analyzer: DumpAnalyzer) -> None:
    analyze_fcc_counter(analyzer)
