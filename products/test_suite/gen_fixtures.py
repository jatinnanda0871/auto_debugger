"""
Regenerates products/test_suite/sample_dumps/* fixtures used by the pytest
suite, CI, and `python main.py <fixture> test_suite`. Deterministic -- no
randomness -- so regenerated output is byte-identical. Run after changing
fixture_schema.py or the scenario set below:

    python -m products.test_suite.gen_fixtures

scenario_*/  7 folders sharing one identical memory.map (50 keys, 5
             non-contiguous 8 KiB blocks, almost entirely zero -- see
             fixture_schema.py). Each has 5 *.dump files, one per block.
             scenario_01 is the "no errors" baseline; every other scenario
             differs from it by a handful of mutated bytes at exactly one
             key's address, introducing exactly one detectable error (a
             count mismatch, a mirrored value going out of sync, a running
             total no longer matching its region, or reserved/unused memory
             unexpectedly becoming nonzero).

Narrow engine-level behaviors (malformed map/dump lines, a zero-byte region,
an out-of-bounds region, missing dump coverage for a declared key) are
covered directly in tests/test_loader.py and tests/test_api.py using
tmp_path-generated files/synthetic objects instead of committed fixtures --
no need to duplicate that here.
"""

from pathlib import Path

from products.test_suite import fixture_schema as schema

FIXTURES_DIR = Path(__file__).parent / "sample_dumps"


# ── Shared dump-text formatting ─────────────────────────────────────────────

def dump_lines(addr: int, dwords: list) -> list:
    """
    Formats a list of dwords into `0xADDR: 0xDW ... 0xDW` lines, 8 per line.
    Pads the tail with zero dwords so a length not a multiple of 8 still
    parses (engine/loader.py's DUMP_LINE_RE requires exactly 8 per line).
    """
    padded = list(dwords)
    remainder = len(padded) % schema.DWORDS_PER_LINE
    if remainder:
        padded.extend([0] * (schema.DWORDS_PER_LINE - remainder))

    lines = []
    for i in range(0, len(padded), schema.DWORDS_PER_LINE):
        chunk     = padded[i:i + schema.DWORDS_PER_LINE]
        line_addr = addr + i * 4
        vals      = "  ".join(f"0x{d:08X}" for d in chunk)
        lines.append(f"0x{line_addr:08X}: {vals}")
    return lines


def bytes_to_dwords(buf: bytes) -> list:
    assert len(buf) % 4 == 0
    return [int.from_bytes(buf[i:i + 4], "little") for i in range(0, len(buf), 4)]


