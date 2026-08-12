# Auto Debugger — Memory Dump Analysis Framework

A Python framework for analyzing firmware memory dumps.
The C++ firmware source is always the single source of truth for addresses,
sizes, and struct layouts — this tool only reads and interprets.

---

## File Structure

```
auto_debugger/
├── main.py                      ← entry point
├── analyzers.py                 ← standalone analyzer functions
├── engine/
│   ├── models.py                ← Region, Chunk, MemoryView (sparse bytearray)
│   ├── api.py                   ← DumpAnalyzer public API
│   ├── loader.py                ← map / dump file loaders (read-only enforced)
│   ├── struct_gen.py            ← libclang-14 header -> ctypes struct generator
│   └── repl.py                  ← interactive GDB-style debug REPL
├── products/
│   ├── <product_id>/
│   │   ├── config.py            ← map key constants + MODULES list
│   │   ├── <product_id>.py      ← STRUCT_HEADERS list (see "Struct Generation")
│   │   ├── product.py           ← product entry point: run(analyzer)
│   │   ├── structs/             ← *.h firmware struct headers (source of truth)
│   │   ├── generated_structs/   ← struct_gen.py output (git-ignored, regenerated)
│   │   └── modules/
│   │       └── <module>.py      ← per-IP analyzer: run(analyzer)
│   └── test_suite/               ← product that smoke-tests the DumpAnalyzer API
│       ├── gen_fixtures.py       ← regenerates sample_dumps/ deterministically
│       └── sample_dumps/         ← one folder per test scenario
├── tests/                        ← pytest suite (see "Testing" below)
└── .github/workflows/tests.yml   ← CI: runs pytest on push/PR to main
```

---

## Quick Start

### Automated analysis
```bash
python main.py <dump_folder> <product_id> [controller_name]
```

### Interactive REPL session
```bash
python main.py <dump_folder> <product_id> [controller_name] --repl
```

`dump_folder` must contain one `*.map` file and one or more `*.dump` files.

`controller_name` is optional (currently — it will become required in a
future release) and selects which controller-specific struct manifest
`product.py` generates from, for products with more than one controller
(e.g. `epdc`'s `controller1.py` / `controller2.py`, each with its own
`STRUCT_HEADERS`). Omit it to fall back to the product-wide manifest
(`products/<id>/<id>.py`), or for products with no controllers at all.

Example:
```bash
python main.py ./dumps/run1 epdc
python main.py ./dumps/run1 epdc controller1
python main.py ./dumps/run1 epdc controller1 --repl
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

### Struct generation
```python
generate_structs(product_id, controller_name=None, force=False)   # regenerate generated_structs/ (see below)
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
    product.py       ← define run(analyzer: DumpAnalyzer, controller_name: str = None) -> None
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

`engine/struct_gen.py` converts a product's C/C++ firmware struct headers
into ctypes-based Python structs using libclang 14. Generation is per-product:

```
products/<id>/
    <id>.py             ← fallback manifest: STRUCT_HEADERS = ["structs/a.h", ...]
    <controller>.py     ← per-controller manifest (e.g. controller1.py, controller2.py)
    structs/            ← *.h headers — the source of truth, edit these
    generated_structs/  ← struct_gen.py output — git-ignored, do not edit
```

Reached through the public API, not called directly:
```python
analyzer.generate_structs(product_id)                                # fallback <id>.py manifest
analyzer.generate_structs(product_id, controller_name="controller1")  # that controller's manifest
analyzer.generate_structs(product_id, "controller1", force=True)      # regenerate unconditionally
```

