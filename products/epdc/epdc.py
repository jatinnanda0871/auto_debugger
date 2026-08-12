# ── EPDC struct manifest ────────────────────────────────────────────────────────
#
# Named after the product id (matches the CLI argument / products/<id> folder)
# so struct_gen can find it purely from the product id string, the same way
# main.py locates products/<id>/product.py.
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
