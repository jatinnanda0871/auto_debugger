# ── test_suite product configuration ───────────────────────────────────────────
#
# This product is not firmware — it exists to validate the engine's public API
# (engine/api.py, engine/loader.py, engine/models.py) end-to-end, the same way
# `epdc` validates real firmware state. It is run against the fixtures under
# products/test_suite/sample_dumps/scenario_* by both the pytest suite and CI.
#
# Every key below is guaranteed present, in every scenario_* fixture, at the
# exact address/size declared in products/test_suite/fixture_schema.py (which
# builds each fixture's memory.map from these same constants). Modules must
# NOT defensively skip on a missing key/region — if one actually goes
# missing, that's a bug and the underlying engine.api call must raise/warn on
# its own (get_region raises KeyError for an unknown key; get_region_dwords
# warns and zero-fills a dword the dump doesn't actually cover). Test that
# deviation directly in tests/test_api.py, not by adding a skip branch here.
#
# All key strings are declared as plain literals below (not built with an
# f-string/loop) so any of them can be copied straight into a memory.map file
# to check by eye.

# ── Module list ────────────────────────────────────────────────────────────────

MODULES = [
    "api_smoke_test",
    "tag_consistency_check",
    "mirror_consistency_check",
    "sum_check",
    "reserved_region_check",
]

# ── Core TagManager / FccManager keys (1 per block 0-4) ────────────────────────

OCCUPIED_TAGS_ADDR = "TagManager::occupied_tags"

PENDING_KEYS = [
    "TagManager::fetch_pending",
    "TagManager::write_pending",
    "TagManager::commit_pending",
]

FCC_COUNTERS_ADDR = "FccManager::counters"
FCC_COUNTER_SIZE  = 8

# ── Mirror pairs — a "primary" dword that must equal its "shadow" dword ────────

MIRROR_PAIR_0 = ["StatusMirror::reg0_primary", "StatusMirror::reg0_shadow"]
MIRROR_PAIR_1 = ["StatusMirror::reg1_primary", "StatusMirror::reg1_shadow"]
MIRROR_PAIR_2 = ["StatusMirror::reg2_primary", "StatusMirror::reg2_shadow"]
MIRROR_PAIR_3 = ["StatusMirror::reg3_primary", "StatusMirror::reg3_shadow"]
MIRROR_PAIR_4 = ["StatusMirror::reg4_primary", "StatusMirror::reg4_shadow"]

MIRROR_PAIRS = [MIRROR_PAIR_0, MIRROR_PAIR_1, MIRROR_PAIR_2, MIRROR_PAIR_3, MIRROR_PAIR_4]

# ── Sum-check groups — a sparse region + a dword holding its sum ───────────────

SUM_CHECK_GROUP_0 = ["SumCheck::group0_region", "SumCheck::group0_total"]
SUM_CHECK_GROUP_1 = ["SumCheck::group1_region", "SumCheck::group1_total"]
SUM_CHECK_GROUP_2 = ["SumCheck::group2_region", "SumCheck::group2_total"]

SUM_CHECK_GROUPS = [SUM_CHECK_GROUP_0, SUM_CHECK_GROUP_1, SUM_CHECK_GROUP_2]
SUM_GROUP_DWORDS = 8  # region size in dwords (32 bytes)

# ── Reserved keys — always zero; only ever checked for any_nonzero ─────────────

RESERVED_KEYS = [
    "Reserved::slot_00", "Reserved::slot_01", "Reserved::slot_02", "Reserved::slot_03",
    "Reserved::slot_04", "Reserved::slot_05", "Reserved::slot_06", "Reserved::slot_07",
    "Reserved::slot_08", "Reserved::slot_09", "Reserved::slot_10", "Reserved::slot_11",
    "Reserved::slot_12", "Reserved::slot_13", "Reserved::slot_14", "Reserved::slot_15",
    "Reserved::slot_16", "Reserved::slot_17", "Reserved::slot_18", "Reserved::slot_19",
    "Reserved::slot_20", "Reserved::slot_21", "Reserved::slot_22", "Reserved::slot_23",
    "Reserved::slot_24", "Reserved::slot_25", "Reserved::slot_26", "Reserved::slot_27",
    "Reserved::slot_28",
]

# Sizes for RESERVED_KEYS, same order, 1-1024 bytes (used only by
# fixture_schema.py to lay out the fixtures — not a per-key "meaning").
RESERVED_KEY_SIZES = [
    1, 2, 4, 8, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024,
    1, 2, 4, 8, 16, 24, 32, 48, 64, 96, 128, 192,
]
assert len(RESERVED_KEYS) == len(RESERVED_KEY_SIZES) == 29
