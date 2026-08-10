import importlib.util
from pathlib import Path
from engine.api import DumpAnalyzer
from products.test_suite.config import MODULES


def run(analyzer: DumpAnalyzer) -> None:
    """
    Called by main.py with a fully built DumpAnalyzer.
    Loads each module listed in config.MODULES and calls its run(analyzer).
    """
    product_dir = Path(__file__).parent

    for module_name in MODULES:
        module_path = product_dir / "modules" / f"{module_name}.py"
        if not module_path.exists():
            print(f"[WARN] Module '{module_name}' not found at {module_path} — skipping")
            continue

        spec   = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "run"):
            print(f"[WARN] Module '{module_name}' has no run() function — skipping")
            continue

        module.run(analyzer)
