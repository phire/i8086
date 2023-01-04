#!/usr/bin/env python3

from enum import Enum
from amaranth import *

from group_decode import GroupRow, GroupDecode

class State(Enum):
    WaitFirstByte = 0
    WaitSecondByte = 1
    ExecutingMicrocode = 2
    Prefetch = 3

class InstructionLoader(Elaboratable):
    """
        The instruction loader is a state machine controls timings between the BIU's instruction queue
        and the rest of instruction decoding.

        It provides two pulses that control timings within the rest of instruction decoding
           - o_first_clock, When the first instruction byte is taken from the queue
           - o_second_clock, When the second instruction byte is taken from the queue

        For non-microcoded instructions, only first clock is emitted
        For microcoded single-byte instructions,
    """
    def __init__(self):
        self.i_queue_ready = Signal()
        self.i_nxt = Signal()
        self.i_rni = Signal()
        self.i_no_microcode = Signal()
        self.i_single_byte = Signal()
        self.i_reset = Signal()

        self.o_first_clock = Signal()
        self.o_second_clock = Signal()

        self.state = Signal(State)

    def elaborate(self, platform):
        m = Module()

        m.d.sync += [
            self.o_first_clock.eq(0),
            self.o_second_clock.eq(0),
        ]

        with m.If(self.i_reset):
            # On reset, execute the reset routine in microcode
            m.d.sync += self.state.eq(State.ExecutingMicrocode)
        with m.Elif(self.i_no_microcode):
            # If there is no microcode, the loader always goes back to the idle state
            m.d.sync += self.state.eq(State.WaitFirstByte)
        with m.Elif(self.i_queue_ready | self.i_single_byte):
            with m.If(self.state == State.WaitFirstByte):
                m.d.sync += [
                    self.o_first_clock.eq(1),
                    self.state.eq(State.WaitSecondByte),
                ]
            with m.Elif((self.state == State.WaitSecondByte) | (self.state == State.Prefetch)):
                m.d.sync += [
                    self.o_second_clock.eq(1),
                    self.state.eq(State.ExecutingMicrocode),
                ]
            with m.Elif(self.state == State.ExecutingMicrocode):
                # Loader will stall here, until the microcode executes an RNI (finish) or NXT (prefetch)
                with m.If(self.i_rni | self.i_nxt):
                    m.d.sync += [
                        self.o_first_clock.eq(1),
                        self.state.eq(Mux(self.i_rni, State.WaitSecondByte, State.Prefetch)),
                    ]
        with m.Elif(self.state == State.ExecutingMicrocode):
            with m.If(self.i_rni): # Reached the end of microcode but the queue is empty
                m.d.sync += self.state.eq(State.WaitFirstByte)
        with m.Elif(self.state == State.Prefetch):
            with m.If(self.i_rni):
                m.d.sync += self.state.eq(State.WaitSecondByte)

        return m

if __name__ == "__main__":
    from amaranth.sim import Simulator

    loader = InstructionLoader()

    def bench():
        yield loader.i_queue_ready.eq(0)
        for _ in range(8):
            yield

        # load one byte
        yield loader.i_queue_ready.eq(1)
        yield
        yield loader.i_queue_ready.eq(0)
        for _ in range(8):
            yield

        # load another byte
        yield loader.i_queue_ready.eq(1)
        yield
        yield loader.i_queue_ready.eq(0)

        for _ in range(8):
            yield

        # finish microcode
        yield loader.i_rni.eq(1)
        yield
        yield loader.i_rni.eq(0)

        for _ in range(8):
            yield

        # now try it with a full queue
        yield loader.i_queue_ready.eq(1)
        for _ in range(4):
            yield
        yield loader.i_rni.eq(1)
        yield
        yield loader.i_rni.eq(0)
        for _ in range(4):
            yield

        # and with a prefetch
        yield loader.i_nxt.eq(1)
        yield
        yield loader.i_nxt.eq(0)
        for _ in range(8):
            yield

    sim = Simulator(loader)
    sim.add_clock(1e-6) # 1 MHz
    sim.add_sync_process(bench)

    with sim.write_vcd("loader.vcd"):
        sim.run()
