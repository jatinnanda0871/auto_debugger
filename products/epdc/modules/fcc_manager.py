from engine.api import DumpAnalyzer
from products.epdc.config import *
from products.epdc.generated_structs.big_struct import dword7_checksum_t


# ── Analyzers ──────────────────────────────────────────────────────────────────

def analyze_fcc_counter(analyzer: DumpAnalyzer) -> None:
    print("\n=== FCC Counter Analysis ===")

    func_count = analyzer.get_region_size_dwords(FCC_COUNTERS_ADDR)
    print(f"  Total Functions      : {func_count}  (derived from region size)")

    print(f"\n  {'Function':<12} {'Raw Dword':<12} {'FCC Counter':<12}")
    print(f"  {'-'*36}")

    total_fcc = 0
    for i in range(func_count):
        # Each per-function dword is typecast to dword7_checksum_t -- the
        # count itself lives in its mixed.crc byte.
        record  = analyzer.get_struct(FCC_COUNTERS_ADDR, dword7_checksum_t, byte_offset=i * 4)
        fcc_val = record.mixed.crc
        total_fcc += fcc_val
        print(f"  Func[{i:<2}]     0x{record.raw:08X}      {fcc_val}")

    pending_count = analyzer.count_set_tags(PENDING_TAG_ADDR)

    print()
    analyzer.assert_equal("FCC count vs pending tags", total_fcc, pending_count)


# ── Module entry point — called by product.py ──────────────────────────────────

def run(analyzer: DumpAnalyzer) -> None:
    analyze_fcc_counter(analyzer)
