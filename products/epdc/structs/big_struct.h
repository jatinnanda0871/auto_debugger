// big_struct.h — firmware struct definitions (single source of truth for layout)
//
// Regenerate via:
//   python struct_gen.py epdc
//
// NOTE on bitfields: bit *allocation order within a storage unit* is
// compiler-ABI-defined (MSVC vs Itanium/GCC/Clang pack bits in opposite
// directions). struct_gen.py must be run with the same target ABI the
// firmware was compiled with, or bitfield values will read back wrong even
// though total struct size still matches.
#pragma once

#include "reg_macros.h"

#pragma pack(push, 1)

// ── Dword 0 — status/control bitfields (mix of widths, incl. single-bit) ───────
union dword0_status_t {
    uint32_t raw;
    struct {
        uint32_t tag_valid   : 1;
        uint32_t tag_locked  : 1;
        uint32_t tag_pending : 1;
        uint32_t priority    : 3;
        uint32_t owner_id    : 6;
        uint32_t sequence    : 12;
        uint32_t reserved    : 8;
    } bits;
};

// ── Dword 1 — plain 4-byte value, signed and unsigned views ────────────────────
union dword1_value_t {
    uint32_t raw;
    int32_t  signed_value;
};

// ── Dword 2 — two 2-byte values ─────────────────────────────────────────────────
union dword2_halfwords_t {
    uint32_t raw;
    struct {
        uint16_t lo;
        uint16_t hi;
    } words;
};

// ── Dword 3 — four 1-byte values ────────────────────────────────────────────────
union dword3_bytes_t {
    uint32_t raw;
    uint8_t  bytes[4];
};

// ── Dword 4 — byte + word + byte mix ────────────────────────────────────────────
union dword4_mixed_bwb_t {
    uint32_t raw;
    struct {
        uint8_t  header;   // 1 byte
        uint16_t payload;  // 2 bytes
        uint8_t  footer;   // 1 byte
    } mixed;
};

// ── Dword 5 — word + byte + byte mix ────────────────────────────────────────────
union dword5_mixed_wbb_t {
    uint32_t raw;
    struct {
        uint16_t code;   // 2 bytes
        uint8_t  sub_a;  // 1 byte
        uint8_t  sub_b;  // 1 byte
    } mixed;
};

// ── Dword 6 — counter bitfields (incl. single-bit enable flag) ─────────────────
union dword6_counter_t {
    uint32_t raw;
    struct {
        uint32_t enabled     : 1;
        uint32_t mode        : 2;
        uint32_t retry_count : 5;
        uint32_t timeout_ms  : 16;
        uint32_t reserved    : 8;
    } bits;
};

// ── Dword 7 — byte + bitfield-byte + word mix ───────────────────────────────────
union dword7_checksum_t {
    uint32_t raw;
    struct {
        uint8_t  crc;              // 1 byte
        uint8_t  parity      : 1;  // bitfield packed into its own byte
        uint8_t  parity_rsvd : 7;
        uint16_t magic;            // 2 bytes
    } mixed;
};

// ── Dword 8 — priority/scheduling bitfields (incl. single-bit enable) ──────────
union dword8_priority_t {
    uint32_t raw;
    struct {
        uint32_t enable  : 1;
        uint32_t channel : 4;
        uint32_t weight  : 8;
        uint32_t credits : 11;
        uint32_t reserved: 8;
    } bits;
};

// ── Dword 9 — plain 4-byte value, alternate name ────────────────────────────────
union dword9_count_t {
    uint32_t raw;
    uint32_t count;
};

// ── Dword 10 — two 2-byte values ────────────────────────────────────────────────
union dword10_range_t {
    uint32_t raw;
    struct {
        uint16_t min;
        uint16_t max;
    } range;
};

// ── Dword 11 — four 1-byte values ───────────────────────────────────────────────
union dword11_channels_t {
    uint32_t raw;
    uint8_t  channels[4];
};

// ── Dword 12 — byte + word + byte mix ───────────────────────────────────────────
union dword12_mixed_bwb_t {
    uint32_t raw;
    struct {
        uint8_t  state;  // 1 byte
        uint16_t index;  // 2 bytes
        uint8_t  mode;   // 1 byte
    } mixed;
};

// ── Dword 13 — word + byte + byte mix ───────────────────────────────────────────
union dword13_mixed_wbb_t {
    uint32_t raw;
    struct {
        uint16_t type;  // 2 bytes
        uint8_t  tag;   // 1 byte
        uint8_t  rev;   // 1 byte
    } mixed;
};

// ── Dword 14 — counter bitfields (incl. single-bit active flag) ────────────────
union dword14_counter2_t {
    uint32_t raw;
    struct {
        uint32_t active : 1;
        uint32_t level  : 3;
        uint32_t count  : 12;
        uint32_t spare  : 16;
    } bits;
};

// ── Dword 15 — byte + bitfield-byte + word mix ──────────────────────────────────
union dword15_checksum2_t {
    uint32_t raw;
    struct {
        uint8_t  seed;             // 1 byte
        uint8_t  flag       : 1;   // bitfield packed into its own byte
        uint8_t  flag_rsvd  : 7;
        uint16_t id;                // 2 bytes
    } mixed;
};

// ── Top-level struct — 16 dwords, 64 bytes total ────────────────────────────────
struct BigStruct64 {
    dword0_status_t     status_flags;
    dword1_value_t      raw_value;
    dword2_halfwords_t  half_words;
    dword3_bytes_t      byte_array;
    dword4_mixed_bwb_t  mixed_bwb;
    dword5_mixed_wbb_t  mixed_wbb;
    dword6_counter_t    counter_bits;
    dword7_checksum_t   checksum;
    dword8_priority_t   priority_bits;
    dword9_count_t      count_value;
    dword10_range_t     range_words;
    dword11_channels_t  channel_bytes;
    dword12_mixed_bwb_t mixed_bwb2;
    dword13_mixed_wbb_t mixed_wbb2;
    dword14_counter2_t  counter_bits2;
    dword15_checksum2_t checksum2;
};

// ── Register block — exercises REG_UINT* macros (macro + volatile) ─────────────
struct RegisterBlock {
    REG_UINT8  status_reg;
    REG_UINT16 config_reg;
    REG_UINT32 data_reg;
};

// ── Nested-struct demo — product code may want only the inner type ─────────────
struct Point16 {
    uint16_t x;
    uint16_t y;
};

struct Rect16 {
    Point16  origin;
    Point16  size;
    uint32_t color;
};

#pragma pack(pop)
