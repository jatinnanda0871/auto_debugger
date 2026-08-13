"""
Tests for main.py -- the CLI entry point. Runs the real script via
subprocess so these exercise the exact path CI/users invoke.
"""

import subprocess
import sys

import pytest

from tests.conftest import ROOT, TEST_SUITE_DUMPS


def run_main(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "main.py"), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_main_with_no_args_prints_usage_and_exits_nonzero():
    result = run_main()
    assert result.returncode == 1
    assert "Usage" in result.stdout or "python main.py" in result.stdout


def test_main_unknown_product_id_exits_nonzero_with_clear_message():
    dump_folder = str(TEST_SUITE_DUMPS / "scenario_01_baseline_no_errors")
    result = run_main(dump_folder, "not_a_real_product")
    assert result.returncode != 0
    assert "not_a_real_product" in (result.stdout + result.stderr)


def test_main_baseline_dump_exits_zero():
    dump_folder = str(TEST_SUITE_DUMPS / "scenario_01_baseline_no_errors")
    result = run_main(dump_folder, "test_suite")
    assert result.returncode == 0
    assert "[PASS]" in result.stdout


def test_main_error_dump_exits_nonzero():
    dump_folder = str(TEST_SUITE_DUMPS / "scenario_02_fcc_counter_value_error")
    result = run_main(dump_folder, "test_suite")
    assert result.returncode == 1
    assert "[FAIL]" in result.stdout


def test_main_merges_multiple_dump_files_in_one_folder():
    # scenario folders ship 5 *.dump files (one per memory block) that must
    # all be merged into a single MemoryView by main.py's load_dump() call.
    dump_folder = str(TEST_SUITE_DUMPS / "scenario_01_baseline_no_errors")
    result = run_main(dump_folder, "test_suite")
    assert "Found 5 dump file(s)" in result.stdout


def test_main_nonexistent_dump_folder_fails_cleanly():
    result = run_main(str(ROOT / "products" / "test_suite" / "sample_dumps" / "does_not_exist"), "test_suite")
    assert result.returncode != 0


def test_main_runs_epdc_against_sample_dump():
    dump_folder = str(ROOT / "products" / "epdc" / "sample_dump" / "1_halted_1")
    result = run_main(dump_folder, "epdc")
    assert result.returncode == 0
    assert "[PASS]" in result.stdout


@pytest.mark.xfail(
    reason="known bug: main.py instantiates DebugREPL(analyzer) with a single "
           "argument, but DebugREPL.__init__ requires (analyzer, structs, analyzers) "
           "-- see engine/repl.py:15 vs main.py's `DebugREPL(analyzer).run()` call. "
           "This test documents the bug so it turns green (unexpectedly) the moment "
           "it's fixed, flagging the fix in CI.",
    strict=True,
)
def test_main_repl_flag_currently_raises_type_error():
    dump_folder = str(TEST_SUITE_DUMPS / "scenario_01_baseline_no_errors")
    result = run_main(dump_folder, "test_suite", "--repl")
    assert "TypeError" not in result.stderr
