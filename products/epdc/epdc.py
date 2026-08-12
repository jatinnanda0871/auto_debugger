# ── EPDC struct manifest (product-wide fallback) ────────────────────────────────
#
# Used when main.py is invoked without a controller_name (python main.py
# <dump> epdc). Products with more than one controller instead ship one
# manifest per controller — see controller1.py / controller2.py — each with
# its own STRUCT_HEADERS, selected via the CLI's 3rd argument
# (python main.py <dump> epdc controller1).
#
# Paths are relative to this file's directory and use forward slashes, which
# pathlib resolves correctly on both Windows and Linux.
#
# List order does not matter — struct_gen topologically sorts headers by
# their actual cross-file type dependencies before generating.

STRUCT_HEADERS = [
    "structs/big_struct.h",
    "structs/tag_record.h",
]
