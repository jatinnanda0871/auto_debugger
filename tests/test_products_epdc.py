"""
End-to-end tests for products/epdc against the repo's existing sample_dump/
fixtures. These exercise the real product.py -> modules/*.py dynamic-loading
path, not just the engine API in isolation.
"""

import importlib.util
from pathlib import Path

import pytest

from tests.conftest import ROOT, build_analyzer

EPDC_DIR = ROOT / "products" / "epdc"


def load_epdc_product():
    spec   = importlib.util.spec_from_file_location("products.epdc.product", EPDC_DIR / "product.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_epdc_product_runs_without_raising_on_every_root_sample(root_sample_scenario):
    analyzer = build_analyzer(root_sample_scenario)
    product  = load_epdc_product()
    product.run(analyzer)  # must not raise for any shipped fixture


def test_epdc_fcc_manager_flags_known_mismatch_scenario():
    analyzer = build_analyzer(ROOT / "sample_dump" / "4_fcc_count_error")
    product  = load_epdc_product()
    product.run(analyzer)
    assert analyzer._error_found is True


def test_epdc_fcc_manager_passes_on_halted_scenario():
    analyzer = build_analyzer(ROOT / "sample_dump" / "1_halted_1")
    product  = load_epdc_product()
    product.run(analyzer)
    assert analyzer._error_found is False


def test_epdc_tag_manager_analyze_occupied_tags_directly():
    from products.epdc.modules import tag_manager
    analyzer = build_analyzer(ROOT / "sample_dump" / "1_halted_1")
    tag_manager.analyze_occupied_tags(analyzer)  # smoke: must not raise


def test_epdc_fcc_manager_analyze_fcc_counter_directly():
    from products.epdc.modules import fcc_manager
    analyzer = build_analyzer(ROOT / "sample_dump" / "1_halted_1")
    fcc_manager.analyze_fcc_counter(analyzer)  # smoke: must not raise


@pytest.mark.parametrize("scenario", [
    "1_halted_1", "2_fcc_tags_mismatch", "3_halted_2",
    "4_fcc_count_error", "5_idle_state", "6_halted_3",
])
def test_epdc_product_error_state_matches_recorded_expectation(scenario):
    """
    Pins the pass/fail outcome of every shipped sample_dump/ scenario.
    Locks current behavior in place -- if a future engine/product change
    flips one of these, it's a deliberate decision, not a silent regression.
    """
    expected_error = {
        "1_halted_1": False,
        "2_fcc_tags_mismatch": False,  # counts happen to match despite the name
        "3_halted_2": False,
        "4_fcc_count_error": True,
        "5_idle_state": False,
        "6_halted_3": False,
    }[scenario]

    analyzer = build_analyzer(ROOT / "sample_dump" / scenario)
    load_epdc_product().run(analyzer)
    assert analyzer._error_found is expected_error
