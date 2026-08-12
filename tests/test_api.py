import pytest

from engine.api import DumpAnalyzer
from engine.models import Region, Chunk, MemoryView


def make_analyzer(regions: dict, chunks: list) -> DumpAnalyzer:
    return DumpAnalyzer(MemoryView(chunks=chunks), regions)


@pytest.fixture
def basic_analyzer():
    """
    One 16-byte (4 dword) region 'A::tags' fully backed by data:
      dword0 = 0x00000007  (bits 0,1,2 set)
      dword1 = 0x00000000
      dword2 = 0xFFFFFFFF  (all 32 bits set)
      dword3 = 0x00000000
    """
    data = bytearray(16)
    data[0:4]  = (0x00000007).to_bytes(4, "little")
    data[4:8]  = (0x00000000).to_bytes(4, "little")
    data[8:12] = (0xFFFFFFFF).to_bytes(4, "little")
    data[12:16] = (0x00000000).to_bytes(4, "little")
    regions = {"A::tags": Region(name="A::tags", base_addr=0x1000, size_bytes=16)}
    return make_analyzer(regions, [Chunk(base_addr=0x1000, data=data)])


# ── get_region / key_exists ──────────────────────────────────────────────────

def test_get_region_returns_region(basic_analyzer):
    r = basic_analyzer.get_region("A::tags")
    assert r.base_addr == 0x1000


def test_get_region_raises_key_error_for_unknown_key(basic_analyzer):
    with pytest.raises(KeyError):
        basic_analyzer.get_region("Nope::missing")


def test_key_exists(basic_analyzer):
    assert basic_analyzer.key_exists("A::tags") is True
    assert basic_analyzer.key_exists("Nope::missing") is False


# ── get_dword / get_byte / get_base_addr / get_region_size_dwords ──────────

def test_get_dword_reads_first_dword(basic_analyzer):
    assert basic_analyzer.get_dword("A::tags") == 0x00000007


def test_get_dword_is_address_false_returns_base_addr_literal(basic_analyzer):
    assert basic_analyzer.get_dword("A::tags", is_address=False) == 0x1000


def test_get_region_dwords_returns_all_dwords(basic_analyzer):
    assert basic_analyzer.get_region_dwords("A::tags") == [7, 0, 0xFFFFFFFF, 0]


def test_get_region_dwords_substitutes_zero_and_warns_for_missing_data(capsys):
    regions = {"A::tags": Region(name="A::tags", base_addr=0x1000, size_bytes=8)}
    a = make_analyzer(regions, [Chunk(base_addr=0x1000, data=bytearray(4))])  # only 1 of 2 dwords
    result = a.get_region_dwords("A::tags")
    assert result == [0, 0]
    assert "[WARN]" in capsys.readouterr().out


def test_get_byte_reads_correct_offset(basic_analyzer):
    assert basic_analyzer.get_byte("A::tags", 0) == 0x07
    assert basic_analyzer.get_byte("A::tags", 8) == 0xFF


def test_get_byte_raises_on_out_of_bounds_offset(basic_analyzer):
    with pytest.raises(ValueError, match="Out-of-bounds"):
        basic_analyzer.get_byte("A::tags", 16)


def test_get_base_addr(basic_analyzer):
    assert basic_analyzer.get_base_addr("A::tags") == 0x1000


def test_get_region_size_dwords(basic_analyzer):
    assert basic_analyzer.get_region_size_dwords("A::tags") == 4


# ── zero-byte region / partial-read regressions ─────────────────────────────
# Regression coverage for the "gracefully handle partial reads and
# out-of-bounds cases" fix (commit ecf1ed8).

def test_get_dword_on_zero_byte_region_raises_value_error():
    regions = {"Z::empty": Region(name="Z::empty", base_addr=0x2000, size_bytes=0)}
    a = make_analyzer(regions, [Chunk(base_addr=0x2000, data=bytearray(4))])
    with pytest.raises(ValueError, match="zero-byte region"):
        a.get_dword("Z::empty")


def test_get_dword_on_partial_region_reads_available_bytes_only():
    # Region declares 2 bytes; only those 2 bytes should be read (not a full dword)
    data = bytearray([0xAB, 0xCD])
    regions = {"P::partial": Region(name="P::partial", base_addr=0x3000, size_bytes=2)}
    a = make_analyzer(regions, [Chunk(base_addr=0x3000, data=data)])
    assert a.get_dword("P::partial") == 0x0000CDAB


def test_get_dword_raises_when_declared_bytes_not_actually_in_dump():
    regions = {"M::missing": Region(name="M::missing", base_addr=0x4000, size_bytes=4)}
    a = make_analyzer(regions, [])  # no chunks at all -- nothing backed
    with pytest.raises(ValueError, match="not in dump"):
        a.get_dword("M::missing")


