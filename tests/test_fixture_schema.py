"""
Unit tests for products/test_suite/fixture_schema.py -- the pure layout/value
logic shared by the fixture generator and data_integrity_check.py.
"""

from products.test_suite import fixture_schema as schema


def test_layout_has_exactly_fifty_keys():
    assert len(schema.LAYOUT) == 50
    assert len(schema.CORE_KEYS) == 5
    assert len(schema.GENERIC_KEYS) == 45


def test_key_sizes_span_one_to_1024_bytes():
    sizes = [size for _, size in schema.GENERIC_KEYS]
    assert min(sizes) == 1
    assert max(sizes) == 1024


def test_all_key_names_are_unique():
    names = [name for name, _, _ in schema.LAYOUT]
    assert len(names) == len(set(names))


def test_one_core_key_per_block():
    for name, _ in schema.CORE_KEYS:
        addr, _ = schema.KEY_INFO[name]
        assert schema._block_index_for_addr(addr) in range(schema.N_BLOCKS)


def test_keys_do_not_overlap_within_a_block():
    by_block = {b: [] for b in range(schema.N_BLOCKS)}
    for name, addr, size in schema.LAYOUT:
        b = schema._block_index_for_addr(addr)
        by_block[b].append((addr, addr + size))

    for b, spans in by_block.items():
        spans.sort()
        for (start_a, end_a), (start_b, end_b) in zip(spans, spans[1:]):
            assert end_a <= start_b, f"overlap in block {b}: {(start_a, end_a)} vs {(start_b, end_b)}"


def test_every_key_fits_entirely_within_one_block():
    for name, addr, size in schema.LAYOUT:
        block_index = schema._block_index_for_addr(addr)
        base = schema.BLOCK_BASES[block_index]
        assert addr >= base
        assert addr + size <= base + schema.BLOCK_SIZE


def test_blocks_are_spaced_beyond_the_chunk_gap_threshold():
    from engine.loader import CHUNK_GAP_THRESHOLD
    bases = sorted(schema.BLOCK_BASES)
    for a, b in zip(bases, bases[1:]):
        gap = b - (a + schema.BLOCK_SIZE)
        assert gap > CHUNK_GAP_THRESHOLD


def test_build_baseline_blocks_is_deterministic():
    first  = schema.build_baseline_blocks()
    second = schema.build_baseline_blocks()
    assert first == second


def test_reserved_keys_are_all_zero():
    blocks = schema.build_baseline_blocks()
    for name in schema.RESERVED_KEY_NAMES:
        addr, size = schema.KEY_INFO[name]
        block_index = schema._block_index_for_addr(addr)
        offset = addr - schema.BLOCK_BASES[block_index]
        raw = blocks[block_index][offset:offset + size]
        assert raw == bytes(size), f"{name} expected all-zero, got nonzero bytes"


def test_most_of_each_block_is_zero():
    """Sanity check that the fixtures are genuinely sparse, not just
    small-key-in-big-buffer with noise filler."""
    blocks = schema.build_baseline_blocks()
    for b, buf in blocks.items():
        nonzero = sum(1 for byte in buf if byte != 0)
        assert nonzero < schema.BLOCK_SIZE * 0.05, (
            f"block {b} is only {100 * (1 - nonzero / schema.BLOCK_SIZE):.1f}% zero"
        )


def test_mirror_pairs_hold_identical_nonzero_values():
    blocks = schema.build_baseline_blocks()

    def dword_at(name):
        addr, _ = schema.KEY_INFO[name]
        block_index = schema._block_index_for_addr(addr)
        offset = addr - schema.BLOCK_BASES[block_index]
        return int.from_bytes(blocks[block_index][offset:offset + 4], "little")

    seen = set()
    for primary, shadow in schema.MIRROR_PAIRS:
        value = dword_at(primary)
        assert value != 0
        assert dword_at(shadow) == value
        seen.add(value)
    assert len(seen) == len(schema.MIRROR_PAIRS)  # each pair's value is distinct


def test_sum_check_groups_region_sum_matches_stored_total():
    blocks = schema.build_baseline_blocks()

    def region_dwords(name, count):
        addr, _ = schema.KEY_INFO[name]
        block_index = schema._block_index_for_addr(addr)
        offset = addr - schema.BLOCK_BASES[block_index]
        raw = blocks[block_index][offset:offset + count * 4]
        return [int.from_bytes(raw[i:i + 4], "little") for i in range(0, len(raw), 4)]

    for region, total in schema.SUM_CHECK_GROUPS:
        dwords = region_dwords(region, schema.SUM_GROUP_DWORDS)
        total_value = region_dwords(total, 1)[0]
        assert sum(dwords) == total_value
        assert sum(1 for d in dwords if d != 0) <= 2  # sparse: only a couple set


def test_baseline_occupied_tags_matches_n_occupied_constant():
    blocks = schema.build_baseline_blocks()
    addr, size = schema.KEY_INFO["TagManager::occupied_tags"]
    block_index = schema._block_index_for_addr(addr)
    offset = addr - schema.BLOCK_BASES[block_index]
    raw = blocks[block_index][offset:offset + size]
    set_bits = sum(bin(byte).count("1") for byte in raw)
    assert set_bits == schema.N_OCCUPIED


def test_baseline_fcc_counters_sum_matches_n_occupied():
    blocks = schema.build_baseline_blocks()
    addr, size = schema.KEY_INFO["FccManager::counters"]
    block_index = schema._block_index_for_addr(addr)
    offset = addr - schema.BLOCK_BASES[block_index]
    raw = blocks[block_index][offset:offset + size]
    total = sum(raw[i] for i in range(0, size, 4))  # low byte of every dword
    assert total == schema.N_OCCUPIED


def test_baseline_pending_keys_are_disjoint_and_subset_of_occupied():
    blocks = schema.build_baseline_blocks()

    def set_bits_for(key_name):
        addr, size = schema.KEY_INFO[key_name]
        block_index = schema._block_index_for_addr(addr)
        offset = addr - schema.BLOCK_BASES[block_index]
        raw = blocks[block_index][offset:offset + size]
        bits = set()
        for byte_idx, byte in enumerate(raw):
            for bit in range(8):
                if byte & (1 << bit):
                    bits.add(byte_idx * 8 + bit)
        return bits

    occupied = set_bits_for("TagManager::occupied_tags")
    fetch    = set_bits_for("TagManager::fetch_pending")
    write    = set_bits_for("TagManager::write_pending")
    commit   = set_bits_for("TagManager::commit_pending")

    assert fetch <= occupied
    assert write <= occupied
    assert commit <= occupied
    assert not (fetch & write)
    assert not (fetch & commit)
    assert not (write & commit)
    assert fetch | write | commit == occupied
