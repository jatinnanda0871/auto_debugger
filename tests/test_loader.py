import pytest

from engine.loader import load_map, load_dump, find_map_file, _parse_dump_lines


# ── load_map ─────────────────────────────────────────────────────────────────

def test_load_map_parses_valid_lines(tmp_path):
    map_file = tmp_path / "memory.map"
    map_file.write_text(
        "TagManager::occupied_tags=0xA0001000,0x10\n"
        "FccManager::counters=0xA0001080,0x10\n"
    )
    regions = load_map(str(map_file))
    assert set(regions) == {"TagManager::occupied_tags", "FccManager::counters"}
    r = regions["TagManager::occupied_tags"]
    assert r.base_addr == 0xA0001000
    assert r.size_bytes == 0x10


def test_load_map_accepts_decimal_address(tmp_path):
    map_file = tmp_path / "memory.map"
    map_file.write_text("Foo::bar=2684358656,0x10\n")  # 0xA0001000 in decimal
    regions = load_map(str(map_file))
    assert regions["Foo::bar"].base_addr == 0xA0001000


def test_load_map_skips_malformed_lines_with_warning(tmp_path, capsys):
    map_file = tmp_path / "memory.map"
    map_file.write_text(
        "TagManager::occupied_tags=0xA0001000,0x10\n"
        "not a valid line at all\n"
        "FccManager::counters=0xA0001080,0x10\n"
    )
    regions = load_map(str(map_file))
    assert set(regions) == {"TagManager::occupied_tags", "FccManager::counters"}
    out = capsys.readouterr().out
    assert "[WARN]" in out
    assert "Map line 2" in out


def test_load_map_ignores_blank_lines(tmp_path):
    map_file = tmp_path / "memory.map"
    map_file.write_text("\nTagManager::occupied_tags=0xA0001000,0x10\n\n")
    regions = load_map(str(map_file))
    assert len(regions) == 1


def test_load_map_empty_file_yields_no_regions(tmp_path):
    map_file = tmp_path / "memory.map"
    map_file.write_text("")
    assert load_map(str(map_file)) == {}


# ── find_map_file ────────────────────────────────────────────────────────────

def test_find_map_file_raises_when_none_present(tmp_path):
    with pytest.raises(ValueError, match="No \\*\\.map file"):
        find_map_file(str(tmp_path))


def test_find_map_file_raises_when_multiple_present(tmp_path):
    (tmp_path / "a.map").write_text("")
    (tmp_path / "b.map").write_text("")
    with pytest.raises(ValueError, match="Multiple \\*\\.map files"):
        find_map_file(str(tmp_path))


def test_find_map_file_returns_the_single_match(tmp_path):
    target = tmp_path / "only.map"
    target.write_text("")
    assert find_map_file(str(tmp_path)) == str(target)


# ── _parse_dump_lines ────────────────────────────────────────────────────────

def test_parse_dump_lines_requires_exactly_eight_dwords(tmp_path, capsys):
    dump_file = tmp_path / "memory.dump"
    dump_file.write_text(
        "0xA0001000: 0x00000001 0x00000000 0x00000000\n"  # only 3 -- malformed
    )
    parsed = _parse_dump_lines(str(dump_file))
    assert parsed == []
    assert "[WARN]" in capsys.readouterr().out


# ── load_dump ────────────────────────────────────────────────────────────────

def _dump_line(addr: int, dwords) -> str:
    vals = "  ".join(f"0x{d:08X}" for d in dwords)
    return f"0x{addr:08X}: {vals}\n"


def test_load_dump_raises_when_no_dump_files(tmp_path):
    with pytest.raises(ValueError, match="No \\*\\.dump files"):
        load_dump(str(tmp_path))


def test_load_dump_raises_when_all_lines_malformed(tmp_path):
    (tmp_path / "memory.dump").write_text("garbage line\n")
    with pytest.raises(ValueError, match="No valid dump lines"):
        load_dump(str(tmp_path))


def test_load_dump_merges_multiple_dump_files(tmp_path):
    (tmp_path / "a.dump").write_text(_dump_line(0xA0001000, [1, 0, 0, 0, 0, 0, 0, 0]))
    (tmp_path / "b.dump").write_text(_dump_line(0xA0002000, [2, 0, 0, 0, 0, 0, 0, 0]))
    mv = load_dump(str(tmp_path))
    assert mv.read_dword(0xA0001000) == 1
    assert mv.read_dword(0xA0002000) == 2


def test_load_dump_last_duplicate_address_wins(tmp_path):
    # Same address appears in two files -- loader dedupes by address, keeping
    # whichever was processed last (files are read in sorted glob order).
    (tmp_path / "a.dump").write_text(_dump_line(0xA0001000, [1, 0, 0, 0, 0, 0, 0, 0]))
    (tmp_path / "b.dump").write_text(_dump_line(0xA0001000, [2, 0, 0, 0, 0, 0, 0, 0]))
    mv = load_dump(str(tmp_path))
    assert mv.read_dword(0xA0001000) == 2


def test_load_dump_splits_into_separate_chunks_beyond_gap_threshold(tmp_path):
    lines = _dump_line(0xA0001000, [1] * 8) + _dump_line(0xA0100000, [2] * 8)
    (tmp_path / "memory.dump").write_text(lines)
    mv = load_dump(str(tmp_path))
    assert len(mv.chunks) == 2


def test_load_dump_single_chunk_when_within_gap_threshold(tmp_path):
    # Two adjacent 32-byte lines, no gap at all
    lines = _dump_line(0xA0001000, [1] * 8) + _dump_line(0xA0001020, [2] * 8)
    (tmp_path / "memory.dump").write_text(lines)
    mv = load_dump(str(tmp_path))
    assert len(mv.chunks) == 1
