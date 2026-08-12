// tag_bitmap.h — internal shape of test_suite's "core" TagManager keys
// (config.OCCUPIED_TAGS_ADDR and each of config.PENDING_KEYS): a flat
// 512-bit (64-byte) occupancy bitmap, one bit per tag -- see
// fixture_schema.py's N_TAGS / _tag_bitmap().
//
// Deliberately just this one key's own bytes: test_suite's keys sit with
// small gaps between them (by design, for sparse-chunk-loading coverage --
// see fixture_schema.py's _pack_block), so unlike epdc's TagRecord/
// BigStruct64, keys here can't be glued into one wider struct without
// silently misreading the gap as if it were real field data.
#pragma once

typedef unsigned char uint8_t;

struct TagBitmap {
    uint8_t bits[64];
};
