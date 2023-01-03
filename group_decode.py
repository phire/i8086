#!/usr/bin/env python3

from enum import Enum
from amaranth import *

import microcode_dump

class Group(Enum):
    io = 0 # only set on in/out instructions
    load_m = 1 # load lower 3 bits (of first byte?) into M
    prefix_byte = 3
    one_byte = 4 # run microcode after first byte
    load_x_n = 5 # reg x will be loaded with bits 3-6 as alu op. n will be loaded with bits 3-5 (not entirely sure on this)
    flags = 6
    not_rm = 7 # set when second byte is not mod RM byte
    mov_seg = 8 # set when M reg is segment register
    do_memory = 9 # run microcode for mod RM byte
    two_byte = 11 # doesn't quite work. in/out DX also has 11 set, despite being a one byte instructions
    enable_microcode = 14 # guess?

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
            m.d.comb += self.o_group[group].eq(~(self.cols & ~int(pattern, 2)).any())

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
            # cols = yield decode.cols
            # print(f"    {cols:038b}")
            # group_10 = int(''.join(reversed(microcode_dump.group_output[11])), 2)

            # print(f"    {group_10:038b}")
            # print(f"    {''.join(reversed(microcode_dump.group_output[10]))}")

    sim = Simulator(decode)
    sim.add_process(bench)

    sim.run()

    # for group, pattern in enumerate(microcode_dump.group_output):
    #     pattern = int(pattern, 2) ^ 0x3fffffffff
    #     print(f"{pattern:038b}")

# c6 00100000000000000000010000100000000000
# c7 00100000000000000000000000100000000000
#00100010000000000000000000100000000000
#00100000000000000000000000100000000000