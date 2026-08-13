"""
Tests for engine/struct_gen.py -- the libclang-based C++ struct -> ctypes
generator. Each test builds a tiny throwaway product (manifest + header(s))
under tmp_path and runs the real generator against it, then imports the
generated module and inspects/instantiates the resulting ctypes classes.

Headers define their own fixed-width typedefs (like products/epdc's
reg_macros.h does) instead of `#include <stdint.h>` -- libclang's bundled
index has no guaranteed system include path in this environment.
"""

import ctypes
import importlib
import importlib.util
import sys

import pytest

from engine import struct_gen

pytest.importorskip("clang.cindex")

_STDINT = """
    typedef unsigned char      uint8_t;
    typedef signed char        int8_t;
    typedef unsigned short     uint16_t;
    typedef signed short       int16_t;
    typedef unsigned int       uint32_t;
    typedef signed int         int32_t;
    typedef unsigned long long uint64_t;
    typedef signed long long   int64_t;
"""


def _build_product(tmp_path, product_id: str, headers: dict, include_paths=None):
    """
    Writes tmp_path/products/<product_id>/<product_id>.py (manifest) plus
    tmp_path/products/<product_id>/structs/<name> for each (name, content) in
    headers, then runs struct_gen against it. Returns the product dir.
    """
    product_dir = tmp_path / "products" / product_id
    structs_dir = product_dir / "structs"
    structs_dir.mkdir(parents=True)

    for name, content in headers.items():
        (structs_dir / name).write_text(content, encoding="utf-8")

    manifest_lines = [
        f'STRUCT_HEADERS = {[f"structs/{n}" for n in headers]!r}',
    ]
    if include_paths:
        manifest_lines.append(f"INCLUDE_PATHS = {include_paths!r}")
    (product_dir / f"{product_id}.py").write_text("\n".join(manifest_lines), encoding="utf-8")

    struct_gen.generate_for_product(product_id, root=tmp_path, force=True)
    return product_dir


def _load_generated(product_dir, stem: str):
    """Imports generated_structs/<stem>.py directly off disk (no cross-file
    import resolution -- fine for single-header tests)."""
    path = product_dir / "generated_structs" / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"_test_struct_gen_{stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_generated_with_cross_refs(tmp_path, product_id: str, stem: str):
    """Imports generated_structs/<stem>.py via its real dotted path
    (products.<id>.generated_structs.<stem>) so `from products.X... import Y`
    cross-file references resolve. Cleans up sys.path/sys.modules after."""
    products_init = tmp_path / "products" / "__init__.py"
    if not products_init.exists():
        products_init.write_text("", encoding="utf-8")
    product_init = tmp_path / "products" / product_id / "__init__.py"
    if not product_init.exists():
        product_init.write_text("", encoding="utf-8")

    sys.path.insert(0, str(tmp_path))
    dotted = f"products.{product_id}.generated_structs.{stem}"
    try:
        for mod_name in list(sys.modules):
            if mod_name == "products" or mod_name.startswith(f"products.{product_id}"):
                del sys.modules[mod_name]
        return importlib.import_module(dotted)
    finally:
        sys.path.remove(str(tmp_path))


# ── CONSTANTARRAY of struct/union elements (bug: previously called
#    _ctype_for directly, which has no mapping for record types) ────────────

def test_array_of_anonymous_struct_elements(tmp_path):
    header = _STDINT + """
        #pragma pack(push, 1)
        struct Container {
            struct { uint8_t x; uint8_t y; } points[3];
        };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "arrstruct", {"h.h": header})
    mod = _load_generated(product_dir, "h")

    assert ctypes.sizeof(mod.Container) == 6
    inst = mod.Container()
    inst.points[1].x = 5
    inst.points[1].y = 9
    assert inst.points[1].x == 5
    assert inst.points[1].y == 9


def test_array_of_anonymous_union_elements(tmp_path):
    header = _STDINT + """
        #pragma pack(push, 1)
        struct Container {
            union { uint32_t raw; uint8_t bytes[4]; } slots[2];
        };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "arrunion", {"h.h": header})
    mod = _load_generated(product_dir, "h")

    inst = mod.Container()
    inst.slots[0].raw = 0x01020304
    assert inst.slots[0].bytes[0] == 0x04  # little-endian
    assert ctypes.sizeof(mod.Container) == 8


