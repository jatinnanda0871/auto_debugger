import ctypes
import sys
from typing import Optional
from engine.models import MemoryView, Region
from engine.struct_gen import generate_for_product


class DumpAnalyzer:
    """
    Public API for dump analysis.
    All lookups are by IP::key string — no raw addresses exposed.
    """

    def __init__(self, mem: MemoryView, regions: dict[str, Region]):
        self._mem         = mem
        self._regions     = regions
        self._error_found = False

    # ── Public accessors ───────────────────────────────────────────────────────

    @property
    def mem(self) -> MemoryView:
        """Underlying sparse memory view. Read-only by convention."""
        return self._mem

    @property
    def regions(self) -> dict:
        """All known regions, keyed by IP::key. Read-only by convention."""
        return self._regions

    def get_region(self, key: str) -> Region:
        """Looks up a region by key. Raises KeyError if not found."""
        region = self._regions.get(key)
        if region is None:
            raise KeyError(f"Key '{key}' not found in map. "
                           f"Available: {list(self._regions.keys())}")
        return region

    # ── Struct generation ──────────────────────────────────────────────────────

    def generate_structs(self, product_id: str, controller_name: str = None,
                          force: bool = False) -> None:
        """
        Regenerates products/<product_id>/generated_structs/ from that
        product's C/C++ headers, listed in the manifest
        products/<product_id>/<controller_name>.py (or
        products/<product_id>/<product_id>.py if controller_name is None).
        No-op if that manifest declares no headers or doesn't exist, or if
        nothing changed since the last generation (unless force=True).
        """
        generate_for_product(product_id, controller_name, force=force)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _get_region(self, key: str) -> Region:
        # Kept for internal call sites; delegates to the public accessor.
        return self.get_region(key)

    def _check_bounds(self, region: Region, byte_offset: int, n_bytes: int) -> None:
        if byte_offset + n_bytes > region.size_bytes:
            raise ValueError(
                f"Out-of-bounds read on '{region.name}': "
                f"offset 0x{byte_offset:X}+{n_bytes}B exceeds region size "
                f"0x{region.size_bytes:X}B ({region.size_dwords} dwords)"
            )

    def _get_dword(self, key: str) -> int:
        region = self._get_region(key)
        if region.size_bytes == 0:
            raise ValueError(f"Key '{key}' has a zero-byte region — nothing to read")
        n      = min(region.size_bytes, 4)
        result = 0
        for i in range(n):
            b = self._mem.read_byte(region.base_addr + i)
            if b is None:
                raise ValueError(f"Key '{key}' at 0x{region.base_addr + i:08X} not in dump")
            result |= b << (i * 8)
        return result

    # ── Core access ────────────────────────────────────────────────────────────

    def get_dword(self, key: str, is_address: bool = True) -> int:
        """
        If is_address=True  → reads dword from dump at region base address.
        If is_address=False → returns the base_addr field directly as literal.
        """
        if not is_address:
            return self._get_region(key).base_addr
        return self._get_dword(key)

    def get_region_dwords(self, key: str) -> list:
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
        self._check_bounds(region, byte_offset, 1)
        val    = self._mem.read_byte(region.base_addr + byte_offset)
        if val is None:
            raise ValueError(f"Byte at 0x{region.base_addr + byte_offset:08X} not in dump")
        return val

    def get_base_addr(self, key: str) -> int:
        return self._get_region(key).base_addr

    def get_struct_field(self, key: str, struct_cls: type, field_path: str,
                          byte_offset: int = 0):
        """
        Interprets the bytes at key's region (starting at byte_offset) as
        struct_cls -- a ctypes Structure/Union from a product's
        generated_structs/ -- and returns the value of one field.

        field_path may be a plain field name ("status") or a dotted path
        into nested structs/unions ("dword0.bits.error_code"), matching how
        the generated ctypes classes mirror the original C struct layout.

        Example:
            from products.epdc.generated_structs.status import DemoStatus
            value = analyzer.get_struct_field("IP::status", DemoStatus, "dword0.bits.error_code")
        """
        region = self._get_region(key)
        size   = ctypes.sizeof(struct_cls)
        self._check_bounds(region, byte_offset, size)

        raw = bytearray(size)
        for i in range(size):
            b = self._mem.read_byte(region.base_addr + byte_offset + i)
            if b is None:
                raise ValueError(
                    f"'{key}'+0x{byte_offset + i:X} not in dump "
                    f"(reading {struct_cls.__name__})"
                )
            raw[i] = b

        value = struct_cls.from_buffer_copy(bytes(raw))
        for part in field_path.split("."):
            try:
                value = getattr(value, part)
            except AttributeError:
                raise AttributeError(
                    f"{struct_cls.__name__} has no field '{part}' "
                    f"(from field_path '{field_path}')"
                )
        return value

    def get_region_size_dwords(self, key: str) -> int:
        return self._get_region(key).size_dwords

    def key_exists(self, key: str) -> bool:
        return key in self._regions

    # ── Bit / tag operations ───────────────────────────────────────────────────

    def is_bit_set(self, key: str, bit: int) -> bool:
        return bool(self._get_dword(key) & (1 << bit))

    def get_set_bits(self, key: str) -> list:
        dwords   = self.get_region_dwords(key)
        set_bits = []
        for dw_idx, dw in enumerate(dwords):
            for bit in range(32):
                if dw & (1 << bit):
                    set_bits.append(dw_idx * 32 + bit)
        return set_bits

    def count_set_tags(self, key: str) -> int:
        return len(self.get_set_bits(key))

    def is_tag_set_in_region(self, key: str, tag_index: int) -> bool:
        """Checks if a specific tag index has its bit set in the given bitmap region."""
        region    = self._get_region(key)
        dw_index  = tag_index // 32
        bit_index = tag_index % 32
        self._check_bounds(region, dw_index * 4, 4)
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
        self._check_bounds(region, byte_offset, 4)
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

    def get_tags_in_any(self, *keys: str) -> list:
        """Returns tags set in at least one of the given regions."""
        result = set()
        for k in keys:
            result |= set(self.get_set_bits(k))
        return sorted(result)

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

    def assert_equal(self, label: str, actual: int, expected: int) -> None:
        if actual != expected:
            print(f"  [FAIL] {label}: {actual} != {expected}  (delta: {abs(actual - expected)})")
            self._error_found = True

    def assert_true(self, label: str, value: int) -> None:
        if value == 0:
            print(f"  [FAIL] {label}: {value} is Zero or False, expected was non-zero or True")
            self._error_found = True

    def assert_false(self, label: str, value: int) -> None:
        if value != 0:
            print(f"  [FAIL] {label}: {value} is non-zero, expected was 0")
            self._error_found = True

    def exit_analyser(self) -> None:
        if self._error_found == True:
            print(f"\n  [FAIL] Encountered error during analysis")
        else:
            print(f"\n  [PASS] No issues found during dump analysis")

        sys.exit(self._error_found)

    # ── Dump coverage ──────────────────────────────────────────────────────────

    def is_region_in_dump(self, key: str) -> bool:
        region = self._regions.get(key)
        if region is None:
            return False
        return self._mem.read_dword(region.base_addr) is not None

    def get_missing_regions(self, *keys: str) -> list:
        return [k for k in keys if not self.is_region_in_dump(k)]
