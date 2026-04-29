import re
import readline
from api import DumpAnalyzer

# ── Prompt ─────────────────────────────────────────────────────────────────────
PROMPT = "(dbg) "

# ── Patterns ───────────────────────────────────────────────────────────────────
RE_KEY        = re.compile(r'^(\w+::\w+)$')
RE_KEY_FIELD  = re.compile(r'^(\w+::\w+)\.(\w+)$')
RE_RAW_FMT    = re.compile(r'^x/(\d+)x[wW]\s+(0x[0-9a-fA-F]+)$')
RE_RAW_SIMPLE = re.compile(r'^x\s+(0x[0-9a-fA-F]+)$')


class DebugREPL:

    def __init__(self, analyzer: DumpAnalyzer, structs: dict, analyzers: dict):
        """
        analyzer  — DumpAnalyzer instance
        structs   — { "TagManager::sfr_base": TagManagerSfr, ... }
                    ctypes struct classes keyed by region name
        analyzers — { "analyze_occupied_tags": fn, ... }
        """
        self._a       = analyzer
        self._structs = structs
        self._fns     = analyzers
        self._setup_completion()

    def _setup_completion(self):
        """Tab-completes region keys."""
        keys = list(self._a.regions.keys())
        def completer(text, state):
            matches = [k for k in keys if k.startswith(text)]
            return matches[state] if state < len(matches) else None
        readline.set_completer(completer)
        readline.parse_and_bind("tab: complete")

    # ── Session ────────────────────────────────────────────────────────────────

    def run(self):
        print("\nMemory Dump Debug Session  —  type 'help' for commands\n")
        while True:
            try:
                raw = input(PROMPT).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not raw:
                continue
            if raw in ("quit", "exit", "q"):
                break
            self._dispatch(raw)

    # ── Dispatcher ─────────────────────────────────────────────────────────────

    def _dispatch(self, raw: str):
        try:
            # TagManager::occupied_tags.field_name
            m = RE_KEY_FIELD.match(raw)
            if m:
                self._print_field(m.group(1), m.group(2))
                return

            # TagManager::occupied_tags
            m = RE_KEY.match(raw)
            if m:
                self._print_region(m.group(1))
                return

            # x/4xw 0xA0001000
            m = RE_RAW_FMT.match(raw)
            if m:
                self._print_raw(int(m.group(2), 16), count=int(m.group(1)))
                return

            # x 0xA0001000
            m = RE_RAW_SIMPLE.match(raw)
            if m:
                self._print_raw(int(m.group(1), 16), count=4)
                return

            parts = raw.split()
            cmd, args = parts[0].lower(), parts[1:]
            if   cmd == "help": self._help()
            elif cmd == "list": self._list()
            elif cmd == "run":  self._run(args)
            else:
                print(f"  Unknown: '{raw}'  —  type 'help'")

        except KeyError as e:
            print(f"  error: {e}")
        except ValueError as e:
            print(f"  error: {e}")
        except Exception as e:
            print(f"  error: {e}")

    # ── Print region ───────────────────────────────────────────────────────────

    def _print_region(self, key: str):
        """
        GDB-style hex dump of full region.

        (dbg) TagManager::occupied_tags
        TagManager::occupied_tags  0xA0001000  192 B

          0xA0001000:  0x00000020  0x00000001  0x00000000  0x00000000
        """
        region = self._a.get_region(key)
        dwords = self._a.get_region_dwords(key)
        print(f"\n{key}  0x{region.base_addr:08X}  {region.size_bytes} B\n")
        self._print_dwords_gdb(region.base_addr, dwords)
        if key in self._structs:
            self._print_struct_fields(key)

    # ── Print field ────────────────────────────────────────────────────────────

    def _print_field(self, key: str, field: str):
        """
        Reflects into ctypes struct for this key and prints the field.

        (dbg) TagManager::sfr_base.tag_count
        TagManager::sfr_base.tag_count  0xA0001008  =  5  (uint16)
        """
        struct_type = self._structs.get(key)
        if struct_type is None:
            print(f"  error: no struct registered for '{key}'")
            print(f"  hint:  use plain '{key}' for raw hex dump")
            return

        region = self._a.get_region(key)
        obj    = self._a.read_struct(region, struct_type)

        if not hasattr(obj, field):
            available = [f[0] for f in struct_type._fields_]
            print(f"  error: '{field}' not in {struct_type.__name__}")
            print(f"  fields: {available}")
            return

        import ctypes
        val          = getattr(obj, field)
        field_offset = getattr(struct_type, field).offset
        field_addr   = region.base_addr + field_offset
        ctype_name   = type(val).__name__.replace("c_", "")

        if isinstance(val, int):
            print(f"\n{key}.{field}  0x{field_addr:08X}  =  "
                  f"0x{val:X}  ({val})  [{ctype_name}]\n")
        elif hasattr(val, '__len__'):
            print(f"\n{key}.{field}  0x{field_addr:08X}  [{ctype_name} * {len(val)}]\n")
            self._print_dwords_gdb(field_addr, list(val))
        else:
            print(f"\n{key}.{field}  0x{field_addr:08X}  =  {val}  [{ctype_name}]\n")

    # ── Print raw address ──────────────────────────────────────────────────────

    def _print_raw(self, addr: int, count: int):
        """
        Reads N dwords from raw address, GDB-style.

        (dbg) x/8xw 0xA0001000
          # TagManager::occupied_tags+0x0

          0xA0001000:  0x00000020  0x00000001  0x00000000  0x00000000
        """
        dwords = []
        for i in range(count):
            dw = self._a.mem.read_dword(addr + i * 4)
            dwords.append(dw if dw is not None else 0xDEADDEAD)

        hint = self._resolve_symbol(addr)
        if hint:
            print(f"\n  # {hint}")

        print()
        self._print_dwords_gdb(addr, dwords)

    # ── Struct fields overview ─────────────────────────────────────────────────

    def _print_struct_fields(self, key: str):
        """Prints all fields of a registered struct — like GDB's 'p *ptr'."""
        struct_type = self._structs[key]
        region      = self._a.get_region(key)
        try:
            obj = self._a.read_struct(region, struct_type)
        except Exception as e:
            print(f"  [struct read error: {e}]")
            return
        print(f"  # {struct_type.__name__} fields:")
        for fname, *_ in struct_type._fields_:
            val          = getattr(obj, fname)
            field_offset = getattr(struct_type, fname).offset
            field_addr   = region.base_addr + field_offset
            if isinstance(val, int):
                print(f"    .{fname:<20}  0x{field_addr:08X}  =  "
                      f"0x{val:08X}  ({val})")
            elif hasattr(val, '__len__'):
                print(f"    .{fname:<20}  0x{field_addr:08X}  "
                      f"[array len={len(val)}]")
        print()

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _print_dwords_gdb(self, base_addr: int, dwords: list):
        """4 dwords per line with leading address — matches GDB x/Nxw output."""
        for i in range(0, len(dwords), 4):
            chunk = dwords[i:i+4]
            addr  = base_addr + i * 4
            vals  = "  ".join(f"0x{d:08X}" for d in chunk)
            print(f"  0x{addr:08X}:  {vals}")
        print()

    def _resolve_symbol(self, addr: int) -> str:
        """Reverse lookup — which key contains this address."""
        for key, region in self._a.regions.items():
            if region.base_addr <= addr < region.end_addr:
                return f"{key}+0x{addr - region.base_addr:X}"
        return ""

    def _list(self):
        print()
        for key, r in sorted(self._a.regions.items()):
            covered    = "✓" if self._a.is_region_in_dump(key) else "✗"
            has_struct = "  [struct]" if key in self._structs else ""
            print(f"  {covered}  {key:<45}  0x{r.base_addr:08X}  "
                  f"{r.size_bytes} B{has_struct}")
        print()

    def _run(self, args):
        if not args:
            print(f"  available: {list(self._fns.keys())}")
            return
        fn = self._fns.get(args[0])
        if fn is None:
            print(f"  error: '{args[0]}' not found")
            return
        fn(self._a)

    def _help(self):
        print("""
  Probe by key:
    TagManager::occupied_tags            hex dump of full region
    TagManager::sfr_base.tag_count       read struct field
    TagManager::sfr_base.occupied_tags   read array field

  Probe by address:
    x/4xw  0xA0001000      read 4 dwords at address
    x/16xw 0xA0001000      read 16 dwords at address
    x      0xA0001000      read 4 dwords (default)

  Session:
    list                   list all known regions
    run <analyzer_name>    run a named analyzer
    help                   this message
    quit                   exit
        """)
