"""
Shared, pure (no file I/O) schema for the products/test_suite realistic-dump
fixtures. Both the generator (gen_fixtures.py) and the checking modules
import this so every "expected" value is computed the same way in one place.
Key *names* live in config.py (as plain literals); this module owns their
sizes/addresses/expected content.

Layout
------
5 memory blocks, BLOCK_SIZE bytes each, spaced far enough apart (more than
engine.loader.CHUNK_GAP_THRESHOLD) that every block loads as its own sparse
MemoryView chunk. Each block's raw bytes are fully populated with dump lines
(no gaps inside a block, so it's one contiguous chunk) -- but the *content*
is almost entirely zero, like real firmware SRAM: a handful of keys hold
live values, everything else -- including most declared keys -- is unused
memory that reads as zero.

50 keys total, identical name/address/size across every scenario folder,
in four categories (see config.py for the exact key names):

  - core (5)         TagManager/FccManager bitmaps + counters (unchanged
                      semantics from products/epdc) -- sparsely occupied.
  - mirror (10, 5 pairs)   A "primary" dword and a "shadow" dword that must
                      always read identically (a common firmware pattern:
                      redundant/backup copies of a status value).
  - sum_check (6, 3 groups)   A small sparse dword region plus a single
                      "total" dword that must equal the sum of that region
                      (a running-total/checksum register next to raw data).
  - reserved (29)     Various sizes, 1-1024 bytes. Always zero -- reserved/
                      unused memory. The only thing ever checked about them
                      is that they stay zero (any_nonzero == False).

Every key is guaranteed present in every scenario_* fixture -- checking
modules must not skip on a missing key/region (see config.py).

Only a handful of bytes differ between the "no errors" baseline and each
error scenario -- everything else (addresses, sizes, filler, all other key
values) is identical.
"""

from products.test_suite import config

DWORDS_PER_LINE = 8
LINE_BYTES      = DWORDS_PER_LINE * 4

BLOCK_SIZE   = 0x2000            # 8 KiB per block
BLOCK_STRIDE = 0x10000           # base-address spacing between blocks
N_BLOCKS     = 5
BLOCK_BASES  = [0xA0000000 + i * BLOCK_STRIDE for i in range(N_BLOCKS)]

N_TAGS     = 512                  # bits in each TagManager bitmap (64 bytes)
N_OCCUPIED = 40                   # tags 0..39 are occupied -- sparse (~8%)

# ── Core keys — one per block, real Tag/Fcc semantics ───────────────────────

