import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.loader import load_map, load_dump, find_map_file
from engine.api import DumpAnalyzer

TEST_SUITE_DUMPS = ROOT / "products" / "test_suite" / "sample_dumps"
EPDC_SAMPLE_DUMPS = ROOT / "products" / "epdc" / "sample_dump"


def build_analyzer(dump_folder: Path) -> DumpAnalyzer:
    """Loads a dump folder (map + dump files) into a fresh DumpAnalyzer."""
    map_file = find_map_file(str(dump_folder))
    regions  = load_map(map_file)
    mem      = load_dump(str(dump_folder))
    return DumpAnalyzer(mem, regions)


@pytest.fixture
def analyzer_factory():
    """Callable fixture: analyzer_factory(folder_path) -> DumpAnalyzer."""
    return build_analyzer


@pytest.fixture(params=sorted(p.name for p in TEST_SUITE_DUMPS.iterdir() if p.is_dir()))
def test_suite_scenario(request):
    """Parametrized over every scenario_* fixture under
    products/test_suite/sample_dumps/."""
    return TEST_SUITE_DUMPS / request.param


@pytest.fixture(params=sorted(
    p.name for p in TEST_SUITE_DUMPS.iterdir() if p.is_dir() and p.name.startswith("scenario_")
))
def identical_layout_scenario(request):
    """Parametrized over the 5 scenario_* fixtures that share one identical
    50-key memory.map -- only mutated bytes differ between them."""
    return TEST_SUITE_DUMPS / request.param


@pytest.fixture(params=sorted(p.name for p in EPDC_SAMPLE_DUMPS.iterdir() if p.is_dir()))
def epdc_sample_scenario(request):
    """Parametrized over every scenario under products/epdc/sample_dump/."""
    return EPDC_SAMPLE_DUMPS / request.param


@pytest.fixture
def baseline_analyzer():
    return build_analyzer(TEST_SUITE_DUMPS / "scenario_01_baseline_no_errors")


@pytest.fixture
def fcc_counter_error_analyzer():
    return build_analyzer(TEST_SUITE_DUMPS / "scenario_02_fcc_counter_value_error")


@pytest.fixture
def occupied_tag_count_error_analyzer():
    return build_analyzer(TEST_SUITE_DUMPS / "scenario_03_occupied_tag_count_error")


@pytest.fixture
def pending_tag_leak_analyzer():
    return build_analyzer(TEST_SUITE_DUMPS / "scenario_04_pending_tag_leak")


@pytest.fixture
def mirror_mismatch_analyzer():
    return build_analyzer(TEST_SUITE_DUMPS / "scenario_05_mirror_mismatch")


@pytest.fixture
def sum_check_mismatch_analyzer():
    return build_analyzer(TEST_SUITE_DUMPS / "scenario_06_sum_check_mismatch")


@pytest.fixture
def reserved_region_set_analyzer():
    return build_analyzer(TEST_SUITE_DUMPS / "scenario_07_reserved_region_set")
