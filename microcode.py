#!/usr/bin/env python3

from amaranth import *

import microcode_dump

class ColumSelector(Elaboratable):
    """
        Logically, the microcode can be considered to be an 8K x 21bit ROM (grouped into 2k cols of 84bits).
        Each instruction starts at a unique offset spaced every 16 instructions, and a counter increments though 16 states.
        But intel have optimized it down to the equivalent of a 512x21bit rom (128 cols) by storing duplicated logical column
        at the same physical column.

        In real hardware, this column selector takes a 11 bit address and activates one of the 128 columns.
        For this implementation, it outputs a 7 bit column index that can be indexed into an FPGA's blockram.
    """
    def __init__(self):
        self.i_addr = Signal(11)
        self.o_column_index = Signal(7)

    def elaborate(self, platform):
        m = Module()

        with m.Switch(self.i_addr):
            default = None
            for column, pattern in enumerate(microcode_dump.selector):
                if pattern == "-----------":
                    # I'm not sure how this is meant to work. This selector (at column 0x48) will match
                    # every single input, and so col 0x48 will will always be selected.
                    # But... every single bit in row 0x48 is zero, so does selecting it is a no-op?
                    #
                    # I feel like intel could have saved space by simply omitting this column?
                    #
                    # For our implementation, we instead emit it as the default case
                    with m.Default():
                        m.d.comb += self.o_column_index.eq(default)
                else:
                    with m.Case(pattern): # note: pattern has don't cares
                        m.d.comb += self.o_column_index.eq(column)
        return m


if __name__ == "__main__":
    from amaranth.sim import Simulator, Settle

    selector = ColumSelector()

    def bench():
        for i in range(256):
            yield selector.i_addr.eq(i << 2)
            yield Settle()
            addr = yield selector.o_column_index
            print(f"{i:02x} -> {addr << 2:03x}")

    sim = Simulator(selector)
    sim.add_process(bench)

    sim.run()