def write_scenario(name: str, map_lines: list, files: dict) -> None:
    """files: {filename: [dump text lines]}"""
    scenario_dir = FIXTURES_DIR / name
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "memory.map").write_text("\n".join(map_lines) + "\n", encoding="utf-8")
    for filename, lines in files.items():
        (scenario_dir / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[gen] wrote {scenario_dir}  ({len(files)} dump file(s))")


def map_lines_for_layout() -> list:
    return [f"{name}=0x{addr:08X},0x{size:08X}" for name, addr, size in schema.LAYOUT]


def blocks_to_files(blocks: dict) -> dict:
    """{block_index: bytearray} -> {'block_N.dump': [lines]} using one dump line
    range per block (block is fully contiguous, one *.dump file per block)."""
    files = {}
    for b in range(schema.N_BLOCKS):
        dwords = bytes_to_dwords(bytes(blocks[b]))
        files[f"block_{b + 1}.dump"] = dump_lines(schema.BLOCK_BASES[b], dwords)
    return files


def key_byte(blocks: dict, key_name: str, byte_offset: int) -> int:
    """Reads the current byte at key_name+byte_offset from a {block_index: bytearray} map."""
    addr, size = schema.KEY_INFO[key_name]
    assert 0 <= byte_offset < size
    block_index = schema._block_index_for_addr(addr)
    local_offset = (addr - schema.BLOCK_BASES[block_index]) + byte_offset
    return blocks[block_index][local_offset]


def mutate(blocks: dict, key_name: str, byte_offset: int, new_byte: int) -> dict:
    """Returns a deep copy of `blocks` with one byte changed at key_name+byte_offset."""
    mutated = {b: bytearray(blocks[b]) for b in blocks}
    addr, size = schema.KEY_INFO[key_name]
    assert 0 <= byte_offset < size, f"offset {byte_offset} out of bounds for '{key_name}' (size {size})"
    block_index = schema._block_index_for_addr(addr)
    local_offset = (addr - schema.BLOCK_BASES[block_index]) + byte_offset
    mutated[block_index][local_offset] = new_byte
    return mutated


# ── scenario_* — identical 50-key layout, single-site value variations ─────
#
# Tag index used for the occupied/pending scenarios: 450 is deliberately
# outside 0..N_OCCUPIED-1 (currently 0..39), so it starts out unset in every
# relevant region in the baseline.

_UNUSED_TAG = 450
_UNUSED_TAG_BYTE, _UNUSED_TAG_BIT = _UNUSED_TAG // 8, _UNUSED_TAG % 8


def gen_scenarios():
    baseline = schema.build_baseline_blocks()
    map_lines = map_lines_for_layout()

    write_scenario("scenario_01_baseline_no_errors", map_lines, blocks_to_files(baseline))

    # FccManager::counters: clear the counter for tag 0 (byte offset 0) ->
    # fcc sum (N_OCCUPIED - 1) no longer matches occupied-tag count (N_OCCUPIED).
    fcc_error = mutate(baseline, "FccManager::counters", byte_offset=0 * 4, new_byte=0)
    write_scenario("scenario_02_fcc_counter_value_error", map_lines, blocks_to_files(fcc_error))

    # TagManager::occupied_tags: mark an unused tag occupied (no pending
    # region references it) -> occupied count (N_OCCUPIED + 1) no longer
    # matches fcc sum (N_OCCUPIED). Isolated from the pending-subset check.
    current = key_byte(baseline, "TagManager::occupied_tags", _UNUSED_TAG_BYTE)
    occupied_error = mutate(baseline, "TagManager::occupied_tags",
                             byte_offset=_UNUSED_TAG_BYTE, new_byte=current | (1 << _UNUSED_TAG_BIT))
    write_scenario("scenario_03_occupied_tag_count_error", map_lines, blocks_to_files(occupied_error))

    # TagManager::commit_pending: mark the same unused tag pending (it's not
    # in occupied_tags in the baseline) -> a pending tag with no matching
    # occupied bit. fcc/tag counts stay matched; only the subset check fails.
    current = key_byte(baseline, "TagManager::commit_pending", _UNUSED_TAG_BYTE)
    pending_leak = mutate(baseline, "TagManager::commit_pending",
                           byte_offset=_UNUSED_TAG_BYTE, new_byte=current | (1 << _UNUSED_TAG_BIT))
    write_scenario("scenario_04_pending_tag_leak", map_lines, blocks_to_files(pending_leak))

    # StatusMirror::reg0_shadow: flip one byte so it no longer equals its
    # primary counterpart -> mirror_consistency_check fails for pair 0 only.
    current = key_byte(baseline, "StatusMirror::reg0_shadow", 0)
    mirror_error = mutate(baseline, "StatusMirror::reg0_shadow", byte_offset=0, new_byte=current ^ 0xFF)
    write_scenario("scenario_05_mirror_mismatch", map_lines, blocks_to_files(mirror_error))

    # SumCheck::group0_region: bump one dword in the region without updating
    # the companion total -> sum(region) != total for group 0 only.
    region_name, _ = schema.SUM_CHECK_GROUPS[0]
    current = key_byte(baseline, region_name, 0)
    sum_error = mutate(baseline, region_name, byte_offset=0, new_byte=current + 1)
    write_scenario("scenario_06_sum_check_mismatch", map_lines, blocks_to_files(sum_error))

    # Reserved::block0_slot_0: set a bit in memory that must always read zero
    # -> reserved_region_check flags that one key as unexpectedly nonzero.
    reserved_name = schema.RESERVED_KEY_NAMES[0]
    reserved_error = mutate(baseline, reserved_name, byte_offset=0, new_byte=0x01)
    write_scenario("scenario_07_reserved_region_set", map_lines, blocks_to_files(reserved_error))


def main():
    gen_scenarios()


if __name__ == "__main__":
    main()
