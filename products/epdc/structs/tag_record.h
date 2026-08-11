// tag_record.h — demonstrates a cross-file struct reference: TagRecord here
// embeds BigStruct64, which is defined in big_struct.h. struct_gen resolves
// this by parsing every header for a product as one translation unit, then
// emitting tag_record.py with `from .big_struct import BigStruct64`.
#pragma once

#include "big_struct.h"

#pragma pack(push, 1)

typedef struct {
    BigStruct64 payload;
    uint32_t    tag_id;
} TagRecord;

#pragma pack(pop)
