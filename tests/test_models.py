from engine.models import Region, Chunk, MemoryView


# ── Region ───────────────────────────────────────────────────────────────────

def test_region_size_dwords_exact_multiple():
    r = Region(name="k", base_addr=0x1000, size_bytes=16)
    assert r.size_dwords == 4


def test_region_size_dwords_rounds_up_for_odd_size():
    # 1 byte still needs 1 whole dword read
    r = Region(name="k", base_addr=0x1000, size_bytes=1)
    assert r.size_dwords == 1
    r = Region(name="k", base_addr=0x1000, size_bytes=5)
    assert r.size_dwords == 2


def test_region_size_dwords_zero_for_zero_size():
    r = Region(name="k", base_addr=0x1000, size_bytes=0)
    assert r.size_dwords == 0


def test_region_end_addr():
    r = Region(name="k", base_addr=0x1000, size_bytes=0x20)
    assert r.end_addr == 0x1020


# ── Chunk ────────────────────────────────────────────────────────────────────

def test_chunk_end_addr():
    c = Chunk(base_addr=0x1000, data=bytearray(16))
    assert c.end_addr == 0x1010


def test_chunk_contains_bounds():
    c = Chunk(base_addr=0x1000, data=bytearray(16))
    assert c.contains(0x1000) is True
    assert c.contains(0x100F) is True
    assert c.contains(0x1010) is False  # end is exclusive
    assert c.contains(0x0FFF) is False


# ── MemoryView ───────────────────────────────────────────────────────────────

def test_read_byte_and_dword_within_single_chunk():
    data = bytearray([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
    mv   = MemoryView(chunks=[Chunk(base_addr=0x1000, data=data)])
    assert mv.read_byte(0x1000) == 0x01
    assert mv.read_byte(0x1004) == 0x05
    assert mv.read_dword(0x1000) == 0x04030201  # little-endian
    assert mv.read_dword(0x1004) == 0x08070605


def test_read_outside_any_chunk_returns_none():
    mv = MemoryView(chunks=[Chunk(base_addr=0x1000, data=bytearray(8))])
    assert mv.read_byte(0x2000) is None
    assert mv.read_dword(0x2000) is None


def test_read_dword_partial_overrun_at_chunk_end_returns_none():
    # Chunk holds only 3 bytes past addr 0x1004 -- not enough for a full dword
    data = bytearray(7)
    mv   = MemoryView(chunks=[Chunk(base_addr=0x1000, data=data)])
    assert mv.read_dword(0x1004) is None  # would need bytes [4:8], only [4:7] exist
    assert mv.read_dword(0x1000) is not None


def test_read_across_multiple_sorted_chunks_binary_search():
    c1 = Chunk(base_addr=0x1000, data=bytearray([0xAA, 0, 0, 0]))
    c2 = Chunk(base_addr=0x5000, data=bytearray([0xBB, 0, 0, 0]))
    c3 = Chunk(base_addr=0x9000, data=bytearray([0xCC, 0, 0, 0]))
    mv = MemoryView(chunks=[c1, c2, c3])
    assert mv.read_byte(0x1000) == 0xAA
    assert mv.read_byte(0x5000) == 0xBB
    assert mv.read_byte(0x9000) == 0xCC
    assert mv.read_byte(0x3000) is None  # gap between c1 and c2


def test_read_region_dwords_mixes_present_and_missing():
    # Only the first dword of the region is actually backed by data
    data = bytearray([0x01, 0x00, 0x00, 0x00])
    mv   = MemoryView(chunks=[Chunk(base_addr=0x1000, data=data)])
    region = Region(name="k", base_addr=0x1000, size_bytes=8)  # 2 dwords
    result = mv.read_region_dwords(region)
    assert result == [1, None]


def test_summary_lists_all_chunks():
    mv = MemoryView(chunks=[Chunk(base_addr=0x1000, data=bytearray(1024))])
    text = mv.summary()
    assert "1 chunk(s)" in text
    assert "0x00001000" in text