def test_array_of_named_typedef_struct_elements(tmp_path):
    header = _STDINT + """
        #pragma pack(push, 1)
        typedef struct { uint16_t x; uint16_t y; } Point16;
        struct Container {
            Point16 pts[4];
        };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "arrtypedef", {"h.h": header})
    mod = _load_generated(product_dir, "h")

    assert ctypes.sizeof(mod.Container) == 16
    inst = mod.Container()
    inst.pts[2].x = 42
    assert inst.pts[2].x == 42


def test_array_of_named_tag_struct_elements(tmp_path):
    # C++-only form: `struct Point16 arr[N];` referring directly to the
    # tag name, no typedef needed.
    header = _STDINT + """
        #pragma pack(push, 1)
        struct Point16 { uint16_t x; uint16_t y; };
        struct Container {
            struct Point16 pts[2];
        };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "arrtag", {"h.h": header})
    mod = _load_generated(product_dir, "h")
    assert ctypes.sizeof(mod.Container) == 8


def test_array_of_plain_scalar_still_works(tmp_path):
    header = _STDINT + """
        #pragma pack(push, 1)
        struct Container { uint8_t bytes[4]; };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "arrscalar", {"h.h": header})
    mod = _load_generated(product_dir, "h")
    assert ctypes.sizeof(mod.Container) == 4


# ── LittleEndianUnion py<3.11 compatibility shim ─────────────────────────────

def test_generated_union_falls_back_when_ctypes_lacks_little_endian_union(tmp_path, monkeypatch):
    header = _STDINT + """
        #pragma pack(push, 1)
        union U { uint32_t raw; uint8_t bytes[4]; };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "unioncompat", {"h.h": header})

    monkeypatch.delattr(ctypes, "LittleEndianUnion", raising=False)
    mod = _load_generated(product_dir, "h")

    inst = mod.U(raw=0x0A0B0C0D)
    assert inst.bytes[0] == 0x0D  # little-endian byte order preserved


def test_generated_union_uses_real_little_endian_union_when_available(tmp_path):
    header = _STDINT + """
        #pragma pack(push, 1)
        union U { uint32_t raw; uint8_t bytes[4]; };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "unionreal", {"h.h": header})
    mod = _load_generated(product_dir, "h")

    if hasattr(ctypes, "LittleEndianUnion"):
        assert issubclass(mod.U, ctypes.LittleEndianUnion)


def test_generated_struct_and_union_are_correctly_packed(tmp_path):
    header = _STDINT + """
        #pragma pack(push, 1)
        struct S { uint8_t a; uint32_t b; };
        union U { uint32_t raw; uint8_t bytes[4]; };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "packcheck", {"h.h": header})
    mod = _load_generated(product_dir, "h")
    assert ctypes.sizeof(mod.S) == 5  # packed, no padding
    assert ctypes.sizeof(mod.U) == 4


# ── Bitfields, anonymous-member promotion, naming ────────────────────────────

def test_bitfield_widths_preserved(tmp_path):
    header = _STDINT + """
        #pragma pack(push, 1)
        struct Flags {
            uint32_t a : 1;
            uint32_t b : 3;
            uint32_t c : 28;
        };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "bitfields", {"h.h": header})
    mod = _load_generated(product_dir, "h")
    inst = mod.Flags()
    inst.b = 5
    assert inst.b == 5
    assert inst.a == 0 and inst.c == 0


def test_true_anonymous_union_member_promotes_fields(tmp_path):
    header = _STDINT + """
        #pragma pack(push, 1)
        struct Outer {
            union { uint32_t raw; uint8_t bytes[4]; };
        };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "anonpromote", {"h.h": header})
    mod = _load_generated(product_dir, "h")
    inst = mod.Outer()
    inst.raw = 0x11223344  # accessible directly on Outer, not via a sub-name
    assert inst.bytes[0] == 0x44


def test_named_anonymous_type_field_not_promoted(tmp_path):
    # `struct {...} grp1;` -- tag-less type but the field itself is named,
    # so access must stay obj.grp1.x, never promoted to obj.x.
    header = _STDINT + """
        #pragma pack(push, 1)
        struct Outer {
            struct { uint8_t x; } grp1;
        };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "notpromoted", {"h.h": header})
    mod = _load_generated(product_dir, "h")
    inst = mod.Outer()
    inst.grp1.x = 7
    assert inst.grp1.x == 7
    assert not hasattr(inst, "x")


# ── Cross-file references ────────────────────────────────────────────────────

def test_cross_file_struct_reference_emits_import(tmp_path):
    header_a = _STDINT + """
        #pragma pack(push, 1)
        struct Point16 { uint16_t x; uint16_t y; };
        #pragma pack(pop)
    """
    header_b = """
        #include "a.h"
        #pragma pack(push, 1)
        struct Rect { Point16 origin; Point16 size; };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "crossref", {"a.h": header_a, "b.h": header_b})
    b_src = (product_dir / "generated_structs" / "b.py").read_text()
    assert "from products.crossref.generated_structs.a import Point16" in b_src

    mod_b = _load_generated_with_cross_refs(tmp_path, "crossref", "b")
    assert ctypes.sizeof(mod_b.Rect) == 8


