#!/usr/bin/env python3

from amaranth import *

from enum import Enum, auto

from bus_regfile import BIURegs, BusRegFile


class BIUMode(Enum):
    Idle = 0
    QueueFetchStart = auto()
    QueueFetchAddrCalc = auto()
    QueueFetchIPInc = auto()
    QueueFetch = auto()
    AddrCalc = auto()
    Read = auto()
    Write = auto()


class BusInterfaceUnit(Elaboratable):
    def __init__(self, is_8088 = False):

        # External signals - to outside 8086
        #############################################

        # External address bus
        self.o_addressbus = Signal(20)
        self.o_addressbus_valid = Signal()

        # External data bus
        self.o_data = Signal(8) if is_8088 else Signal(16)
        self.i_data = Signal(8) if is_8088 else Signal(16)

        # Internal signals - to other parts of 8086
        #############################################

        # Q bus, BIU's instruction queue to instruction decoder
        self.o_qbus = Signal(8)
        self.o_qbus_valid = Signal()
        self.i_qbus_take = Signal() # Take byte from instruction queue next cycle
        self.i_qbus_to_alu = Signal()

        # ALU bus, Between ALU and Bus Interface Unit
        self.i_alubus = Signal(16)
        self.o_alubus = Signal(16)
        self.o_alubus_rdy = Signal()

        # control
        self.i_sbus = Signal(3)
        self.i_dbus = Signal(3)

        self.i_add16 = Signal()
        self.i_add20 = Signal()


        # BIU Private internals
        #########################

        self.mode = Signal(BIUMode)
        self.next_mode = Signal(BIUMode)
        self.t_state = Signal(3)

        self.start_mem = Signal() # Latch the address on the next cycle

        # Q Control
        self.q_read_ptr = Signal(3)
        self.q_write_ptr = Signal(2) # writes are always 16 bit aligned
        self.q_empty = Signal(reset=1)
        self.q_count = Signal(3)
        self.q_odd = Signal()
        self.q_inc = Signal(2)


        # Registers
        self.register_file = BusRegFile(is_8088)

        self.adder_result = Signal(16)
        self.b_reg = Signal(16)
        self.c_reg = Signal(16)
        self.c_bus_src = Signal() # adder or memory


        self.is_8088 = is_8088


    def elaborate(self, platform):
        m = Module()
        m.submodules.register_file = self.register_file

        q_max = 4 if self.is_8088 else 6

        add20 = Signal()
        m.d.comb += [
            add20.eq(self.i_add20),
        ]

        # Connect Instruction queue to q bus
        m.d.comb += [
            self.o_qbus.eq(self.register_file.o_qbus),
            self.o_qbus_valid.eq(self.q_count > 0),
        ]

        with m.If(self.i_qbus_take):
            m.d.sync += [
                self.q_read_ptr.eq(Mux(self.q_read_ptr == q_max, 0, self.q_read_ptr + 1))
            ]

        m.d.comb += [self.q_inc.eq(0)] # default to 0 when not set elsewhere
        m.d.sync += self.q_count.eq(self.q_count + self.q_inc - self.i_qbus_take),

        # register file
        m.d.comb += [
            self.register_file.i_write_data.eq(Mux(self.c_bus_src, self.i_data, self.adder_result[0:16])),
            self.register_file.i_q_read.eq(self.q_read_ptr),
        ]

        # Currently we only support fetching the queue
        # TODO: Implement other BUI operations
        m.d.comb += self.next_mode.eq(Mux(
            self.q_count > (q_max - 1),
             BIUMode.Idle,
             BIUMode.QueueFetchAddrCalc
        ))

        m.d.comb += [
            self.register_file.i_b_read.eq(BIURegs.None_),
        ]

        m.d.sync += [
            self.register_file.i_write_en.eq(0),
            self.register_file.i_write.eq(BIURegs.None_),
        ]


        with m.Switch(self.mode):
            with m.Case(BIUMode.QueueFetchStart):
                m.d.comb += [
                    self.register_file.i_b_read.eq(BIURegs.IP),
                    self.c_reg.eq(Const(0)),
                ]
            with m.Case(BIUMode.QueueFetchAddrCalc):
                m.d.comb += [
                    self.register_file.i_b_read.eq(BIURegs.CS), # Add the code segment to IP
                    self.c_reg.eq(self.adder_result[0:16]), # IP is in adder_result
                ]
                m.d.sync += [
                    self.start_mem.eq(1),
                    self.mode.eq(BIUMode.QueueFetchIPInc),
                ]
            with m.Case(BIUMode.QueueFetchIPInc):
                q_odd_next = Signal()
                m.d.comb += [
                    q_odd_next.eq(self.c_reg[0]), # c_reg contains the IP
                    self.register_file.i_b_read.eq(BIURegs.IP),
                    self.c_reg.eq(Mux(q_odd_next, Const(2), Const(1))),
                ]

                m.d.sync += [
                    self.q_odd.eq(q_odd_next),

                    self.q_count.eq(self.q_count + 2),
                    self.c_bus_src.eq(0),
                    self.mode.eq(BIUMode.QueueFetch),
                    self.register_file.i_write.eq(BIURegs.IP),
                    self.register_file.i_write_en.eq(1),
                ]
                m.d.comb += add20.eq(1)
            with m.Case(BIUMode.QueueFetch):
                with m.If(self.t_state == 4):
                    m.d.comb += self.q_inc.eq(2 - self.q_odd)
                    m.d.sync += [
                        self.q_write_ptr.eq(self.q_write_ptr + 1),
                        # Intel manual says "5 or 6 bytes constitute a full queue in the 8086" which suggests the queue
                        # always does 16bit aligned writes, and just ignores the first byte if a jump results in an
                        # unaligned address
                        self.register_file.i_write.eq(BIURegs.Queue + self.q_write_ptr[1:]),

                        self.c_bus_src.eq(1),
                        self.register_file.i_write_en.eq(1),

                        self.q_empty.eq(0),
                        self.mode.eq(self.next_mode),
                    ]
            with m.Case(BIUMode.Idle):
                m.d.sync += self.mode.eq(self.next_mode)

        with m.If(self.start_mem):
            m.d.sync += [
                self.start_mem.eq(0),
                self.t_state.eq(1),
                self.o_addressbus.eq(self.adder_result),
                self.o_addressbus_valid.eq(1),
            ]

        # t state counter
        with m.If(self.t_state == 4):
            m.d.sync += self.t_state.eq(0)
        with m.Elif(self.t_state != 0):
            m.d.sync += self.t_state.eq(self.t_state + 1)

        m.d.comb += [
            self.b_reg.eq(self.register_file.o_b_bus),
        ]

        # Adder

        # The adder always does a 16 bit add
        m.d.comb += [
            self.adder_result.eq(self.b_reg + self.c_reg),

        ]

        return m


