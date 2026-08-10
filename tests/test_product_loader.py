"""
Covers the module-loading warn-and-skip branches shared by every product's
product.py (dynamic import of modules/<name>.py, listed via config.MODULES).
"""

import importlib.util

from engine.api import DumpAnalyzer
from engine.models import MemoryView
from tests.conftest import ROOT


def load_product_module(product_id: str):
    path   = ROOT / "products" / product_id / "product.py"
    spec   = importlib.util.spec_from_file_location(f"products.{product_id}.product", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def empty_analyzer() -> DumpAnalyzer:
    return DumpAnalyzer(MemoryView(chunks=[]), {})


def test_product_skips_module_listed_but_not_present_on_disk(capsys):
    product = load_product_module("epdc")
    product.MODULES = ["does_not_exist_as_a_file"]
    product.run(empty_analyzer())
    out = capsys.readouterr().out
    assert "[WARN]" in out
    assert "not found" in out


def test_product_skips_module_missing_run_function(tmp_path, capsys, monkeypatch):
    product = load_product_module("epdc")
    fake_modules_dir = tmp_path / "modules"
    fake_modules_dir.mkdir()
    (fake_modules_dir / "no_run_here.py").write_text("VALUE = 1\n")

    monkeypatch.setattr(product, "__file__", str(tmp_path / "product.py"))
    product.MODULES = ["no_run_here"]
    product.run(empty_analyzer())

    out = capsys.readouterr().out
    assert "[WARN]" in out
    assert "no run()" in out
