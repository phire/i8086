#!/usr/bin/env python3

from enum import Enum
from amaranth import *

import microcode_dump

class Group(Enum):
    io = 0 # only set on in/out instructions
    load_m = 1 # load lower 3 bits (of first byte?) into M
    r_to_microcode = 2 # replace lower 3 bits of microcode address with the r bits (3-5) of the mod RM byte (used for grp1/2)
    prefix_byte = 3
    one_byte = 4 # run microcode after first byte
    load_n = 5 # load bits 3-5 into N
    flags = 6
    not_rm = 7 # set when second byte is not mod RM byte
    mov_seg = 8 # set when M reg is segment register
    do_memory = 9 # run microcode for mod RM byte
    no_imm = 10 # ? set for an alu instruction with no immediate
    has_displacement = 11 # doesn't quite work. in/out DX also has 11 set, despite being a one byte instructions
    unk12 = 12 # covers all ascii instructions, and xlat
    unk13 = 13 # covers control flow and the immediate alu instructions at 80-87
    unk14 = 14 # set for everything except inc/dec, some control flow and some push/pop

class GroupDecode(Elaboratable):
    def __init__(self):
        self.i = Signal(9)
        self.o_group = Signal(15)
        self.o_col36 = Signal()
        self.o_col37 = Signal()

        # private
        self.cols = Signal(38)

    def elaborate(self, platform):
        m = Module()

        for col, pattern in enumerate(microcode_dump.group_input):
            ones_mask =  int("".join(["1" if c == "1" else "0" for c in reversed(pattern)]), 2)
            zeros_mask = int("".join(["1" if c == "0" else "0" for c in reversed(pattern)]), 2)
            m.d.comb += self.cols[col].eq(~((~self.i & ones_mask).any() | (self.i & zeros_mask).any()))

        for group, pattern in enumerate(microcode_dump.group_output):
            pattern = "".join(reversed(pattern))
            m.d.comb += self.o_group[group].eq(~(self.cols & int(pattern, 2)).any())

        m.d.comb += [
            self.o_col36.eq(self.cols[36]),
            self.o_col37.eq(self.cols[37]),
        ]

        return m

if __name__ == "__main__":
    from amaranth.sim import Simulator, Settle

    decode = GroupDecode()

    def bench():
        for i in range(0x100):
            yield decode.i.eq(i)
            yield Settle()
            group = yield decode.o_group

            str = ""
            for group in range(15):
                if (yield decode.o_group[group]):
                    str += f" {group:2}"
                else:
                    str += "   "

            col36 = yield decode.o_col36
            col37 = yield decode.o_col37

            if col36:
                str += " col36"
            if col37:
                str += " col37"

            print(f"{i:03x} -> {str}")

    sim = Simulator(decode)
    sim.add_process(bench)

    sim.run()