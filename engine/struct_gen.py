"""
struct_gen.py — converts a product's C++ firmware struct headers into
ctypes-based Python structs, using libclang 14.

Per-product, not global: each product declares its header list in
products/<id>/<id>.py (STRUCT_HEADERS, paths relative to that file's
directory), and optionally an INCLUDE_PATHS list of extra directories
(also relative to that file's directory, but may point anywhere -- they
don't need to share a subpath with the product) to search for headers
pulled in via `#include` that aren't themselves in STRUCT_HEADERS (e.g.
a shared SDK header). struct_gen parses *each header as its own
independent translation unit* — never combined into one — so identical
struct/union names in unrelated headers never collide at parse time. If
header B `#include`s header A directly (the supported way to reference
A's types from B), struct_gen detects that a type came from a different
file (via libclang's own source-location tracking) and emits an import
instead of a duplicate class.

Headers are parsed as C++ (not C) — `extern "C" { ... }` linkage blocks
are unwrapped transparently, so structs/unions declared inside one are
picked up exactly as if they weren't wrapped.

Output is flat, not mirrored: every header in STRUCT_HEADERS produces one
file directly under products/<id>/generated_structs/ (git-ignored — fully
derived from the .h files), named after the header's stem regardless of
where the header lives on disk: structs/big_struct.h becomes
generated_structs/big_struct.py. Names are never mangled. Two headers
that share a stem is a configuration error (struct_gen raises rather than
letting one silently overwrite the other).

Usage
-----
    python -m engine.struct_gen <product_id> [--force]

Normally reached through the public API instead of directly:
    analyzer.generate_structs("epdc")   # DumpAnalyzer method, regenerates only if stale

Requires the `libclang` package (pinned to 14.x in requirements-dev.txt) —
a codegen-time dependency only. Generated output only needs ctypes.
"""

import importlib.util
import os
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

