from amaranth import *
from enum import Enum

class BIURegs(Enum):
    CS = 0 # Code segment
    DS = 1 # Data segment
    SS = 2 # Stack segment
    ES = 3 # Extra segment
    IP = 4 # Instruction pointer (well, it actually points to the next queue fetch)
           # the real PC is calculated when needed by subtracting the unused queue entries
    IND = 5 # Internal reg: indirect
    OPR = 6 # Internal reg: operand

    Queue0 = 7 # Instruction queue entries 0-1
    Queue1 = 8 # Instruction queue entries 2-3
    Queue2 = 9 # Instruction queue entries 4-5

    Queue = 7 # Instruction queue
    None_ = 10 # No register


class BusRegFile(Elaboratable):
    """
        The bus register file is a 10x16 register file that is used to store
        segment registers, the instruction pointer, a few internal registers and the instruction queue

        There is one write 16bit write port.
        There are two read ports:
           - A 16bit read port for registers 0-6 (CS, DS, SS, ES, IP, IND, OPR)
           - An 8bit read port for the instruction queue (in registers 7-9)

        On an 8088, the last instruction queue entry has been repurposed as a buffer register
    """
    def __init__(self, is_8088 = False):
        self.is_8088 = is_8088

        # write port
        self.i_write_en = Signal()
        self.i_write = Signal(3)
        self.i_write_data = Signal(16)

        # b read port
        self.i_b_read = Signal(3)
        self.o_b_bus = Signal(16)

        # q read port
        self.i_q_read = Signal(3)
        self.o_qbus = Signal(8)

        # private
        num_regs = 9 if is_8088 else 10

        def get_default(reg):
            match reg:
                case BIURegs.IP: return 0xfff0
                case BIURegs.CS: return 0xf000
                case _ : return 0xcccc



        self.register_file = Array([Signal(16, name=f"Reg_{BIURegs(i).name}", reset=get_default(i)) for i in range(num_regs)])



    def elaborate(self, platform):
        m = Module()

        # write port
        with m.If(self.i_write_en):
            m.d.sync += self.register_file[self.i_write].eq(self.i_write_data)

        # b read port
        m.d.sync += self.o_b_bus.eq(self.register_file[self.i_b_read])

        # q read port
        q_word = Signal(16)
        if self.is_8088:
            # the 8088 only has four queue entries (2 16bit words)
            m.d.comb += q_word.eq(self.register_file[self.i_q_read[2]]),
        else:
            m.d.comb += q_word.eq(self.register_file[self.i_q_read[1:]]),

        m.d.comb += [
            self.o_qbus.eq(Mux(self.i_q_read[0], q_word[0:7], q_word[8:])),
        ]

        return m