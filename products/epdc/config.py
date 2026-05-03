# ── EPDC product configuration ─────────────────────────────────────────────────
#
# All map key names and fixed constants for this product live here.
# Analyzers import from this file — never hardcode strings inside analyzer logic.
#
# Key names must exactly match entries in the product's *.map file.

# ── TagManager ─────────────────────────────────────────────────────────────────

TAG_OCCUPIED_KEY = "TagManager::occupied_tags"

TAG_PENDING_KEYS = [
    "TagManager::fetch_pending",
    "TagManager::write_pending",
    "TagManager::commit_pending",
]

# ── FccManager ─────────────────────────────────────────────────────────────────

FCC_COUNTERS_KEY      = "FccManager::counters"
FCC_COUNTER_SIZE_KEY  = "FccManager::fcc_counter_size"
