"""
struct_gen.py — converts a product's C/C++ firmware struct headers into
ctypes-based Python structs, using libclang 14.

Per-product, not global: each product declares its header list in
products/<id>/<id>.py (STRUCT_HEADERS, paths relative to that file's
directory). struct_gen parses *each header as its own independent
translation unit* — never combined into one — so identical struct/union
names in unrelated headers never collide at parse time. If header B
`#include`s header A directly (the supported way to reference A's types
from B), struct_gen detects that a type came from a different file (via
libclang's own source-location tracking) and emits an import instead of a
duplicate class.

Output mirrors the header layout 1:1 under products/<id>/generated_structs/
(git-ignored — fully derived from the .h files): dword0_status_t defined in
structs/big_struct.h becomes the class `dword0_status_t` in
generated_structs/structs/big_struct.py. Names are never mangled.

Usage
-----
    python -m engine.struct_gen <product_id> [--force]

Normally reached through the public API instead of directly:
    analyzer.generate_structs("epdc")   # DumpAnalyzer method, regenerates only if stale

Requires the `libclang` package (pinned to 14.x in requirements-dev.txt) —
a codegen-time dependency only. Generated output only needs ctypes.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent  # repo root — this file lives in engine/

# Populated lazily inside _ctype_for(), once clang.cindex is importable.
# Keyed by clang.cindex.TypeKind (the *canonical*, qualifier-stripped kind),
# not by type spelling -- so macros (`REG_UINT8` -> `volatile uint8_t`) and
# `const`/`volatile` qualifiers resolve to the same ctypes mapping as the
# plain type would. Deliberately excludes plain `long`/`unsigned long`: their
# width is platform/ABI-dependent (4 bytes on Windows, 8 on 64-bit Linux),
# so silently mapping them would risk a layout mismatch. Firmware headers
# should use fixed-width types (or macros expanding to them) instead.
_TYPE_KIND_MAP = {}


def _ctype_for(clang_type) -> str:
    import clang.cindex as ci

    if not _TYPE_KIND_MAP:
        _TYPE_KIND_MAP.update({
            ci.TypeKind.UCHAR:     "c_uint8",
            ci.TypeKind.SCHAR:     "c_int8",
            ci.TypeKind.USHORT:    "c_uint16",
            ci.TypeKind.SHORT:     "c_int16",
            ci.TypeKind.UINT:      "c_uint32",
            ci.TypeKind.INT:       "c_int32",
            ci.TypeKind.ULONGLONG: "c_uint64",
            ci.TypeKind.LONGLONG:  "c_int64",
            ci.TypeKind.FLOAT:     "c_float",
            ci.TypeKind.DOUBLE:    "c_double",
            ci.TypeKind.BOOL:      "c_bool",
        })

    canonical = clang_type.get_canonical()
    ctype = _TYPE_KIND_MAP.get(canonical.kind)
    if ctype is None:
        raise TypeError(
            f"struct_gen: no ctypes mapping for C type '{clang_type.spelling}' "
            f"(canonical kind {canonical.kind}). Avoid platform-ambiguous "
            f"types like 'long'/'unsigned long' -- use stdint.h-style "
            f"fixed-width types (or macros expanding to them) instead."
        )
    return ctype


# ── AST walking ──────────────────────────────────────────────────────────────

def _named_record_ref(field_type, ci):
    """
    If field_type (or its array element type) is a typedef to a struct/union,
    returns that typedef's cursor. Otherwise returns None.
    """
    elem_type = (field_type.get_array_element_type()
                 if field_type.kind == ci.TypeKind.CONSTANTARRAY else field_type)
    decl = elem_type.get_declaration()
    if decl.kind == ci.CursorKind.TYPEDEF_DECL and elem_type.get_canonical().kind == ci.TypeKind.RECORD:
        return decl
    return None


def _referenced_named_types(record_cursor, ci) -> set:
    """Named record types referenced anywhere in record_cursor's fields,
    including inside anonymous nested structs/unions (recursively)."""
    refs = set()
    for field in record_cursor.get_children():
        if field.kind != ci.CursorKind.FIELD_DECL:
            continue
        ref_decl = _named_record_ref(field.type, ci)
        if ref_decl is not None:
            refs.add(ref_decl.spelling)
            continue
        decl = field.type.get_declaration()
        if decl.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL) and decl.is_anonymous():
            refs |= _referenced_named_types(decl, ci)
    return refs


def _emit_record(cursor, class_name: str, lines: list, ci) -> None:
    """Emits one ctypes.LittleEndian{Structure,Union} subclass for a
    STRUCT_DECL/UNION_DECL cursor."""
    base = "LittleEndianUnion" if cursor.kind == ci.CursorKind.UNION_DECL else "LittleEndianStructure"

    # Nested (anonymous) records are fully emitted as their own top-level
    # classes *before* this class's own header line -- Python needs the name
    # bound by the time this class's `_fields_` list is evaluated, and
    # building `fields` first (nested emission is a side effect of that)
    # keeps the two blocks from interleaving.
    fields, anon_nested = [], []
    for field in cursor.get_children():
        if field.kind != ci.CursorKind.FIELD_DECL:
            continue
        name = field.spelling
        ftype = field.type

        if ftype.kind == ci.TypeKind.CONSTANTARRAY:
            elem = _ctype_for(ftype.get_array_element_type())
            count = ftype.get_array_size()
            fields.append(f'("{name}", ctypes.{elem} * {count})')
            continue

        ref_decl = _named_record_ref(ftype, ci)
        if ref_decl is not None:
            # typedef'd struct/union -- either a sibling class already
            # emitted in this file, or imported from another file.
            fields.append(f'("{name}", {ref_decl.spelling})')
            continue

        decl = ftype.get_declaration()
        if decl.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL) and decl.is_anonymous():
            nested_name = f"_{class_name}_{name}"
            _emit_record(decl, nested_name, lines, ci)
            fields.append(f'("{name}", {nested_name})')
            anon_nested.append(name)
            continue

        base_ctype = _ctype_for(ftype)
        if field.is_bitfield():
            width = field.get_bitfield_width()
            fields.append(f'("{name}", ctypes.{base_ctype}, {width})')
        else:
            fields.append(f'("{name}", ctypes.{base_ctype})')

    lines.append(f"class {class_name}(ctypes.{base}):")
    lines.append("    _pack_ = 1")
    lines.append("    _fields_ = [")
    for f in fields:
        lines.append(f"        {f},")
    lines.append("    ]")
    if anon_nested:
        lines.append(f"    _anonymous_ = {tuple(anon_nested)!r}")
    lines.append("")


def _parse_header(header_path: Path):
    import clang.cindex as ci

    index = ci.Index.create()
    tu = index.parse(str(header_path), args=["-x", "c", "-std=c11"])
    errors = [d for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
    if errors:
        raise SyntaxError(
            f"struct_gen: failed to parse {header_path}:\n" +
            "\n".join(f"  {d.spelling} ({d.location})" for d in errors)
        )
    return tu, ci


def _top_level_records(tu, ci):
    """Yields (name, cursor, origin_file) for every named struct/union
    definition reachable from this translation unit -- including ones
    pulled in transitively via #include -- in source order."""
    seen = set()
    for cursor in tu.cursor.get_children():
        decl, name = None, None
        if cursor.kind == ci.CursorKind.TYPEDEF_DECL:
            underlying_decl = cursor.underlying_typedef_type.get_declaration()
            if underlying_decl.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL) \
                    and underlying_decl.is_definition():
                decl, name = underlying_decl, cursor.spelling
        elif cursor.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL) \
                and cursor.is_definition() and cursor.spelling and not cursor.is_anonymous():
            decl, name = cursor, cursor.spelling

        if decl is None or name in seen or cursor.location.file is None:
            continue
        seen.add(name)
        yield name, decl, Path(cursor.location.file.name).resolve()


