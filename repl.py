import re
import readline
from api import DumpAnalyzer

# ── Prompt ─────────────────────────────────────────────────────────────────────
PROMPT = "(dbg) "

# ── Patterns ───────────────────────────────────────────────────────────────────
RE_RAW_FMT    = re.compile(r'^x/(\d+)x[wW]\s+(0x[0-9a-fA-F]+)$')
RE_RAW_SIMPLE = re.compile(r'^x\s+(0x[0-9a-fA-F]+)$')


class DebugREPL:

    def __init__(self, analyzer: DumpAnalyzer):
        """
        analyzer  — DumpAnalyzer instance
        structs   — { "TagManager::sfr_base": TagManagerSfr, ... }
                    ctypes struct classes keyed by region name
        analyzers — { "analyze_occupied_tags": fn, ... }
        """
        self._a       = analyzer
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
            else:
                print(f"  Unknown: '{raw}'  —  type 'help'")

        except KeyError as e:
            print(f"  error: {e}")
        except ValueError as e:
            print(f"  error: {e}")
        except Exception as e:
            print(f"  error: {e}")

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
            print(f"  {covered}  {key:<45}  0x{r.base_addr:08X}  "
                  f"{r.size_bytes}")
        print()

    def _help(self):
        print("""
  Probe by address:
    x/4xw  0xA0001000      read 4 dwords at address
    x/16xw 0xA0001000      read 16 dwords at address
    x      0xA0001000      read 4 dwords (default)

  Session:
    list                   list all known regions
    help                   this message
    quit                   exit
        """)
