# ── EPDC product configuration ─────────────────────────────────────────────────
#
# MODULES   : ordered list of module filenames (without .py) under modules/
#             product.py iterates this list — add/remove modules here only
#
# All map key names used by this product's analyzers are declared below.
# Analyzers import from here — never hardcode key strings inside analyzer logic.
# Key names must exactly match entries in the product's *.map file.

# ── Module list ────────────────────────────────────────────────────────────────

MODULES = [
    "tag_manager",
    "fcc_manager",
]

# ── TagManager keys ────────────────────────────────────────────────────────────

PENDING_TAG_ADDR = "TagManager::occupied_tags"

PENDING_TAG_SUBSET_ADDR = [
    "TagManager::fetch_pending",
    "TagManager::write_pending",
    "TagManager::commit_pending",
]

PENDING_KEYS = [
    "TagManager::fetch_pending",
    "TagManager::write_pending",
    "TagManager::commit_pending",
]

# ── FccManager keys ────────────────────────────────────────────────────────────

FCC_COUNTERS_ADDR     = "FccManager::counters"
FCC_COUNTER_SIZE = 8