def test_unresolvable_cross_header_reference_raises(tmp_path):
    header_a = _STDINT + """
        #pragma pack(push, 1)
        struct NotListed { uint8_t x; };
        #pragma pack(pop)
    """
    header_b = """
        #include "a.h"
        #pragma pack(push, 1)
        struct Uses { NotListed inner; };
        #pragma pack(pop)
    """
    product_dir = tmp_path / "products" / "badref"
    structs_dir = product_dir / "structs"
    structs_dir.mkdir(parents=True)
    (structs_dir / "a.h").write_text(header_a, encoding="utf-8")
    (structs_dir / "b.h").write_text(header_b, encoding="utf-8")
    # Only b.h listed -- a.h (where NotListed lives) is missing from STRUCT_HEADERS.
    (product_dir / "badref.py").write_text('STRUCT_HEADERS = ["structs/b.h"]', encoding="utf-8")

    with pytest.raises(ValueError, match="STRUCT_HEADERS"):
        struct_gen.generate_for_product("badref", root=tmp_path, force=True)


# ── Error paths ───────────────────────────────────────────────────────────────

def test_platform_ambiguous_long_type_raises_typeerror(tmp_path):
    header = """
        #pragma pack(push, 1)
        struct S { long value; };
        #pragma pack(pop)
    """
    with pytest.raises(TypeError, match="no ctypes mapping"):
        _build_product(tmp_path, "longtype", {"h.h": header})


def test_duplicate_header_stems_raises(tmp_path):
    product_dir = tmp_path / "products" / "dupstem"
    (product_dir / "structs" / "sub1").mkdir(parents=True)
    (product_dir / "structs" / "sub2").mkdir(parents=True)
    (product_dir / "structs" / "sub1" / "h.h").write_text(
        _STDINT + "#pragma pack(push,1)\nstruct A { uint8_t x; };\n#pragma pack(pop)\n")
    (product_dir / "structs" / "sub2" / "h.h").write_text(
        _STDINT + "#pragma pack(push,1)\nstruct B { uint8_t x; };\n#pragma pack(pop)\n")
    (product_dir / "dupstem.py").write_text(
        'STRUCT_HEADERS = ["structs/sub1/h.h", "structs/sub2/h.h"]', encoding="utf-8")

    with pytest.raises(ValueError, match="same filename stem"):
        struct_gen.generate_for_product("dupstem", root=tmp_path, force=True)


def test_missing_manifest_is_a_noop(tmp_path):
    # No products/<id>/<id>.py at all -- generate_for_product must not raise.
    struct_gen.generate_for_product("does_not_exist", root=tmp_path, force=True)


def test_header_outside_product_dir_via_relative_manifest_path(tmp_path):
    # A controller manifest may reference a header via a "../"-style path
    # that resolves outside products/<id>/ (e.g. a header shared across
    # controllers/products) -- generation must not crash writing the output
    # file's header comment just because the source header isn't a subpath
    # of product_dir.
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    (shared_dir / "common.h").write_text(
        _STDINT + "#pragma pack(push,1)\nstruct Common { uint8_t x; };\n#pragma pack(pop)\n",
        encoding="utf-8")

    product_dir = tmp_path / "products" / "outsideref"
    product_dir.mkdir(parents=True)
    (product_dir / "controller1.py").write_text(
        'STRUCT_HEADERS = ["../../shared/common.h"]', encoding="utf-8")

    struct_gen.generate_for_product("outsideref", "controller1", root=tmp_path, force=True)

    out_path = product_dir / "generated_structs" / "common.py"
    assert "../../shared/common.h" in out_path.read_text()
    mod = _load_generated(product_dir, "common")
    assert ctypes.sizeof(mod.Common) == 1


def test_syntax_error_in_header_raises(tmp_path):
    header = "struct Broken { this is not valid c++ !!! "
    with pytest.raises(SyntaxError):
        _build_product(tmp_path, "badsyntax", {"h.h": header})


# ── Regeneration / staleness ─────────────────────────────────────────────────

def test_regeneration_skipped_when_up_to_date(tmp_path):
    header = _STDINT + """
        #pragma pack(push, 1)
        struct S { uint8_t x; };
        #pragma pack(pop)
    """
    product_dir = _build_product(tmp_path, "stale", {"h.h": header})
    out_path = product_dir / "generated_structs" / "h.py"
    first_mtime = out_path.stat().st_mtime

    # Re-run without --force and without touching sources -- must be a no-op
    # (marker is newer than sources), so mtime is untouched.
    struct_gen.generate_for_product("stale", root=tmp_path, force=False)
    assert out_path.stat().st_mtime == first_mtime
