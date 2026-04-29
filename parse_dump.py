import sys
import re
import glob
import os
from typing import Optional
from models import Region, Chunk, MemoryView
from api import DumpAnalyzer
from analyzers import *
from repl import DebugREPL

# ── Constants ──────────────────────────────────────────────────────────────────

DWORDS_PER_LINE     = 8
LINE_BYTES          = DWORDS_PER_LINE * 4
CHUNK_GAP_THRESHOLD = 0x1000  # 4 KB — new chunk if gap exceeds this

# ── Map loader ─────────────────────────────────────────────────────────────────
#
# Format: IP::key=0xADDR,0xSIZE
# Example: TagManager::occupied_tags=0xA0001234,0x000000C0

MAP_LINE_RE = re.compile(
    r'^(\w+::\w+)\s*=\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)$'
)

def load_map(map_file: str) -> dict[str, Region]:
    regions = {}
    with open(map_file) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            m = MAP_LINE_RE.match(line)
            if not m:
                print(f"[WARN] Map line {lineno}: unexpected format — '{line}'")
                continue
            name, addr_str, size_str = m.group(1), m.group(2), m.group(3)
            size_dwords = int(size_str, 16) // 4
            regions[name] = Region(
                name=name,
                base_addr=int(addr_str, 16),
                size_dwords=size_dwords
            )
    return regions

# ── Dump loader ────────────────────────────────────────────────────────────────
#
# Format: 0xADDR: 0xDW1 0xDW2 0xDW3 0xDW4 0xDW5 0xDW6 0xDW7 0xDW8

DUMP_LINE_RE = re.compile(
    r'^(0x[0-9a-fA-F]+)\s*:\s*'
    r'((?:0x[0-9a-fA-F]+\s*){8})$'
)

def _parse_dump_lines(dump_file: str) -> list[tuple[int, list[int]]]:
    parsed = []
    with open(dump_file) as f:
        for lineno, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            m = DUMP_LINE_RE.match(raw)
            if not m:
                print(f"[WARN] Dump line {lineno}: unrecognized — '{raw}'")
                continue
            addr   = int(m.group(1), 16)
            dwords = [int(d, 16) for d in m.group(2).split()]
            parsed.append((addr, dwords))
    return parsed

def _lines_to_chunk(base_addr: int, lines: list[tuple[int, list[int]]]) -> Chunk:
    last_addr  = lines[-1][0]
    total_size = (last_addr - base_addr) + LINE_BYTES
    buf        = bytearray(total_size)
    for addr, dwords in lines:
        for i, dw in enumerate(dwords):
            offset          = (addr - base_addr) + i * 4
            buf[offset]     =  dw        & 0xFF
            buf[offset + 1] = (dw >>  8) & 0xFF
            buf[offset + 2] = (dw >> 16) & 0xFF
            buf[offset + 3] = (dw >> 24) & 0xFF
    return Chunk(base_addr=base_addr, data=buf)

def _build_chunks(parsed_lines: list[tuple[int, list[int]]]) -> list[Chunk]:
    if not parsed_lines:
        return []
    parsed_lines.sort(key=lambda x: x[0])
    chunks      = []
    chunk_start = parsed_lines[0][0]
    chunk_lines = [parsed_lines[0]]
    for addr, dwords in parsed_lines[1:]:
        prev_addr = chunk_lines[-1][0]
        gap       = addr - (prev_addr + LINE_BYTES)
        if gap > CHUNK_GAP_THRESHOLD:
            chunks.append(_lines_to_chunk(chunk_start, chunk_lines))
            chunk_start = addr
            chunk_lines = []
        chunk_lines.append((addr, dwords))
    chunks.append(_lines_to_chunk(chunk_start, chunk_lines))
    return chunks

def load_dump(dump_path: str) -> MemoryView:
    """
    Accepts a folder (loads all *.dump files) or a single file.
    All files merged into one sparse MemoryView.
    """
    if os.path.isdir(dump_path):
        dump_files = sorted(glob.glob(os.path.join(dump_path, "*.dump")))
        if not dump_files:
            raise ValueError(f"No *.dump files found in '{dump_path}'")
        print(f"[INFO] Found {len(dump_files)} dump file(s) in '{dump_path}'")
    else:
        dump_files = [dump_path]

    all_parsed = []
    for f in dump_files:
        print(f"[INFO] Parsing {os.path.basename(f)}...")
        parsed = _parse_dump_lines(f)
        print(f"       {len(parsed)} lines parsed")
        all_parsed.extend(parsed)

    if not all_parsed:
        raise ValueError("No valid dump lines found")

    # Deduplicate — last file wins on address collision
    seen = {}
    for addr, dwords in all_parsed:
        seen[addr] = dwords
    deduped = sorted(seen.items(), key=lambda x: x[0])

    chunks = _build_chunks(deduped)
    mv     = MemoryView(chunks=chunks)
    print(f"[INFO] Loaded dump —\n{mv.summary()}")
    return mv

# ── Analyzer registry ──────────────────────────────────────────────────────────

ANALYZERS = [
    analyze_occupied_tags,
    analyze_fcc_counter,
    # add more here
]

# Map name → function for REPL 'run' command
ANALYZER_MAP = { fn.__name__: fn for fn in ANALYZERS }

# Map region key → ctypes struct class (add entries as structs are generated)
# Example: from structs import TagManagerSfr
# STRUCT_MAP = { "TagManager::sfr_base": TagManagerSfr }
STRUCT_MAP = {}

# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <dump_folder_or_file> <map_file> [--repl]")
        sys.exit(1)

    dump_path, map_file = sys.argv[1], sys.argv[2]
    interactive = "--repl" in sys.argv

    regions  = load_map(map_file)
    mem      = load_dump(dump_path)
    analyzer = DumpAnalyzer(mem, regions)

    if interactive:
        DebugREPL(analyzer, STRUCT_MAP, ANALYZER_MAP).run()
    else:
        for fn in ANALYZERS:
            try:
                fn(analyzer)
            except Exception as e:
                print(f"\n[ERROR] {fn.__name__} failed: {e}")

if __name__ == "__main__":
    main()
