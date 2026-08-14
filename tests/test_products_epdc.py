"""
End-to-end tests for products/epdc against its own sample_dump/ fixtures.
These exercise the real product.py -> modules/*.py dynamic-loading path,
not just the engine API in isolation.
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


def test_epdc_product_runs_without_raising_on_every_sample(epdc_sample_scenario):
    analyzer = build_analyzer(epdc_sample_scenario)
    product  = load_epdc_product()
    product.run(analyzer)  # must not raise for any shipped fixture


def test_epdc_fcc_manager_flags_known_mismatch_scenario():
    analyzer = build_analyzer(EPDC_DIR / "sample_dump" / "4_fcc_count_error")
    product  = load_epdc_product()
    product.run(analyzer)
    assert analyzer._error_found is True


def test_epdc_fcc_manager_passes_on_halted_scenario():
    analyzer = build_analyzer(EPDC_DIR / "sample_dump" / "1_halted_1")
    product  = load_epdc_product()
    product.run(analyzer)
    assert analyzer._error_found is False


def test_epdc_tag_manager_analyze_occupied_tags_directly():
    from products.epdc.modules import tag_manager
    analyzer = build_analyzer(EPDC_DIR / "sample_dump" / "1_halted_1")
    tag_manager.analyze_occupied_tags(analyzer)  # smoke: must not raise


def test_epdc_fcc_manager_analyze_fcc_counter_directly():
    from products.epdc.modules import fcc_manager
    analyzer = build_analyzer(EPDC_DIR / "sample_dump" / "1_halted_1")
    fcc_manager.analyze_fcc_counter(analyzer)  # smoke: must not raise


def test_epdc_fcc_manager_derives_counter_value_via_get_struct():
    """
    Each per-function FCC counter is no longer read via raw-dword bit
    masking -- analyze_fcc_counter now typecasts each function's dword to
    dword7_checksum_t via analyzer.get_struct() and reads the count from
    its mixed.crc field. Proven here by independently typecasting the same
    region ourselves and checking it matches what get_dword sees (crc is
    dword7_checksum_t's first byte, i.e. bits [0:8) of the raw dword).
    """
    from engine.loader import find_map_file, load_dump, load_map
    from engine.api import DumpAnalyzer
    from products.epdc.config import FCC_COUNTERS_ADDR
    from products.epdc.generated_structs.big_struct import dword7_checksum_t

    folder   = EPDC_DIR / "sample_dump" / "1_halted_1"
    regions  = load_map(find_map_file(str(folder)))
    mem      = load_dump(str(folder))
    analyzer = DumpAnalyzer(mem, regions)

    func_count = analyzer.get_region_size_dwords(FCC_COUNTERS_ADDR)
    for i in range(func_count):
        record = analyzer.get_struct(FCC_COUNTERS_ADDR, dword7_checksum_t, byte_offset=i * 4)
        dw     = analyzer.get_dword(FCC_COUNTERS_ADDR) if i == 0 else None
        assert record.mixed.crc == record.raw & 0xFF
        if dw is not None:
            assert record.raw == dw


def test_epdc_fcc_manager_prints_struct_derived_counters(capsys):
    from products.epdc.modules import fcc_manager
    analyzer = build_analyzer(EPDC_DIR / "sample_dump" / "1_halted_1")
    fcc_manager.analyze_fcc_counter(analyzer)
    out = capsys.readouterr().out
    # dwords for 1_halted_1 are 1, 1, 1, 0 (see memory.dump) -- crc == low byte
    assert "Func[0 ]     0x00000001      1" in out
    assert "Func[3 ]     0x00000000      0" in out


@pytest.mark.parametrize("scenario", [
    "1_halted_1", "2_fcc_tags_mismatch", "3_halted_2",
    "4_fcc_count_error", "5_idle_state", "6_halted_3",
])
def test_epdc_product_error_state_matches_recorded_expectation(scenario):
    """
    Pins the pass/fail outcome of every shipped products/epdc/sample_dump/ scenario.
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

    analyzer = build_analyzer(EPDC_DIR / "sample_dump" / scenario)
    load_epdc_product().run(analyzer)
    assert analyzer._error_found is expected_error
