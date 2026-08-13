// fcc_counters.h — internal shape of test_suite's config.FCC_COUNTERS_ADDR
// key: one uint32_t per tag (only the low byte is ever a real counter value
// -- see fixture_schema.py's _expected_value for FCC_COUNTERS_ADDR), 512
// tags -> 2048 bytes total. Same single-key-only scoping note as
// tag_bitmap.h applies -- this describes only FCC_COUNTERS_ADDR's own
// bytes, not anything beyond them.
#pragma once

typedef unsigned int uint32_t;

struct FccCounterTable {
    uint32_t counters[512];
};
