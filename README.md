# Auto Debugger — Memory Dump Analysis Framework

A Python framework for analyzing firmware memory dumps.
The C++ firmware source is always the single source of truth for addresses,
sizes, and struct layouts — this tool only reads and interprets.

---

## File Structure

```
auto_debugger/
├── main.py                      ← entry point
├── structs.py                   ← auto-generated ctypes structs (do not edit)
├── analyzers.py                 ← standalone analyzer functions
├── engine/
│   ├── models.py                ← Region, Chunk, MemoryView (sparse bytearray)
│   ├── api.py                   ← DumpAnalyzer public API
│   ├── loader.py                ← map / dump file loaders (read-only enforced)
│   └── repl.py                  ← interactive GDB-style debug REPL
└── products/
    └── <product_id>/
        ├── config.py            ← map key constants + MODULES list
        ├── product.py           ← product entry point: run(analyzer)
        └── modules/
            └── <module>.py      ← per-IP analyzer: run(analyzer)
```

---

## Quick Start

### Automated analysis
```bash
python main.py <dump_folder> <product_id>
```

### Interactive REPL session
```bash
python main.py <dump_folder> <product_id> --repl
```

`dump_folder` must contain one `*.map` file and one or more `*.dump` files.

Example:
```bash
python main.py ./dumps/run1 epdc
python main.py ./dumps/run1 epdc --repl
```

---

## File Formats

### Map file (`*.map`)
```
IP::key=0xADDR,0xSIZE
```
Size is in bytes (hex). One entry per line. Key names must use the `IP::key` form.

```
TagManager::occupied_tags=0xA0001000,0x000000C0
TagManager::fetch_pending=0xA0001100,0x000000C0
FccManager::counters=0xA0002000,0x00000080
```

### Dump file (`*.dump`)
Each line: `0xADDR: 0xDW1 0xDW2 0xDW3 0xDW4 0xDW5 0xDW6 0xDW7 0xDW8`

- Exactly 8 dwords per line, 4-byte aligned addresses
- Multiple `*.dump` files in the folder are merged automatically
- Gaps between address ranges are handled via a sparse chunk model (gap threshold: 4 KB)
- Files are opened `O_RDONLY` at the OS level — the tool cannot write to them
- 0xADDR will be address from firmware view

---

## REPL Commands

| Command | Description |
|---|---|
| `x/NxW 0xADDR` | Read N dwords at raw address (e.g. `x/8xw 0xA0001000`) |
| `x 0xADDR` | Read 4 dwords at address (shorthand) |
| `list` | List all known regions with coverage status |
| `help` | Show command reference |
| `quit` / `q` | Exit session |

---

## API Reference (`DumpAnalyzer`)

### Core access
```python
get_region(key)                             # Region object; raises KeyError if missing
get_dword(key, is_address=True)             # dword at region base, or literal base_addr
get_region_dwords(key)                      # all dwords in region as list[int]
get_byte(key, byte_offset)                  # single byte within region
get_base_addr(key)                          # base address of region
get_region_size_dwords(key)                 # size in dwords
key_exists(key)                             # bool — key present in map
```

### Bit / tag operations
```python
is_bit_set(key, bit)                        # single bit check
get_set_bits(key)                           # list of all set bit positions
count_set_tags(key)                         # count of set bits
is_tag_set_in_region(key, tag_index)        # check specific tag in bitmap
```

### Bitfield extraction
```python
get_bitfield(key, bit_offset, bit_width)
get_bitfield_at_offset(key, byte_offset, bit_offset, bit_width)
```

### Array iteration
```python
iter_dwords(key)                            # generator: (index, dword_value)
iter_struct_array(key, struct_size_bytes)   # generator: (index, byte_offset)
```

### Aggregation
```python
sum_bitfield_across_region(key, bit_offset, bit_width)
any_nonzero(key)
```

### Cross-region correlation
```python
get_tags_in_any(*keys)                      # union of set bits across regions
compare_tag_counts(key_a, key_b)            # {count_a, count_b, delta, match}
```

### Dump coverage
```python
is_region_in_dump(key)                      # bool — region address present in dump
get_missing_regions(*keys)                  # list of keys absent from dump
```

### Validation
```python
assert_equal(label, actual, expected)       # prints [FAIL] and sets error flag if unequal
assert_true(label, value)                   # [FAIL] if value == 0
assert_false(label, value)                  # [FAIL] if value != 0
exit_analyser()                             # prints summary; sys.exit(1) if any failure
```

---

## Adding a New Product

Create a folder under `products/` with this layout:

```
products/my_product/
    __init__.py
    config.py        ← declare MODULES list and all map key constants
    product.py       ← define run(analyzer: DumpAnalyzer) -> None
    modules/
        my_module.py ← define run(analyzer: DumpAnalyzer) -> None
```

`product.py` loads and runs each module listed in `config.MODULES` in order.
Use the existing `products/epdc/` layout as a reference.

---

## Adding a Module to an Existing Product

1. Create `products/<product>/modules/my_module.py` with a `run(analyzer)` function.
2. Add `"my_module"` to `MODULES` in `products/<product>/config.py`.

```python
# products/epdc/modules/my_module.py
from engine.api import DumpAnalyzer
from products.epdc.config import MY_KEY

def run(analyzer: DumpAnalyzer) -> None:
    print("\n=== My Module ===")
    val = analyzer.get_dword(MY_KEY)
    print(f"  value = 0x{val:08X}")
```

All map key strings must be declared as constants in `config.py` — never hardcode them in module logic.

---

## Struct Generation

`structs.py` is auto-generated from firmware headers. Do not edit manually.

```bash
# From firmware headers via struct_gen
make structs.py

# From IP-XACT
python ipxact_to_structs.py <file.xml> structs.py
```

Always analyze a dump with the `structs.py` and `*.map` from the matching firmware release.

---

## Release Artifacts

```
releases/v1.x.x/
    firmware.bin
    dump.map       ← addresses (from dump_map_gen)
    structs.py     ← struct layouts (from struct_gen or IP-XACT)
```
