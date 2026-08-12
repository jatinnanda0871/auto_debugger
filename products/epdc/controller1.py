# ── Controller1 struct manifest ─────────────────────────────────────────────────
#
# Selected via: python main.py <dump_folder> epdc controller1
#
# controller1 uses the full BigStruct64 layout plus the TagRecord wrapper
# that embeds it — a different header set than controller2, to demonstrate
# that controllers within the same product can have independent structs.

STRUCT_HEADERS = [
    "structs/big_struct.h",
    "structs/tag_record.h",
]