# ── Per-product generation ───────────────────────────────────────────────────

def _load_manifest(product_id: str, root: Path):
    product_dir = (root / "products" / product_id).resolve()
    manifest_path = product_dir / f"{product_id}.py"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"struct_gen: no manifest at {manifest_path} "
            f"(expected products/{product_id}/{product_id}.py with STRUCT_HEADERS)"
        )
    spec = importlib.util.spec_from_file_location(f"_struct_gen_manifest_{product_id}", manifest_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    headers = [(product_dir / h).resolve() for h in module.STRUCT_HEADERS]
    return product_dir, manifest_path, headers


def _module_dotted(product_id: str, product_dir: Path, header_path: Path) -> str:
    rel = header_path.relative_to(product_dir).with_suffix("")
    return ".".join(["products", product_id, "generated_structs", *rel.parts])


def _topo_sort_headers(headers: list, cross_refs: dict) -> list:
    """cross_refs: {header_path: set(header_paths it references types from)}."""
    remaining = {h: set(cross_refs.get(h, ())) for h in headers}
    order = []
    while remaining:
        ready = sorted((h for h, deps in remaining.items() if not deps),
                        key=lambda h: headers.index(h))
        if not ready:
            cyc = ", ".join(h.name for h in remaining)
            raise ValueError(f"struct_gen: circular header dependency among: {cyc}")
        for h in ready:
            order.append(h)
            del remaining[h]
        for deps in remaining.values():
            deps -= set(ready)
    return order


def _ensure_package_dirs(output_dir: Path, rel_py_path: Path) -> None:
    for part in (output_dir, *[output_dir / p for p in _accumulate(rel_py_path.parent.parts)]):
        part.mkdir(parents=True, exist_ok=True)
        init = part / "__init__.py"
        if not init.exists():
            init.write_text("# auto-generated package marker\n", encoding="utf-8")


def _accumulate(parts):
    acc = Path()
    for p in parts:
        acc = acc / p
        yield acc


def generate_for_product(product_id: str, root: Path = ROOT, force: bool = False) -> None:
    """
    Regenerates products/<id>/generated_structs/ from the headers listed in
    products/<id>/<id>.py (STRUCT_HEADERS), unless already up to date.
    A no-op for products that don't declare a products/<id>/<id>.py manifest
    -- not every product needs generated structs. Never raises if libclang
    isn't installed and output already exists -- just warns and leaves the
    existing generated output as-is.
    """
    try:
        product_dir, manifest_path, headers = _load_manifest(product_id, root)
    except FileNotFoundError:
        return

    output_dir = product_dir / "generated_structs"
    marker = output_dir / ".generated_marker"

    search_dirs = {h.parent for h in headers}
    watched = [manifest_path, *headers]
    for d in search_dirs:
        watched.extend(d.glob("*.h"))
    latest_source = max((f.stat().st_mtime for f in watched if f.exists()), default=0)

    if not force and marker.exists() and marker.stat().st_mtime >= latest_source:
        return  # up to date

    try:
        _generate_for_product(product_id, product_dir, headers, output_dir)
    except ImportError:
        if output_dir.exists() and any(output_dir.rglob("*.py")):
            print(f"[WARN] struct_gen: headers changed for product '{product_id}' but libclang "
                  f"isn't installed -- keeping existing generated_structs/ as-is. "
                  f"Run `pip install -r requirements-dev.txt` to regenerate.")
        else:
            raise
    else:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("", encoding="utf-8")


def _generate_for_product(product_id: str, product_dir: Path, headers: list, output_dir: Path) -> None:
    headers_set = set(headers)
    per_header = {}  # header_path -> list[(name, decl)] defined directly in that header
    cross_refs = {}  # header_path -> set(header_paths whose types it references)
    ci_mod = None

    for header in headers:
        tu, ci = _parse_header(header)
        ci_mod = ci

        records = list(_top_level_records(tu, ci))
        name_to_origin = {name: origin_file for name, _, origin_file in records}
        own_records = [(name, decl) for name, decl, origin_file in records if origin_file == header]

        refs_here = set()
        for name, decl in own_records:
            for ref_name in _referenced_named_types(decl, ci):
                ref_file = name_to_origin.get(ref_name)
                if ref_file is None or ref_file not in headers_set:
                    raise ValueError(
                        f"struct_gen: '{name}' in {header.name} references type '{ref_name}' "
                        f"whose header isn't listed in this product's STRUCT_HEADERS"
                    )
                if ref_file != header:
                    refs_here.add(ref_file)

        per_header[header] = own_records
        cross_refs[header] = refs_here

    order = _topo_sort_headers(headers, cross_refs)

    for header in order:
        rel_py = header.relative_to(product_dir).with_suffix(".py")
        out_path = output_dir / rel_py
        _ensure_package_dirs(output_dir, rel_py)

        lines = [
            "# AUTO-GENERATED — DO NOT EDIT MANUALLY",
            f"# Generated by struct_gen.py from {header.relative_to(product_dir).as_posix()}",
            "#",
            f"# To regenerate: python struct_gen.py {product_id}",
            "#",
            "# _pack_ = 1 on every class — layout must match the raw firmware",
            "# struct byte-for-byte, so no compiler alignment padding is applied.",
            "",
            "import ctypes",
        ]

        needed_imports = {}  # ref_header -> set(names)
        for name, decl in per_header[header]:
            for ref_name in _referenced_named_types(decl, ci_mod):
                for ref_header in headers:
                    if ref_header == header:
                        continue
                    if any(n == ref_name for n, _ in per_header.get(ref_header, [])):
                        needed_imports.setdefault(ref_header, set()).add(ref_name)

        for ref_header in sorted(needed_imports, key=lambda h: str(h)):
            dotted = _module_dotted(product_id, product_dir, ref_header)
            names = ", ".join(sorted(needed_imports[ref_header]))
            lines.append(f"from {dotted} import {names}")
        lines.append("")

        for name, decl in per_header[header]:
            _emit_record(decl, name, lines, ci_mod)

        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[struct_gen] Wrote {out_path.relative_to(product_dir.parent.parent)} "
              f"({len(per_header[header])} type(s))")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m engine.struct_gen <product_id> [--force]")
        sys.exit(1)
    generate_for_product(sys.argv[1], force="--force" in sys.argv[2:])