def test_is_tag_set_in_region_raises_when_tag_index_beyond_region_bounds(basic_analyzer):
    # region is 4 dwords (128 tags); tag 128 is the first one out of range
    with pytest.raises(ValueError, match="Out-of-bounds"):
        basic_analyzer.is_tag_set_in_region("A::tags", 128)


def test_is_tag_set_in_region_last_valid_tag_index_does_not_raise(basic_analyzer):
    # tag 96 -> dword index 3 (last valid dword), bit 0 -> not set
    assert basic_analyzer.is_tag_set_in_region("A::tags", 96) is False
    # tag 64 -> dword index 2 (0xFFFFFFFF) -> set
    assert basic_analyzer.is_tag_set_in_region("A::tags", 64) is True


def test_get_bitfield_at_offset_raises_on_out_of_bounds_offset(basic_analyzer):
    with pytest.raises(ValueError, match="Out-of-bounds"):
        basic_analyzer.get_bitfield_at_offset("A::tags", 16, 0, 4)


# ── bit / tag operations ─────────────────────────────────────────────────────

def test_is_bit_set(basic_analyzer):
    assert basic_analyzer.is_bit_set("A::tags", 0) is True
    assert basic_analyzer.is_bit_set("A::tags", 3) is False


def test_get_set_bits(basic_analyzer):
    bits = basic_analyzer.get_set_bits("A::tags")
    assert bits[:3] == [0, 1, 2]
    assert set(range(64, 96)).issubset(set(bits))  # dword index 2 fully set
    assert len(bits) == 3 + 32


def test_count_set_tags(basic_analyzer):
    assert basic_analyzer.count_set_tags("A::tags") == 35


def test_is_tag_set_in_region_individual_bits(basic_analyzer):
    assert basic_analyzer.is_tag_set_in_region("A::tags", 0) is True
    assert basic_analyzer.is_tag_set_in_region("A::tags", 1) is True
    assert basic_analyzer.is_tag_set_in_region("A::tags", 3) is False
    assert basic_analyzer.is_tag_set_in_region("A::tags", 64) is True


# ── bitfield extraction ───────────────────────────────────────────────────────

def test_get_bitfield_extracts_low_byte(basic_analyzer):
    assert basic_analyzer.get_bitfield("A::tags", bit_offset=0, bit_width=8) == 0x07


def test_get_bitfield_extracts_middle_bits(basic_analyzer):
    # dword0 = 0x00000007 -> bits [1:3] = 0b11 = 3
    assert basic_analyzer.get_bitfield("A::tags", bit_offset=1, bit_width=2) == 0b11


def test_get_bitfield_at_offset(basic_analyzer):
    assert basic_analyzer.get_bitfield_at_offset("A::tags", byte_offset=8, bit_offset=0, bit_width=8) == 0xFF


# ── array iteration ────────────────────────────────────────────────────────

def test_iter_dwords_yields_index_value_pairs(basic_analyzer):
    result = list(basic_analyzer.iter_dwords("A::tags"))
    assert result == [(0, 7), (1, 0), (2, 0xFFFFFFFF), (3, 0)]


def test_iter_struct_array_yields_expected_offsets(basic_analyzer):
    result = list(basic_analyzer.iter_struct_array("A::tags", struct_size_bytes=4))
    assert result == [(0, 0), (1, 4), (2, 8), (3, 12)]


def test_iter_struct_array_truncates_partial_trailing_struct(basic_analyzer):
    # 16 bytes / 5-byte structs = 3 whole structs, remainder dropped
    result = list(basic_analyzer.iter_struct_array("A::tags", struct_size_bytes=5))
    assert len(result) == 3


# ── aggregation ────────────────────────────────────────────────────────────

def test_sum_bitfield_across_region(basic_analyzer):
    # low byte of each dword: 0x07, 0x00, 0xFF, 0x00 -> 7 + 0 + 255 + 0
    assert basic_analyzer.sum_bitfield_across_region("A::tags", bit_offset=0, bit_width=8) == 262


def test_any_nonzero_true_when_a_dword_is_nonzero(basic_analyzer):
    assert basic_analyzer.any_nonzero("A::tags") is True


def test_any_nonzero_false_for_all_zero_region():
    regions = {"Z::zero": Region(name="Z::zero", base_addr=0x5000, size_bytes=8)}
    a = make_analyzer(regions, [Chunk(base_addr=0x5000, data=bytearray(8))])
    assert a.any_nonzero("Z::zero") is False


# ── cross-region correlation ─────────────────────────────────────────────────

@pytest.fixture
def two_region_analyzer():
    d1 = bytearray(4)
    d1[0:4] = (0b0011).to_bytes(4, "little")  # tags 0,1
    d2 = bytearray(4)
    d2[0:4] = (0b0110).to_bytes(4, "little")  # tags 1,2
    regions = {
        "B::a": Region(name="B::a", base_addr=0x6000, size_bytes=4),
        "B::b": Region(name="B::b", base_addr=0x7000, size_bytes=4),
    }
    return make_analyzer(regions, [
        Chunk(base_addr=0x6000, data=d1),
        Chunk(base_addr=0x7000, data=d2),
    ])


