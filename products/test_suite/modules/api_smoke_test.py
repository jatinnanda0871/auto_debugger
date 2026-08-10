from engine.api import DumpAnalyzer
from products.test_suite.config import (
    OCCUPIED_TAGS_ADDR,
    PENDING_KEYS,
    FCC_COUNTERS_ADDR,
    FCC_COUNTER_SIZE,
)

# ── Analyzers ──────────────────────────────────────────────────────────────────
#
# Exercises the DumpAnalyzer public API broadly against the scenario_*
# fixtures -- every method reachable for the declared keys gets called at
# least once. Every key here is guaranteed present in every scenario_*
# fixture (see config.py), so these do NOT defensively check
# key_exists/is_region_in_dump/get_missing_regions before using a key -- if
# one ever actually goes missing, the underlying engine.api call is the
# thing that should raise or warn, and that's what tests/test_api.py checks
# directly. Skipping here would just hide that regression.


def analyze_key_presence(analyzer: DumpAnalyzer) -> None:
    print("\n=== Key presence ===")
    for key in [OCCUPIED_TAGS_ADDR, *PENDING_KEYS, FCC_COUNTERS_ADDR]:
        print(f"  key_exists({key}) = {analyzer.key_exists(key)}")


def analyze_coverage(analyzer: DumpAnalyzer) -> None:
    print("\n=== Dump coverage ===")
    for key in [OCCUPIED_TAGS_ADDR, *PENDING_KEYS, FCC_COUNTERS_ADDR]:
        print(f"  is_region_in_dump({key}) = {analyzer.is_region_in_dump(key)}")


def analyze_occupied_tags(analyzer: DumpAnalyzer) -> None:
    print("\n=== Occupied tags (API smoke) ===")

    region = analyzer.get_region(OCCUPIED_TAGS_ADDR)
    print(f"  base_addr=0x{region.base_addr:08X} size_bytes={region.size_bytes} "
          f"size_dwords={region.size_dwords}")

    dwords = analyzer.get_region_dwords(OCCUPIED_TAGS_ADDR)
    print(f"  get_region_dwords -> {len(dwords)} dword(s)")

    for i, dw in analyzer.iter_dwords(OCCUPIED_TAGS_ADDR):
        pass  # exercised for coverage; per-dword detail not needed here
    print(f"  iter_dwords -> {i + 1} dword(s) walked")

    tags = analyzer.get_set_bits(OCCUPIED_TAGS_ADDR)
    print(f"  get_set_bits -> {len(tags)} set")
    print(f"  count_set_tags -> {analyzer.count_set_tags(OCCUPIED_TAGS_ADDR)}")

    if tags:
        first_tag = tags[0]
        print(f"  is_tag_set_in_region(first={first_tag}) -> "
              f"{analyzer.is_tag_set_in_region(OCCUPIED_TAGS_ADDR, first_tag)}")

    union = analyzer.get_tags_in_any(*PENDING_KEYS)
    print(f"  get_tags_in_any({PENDING_KEYS}) -> {len(union)} tag(s)")

    cmp = analyzer.compare_tag_counts(PENDING_KEYS[0], PENDING_KEYS[1])
    print(f"  compare_tag_counts -> {cmp}")


def analyze_fcc_vs_tags(analyzer: DumpAnalyzer) -> None:
    print("\n=== FCC counters vs occupied tags (API smoke) ===")

    fcc_mask = (1 << FCC_COUNTER_SIZE) - 1
    print(f"  fcc mask = 0x{fcc_mask:02X}")

    total_fcc = analyzer.sum_bitfield_across_region(FCC_COUNTERS_ADDR, bit_offset=0, bit_width=FCC_COUNTER_SIZE)
    print(f"  sum_bitfield_across_region -> {total_fcc}")

    print(f"  any_nonzero(FccManager::counters) -> {analyzer.any_nonzero(FCC_COUNTERS_ADDR)}")

    struct_count = 0
    for idx, byte_offset in analyzer.iter_struct_array(FCC_COUNTERS_ADDR, struct_size_bytes=4):
        struct_count += 1
    print(f"  iter_struct_array(struct_size=4) -> {struct_count} entries")

    pending_count = analyzer.count_set_tags(OCCUPIED_TAGS_ADDR)
    print(f"  count_set_tags(occupied) -> {pending_count}"
          f"  (real assertion lives in tag_consistency_check.py, not here)")


def analyze_bitfield_access(analyzer: DumpAnalyzer) -> None:
    print("\n=== Bitfield access (API smoke) ===")

    low_byte = analyzer.get_bitfield(OCCUPIED_TAGS_ADDR, bit_offset=0, bit_width=8)
    print(f"  get_bitfield(bit_offset=0, bit_width=8) -> 0x{low_byte:02X}")

    at_offset = analyzer.get_bitfield_at_offset(OCCUPIED_TAGS_ADDR, byte_offset=0, bit_offset=0, bit_width=1)
    print(f"  get_bitfield_at_offset(0,0,1) -> {at_offset}")

    first_byte = analyzer.get_byte(OCCUPIED_TAGS_ADDR, byte_offset=0)
    print(f"  get_byte(offset=0) -> 0x{first_byte:02X}")

    print(f"  is_bit_set(bit=0) -> {analyzer.is_bit_set(OCCUPIED_TAGS_ADDR, 0)}")
    print(f"  get_dword(is_address=False) -> 0x{analyzer.get_dword(OCCUPIED_TAGS_ADDR, is_address=False):08X}")


# ── Module entry point — called by product.py ──────────────────────────────────

def run(analyzer: DumpAnalyzer) -> None:
    analyze_key_presence(analyzer)
    analyze_coverage(analyzer)
    analyze_occupied_tags(analyzer)
    analyze_bitfield_access(analyzer)
    analyze_fcc_vs_tags(analyzer)
