"""
Dedicated home for regressions -- one test per bug once it has been found.

Convention (see README.md "Testing"):
  Any bug we hit gets a test here (or in the most relevant tests/test_*.py
  file, cross-referenced from here) that fails on the old broken behavior
  and passes once fixed, so it can never silently come back.
"""

import inspect

import pytest

from engine.api import DumpAnalyzer
from engine.models import Region, Chunk, MemoryView


# ── commit ecf1ed8: "gracefully handle partial reads and out-of-bounds
#    cases in the API" -- full API-level coverage lives in test_api.py under
#    the "zero-byte region / partial-read regressions" section. Cross-ref:
#    test_get_dword_on_zero_byte_region_raises_value_error,
#    test_get_dword_on_partial_region_reads_available_bytes_only,
#    test_is_tag_set_in_region_raises_when_tag_index_beyond_region_bounds,
#    test_get_bitfield_at_offset_raises_on_out_of_bounds_offset,
#    test_get_byte_raises_on_out_of_bounds_offset.


# ── DebugREPL(analyzer) arg-count mismatch (found while building this suite) ─
#
# main.py:81 calls `DebugREPL(analyzer).run()` with a single positional arg.
# engine/repl.py:15 declares `__init__(self, analyzer, structs, analyzers)`,
# which requires three. Every `--repl` invocation currently raises TypeError
# before the REPL can start (subprocess-level proof: test_main_cli.py::
# test_main_repl_flag_currently_raises_type_error, marked xfail(strict=True)
# so it flips to a hard failure -- flagging the fix -- the moment someone
# changes either signature).
#
# This test pins the *reason* directly against the constructor signature so
# the mismatch is caught even before `--repl` is ever exercised end-to-end.

def test_debug_repl_constructor_signature_documented_mismatch():
    from engine.repl import DebugREPL
    params = list(inspect.signature(DebugREPL.__init__).parameters)
    assert params == ["self", "analyzer", "structs", "analyzers"], (
        "DebugREPL.__init__ signature changed -- check whether main.py's "
        "`DebugREPL(analyzer).run()` call (main.py, --repl branch) was "
        "updated to match. If it now takes only `analyzer`, delete this "
        "test and un-xfail test_main_cli.py::"
        "test_main_repl_flag_currently_raises_type_error."
    )


# ── Template for the next regression ─────────────────────────────────────────
#
# def test_<short_bug_description>():
#     """
#     <what broke, and under what input>
#     Bug: <link/commit/issue if any>
#     """
#     ...