if __name__ == "__main__":
    from amaranth.sim import Simulator
    from amaranth.back import verilog


    bui = BusInterfaceUnit()

    with open("bui.v", "w") as f:
        f.write(verilog.convert(bui, ports=[
            bui.o_addressbus,
            bui.o_addressbus_valid,
            bui.o_data,
            bui.i_data,
            bui.o_qbus,
            bui.o_qbus_valid,
            bui.i_qbus_take,
            bui.i_qbus_to_alu,
            bui.i_alubus,
            bui.o_alubus,
            bui.o_alubus_rdy,
            bui.i_sbus,
            bui.i_dbus,
            bui.i_add16,
            bui.i_add20]
        ))

    mem = [i for i in range(256)]

    def bench():
        # let the queue fill up
        data = 0
        for i in range(20):
            t_state = yield bui.t_state
            match t_state:
                case 1:
                    addr = (yield bui.o_addressbus)
                    addr_trunk = addr & 0xfe
                    print(f"mem read: {addr} = {mem[addr_trunk]:x} {mem[addr_trunk + 1]:x}")
                    data = mem[addr_trunk] | (mem[addr_trunk + 1] << 8)
                case 3:
                    yield bui.i_data.eq(data)
            yield

        # take some bytes
        for i in range(6):
            qbus = yield bui.o_qbus
            print(f"qbus: {qbus}")
            yield bui.i_qbus_take.eq(1)
            yield
            yield bui.i_qbus_take.eq(0)
            yield


    sim = Simulator(bui)
    sim.add_clock(1e-6) # 1 MHz
    sim.add_sync_process(bench)

    with sim.write_vcd("bui.vcd"):
        sim.run()