_RST_PREFIX = "rst"


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
    If field_type (or its array element type) refers to a named struct/union
    -- either via a typedef, or directly by the record's own tag name (valid
    in C++, unlike C: `struct DemoStatus status;` needs no typedef there) --
    returns that struct/union's own definition cursor. Otherwise returns None.
    """
    elem_type = (field_type.get_array_element_type()
                 if field_type.kind == ci.TypeKind.CONSTANTARRAY else field_type)
    decl = elem_type.get_declaration()
    if decl.kind == ci.CursorKind.TYPEDEF_DECL and elem_type.get_canonical().kind == ci.TypeKind.RECORD:
        return decl
    if decl.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL) and not decl.is_anonymous():
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


def _rst_derived_union_name(union_decl, ci):
    """
    Project naming convention for a truly-anonymous union member (no field
    name of its own -- the C/C++ "anonymous union" form): if one of its
    direct fields is a named struct/union carrying the 'rst' prefix (e.g.
    `struct {...} rstmystruct2;`), the union itself is named by stripping
    that prefix and prepending 'union' -- 'rstmystruct2' -> 'unionmystruct2'.
    Returns None if no such field exists, so the caller can fall back to a
    generated name.
    """
    for child in union_decl.get_children():
        if child.kind == ci.CursorKind.FIELD_DECL and child.spelling.startswith(_RST_PREFIX):
            return "union" + child.spelling[len(_RST_PREFIX):]
    return None


def _decl_key(decl):
    """Identity key for a declaration cursor, stable across the different
    paths libclang lets you reach the *same* underlying decl (e.g. directly
    as a child cursor vs. via a field's `.type.get_declaration()`) -- source
    location is that stable identity; `cursor ==` / `.hash` are not reliably
    consistent across those paths in libclang 14."""
    loc = decl.extent.start
    return (loc.file.name if loc.file else None, loc.offset)


def _unique_name(preferred, fallback: str, used_names: set) -> str:
    """
    Returns `preferred` if it's free (and not None); otherwise `fallback` if
    that's free; otherwise `fallback` suffixed with an incrementing counter.
    Never raises -- struct/union field names repeat across a header often
    enough (e.g. multiple dwordN_t unions each with a `bits` sub-struct)
    that failing generation over it would be worse than a slightly uglier
    but still-correct fallback name.
    """
    if preferred and preferred not in used_names:
        return preferred
    if fallback not in used_names:
        return fallback
    i = 2
    while f"{fallback}{i}" in used_names:
        i += 1
    return f"{fallback}{i}"


def _emit_record(cursor, class_name: str, lines: list, ci, used_names: set) -> None:
    """Emits one ctypes.LittleEndian{Structure,Union} subclass for a
    STRUCT_DECL/UNION_DECL cursor."""
    used_names.add(class_name)
    # LittleEndianUnion (bare name) resolves to the module-level compat
    # shim defined at the top of the generated file -- ctypes.LittleEndianUnion
    # itself doesn't exist before Python 3.11. LittleEndianStructure has been
    # in ctypes since forever, so it's referenced straight off the module.
    is_union = cursor.kind == ci.CursorKind.UNION_DECL
    base = "LittleEndianUnion" if is_union else "ctypes.LittleEndianStructure"

    # Nested (anonymous) records are fully emitted as their own top-level
    # classes *before* this class's own header line -- Python needs the name
    # bound by the time this class's `_fields_` list is evaluated, and
    # building `fields` first (nested emission is a side effect of that)
    # keeps the two blocks from interleaving.
    # libclang lists the definition of a *named* field's anonymous-tag type
    # (`struct {...} grp1;`) as its own STRUCT_DECL/UNION_DECL sibling child,
    # in addition to the FIELD_DECL 'grp1' that uses it -- same struct, two
    # cursors. Only a record with no such owning FIELD_DECL is a true C/C++
    # anonymous member (`union {...};`, no trailing name); collect the
    # "owned" ones first so the loop below can tell the two apart instead of
    # emitting the struct/union twice under different names.
    owned_decl_keys = set()
    for child in cursor.get_children():
        if child.kind == ci.CursorKind.FIELD_DECL:
            ftype = child.type
            elem_type = (ftype.get_array_element_type()
                         if ftype.kind == ci.TypeKind.CONSTANTARRAY else ftype)
            d = elem_type.get_declaration()
            if d.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL):
                owned_decl_keys.add(_decl_key(d))

    fields, anon_nested = [], []
    anon_index = 0
    for field in cursor.get_children():
        if field.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL) \
                and _decl_key(field) not in owned_decl_keys:
            # True anonymous struct/union member -- `union {...};` with no
            # trailing name. libclang surfaces these as a bare STRUCT_DECL/
            # UNION_DECL child, not wrapped in a FIELD_DECL, so they must be
            # caught here rather than in the FIELD_DECL branch below. Its
            # fields promote up to this class via ctypes' `_anonymous_`,
            # matching C/C++ anonymous-member semantics.
            decl = field
            preferred = (_rst_derived_union_name(decl, ci)
                         if decl.kind == ci.CursorKind.UNION_DECL else None)
            nested_name = _unique_name(preferred, f"_{class_name}_anon{anon_index}", used_names)
            anon_index += 1
            _emit_record(decl, nested_name, lines, ci, used_names)
            fields.append(f'("{nested_name}", {nested_name})')
            anon_nested.append(nested_name)
            continue

        if field.kind != ci.CursorKind.FIELD_DECL:
            continue
        name = field.spelling
        ftype = field.type

        if ftype.kind == ci.TypeKind.CONSTANTARRAY:
            count = ftype.get_array_size()
            elem_type = ftype.get_array_element_type()

            array_ref_decl = _named_record_ref(ftype, ci)
            if array_ref_decl is not None:
                # Array of a typedef'd or tag-named struct/union -- either a
                # sibling class already emitted in this file, or imported
                # from another file.
                fields.append(f'("{name}", {array_ref_decl.spelling} * {count})')
                continue

            elem_decl = elem_type.get_declaration()
            if elem_decl.kind in (ci.CursorKind.STRUCT_DECL, ci.CursorKind.UNION_DECL) \
                    and elem_decl.is_anonymous():
                # `struct {...} arr[N];` -- the element type has no tag, so
                # it must be emitted as its own nested class first, just like
                # the non-array anonymous-record field case below.
                nested_name = _unique_name(name, f"_{class_name}_{name}", used_names)
                _emit_record(elem_decl, nested_name, lines, ci, used_names)
                fields.append(f'("{name}", {nested_name} * {count})')
                continue

            elem = _ctype_for(elem_type)
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
            if name:
                # `struct {...} grp1;` -- the type has no tag, but the field
                # itself is named, so it is NOT a C/C++ anonymous member:
                # access stays `obj.grp1.x`, never promoted to `obj.x`.
                nested_name = _unique_name(name, f"_{class_name}_{name}", used_names)
                field_key = name
                promote = False
            else:
                # `union {...};` / `struct {...};` with no trailing name --
                # a real anonymous member; its fields promote up to this
                # class via ctypes' `_anonymous_`, matching C/C++ semantics.
                preferred = (_rst_derived_union_name(decl, ci)
                             if decl.kind == ci.CursorKind.UNION_DECL else None)
                nested_name = _unique_name(preferred, f"_{class_name}_anon{anon_index}", used_names)
                anon_index += 1
                field_key = nested_name
                promote = True

            _emit_record(decl, nested_name, lines, ci, used_names)
            fields.append(f'("{field_key}", {nested_name})')
            if promote:
                anon_nested.append(field_key)
            continue

        base_ctype = _ctype_for(ftype)
        if field.is_bitfield():
            width = field.get_bitfield_width()
            fields.append(f'("{name}", ctypes.{base_ctype}, {width})')
        else:
            fields.append(f'("{name}", ctypes.{base_ctype})')

    lines.append(f"class {class_name}({base}):")
    lines.append("    _pack_ = 1")
    lines.append("    _fields_ = [")
    for f in fields:
        lines.append(f"        {f},")
    lines.append("    ]")
    if anon_nested:
        lines.append(f"    _anonymous_ = {tuple(anon_nested)!r}")
    lines.append("")


def _parse_header(header_path: Path, include_paths: list):
    import clang.cindex as ci

    index = ci.Index.create()
    args = ["-x", "c++", "-std=c++17"] + [f"-I{p}" for p in include_paths]
    tu = index.parse(str(header_path), args=args)
    errors = [d for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
    if errors:
        raise SyntaxError(
            f"struct_gen: failed to parse {header_path}:\n" +
            "\n".join(f"  {d.spelling} ({d.location})" for d in errors)
        )
    return tu, ci


def _iter_toplevel_decls(cursor, ci):
    """Children of `cursor`, transparently descending into `extern "C" {
    ... }` linkage-spec blocks so struct/union/typedef decls inside one are
    yielded exactly as if they weren't wrapped. libclang reports these
    blocks as LINKAGE_SPEC in some versions and as an anonymous
    UNEXPOSED_DECL in others -- both are unwrapped the same way."""
    for child in cursor.get_children():
        if child.kind in (ci.CursorKind.LINKAGE_SPEC, ci.CursorKind.UNEXPOSED_DECL):
            yield from _iter_toplevel_decls(child, ci)
        else:
            yield child


def _top_level_records(tu, ci):
    """Yields (name, cursor, origin_file) for every named struct/union
    definition reachable from this translation unit -- including ones
    pulled in transitively via #include, and ones inside `extern "C"`
    blocks -- in source order."""
    seen = set()
    for cursor in _iter_toplevel_decls(tu.cursor, ci):
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

def _load_manifest(product_id: str, root: Path, controller_name: str = None):
    """
    Manifest file is products/<id>/<controller_name>.py when controller_name
    is given (one manifest per controller, e.g. "controller1", "controller2"
    for products with more than one), or products/<id>/<id>.py otherwise
    (single-controller / not-yet-migrated products).

    STRUCT_HEADERS (required) and INCLUDE_PATHS (optional, defaults to [])
    are both resolved relative to the manifest file's own directory into
    absolute paths -- INCLUDE_PATHS entries don't need to share a subpath
    with the product; they can point anywhere on disk (e.g. `../../shared_sdk`).
    """
    product_dir = (root / "products" / product_id).resolve()
    manifest_stem = controller_name or product_id
    manifest_path = product_dir / f"{manifest_stem}.py"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"struct_gen: no manifest at {manifest_path} "
            f"(expected products/{product_id}/{manifest_stem}.py with STRUCT_HEADERS)"
        )
    spec = importlib.util.spec_from_file_location(
        f"_struct_gen_manifest_{product_id}_{manifest_stem}", manifest_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    headers = [(product_dir / h).resolve() for h in module.STRUCT_HEADERS]
    include_paths = [(product_dir / p).resolve() for p in getattr(module, "INCLUDE_PATHS", [])]
    return product_dir, manifest_path, headers, include_paths


def _module_dotted(product_id: str, header_path: Path) -> str:
    return f"products.{product_id}.generated_structs.{header_path.stem}"


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


def generate_for_product(product_id: str, controller_name: str = None,
                          root: Path = ROOT, force: bool = False) -> None:
    """
    Regenerates products/<id>/generated_structs/ from the headers listed in
    that product's manifest -- products/<id>/<controller_name>.py if
    controller_name is given, else products/<id>/<id>.py -- unless already
    up to date. A no-op if that manifest doesn't exist -- not every product
    (or controller) needs generated structs. Never raises if libclang isn't
    installed and output already exists -- just warns and leaves the
    existing generated output as-is.
    """
    try:
        product_dir, manifest_path, headers, include_paths = _load_manifest(product_id, root, controller_name)
    except FileNotFoundError:
        return

    output_dir = product_dir / "generated_structs"
    marker = output_dir / f".generated_marker.{controller_name or product_id}"

    search_dirs = {h.parent for h in headers} | set(include_paths)
    watched = [manifest_path, *headers]
    for d in search_dirs:
        if d.exists():
            watched.extend(d.glob("*.h"))
    latest_source = max((f.stat().st_mtime for f in watched if f.exists()), default=0)

    if not force and marker.exists() and marker.stat().st_mtime >= latest_source:
        return  # up to date

    try:
        _generate_for_product(product_id, product_dir, headers, include_paths, output_dir)
    except ImportError:
        if output_dir.exists() and any(output_dir.glob("*.py")):
            print(f"[WARN] struct_gen: headers changed for product '{product_id}' but libclang "
                  f"isn't installed -- keeping existing generated_structs/ as-is. "
                  f"Run `pip install -r requirements-dev.txt` to regenerate.")
        else:
            raise
    else:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("", encoding="utf-8")


def _generate_for_product(product_id: str, product_dir: Path, headers: list,
                           include_paths: list, output_dir: Path) -> None:
    stems = {}
    for h in headers:
        stems.setdefault(h.stem, []).append(h)
    collisions = {stem: hs for stem, hs in stems.items() if len(hs) > 1}
    if collisions:
        detail = "; ".join(f"{stem}: {[str(h) for h in hs]}" for stem, hs in collisions.items())
        raise ValueError(
            f"struct_gen: STRUCT_HEADERS has headers with the same filename stem -- "
            f"output is flat (one .py per stem) under generated_structs/, so stems "
            f"must be unique: {detail}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    init_path = output_dir / "__init__.py"
    if not init_path.exists():
        init_path.write_text("# auto-generated package marker\n", encoding="utf-8")

    headers_set = set(headers)
    per_header = {}  # header_path -> list[(name, decl)] defined directly in that header
    cross_refs = {}  # header_path -> set(header_paths whose types it references)
    ci_mod = None

    for header in headers:
        tu, ci = _parse_header(header, include_paths)
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
        out_path = output_dir / f"{header.stem}.py"

        lines = [
            "# AUTO-GENERATED — DO NOT EDIT MANUALLY",
            # Header may live outside product_dir (e.g. a shared header
            # reached via a "../"-style STRUCT_HEADERS/INCLUDE_PATHS entry --
            # see the module docstring), so relative_to() (which requires
            # header to be a true subpath of product_dir) isn't safe here.
            # os.path.relpath handles both cases, walking ".." as needed.
            f"# Generated by struct_gen.py from "
            f"{Path(os.path.relpath(header, product_dir)).as_posix()}",
            "#",
            f"# To regenerate: python struct_gen.py {product_id}",
            "#",
            "# _pack_ = 1 on every class — layout must match the raw firmware",
            "# struct byte-for-byte, so no compiler alignment padding is applied.",
            "",
            "import ctypes",
            "import sys",
            "",
            "if hasattr(ctypes, \"LittleEndianUnion\"):",
            "    LittleEndianUnion = ctypes.LittleEndianUnion",
            "elif sys.byteorder == \"little\":",
            "    # ctypes.LittleEndianUnion was only added in Python 3.11 (bpo-46913).",
            "    # On a little-endian host a plain ctypes.Union is already byte-order",
            "    # identical to LittleEndianUnion -- the same reasoning ctypes itself",
            "    # uses to alias LittleEndianStructure = Structure in that case (see",
            "    # ctypes/_endian.py).",
            "    LittleEndianUnion = ctypes.Union",
            "else:",
            "    raise RuntimeError(",
            "        \"ctypes.LittleEndianUnion is unavailable (needs Python 3.11+) and \"",
            "        \"this host is big-endian, so a plain ctypes.Union isn't a safe substitute.\"",
            "    )",
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
            dotted = _module_dotted(product_id, ref_header)
            names = ", ".join(sorted(needed_imports[ref_header]))
            lines.append(f"from {dotted} import {names}")
        lines.append("")

        used_names = set()
        for name, decl in per_header[header]:
            _emit_record(decl, name, lines, ci_mod, used_names)

        out_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[struct_gen] Wrote {out_path.relative_to(product_dir.parent.parent)} "
              f"({len(per_header[header])} type(s))")


if __name__ == "__main__":
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(positional) < 1:
        print("Usage: python -m engine.struct_gen <product_id> [controller_name] [--force]")
        sys.exit(1)
    cli_product_id = positional[0]
    cli_controller_name = positional[1] if len(positional) > 1 else None
    generate_for_product(cli_product_id, cli_controller_name, force="--force" in sys.argv[1:])
