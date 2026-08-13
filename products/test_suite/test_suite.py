# ── test_suite struct manifest ──────────────────────────────────────────────
#
# test_suite has no controllers, so this is the fallback manifest (no
# per-controller file needed). Only the two "core" keys that actually have
# internal array structure get a struct -- see structs/*.h for why mirror/
# sum-check/reserved keys don't (they're plain scalars, or keys spaced too
# far apart to safely combine into one struct).

STRUCT_HEADERS = [
    "structs/tag_bitmap.h",
    "structs/fcc_counters.h",
]
