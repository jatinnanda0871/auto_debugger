// controller2_regs.h — controller2's own register layout, independent of
// controller1's BigStruct64/TagRecord (structs/big_struct.h, tag_record.h).
#pragma once

#include "reg_macros.h"

#pragma pack(push, 1)

struct Controller2Status {
    REG_UINT8  link_state;
    REG_UINT8  error_code;
    REG_UINT16 frame_count;
    struct {
        uint32_t retry_enabled : 1;
        uint32_t speed_mode    : 2;
        uint32_t reserved      : 29;
    } control;
};

#pragma pack(pop)
