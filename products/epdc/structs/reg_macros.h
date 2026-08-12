// reg_macros.h — register-width macros, #included directly by struct files
// that need them (not itself listed in STRUCT_HEADERS — it has no struct or
// union definitions of its own, so struct_gen has nothing to emit for it).
#pragma once

typedef unsigned char      uint8_t;
typedef signed char        int8_t;
typedef unsigned short     uint16_t;
typedef signed short       int16_t;
typedef unsigned int       uint32_t;
typedef signed int         int32_t;
typedef unsigned long long uint64_t;
typedef signed long long   int64_t;

// Typical firmware register-access macros: a type alias plus a volatile
// qualifier. struct_gen maps by canonical type *kind*, not by spelling, so
// it sees straight through both the macro and the volatile qualifier down
// to the real underlying width.
#define REG_UINT8  volatile uint8_t
#define REG_UINT16 volatile uint16_t
#define REG_UINT32 volatile uint32_t