It also runs automatically (as a no-op if nothing's stale) from both
`main.py` (which passes through its own optional `controller_name` CLI arg)
and `products/<id>/product.py`, so a fresh checkout regenerates on first run
without any manual step. A no-op if the resolved manifest
(`<controller_name>.py`, or `<id>.py` when no controller is given) doesn't
exist for that product.

For scripting/CI, the same thing is available as a CLI:
```bash
python -m engine.struct_gen <product_id> [controller_name]            # regenerate if headers changed
python -m engine.struct_gen <product_id> [controller_name] --force     # regenerate unconditionally
```

Key properties:
- **Output mirrors input 1:1** — `structs/a.h` → `generated_structs/structs/a.py`.
  Class and field names are copied verbatim from the C names; no mangling.
- **Each header is parsed independently** (never combined into one
  translation unit), so identical struct/union names in unrelated headers
  never collide. If header B needs a type from header A, `#include "a.h"`
  directly in B — struct_gen detects the type actually originates in A (via
  source location) and emits `from ...a import TypeName` instead of a
  duplicate class.
- **Header dependencies are topologically sorted** before generation, from
  the cross-file references above — you don't need to list headers in any
  particular order in `STRUCT_HEADERS`.
- **Type mapping is by canonical type kind, not spelling** — register-access
  macros (`#define REG_UINT8 volatile uint8_t`) and `const`/`volatile`
  qualifiers resolve to the same ctypes mapping as the plain type would.
  Platform-ambiguous types (`long`, `unsigned long`) are deliberately
  unsupported — use fixed-width types (or macros expanding to them).
- **`_pack_ = 1`** on every generated class — layout must match the raw
  firmware struct byte-for-byte, so no compiler alignment padding applies.
- **Bitfield allocation order is compiler-ABI-defined** (MSVC vs
  Itanium/GCC/Clang pack bits in opposite directions) — struct_gen must run
  against the same target ABI the firmware was compiled with, or bitfield
  values will read back wrong even though total struct size still matches.

Once generated, cast any address to a struct with `from_address`:
```python
from products.epdc.generated_structs.structs.big_struct import BigStruct64
s = BigStruct64.from_address(addr)   # live, zero-copy view onto that memory
```

---

## Release Artifacts

```
releases/v1.x.x/
    firmware.bin
    dump.map              ← addresses (from dump_map_gen)
    generated_structs/    ← struct layouts (from struct_gen, per product)
```

---

## Testing

The project has a `pytest` suite under `tests/`, covering `engine/` (models,
loader, `DumpAnalyzer`), the `epdc` product, and the `test_suite` product
itself. It runs locally and in GitHub Actions (`.github/workflows/tests.yml`)
on every push/PR to `main`, against Python 3.11–3.13.

### Running locally
```bash
pip install -r requirements-dev.txt
python -m pytest                                   # run everything
python -m pytest --cov --cov-report=term-missing    # with coverage
python -m pytest tests/test_api.py -v               # a single file
```

### `products/test_suite/` — the test-suite product

`test_suite` is a real product (same shape as `epdc`): `config.py` +
`product.py` + five modules:
- `api_smoke_test.py` — exercises the `DumpAnalyzer` API broadly
- `tag_consistency_check.py` — FCC-counter-sum vs occupied-tag-count, and
  pending-tags-are-a-subset-of-occupied
- `mirror_consistency_check.py` — a "primary" dword must equal its "shadow"
  dword (redundant/backup register pairs)
- `sum_check.py` — sum of a region's dwords must equal a separate stored
  "total" dword (a running-total register next to raw data)
- `reserved_region_check.py` — reserved/unused memory must stay all-zero

It can be run standalone like any other product:
```bash
python main.py products/test_suite/sample_dumps/scenario_01_baseline_no_errors test_suite
```

Its fixtures live in `products/test_suite/sample_dumps/` (regenerate
deterministically via `python -m products.test_suite.gen_fixtures`):

**`scenario_*/`** — 7 folders sharing one identical `memory.map` (defined
once in `fixture_schema.py`): 50 keys, sizes 1–1024 bytes, packed into 5
non-contiguous 8 KiB memory blocks (5 `*.dump` files per folder, one per
block — exercising the loader's multi-file merge and the sparse chunk model
in the same fixture). Like a real firmware dump, the memory is almost
entirely zero — only ~1.5% of each block holds live data; the rest is
reserved/unused space. `scenario_01` is the "no errors" baseline; every
other scenario is a byte-for-byte copy of it with exactly one value changed
at one key's address, so it introduces exactly one detectable error:

| Scenario | What differs from the baseline |
|---|---|
| `scenario_01_baseline_no_errors` | Nothing — everything passes |
| `scenario_02_fcc_counter_value_error` | One FCC counter cleared → counter sum ≠ occupied-tag count |
| `scenario_03_occupied_tag_count_error` | One extra tag marked occupied → occupied-tag count ≠ counter sum |
| `scenario_04_pending_tag_leak` | One tag marked pending that was never occupied → pending ⊄ occupied |
| `scenario_05_mirror_mismatch` | One shadow register byte flipped → no longer equals its primary |
| `scenario_06_sum_check_mismatch` | One region dword bumped without updating the total → sum ≠ stored total |
| `scenario_07_reserved_region_set` | One bit set in memory that must always read zero |

Narrow engine-level behaviors that don't fit the identical-map layout
(malformed map/dump lines, a zero-byte region, an out-of-bounds region,
missing dump coverage for a declared key) are covered directly in
`tests/test_loader.py` and `tests/test_api.py` via `tmp_path`-generated
files/synthetic objects rather than committed fixtures.

### Adding tests for new code

- **New API method / product / module**: add tests exercising it in the
  matching `tests/test_*.py` file (`test_api.py` for `DumpAnalyzer`,
  `test_products_<product>.py` for a product). If it needs a specific dump
  shape not covered by an existing fixture, add a scenario to
  `gen_fixtures.py` (or a product's own sample dumps) rather than hand-editing
  `.map`/`.dump` files.
- **Any bug found**: add a regression test that fails on the old behavior and
  passes once fixed — in `tests/test_regression.py`, or alongside the related
  tests in the relevant `test_*.py` file with a comment cross-referencing it
  from `test_regression.py`. See that file for the current example (the
  `DebugREPL` constructor arg-count bug).