def test_get_tags_in_any_returns_union(two_region_analyzer):
    assert two_region_analyzer.get_tags_in_any("B::a", "B::b") == [0, 1, 2]


def test_compare_tag_counts(two_region_analyzer):
    result = two_region_analyzer.compare_tag_counts("B::a", "B::b")
    assert result == {"count_a": 2, "count_b": 2, "delta": 0, "match": True}


def test_compare_tag_counts_reports_mismatch():
    regions = {
        "C::a": Region(name="C::a", base_addr=0x8000, size_bytes=4),
        "C::b": Region(name="C::b", base_addr=0x9000, size_bytes=4),
    }
    d1 = (0b111).to_bytes(4, "little")
    d2 = (0b1).to_bytes(4, "little")
    a = make_analyzer(regions, [
        Chunk(base_addr=0x8000, data=bytearray(d1)),
        Chunk(base_addr=0x9000, data=bytearray(d2)),
    ])
    result = a.compare_tag_counts("C::a", "C::b")
    assert result == {"count_a": 3, "count_b": 1, "delta": 2, "match": False}


# ── validation ────────────────────────────────────────────────────────────────

def test_assert_equal_pass_does_not_set_error_flag(basic_analyzer, capsys):
    basic_analyzer.assert_equal("label", 5, 5)
    assert basic_analyzer._error_found is False
    assert "[FAIL]" not in capsys.readouterr().out


def test_assert_equal_fail_sets_error_flag_and_prints(basic_analyzer, capsys):
    basic_analyzer.assert_equal("label", 5, 6)
    assert basic_analyzer._error_found is True
    out = capsys.readouterr().out
    assert "[FAIL]" in out
    assert "delta: 1" in out


def test_assert_true_zero_fails(basic_analyzer):
    basic_analyzer.assert_true("label", 0)
    assert basic_analyzer._error_found is True


def test_assert_true_nonzero_passes(basic_analyzer):
    basic_analyzer.assert_true("label", 1)
    assert basic_analyzer._error_found is False


def test_assert_false_nonzero_fails(basic_analyzer):
    basic_analyzer.assert_false("label", 1)
    assert basic_analyzer._error_found is True


def test_assert_false_zero_passes(basic_analyzer):
    basic_analyzer.assert_false("label", 0)
    assert basic_analyzer._error_found is False


def test_error_flag_latches_true_across_multiple_asserts(basic_analyzer):
    basic_analyzer.assert_equal("first", 1, 1)   # pass
    basic_analyzer.assert_equal("second", 1, 2)  # fail -> latches
    basic_analyzer.assert_equal("third", 3, 3)    # pass, must not clear the flag
    assert basic_analyzer._error_found is True


def test_exit_analyser_exits_zero_on_success(basic_analyzer):
    with pytest.raises(SystemExit) as exc_info:
        basic_analyzer.exit_analyser()
    assert exc_info.value.code == 0


def test_exit_analyser_exits_nonzero_on_failure(basic_analyzer):
    basic_analyzer.assert_equal("label", 1, 2)
    with pytest.raises(SystemExit) as exc_info:
        basic_analyzer.exit_analyser()
    assert exc_info.value.code == 1


# ── dump coverage ─────────────────────────────────────────────────────────────

def test_is_region_in_dump_true_when_backed_by_data(basic_analyzer):
    assert basic_analyzer.is_region_in_dump("A::tags") is True


def test_is_region_in_dump_false_when_key_unknown(basic_analyzer):
    assert basic_analyzer.is_region_in_dump("Nope::missing") is False


def test_is_region_in_dump_false_when_declared_but_not_dumped():
    regions = {"D::gone": Region(name="D::gone", base_addr=0xB000, size_bytes=4)}
    a = make_analyzer(regions, [])
    assert a.is_region_in_dump("D::gone") is False


def test_get_missing_regions_returns_only_the_missing_ones(basic_analyzer):
    regions = dict(basic_analyzer.regions)
    regions["D::gone"] = Region(name="D::gone", base_addr=0xB000, size_bytes=4)
    a = DumpAnalyzer(basic_analyzer.mem, regions)
    assert a.get_missing_regions("A::tags", "D::gone") == ["D::gone"]


def test_get_missing_regions_empty_when_all_present(basic_analyzer):
    assert basic_analyzer.get_missing_regions("A::tags") == []


# ── properties ────────────────────────────────────────────────────────────────

def test_mem_and_regions_properties_expose_underlying_objects(basic_analyzer):
    assert basic_analyzer.mem is not None
    assert "A::tags" in basic_analyzer.regions
