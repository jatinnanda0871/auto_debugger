import re
import glob
import os
from engine.models import Region, Chunk, MemoryView

# ── Constants ──────────────────────────────────────────────────────────────────

DWORDS_PER_LINE     = 8
LINE_BYTES          = DWORDS_PER_LINE * 4
CHUNK_GAP_THRESHOLD = 0x1000  # 4 KB — new chunk if gap exceeds this

# ── Map loader ─────────────────────────────────────────────────────────────────
#
# Format: IP::key=0xADDR,0xSIZE
# Example: TagManager::occupied_tags=0xA0001234,0x000000C0
#
# Literal values (no 0x prefix on address) are stored as-is in base_addr
# and returned directly by get_value(key, is_address=False).

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
            base_addr   = int(addr_str, 16)
            size_dwords = int(size_str, 16) // 4
            regions[name] = Region(
                name=name,
                base_addr=base_addr,
                size_dwords=size_dwords,
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

def load_dump(dump_folder: str) -> MemoryView:
    """
    Loads all *.dump files from dump_folder into one sparse MemoryView.
    """
    dump_files = sorted(glob.glob(os.path.join(dump_folder, "*.dump")))
    if not dump_files:
        raise ValueError(f"No *.dump files found in '{dump_folder}'")
    print(f"[INFO] Found {len(dump_files)} dump file(s) in '{dump_folder}'")

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

def find_map_file(dump_folder: str) -> str:
    """
    Finds exactly one *.map file in dump_folder.
    Raises clearly if none or more than one found.
    """
    map_files = glob.glob(os.path.join(dump_folder, "*.map"))
    if not map_files:
        raise ValueError(f"No *.map file found in '{dump_folder}'")
    if len(map_files) > 1:
        raise ValueError(
            f"Multiple *.map files found in '{dump_folder}': {map_files}\n"
            f"Please keep exactly one .map file per dump folder."
        )
    return map_files[0]
