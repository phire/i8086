#!/usr/bin/env python3

from enum import Enum
from amaranth import *

import microcode_dump

class GroupRow(Enum):
    IsIO = 0 # only set on in/out instructions
    LoadM = 1 # load lower 3 bits (of first byte?) into M
    RToMicrocode = 2 # replace lower 3 bits of microcode address with the r bits (3-5) of the mod RM byte (used for grp1/2)
    IsPrefix = 3
    OneByte = 4 # run microcode after first byte
    LoadN = 5 # load bits 3-5 into N
    Flags = 6
    IsAccumulator = 7 # set when second byte is not mod RM byte
    MovSeg = 8 # set when M reg is segment register
    DirectionInBit1 = 9 # read/write is based on bit 1
    NoMicrocode = 10
    WidthInBit0 = 11 # Width in bit 0
    unk12 = 12 # covers all ascii instructions, and xlat
    unk13 = 13 # covers control flow and the immediate alu instructions at 80-87 (reeninge has this as "F1zz from prefix")
    unk14 = 14 # set for everything except inc/dec, some control flow and some push/pop

class GroupColumn(Enum):
    LoadRegImm = 10
    WidthInBit0 = 12
    CMC = 13
    HLT = 14
    REP = 31
    SegmentOverride = 32
    Lock = 33
    CLI = 34
    MovSeg = 36
    PopSeg = 37

class GroupDecode(Elaboratable):
    """ The group decode logic generates a bunch of random control signals that mostly get used
        by the loader.

        Intel call it the "Group Decode ROM", but it's more of a PLA than a rom.
        The lower half does pattern matching on 9 input signals to produce 38 columns (except 0, expect 1 or don't care)
        The upper half NORs various columns together to produce 15 rows of control signals.

        Additionally, 10 of the Columns are tapped directly for an additional control signals.
    """
    def __init__(self):
        self.i = Signal(9)
        self.o_rows = Signal(15)
        self.o_columns = Signal(38)

    def elaborate(self, platform):
        m = Module()

        for col, pattern in enumerate(microcode_dump.group_input):
            ones_mask =  int("".join(["1" if c == "1" else "0" for c in reversed(pattern)]), 2)
            zeros_mask = int("".join(["1" if c == "0" else "0" for c in reversed(pattern)]), 2)
            m.d.comb += self.o_columns[col].eq(~((~self.i & ones_mask).any() | (self.i & zeros_mask).any()))

        for group, pattern in enumerate(microcode_dump.group_output):
            pattern = "".join(reversed(pattern))
            m.d.comb += self.o_rows[group].eq(~(self.o_columns & int(pattern, 2)).any())

        return m

if __name__ == "__main__":
    from amaranth.sim import Simulator, Settle

    decode = GroupDecode()

    def bench():
        for i in range(0x101):
            yield decode.i.eq(i)
            yield Settle()

            str = ""
            for group in range(15):
                if (yield decode.o_rows[group]):
                    str += f" {group:2}"
                else:
                    str += "   "

            columns = yield decode.o_columns
            for col in GroupColumn:
                if columns & (1 << col.value):
                    str += f" {col.name}"


            print(f"{i:03x} -> {str}")

    sim = Simulator(decode)
    sim.add_process(bench)

    sim.run()