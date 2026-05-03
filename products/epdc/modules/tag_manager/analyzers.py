from engine.api import DumpAnalyzer
from products.epdc.config import TAG_OCCUPIED_KEY, TAG_PENDING_KEYS


def analyze_occupied_tags(analyzer: DumpAnalyzer) -> None:
    print("\n=== Occupied Tags ===")

    missing = analyzer.get_missing_regions(TAG_OCCUPIED_KEY, *TAG_PENDING_KEYS)
    if missing:
        print(f"  [SKIP] Missing regions: {missing}")
        return

    tags = analyzer.get_set_tags(TAG_OCCUPIED_KEY)

    if not tags:
        print("  No tags occupied")
        return

    print(f"  Occupied tags ({len(tags)} total):")

    # Orphan check — occupied but not pending anywhere
    orphaned = analyzer.get_tags_only_in(TAG_OCCUPIED_KEY, *TAG_PENDING_KEYS)
    if orphaned:
        print(f"  [WARN] Orphaned tags (no pending work): {[hex(t) for t in orphaned]}")

    # Stuck check — pending in multiple queues simultaneously
    stuck = analyzer.get_tags_in_all(*TAG_PENDING_KEYS)
    if stuck:
        print(f"  [WARN] Tags stuck across all queues: {[hex(t) for t in stuck]}")

    for tag in tags:
        print(f"\n  Tag 0x{tag:04X}:")
        any_pending = False
        for key in TAG_PENDING_KEYS:
            if analyzer.is_region_in_dump(key) and analyzer.is_tag_set_in_region(key, tag):
                queue_name = key.split("::")[-1]
                print(f"    Pending in: {queue_name}")
                any_pending = True
        if not any_pending:
            print(f"    Not pending in any queue")
