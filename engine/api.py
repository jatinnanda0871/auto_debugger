from typing import Optional
from engine.models import MemoryView, Region


class DumpAnalyzer:
    """
    Public API for dump analysis.
    All lookups are by IP::key string — no raw addresses exposed.
    """

    def __init__(self, mem: MemoryView, regions: dict[str, Region]):
        self._mem     = mem
        self._regions = regions

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get_region(self, key: str) -> Region:
        region = self._regions.get(key)
        if region is None:
            raise KeyError(f"Key '{key}' not found in map. "
                           f"Available: {list(self._regions.keys())}")
        return region

    def _get_dword(self, key: str) -> int:
        region = self._get_region(key)
        dword  = self._mem.read_dword(region.base_addr)
        if dword is None:
            raise ValueError(f"Key '{key}' at 0x{region.base_addr:08X} not in dump")
        return dword

    # ── Core access ────────────────────────────────────────────────────────────

    def get_value(self, key: str, is_address: bool = True) -> int:
        """
        If is_address=True  → reads dword from dump at region base address.
        If is_address=False → returns the base_addr field directly as literal.
        """
        region = self._get_region(key)
        if not is_address:
            return region.base_addr
        dword = self._mem.read_dword(region.base_addr)
        if dword is None:
            raise ValueError(f"Key '{key}' at 0x{region.base_addr:08X} not in dump")
        return dword

    def get_region_dwords(self, key: str) -> list[int]:
        region = self._get_region(key)
        result = []
        for dw in self._mem.read_region_dwords(region):
            if dw is None:
                print(f"[WARN] '{key}': missing dword in dump, treating as 0")
                result.append(0)
            else:
                result.append(dw)
        return result

    def get_byte(self, key: str, byte_offset: int) -> int:
        region = self._get_region(key)
        val    = self._mem.read_byte(region.base_addr + byte_offset)
        if val is None:
            raise ValueError(f"Byte at 0x{region.base_addr + byte_offset:08X} not in dump")
        return val

    def get_base_addr(self, key: str) -> int:
        return self._get_region(key).base_addr

    def get_region_size_dwords(self, key: str) -> int:
        return self._get_region(key).size_dwords

    def key_exists(self, key: str) -> bool:
        return key in self._regions

    # ── Bit / tag operations ───────────────────────────────────────────────────

    def is_zero(self, key: str) -> bool:
        return self._get_dword(key) == 0

    def is_bit_set(self, key: str, bit: int) -> bool:
        return bool(self._get_dword(key) & (1 << bit))

    def get_set_bits(self, key: str) -> list[int]:
        dwords   = self.get_region_dwords(key)
        set_bits = []
        for dw_idx, dw in enumerate(dwords):
            for bit in range(32):
                if dw & (1 << bit):
                    set_bits.append(dw_idx * 32 + bit)
        return set_bits

    def get_set_tags(self, key: str) -> list[int]:
        return self.get_set_bits(key)

    def count_set_tags(self, key: str) -> int:
        return len(self.get_set_bits(key))

    def is_tag_set_in_region(self, key: str, tag_index: int) -> bool:
        """Checks if a specific tag index has its bit set in the given bitmap region."""
        region    = self._get_region(key)
        dw_index  = tag_index // 32
        bit_index = tag_index % 32
        dword     = self._mem.read_dword(region.base_addr + dw_index * 4)
        if dword is None:
            raise ValueError(f"Key '{key}' dword {dw_index} not in dump")
        return bool(dword & (1 << bit_index))

    # ── Bitfield extraction ────────────────────────────────────────────────────

    def get_bitfield(self, key: str, bit_offset: int, bit_width: int) -> int:
        """Extracts a bitfield from the dword at key's base address."""
        dword = self._get_dword(key)
        mask  = (1 << bit_width) - 1
        return (dword >> bit_offset) & mask

    def get_bitfield_at_offset(self, key: str, byte_offset: int,
                                bit_offset: int, bit_width: int) -> int:
        """Extracts a bitfield from a dword at byte_offset within the region."""
        region = self._get_region(key)
        dword  = self._mem.read_dword(region.base_addr + byte_offset)
        if dword is None:
            raise ValueError(f"'{key}'+0x{byte_offset:X} not in dump")
        mask = (1 << bit_width) - 1
        return (dword >> bit_offset) & mask

    # ── Array iteration ────────────────────────────────────────────────────────

    def iter_dwords(self, key: str):
        """Generator — yields (index, dword_value) for every dword in region."""
        for i, dw in enumerate(self.get_region_dwords(key)):
            yield i, dw

    def iter_struct_array(self, key: str, struct_size_bytes: int):
        """Generator — yields (index, byte_offset) for each struct in array."""
        region = self._get_region(key)
        count  = region.size_bytes // struct_size_bytes
        for i in range(count):
            yield i, i * struct_size_bytes

    # ── Aggregation ────────────────────────────────────────────────────────────

    def sum_bitfield_across_region(self, key: str,
                                    bit_offset: int, bit_width: int) -> int:
        """Sums the same bitfield extracted from every dword in the region."""
        mask  = (1 << bit_width) - 1
        total = 0
        for _, dw in self.iter_dwords(key):
            total += (dw >> bit_offset) & mask
        return total

    def any_nonzero(self, key: str) -> bool:
        return any(dw != 0 for _, dw in self.iter_dwords(key))

    # ── Cross-region correlation ───────────────────────────────────────────────

    def get_tags_in_all(self, *keys: str) -> list[int]:
        """Returns tags set in ALL given bitmap regions simultaneously."""
        if not keys:
            return []
        sets = [set(self.get_set_tags(k)) for k in keys]
        result = sets[0]
        for s in sets[1:]:
            result = result & s
        return sorted(result)

    def get_tags_in_any(self, *keys: str) -> list[int]:
        """Returns tags set in at least one of the given regions."""
        result = set()
        for k in keys:
            result |= set(self.get_set_tags(k))
        return sorted(result)

    def get_tags_only_in(self, source_key: str, *exclude_keys: str) -> list[int]:
        """Returns tags in source_key but NOT in any of the exclude_keys."""
        source  = set(self.get_set_tags(source_key))
        exclude = set()
        for k in exclude_keys:
            exclude |= set(self.get_set_tags(k))
        return sorted(source - exclude)

    def compare_tag_counts(self, key_a: str, key_b: str) -> dict:
        """Compares set-bit counts between two regions."""
        count_a = self.count_set_tags(key_a)
        count_b = self.count_set_tags(key_b)
        return {
            "count_a": count_a,
            "count_b": count_b,
            "delta":   abs(count_a - count_b),
            "match":   count_a == count_b,
        }

    # ── Validation ─────────────────────────────────────────────────────────────

    def assert_equal(self, label: str, actual: int, expected: int) -> bool:
        if actual == expected:
            print(f"  [PASS] {label}: {actual} == {expected}")
            return True
        else:
            print(f"  [FAIL] {label}: {actual} != {expected}  (delta: {abs(actual - expected)})")
            return False

    def assert_zero(self, label: str, key: str) -> bool:
        val = self._get_dword(key)
        if val == 0:
            print(f"  [PASS] {label}: 0x{self.get_base_addr(key):08X} == 0")
            return True
        else:
            print(f"  [FAIL] {label}: 0x{self.get_base_addr(key):08X} = 0x{val:08X} (non-zero)")
            return False

    def assert_no_tags_set(self, label: str, key: str) -> bool:
        tags = self.get_set_tags(key)
        if not tags:
            print(f"  [PASS] {label}: no bits set in '{key}'")
            return True
        else:
            print(f"  [FAIL] {label}: {len(tags)} bit(s) set in '{key}': {tags[:8]}...")
            return False

    # ── Dump coverage ──────────────────────────────────────────────────────────

    def is_region_in_dump(self, key: str) -> bool:
        region = self._regions.get(key)
        if region is None:
            return False
        return self._mem.read_dword(region.base_addr) is not None

    def get_missing_regions(self, *keys: str) -> list[str]:
        return [k for k in keys if not self.is_region_in_dump(k)]
