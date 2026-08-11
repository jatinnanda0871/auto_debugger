# ── Controller2 struct manifest ─────────────────────────────────────────────────
#
# Selected via: python main.py <dump_folder> epdc controller2
#
# controller2 has its own register layout (structs/controller2_regs.h),
# entirely separate from controller1's BigStruct64/TagRecord headers.

STRUCT_HEADERS = [
    "structs/controller2_regs.h",
]
