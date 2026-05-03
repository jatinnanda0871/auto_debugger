from engine.api import DumpAnalyzer
from products.epdc.config import TAG_OCCUPIED_KEY, FCC_COUNTERS_KEY, FCC_COUNTER_SIZE_KEY


def analyze_fcc_counter(analyzer: DumpAnalyzer) -> None:
    print("\n=== FCC Counter Analysis ===")

    missing = analyzer.get_missing_regions(
        FCC_COUNTER_SIZE_KEY,
        FCC_COUNTERS_KEY,
        TAG_OCCUPIED_KEY,
    )
    if missing:
        print(f"  [SKIP] Missing regions: {missing}")
        return

    fcc_counter_size = analyzer.get_value(FCC_COUNTER_SIZE_KEY, is_address=False)
    fcc_mask         = (1 << fcc_counter_size) - 1
    print(f"  fcc_counter_size : {fcc_counter_size} bits  (mask=0x{fcc_mask:08X})")

    func_count = analyzer.get_region_size_dwords(FCC_COUNTERS_KEY)
    print(f"  func_count       : {func_count}  (derived from region size)")

    print(f"\n  {'Function':<12} {'Raw Dword':<12} {'FCC Counter':<12}")
    print(f"  {'-'*36}")

    total_fcc = analyzer.sum_bitfield_across_region(
        FCC_COUNTERS_KEY, bit_offset=0, bit_width=fcc_counter_size
    )

    for i, dw in analyzer.iter_dwords(FCC_COUNTERS_KEY):
        fcc_val = dw & fcc_mask
        print(f"  Func[{i:<6}]  0x{dw:08X}   {fcc_val}")

    pending_count = analyzer.count_set_tags(TAG_OCCUPIED_KEY)

    print()
    analyzer.assert_equal("FCC count vs pending tags", total_fcc, pending_count)
