from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Region ─────────────────────────────────────────────────────────────────────

@dataclass
class Region:
    name: str
    base_addr: int
    size_bytes: int  # exact byte count from map file

    @property
    def size_dwords(self) -> int:
        return (self.size_bytes + 3) // 4

    @property
    def end_addr(self) -> int:
        return self.base_addr + self.size_bytes


# ── Sparse MemoryView ──────────────────────────────────────────────────────────

@dataclass
class Chunk:
    base_addr: int
    data: bytearray

    @property
    def end_addr(self) -> int:
        return self.base_addr + len(self.data)

    def contains(self, addr: int) -> bool:
        return self.base_addr <= addr < self.end_addr


@dataclass
class MemoryView:
    chunks: list[Chunk] = field(default_factory=list)  # sorted by base_addr

    def _find_chunk(self, addr: int) -> Optional[Chunk]:
        lo, hi = 0, len(self.chunks) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            c = self.chunks[mid]
            if addr < c.base_addr:
                hi = mid - 1
            elif addr >= c.end_addr:
                lo = mid + 1
            else:
                return c
        return None

    def read_byte(self, addr: int) -> Optional[int]:
        c = self._find_chunk(addr)
        return c.data[addr - c.base_addr] if c else None

    def read_dword(self, addr: int) -> Optional[int]:
        c = self._find_chunk(addr)
        if c is None:
            return None
        offset = addr - c.base_addr
        if offset + 4 > len(c.data):
            return None
        b = c.data[offset:offset + 4]
        return b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)

    def read_bytes(self, addr: int, n: int) -> Optional[bytes]:
        c = self._find_chunk(addr)
        if c is None:
            return None
        offset = addr - c.base_addr
        if offset + n > len(c.data):
            return None
        return bytes(c.data[offset:offset + n])

    def read_region_dwords(self, region: Region) -> list:
        return [self.read_dword(region.base_addr + i * 4)
                for i in range(region.size_dwords)]

    def summary(self) -> str:
        lines = [f"  {len(self.chunks)} chunk(s):"]
        for c in self.chunks:
            lines.append(
                f"    0x{c.base_addr:08X} - 0x{c.end_addr:08X}"
                f"  ({len(c.data) / 1024:.1f} KB)"
            )
        return "\n".join(lines)