CORE_KEYS = [
    (config.OCCUPIED_TAGS_ADDR, N_TAGS // 8),    # block 0 — 64 bytes
    (config.PENDING_KEYS[0], N_TAGS // 8),        # block 1 — 64 bytes (fetch_pending)
    (config.PENDING_KEYS[1], N_TAGS // 8),        # block 2 — 64 bytes (write_pending)
    (config.PENDING_KEYS[2], N_TAGS // 8),        # block 3 — 64 bytes (commit_pending)
    (config.FCC_COUNTERS_ADDR, N_TAGS * 4),       # block 4 — 2048 bytes (1 dword/tag)
]

# ── Mirror pairs — primary/shadow dwords that must read identically ────────

MIRROR_PAIRS = config.MIRROR_PAIRS
MIRROR_KEYS  = [(name, 4) for pair in MIRROR_PAIRS for name in pair]  # 10 keys, 4 bytes each


def mirror_expected_value(pair_index: int) -> int:
    """Sparse, distinct, nonzero value shared by both keys in a mirror pair."""
    return 1 << (pair_index + 1)  # 0x2, 0x4, 0x8, 0x10, 0x20


# ── Sum-check groups — sparse region + a dword that must equal its sum ─────

SUM_CHECK_GROUPS = config.SUM_CHECK_GROUPS
SUM_GROUP_DWORDS = config.SUM_GROUP_DWORDS
SUM_CHECK_KEYS = (
    [(region, SUM_GROUP_DWORDS * 4) for region, _ in SUM_CHECK_GROUPS]
    + [(total, 4) for _, total in SUM_CHECK_GROUPS]
)  # 6 keys


def sum_group_dword_values(group_index: int) -> list:
    """Sparse dword values for one sum-check region: only 2 of 8 are nonzero."""
    values = [0] * SUM_GROUP_DWORDS
    values[2] = 5 + group_index
    values[5] = 7 + group_index
    return values


# ── Reserved keys — always zero; only ever checked for any_nonzero ─────────

RESERVED_KEY_NAMES = config.RESERVED_KEYS
RESERVED_KEYS = list(zip(config.RESERVED_KEYS, config.RESERVED_KEY_SIZES))  # 29 keys

# ── Combined "generic" (non-core) key list, and full layout ────────────────

GENERIC_KEYS = MIRROR_KEYS + SUM_CHECK_KEYS + RESERVED_KEYS  # 10 + 6 + 29 = 45
assert len(GENERIC_KEYS) == 45


def _pack_block(block_index: int, core_key, generic_keys) -> list:
    """Returns [(name, addr, size), ...] packed sequentially into one block."""
    base   = BLOCK_BASES[block_index]
    offset = 0
    placed = []
    for name, size in [core_key] + generic_keys:
        addr = base + offset
        placed.append((name, addr, size))
        offset += ((size + 3) // 4) * 4 + 4  # 4-byte align + 4-byte gap
    assert offset <= BLOCK_SIZE, (
        f"block {block_index} overflow: packed {offset} bytes into {BLOCK_SIZE}"
    )
    return placed


def build_layout() -> list:
    """Returns [(name, addr, size), ...] for all 50 keys, block-packed."""
    layout = []
    for b in range(N_BLOCKS):
        core = CORE_KEYS[b]
        generic = GENERIC_KEYS[b * 9:(b + 1) * 9]
        layout.extend(_pack_block(b, core, generic))
    return layout


LAYOUT = build_layout()                                   # [(name, addr, size), ...]
KEY_INFO = {name: (addr, size) for name, addr, size in LAYOUT}


def _block_index_for_addr(addr: int) -> int:
    for i, base in enumerate(BLOCK_BASES):
        if base <= addr < base + BLOCK_SIZE:
            return i
    raise ValueError(f"address 0x{addr:X} not within any block")


def _expected_value(name: str, size: int) -> bytes:
    if name == config.OCCUPIED_TAGS_ADDR:
        return _tag_bitmap(lambda tag: tag < N_OCCUPIED)
    if name == config.PENDING_KEYS[0]:
        return _tag_bitmap(lambda tag: tag < N_OCCUPIED and tag % 3 == 0)
    if name == config.PENDING_KEYS[1]:
        return _tag_bitmap(lambda tag: tag < N_OCCUPIED and tag % 3 == 1)
    if name == config.PENDING_KEYS[2]:
        return _tag_bitmap(lambda tag: tag < N_OCCUPIED and tag % 3 == 2)
    if name == config.FCC_COUNTERS_ADDR:
        buf = bytearray(size)
        for tag in range(N_TAGS):
            if tag < N_OCCUPIED:
                buf[tag * 4] = 1  # low byte of each dword = 1 counter per occupied tag
        return bytes(buf)

    for i, (primary, shadow) in enumerate(MIRROR_PAIRS):
        if name in (primary, shadow):
            return mirror_expected_value(i).to_bytes(4, "little")

    for i, (region, total) in enumerate(SUM_CHECK_GROUPS):
        if name == region:
            values = sum_group_dword_values(i)
            return b"".join(v.to_bytes(4, "little") for v in values)
        if name == total:
            return sum(sum_group_dword_values(i)).to_bytes(4, "little")

    if name in RESERVED_KEY_NAMES:
        return bytes(size)  # all zero

    raise KeyError(f"no expected-value rule for key '{name}'")


def _tag_bitmap(is_set) -> bytes:
    buf = bytearray(N_TAGS // 8)
    for tag in range(N_TAGS):
        if is_set(tag):
            buf[tag // 8] |= 1 << (tag % 8)
    return bytes(buf)


def build_baseline_blocks() -> dict:
    """
    Returns {block_index: bytearray(BLOCK_SIZE)} with every key's expected
    ("no errors") content written at its address, and zero everywhere else
    (unused/reserved memory reads as zero, like real SRAM).
    """
    blocks = {b: bytearray(BLOCK_SIZE) for b in range(N_BLOCKS)}  # bytearray() is zero-filled

    for name, addr, size in LAYOUT:
        block_index = _block_index_for_addr(addr)
        offset = addr - BLOCK_BASES[block_index]
        blocks[block_index][offset:offset + size] = _expected_value(name, size)

    return blocks
