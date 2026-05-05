"""
auto_debugger — Memory Dump Analysis Framework

Usage
-----
    python main.py <dump_folder> <product_id> [--repl]

Arguments
---------
dump_folder : path to a folder containing *.dump files and exactly one *.map file
product_id  : product name matching a subfolder under products/
              e.g. "epdc", "ufs", "nvme"

--repl      : drop into interactive GDB-style session after analysis
"""

import sys
import importlib.util
from pathlib import Path

from engine.loader import find_map_file, load_map, load_dump
from api import DumpAnalyzer


def _load_product(product_id: str):
    """
    Resolves product_id → products/<product_id>/product.py and imports it.
    The module must define: run(analyzer: DumpAnalyzer) -> None
    """
    product_path = Path("products") / product_id / "product.py"
    if not product_path.exists():
        available = sorted(
            p.name for p in Path("products").iterdir()
            if p.is_dir() and (p / "product.py").exists()
        ) if Path("products").exists() else []
        raise FileNotFoundError(
            f"Product '{product_id}' not found.\n"
            f"Expected: {product_path}\n"
            f"Available products: {available if available else '(none)'}"
        )

    spec   = importlib.util.spec_from_file_location(
                f"products.{product_id}.product", product_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "run"):
        raise AttributeError(
            f"products/{product_id}/product.py must define: "
            f"run(analyzer: DumpAnalyzer) -> None"
        )
    return module


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    dump_folder = sys.argv[1]
    product_id  = sys.argv[2]
    interactive = "--repl" in sys.argv

    # ── Build analyzer — main's only job ──────────────────────────────────────
    map_file = find_map_file(dump_folder)
    print(f"[INFO] Using map : {map_file}")
    regions  = load_map(map_file)
    mem      = load_dump(dump_folder)
    analyzer = DumpAnalyzer(mem, regions)

    # ── Hand off to product — main knows nothing beyond this point ────────────
    print(f"[INFO] Running product '{product_id}'\n")
    product = _load_product(product_id)
    product.run(analyzer)

    # ── Optional REPL — always after analysis ─────────────────────────────────
    if interactive:
        from repl import DebugREPL
        DebugREPL(analyzer).run()


if __name__ == "__main__":
    main()
