# Auto Debugger — Memory Dump Analysis Framework

A Python framework for analyzing NVMe controller emulator memory dumps.
Designed as a companion to the firmware build — the C++ source is always
the single source of truth for addresses, sizes, and struct layouts.

---

## File Structure

```
auto_debugger/
├── models.py        ← Region, Chunk, MemoryView (sparse bytearray)
├── api.py           ← DumpAnalyzer public API
├── analyzers.py     ← per-IP analyzer functions
├── repl.py          ← interactive GDB-style debug REPL
└── parse_dump.py    ← loaders, main entry point
```

---

## Quick Start

### Automated analysis
```bash
python parse_dump.py <dump_folder_or_file> <map_file>
```

### Interactive REPL session
```bash
python parse_dump.py <dump_folder_or_file> <map_file> --repl
```

---

## Map File Format
```
key=0xADDR,0xSIZE
```

Example:
```
occupied_tags=0xA0001000,0x000000C0
counters=0xA0002000,0x00000080
fcc_counter_size=0x30,0x4
```

Size is in bytes (hex). Values are always hex (`0x`-prefixed). For literal
constants (not addresses into the dump), pass `is_address=False` to
`get_value()` — the same value is then returned directly without a dump lookup.

---

## Dump File Format

Each line: `0xADDR: 0xDW1 0xDW2 0xDW3 0xDW4 0xDW5 0xDW6 0xDW7 0xDW8`

- 8 dwords per line, 4-byte aligned addresses
- Multiple `*.dump` files in a folder are merged automatically
- Gaps between files handled via sparse chunk model (threshold: 4 KB)

---

## REPL Commands

| Command | Description |
|---|---|
| `TagManager::occupied_tags` | GDB-style hex dump of full region |
| `TagManager::sfr_base.tag_count` | Read struct field (address + value + type) |
| `x/8xw 0xA0001000` | Read N dwords at raw address |
| `x 0xA0001000` | Read 4 dwords at address (default) |
| `list` | List all known regions |
| `run <analyzer_name>` | Run a named analyzer function |
| `help` | Show command reference |
| `quit` | Exit session |

---

## API Reference

### Core access
```python
get_value(key, is_address=True)         # dword at address, or literal value
get_region_dwords(key)                  # all dwords in region
get_byte(key, byte_offset)              # single byte within region
get_base_addr(key)                      # base address of region
get_region_size_dwords(key)             # size in dwords
key_exists(key)                         # check if key is in map
```

### Bit / tag operations
```python
is_zero(key)                            # dword == 0
is_bit_set(key, bit)                    # single bit check
get_set_bits(key)                       # all set bit positions
get_set_tags(key)                       # alias for get_set_bits
count_set_tags(key)                     # count only, no list
is_tag_set_in_region(key, tag_index)    # check specific tag in bitmap
```

### Bitfield extraction
```python
get_bitfield(key, bit_offset, bit_width)
get_bitfield_at_offset(key, byte_offset, bit_offset, bit_width)
```

### Array iteration
```python
iter_dwords(key)                          # generator: (index, dword)
iter_struct_array(key, struct_size_bytes) # generator: (index, byte_offset)
```

### Aggregation
```python
sum_bitfield_across_region(key, bit_offset, bit_width)
any_nonzero(key)
```

### Cross-region correlation
```python
get_tags_in_all(*keys)                # set intersection
get_tags_in_any(*keys)                # set union
get_tags_only_in(source, *excludes)   # orphan detection
compare_tag_counts(key_a, key_b)      # {count_a, count_b, delta, match}
```

### Validation
```python
assert_equal(label, actual, expected)   # prints [PASS]/[FAIL]
assert_zero(label, key)
assert_no_tags_set(label, key)
```

### Dump coverage
```python
is_region_in_dump(key)
get_missing_regions(*keys)
```

### Struct access
```python
read_struct(region, struct_type)        # ctypes overlay — reinterpret_cast equivalent
```

---

## Adding a New Analyzer

1. Write the function in `analyzers.py` — takes `DumpAnalyzer` as sole argument
2. Add it to `ANALYZERS` list in `parse_dump.py`

```python
def analyze_my_region(analyzer: DumpAnalyzer) -> None:
    print("\n=== My Region ===")
    missing = analyzer.get_missing_regions("my_key")
    if missing:
        print(f"  [SKIP] {missing}")
        return
    val = analyzer.get_value("my_key")
    print(f"  value = 0x{val:08X}")
```

---

## Struct Generation

# pip install ctypeslib2
# clang2py my_struct.h -o my_struct.py

```
Register generated structs in `parse_dump.py`:
```python
from structs import TagManagerSfr

STRUCT_MAP = {
    "TagManager::sfr_base": TagManagerSfr,
}
```

---

## Release Artifacts

On every release build (`cmake -DRELEASE_BUILD=ON`):

```
releases/v1.x.x/
    firmware.bin
    dump.map       ← addresses (from dump_map_gen)
    structs.py     ← struct layouts (from struct_gen or IP-XACT)
```

Always analyze a dump with the map/structs from the matching release.
