from api import DumpAnalyzer

# Keys for the 3 pending bitmap regions — update to match your IP::key names
PENDING_KEYS = [
    "TagManager::fetch_pending",
    "TagManager::write_pending",
    "TagManager::commit_pending",
]


def analyze_occupied_tags(analyzer: DumpAnalyzer) -> None:
    print("\n=== Occupied Tags ===")

    missing = analyzer.get_missing_regions(
        "TagManager::occupied_tags", *PENDING_KEYS
    )
    if missing:
        print(f"  [SKIP] Missing regions: {missing}")
        return

    tags = analyzer.get_set_tags("TagManager::occupied_tags")

    if not tags:
        print("  No tags occupied")
        return

    print(f"  Occupied tags ({len(tags)} total):")

    # Orphan check — occupied but not pending anywhere
    orphaned = analyzer.get_tags_only_in(
        "TagManager::occupied_tags", *PENDING_KEYS
    )
    if orphaned:
        print(f"  [WARN] Orphaned tags (no pending work): {[hex(t) for t in orphaned]}")

    # Stuck check — pending in multiple queues simultaneously
    stuck = analyzer.get_tags_in_all(*PENDING_KEYS)
    if stuck:
        print(f"  [WARN] Tags stuck across all queues: {[hex(t) for t in stuck]}")

    for tag in tags:
        print(f"\n  Tag 0x{tag:04X}:")
        any_pending = False
        for key in PENDING_KEYS:
            if analyzer.is_tag_set_in_region(key, tag):
                queue_name = key.split("::")[-1]
                print(f"    Pending in : {queue_name}")
                any_pending = True
        if not any_pending:
            print(f"    Not pending in any queue")


def analyze_fcc_counter(analyzer: DumpAnalyzer) -> None:
    print("\n=== FCC Counter Analysis ===")

    missing = analyzer.get_missing_regions(
        "FccManager::fcc_counter_size",
        "FccManager::counters",
        "TagManager::occupied_tags",
    )
    if missing:
        print(f"  [SKIP] Missing regions: {missing}")
        return

    fcc_counter_size = analyzer.get_value("FccManager::fcc_counter_size",
                                           is_address=False)
    fcc_mask         = (1 << fcc_counter_size) - 1
    print(f"  fcc_counter_size : {fcc_counter_size} bits  (mask=0x{fcc_mask:08X})")

    func_count    = analyzer.get_region_size_dwords("FccManager::counters")
    counters_base = analyzer.get_base_addr("FccManager::counters")
    print(f"  func_count       : {func_count}  (derived from region size)")

    print(f"\n  {'Function':<12} {'Raw Dword':<12} {'FCC Counter':<12}")
    print(f"  {'-'*36}")

    total_fcc = analyzer.sum_bitfield_across_region(
        "FccManager::counters", bit_offset=0, bit_width=fcc_counter_size
    )

    for i, dw in analyzer.iter_dwords("FccManager::counters"):
        fcc_val = dw & fcc_mask
        print(f"  Func[{i:<6}]  0x{dw:08X}   {fcc_val}")

    pending_count = analyzer.count_set_tags("TagManager::occupied_tags")

    print()
    analyzer.assert_equal("FCC count vs pending tags", total_fcc, pending_count)


def analyze_single_dword(analyzer: DumpAnalyzer, region_name: str) -> None:
    print(f"\n=== {region_name} ===")
    region = analyzer.regions.get(region_name)
    if region is None:
        print(f"  [ERROR] '{region_name}' not found in map")
        return
    dword = analyzer.mem.read_dword(region.base_addr)
    if dword is None:
        print(f"  [WARN] Address 0x{region.base_addr:08X} not in dump")
        return
    if dword == 0:
        print(f"  0x{region.base_addr:08X} = 0x{dword:08X}  (ZERO)")
    else:
        print(f"  0x{region.base_addr:08X} = 0x{dword:08X}  (NON-ZERO)")
