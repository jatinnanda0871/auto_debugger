from engine.api import DumpAnalyzer
import config

def analyze_occupied_tags(analyzer: DumpAnalyzer) -> None:
    print("\n=== Occupied Tags ===")

    tags = analyzer.get_set_bits("TagManager::occupied_tags")

    if not tags:
        print("  No tags occupied")
        return

    print(f"  Occupied tags ({len(tags)} total):")

    for tag in tags:
        print(f"\n  Tag 0x{tag:04X}:")

        # Only check pending regions if tag is occupied
        any_pending = False
        for key in PENDING_KEYS:
            dw_index  = tag // 32
            bit_index = tag % 32
            dwords    = analyzer.get_region_dwords(key)

            if dw_index < len(dwords) and (dwords[dw_index] & (1 << bit_index)):
                queue_name = key.split("::")[-1]
                print(f"    Pending in : {queue_name}")
                any_pending = True

        if not any_pending:
            print(f"    Not pending in any queue")


def analyze_fcc_counter(analyzer: DumpAnalyzer) -> None:
    print("\n=== FCC Counter Analysis ===")

    fcc_counter_size = FCC_COUNTER_SIZE
    fcc_mask         = (1 << fcc_counter_size) - 1
    print(f"  fcc_count_field_size : {fcc_counter_size} bits  (mask=0x{fcc_mask:08X})")

    func_count    = analyzer.get_region_size_dwords("FccManager::counters")
    print(f"  Total Functions  : {func_count}  (derived from region size)")

    print(f"\n  {'Function':<12} {'Raw Dword':<12} {'FCC Counter':<12}")
    print(f"  {'-'*36}")

    total_fcc = analyzer.sum_bitfield_across_region(
        "FccManager::counters", bit_offset=0, bit_width=fcc_counter_size
    )

    for i, dw in analyzer.iter_dwords("FccManager::counters"):
        fcc_val = dw & fcc_mask
        print(f"  Func[{i:<2}]     0x{dw:08X}      {fcc_val}")

    pending_count = analyzer.count_set_tags("TagManager::occupied_tags")

    print()
    analyzer.assert_equal("FCC count vs pending tags", total_fcc, pending_count)
