from api import DumpAnalyzer
from products.epdc.config import PENDING_TAG_ADDR, PENDING_TAG_SUBSET_ADDR


# ── Analyzers ──────────────────────────────────────────────────────────────────

def analyze_occupied_tags(analyzer: DumpAnalyzer) -> None:
    print("\n=== Occupied Tags ===")

    missing = analyzer.get_missing_regions(PENDING_TAG_ADDR, *PENDING_TAG_SUBSET_ADDR)
    if missing:
        print(f"  [SKIP] Missing regions: {missing}")
        return

    tags = analyzer.get_set_bits(PENDING_TAG_ADDR)
    if not tags:
        print("  No tags occupied")
        return

    print(f"  Occupied tags ({len(tags)} total):")

    orphaned = analyzer.get_tags_only_in(PENDING_TAG_ADDR, *PENDING_TAG_SUBSET_ADDR)
    if orphaned:
        print(f"  [WARN] Orphaned tags (not pending anywhere): {[hex(t) for t in orphaned]}")

    stuck = analyzer.get_tags_in_all(*PENDING_TAG_SUBSET_ADDR)
    if stuck:
        print(f"  [WARN] Tags stuck across all queues: {[hex(t) for t in stuck]}")

    for tag in tags:
        print(f"\n  Tag 0x{tag:04X}:")
        any_pending = False
        for key in PENDING_TAG_SUBSET_ADDR:
            if analyzer.is_tag_set_in_region(key, tag):
                print(f"    Pending in : {key.split('::')[-1]}")
                any_pending = True
        if not any_pending:
            print(f"    Not pending in any queue")


# ── Module entry point — called by product.py ──────────────────────────────────

def run(analyzer: DumpAnalyzer) -> None:
    analyze_occupied_tags(analyzer)
