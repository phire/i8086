#!/usr/bin/env python3

# Reengine did the hard work of extracting the microcode bits from the 8086/8088 dies, and reversing it
#     https://www.reenigne.org/blog/8086-microcode-disassembled
# This file is a re-implementation of Reengine's 8086_micocode.cpp
#   https://github.com/reenigne/reenigne/blob/479807ae633df2456b81e949aaef344ddad74f48/8088/8086_microcode/8086_microcode.cpp
#

from enum import Enum, auto


def read_microcode():
    # If you look at a photo of the 8086 die, Reengine's microcode ROM extracts are laid out as:
    #
    # 84x128 microcode storage:
    #   <-----------64 cols------------->   <-----------64 cols------------->
    # +-----------------------------------+-----------------------------------+
    # |                                   |                                   |
    # |              l0a.txt              |              r0a.txt              | <- 24 rows
    # |                                   |                                   |
    # +-----------------------------------+-----------------------------------+
    # |                                   |                                   |
    # |              l1a.txt              |              r1a.txt              | <- 24 rows
    # |                                   |                                   |
    # +-----------------------------------+-----------------------------------+
    # |                                   |                                   |
    # |              l2a.txt              |              r2a.txt              | <- 24 rows
    # |                                   |                                   |
    # +-----------------------------------+-----------------------------------+
    # |              l3a.txt              |              r3a.txt              | <- Only 12 rows
    # +-----------------------------------+-----------------------------------+
    #
    # (the a files have 8086, the non-a files have 8088. They are mostly identical)
    # So we need to glue the files back together

    # Additionally, we need to convert it back to the original 512x21 layout
    # by splitting each 84 bit column into four 21 bit columns

    def read_half(half):
        # load left and right bitplanes into two 84x64 matrices
        half = ("".join([open(f"microcode/{half}{i}a.txt", "rt").read() for i in range(4)])).splitlines()

        # invert the bits
        half = [['0' if c == '1' else '1' for c in row] for row in half]

        # transpose to get 64 rows of 84 columns
        return [ "".join([half[x][y] for x in range(84)]) for y in range(64)]

    # interleave right halves and zip the lines together
    microcode = [row for zipped in zip(read_half('l'), read_half('r')) for row in zipped]

    # split each row into four 21 bit rows
    microcode = [ "".join([row[x] for x in range(3 - i, 84, 4)]) for row in microcode for i in range(4) ]

    # convert from binary ascii to int
    microcode = [ int(row, 2) for row in microcode]

    return reversed(microcode)

def read_column_selector():
    # and the extracts of the column selector are laid out as:

    # Column selection:
    # +-----+--------+--------+--------+--------+--------+--------+--------+-----+    ^
    # |     |        |        |        |        |        |        |        |     |    |
    # | 0t  | 1t.txt | 2t.txt | 3t.txt | 4t.txt | 5t.txt | 6t.txt | 7t.txt |  8t |    |
    # |  +  |   +    |   +    |   +    |   +    |   +    |   +    |   +    |  +  | 11 rows
    # |  b0 | 1b.txt | 2b.txt | 3b.txt | 4b.txt | 5b.txt | 6b.txt | 7b.txt |  8b |    |
    # |     |        |        |        |        |        |        |        |     |    |
    # +-----+--------+--------+--------+--------+--------+--------+--------+-----+    v
    #  8cols  16cols   16cols   16cols   16cols   16cols   16cols   16cols  8cols
    #
    # Each cell has two bits. One in t*, one in b* (top and bottom?)

    def read_horizontal(file):
        # read all 9 files
        files = [open(f"microcode/{i}{file}.txt", "rt").read().splitlines() for i in range(9)]

        # join all lines across all files to create a 128x11 matrix
        rows = ["".join(row) for row in zip(*files)]

        # transpose to get 11 rows of 128 columns
        return ["".join([rows[x][127-y] for x in range(11)]) for y in range(128)]

    selector = []

    for bot, top in zip(read_horizontal("b"), read_horizontal("t")):
        # Intel scrambled this to make the layout better. Lets rearrange back to a sensible order
        match_zero =  int(top[7] + bot[2] + bot[1] + bot[0] + top[5:7] + top[8:] + top[3:5], 2)
        match_one  =  int(bot[7] + top[2] + top[1] + top[0] + bot[5:7] + bot[8:] + bot[3:5], 2)

        selector.append((match_zero, match_one))

    return selector



microcode = read_microcode()
selector = read_column_selector()

class regNames(Enum):
    RA = 0x0        # ES
    RC = 0x1        # CS
    RS = 0x2        # SS - presumably, to fit pattern. Only used in RESET
    RD = 0x3        # DS
    PC = 0x4
    IND = 0x5
    OPR = 0x6
    no_dest = 0x7   # as dest only - source is Q
    A = 0x8         # AL
    C = 0x9         # CL? - not used
    E = 0xa         # DL? - not used
    L = 0xb         # BL? - not used
    tmpa = 0xc
    tmpb = 0xd
    tmpc = 0xe
    F = 0xf         # flags register
    X = 0x10        # AH
    B = 0x11        # CH? - not used
    M = 0x12
    R = 0x13        # source specified by modrm and direction, destination specified by r field of modrm
    tmpaL = 0x14    # as dest only - source is SIGMA
    tmpbL = 0x15    # as dest only - source is ONES
    tmpaH = 0x16    # as dest only - source is CR
    tmpbH = 0x17    # as dest only - source is ZERO
    XA = 0x18       # AX
    BC = 0x19       # CX
    DE = 0x1a       # DX
    HL = 0x1b       # BX
    SP = 0x1c       # SP
    MP = 0x1d       # BP
    IJ = 0x1e       # SI
    IK = 0x1f       # DI

class srcRegNames(Enum):
    Q = 0x7 # read next byte from prefetch queue
    SIGMA = 0x14 # result of last ALU operation
    ONES = 0x15 # all bits 1
    CR = 0x16   #
    ZERO = 0x17 # all bits 0


def disassemble():
    # This function mostly replicates Reengine's 8086_microcode.cpp
    # it's mostly useful for verifying the loading code is correct
    for addr, d in enumerate(microcode):
        print(f"{addr:03x} ", end='')
        for i in range(21):
            if 1 << (20 -i) & d != 0:
                print(chr(ord('A') + i), end='')
            else:
                print(' ', end='')
        print("       ", end='')

        if d == 0:
            print("                                     ", end='')
        else:
            s = ((d >> 13) & 1) + ((d >> 10) & 6) + ((d >> 11) & 0x18)
            dd = ((d >> 20) & 1) + ((d >> 18) & 2) + ((d >> 16) & 4) + ((d >> 14) & 8) + ((d >> 12) & 0x10)
            typ = (d >> 7) & 7
            if typ & 4 == 0:
                typ >>= 1

            if s == 0x15 and dd == 0x07: # "ONES  -> Q" used as no-op move
                print("                ", end='')
            else:
                source = regNames(s).name

                if s in set(item.value for item in srcRegNames):
                    source = srcRegNames(s).name

                print(f"{source:5} -> {regNames(dd).name:7}", end='')

            print("   ", end='')

            if not (typ == 4 and (d & 0x7f) == 0x7f):
                print(f"{typ}   ", end='')

            match typ:
                case 0 | 5 | 7: # Microcode control flow
                    match d >> 4 & 0xf:
                        case 0x00: print("F1ZZ", end='') # jump if REPNE flag differs from ZF?
                        case 0x01: print("MOD1", end='') # jump if short offset in effective address
                        case 0x02: print("L8  ", end='') # jump if short immediate (skip 2nd byte from Q)
                        case 0x03: print("Z   ", end='') # jump if zero (used in IMULCOF/MULCOF)
                        case 0x04: print("NCZ ", end='') # jump if internal counter not zero
                        case 0x05: print("TEST", end='') # jump if -TEST pin not asserted
                        case 0x06: print("OF  ", end='') # jump if overflow flag is set
                        case 0x07: print("CY  ", end='') # jump if carry
                        case 0x08: print("UNC ", end='') # unconditional jump
                        case 0x09: print("NF1 ", end='') # jump if F1 flag is not active (could also be used in long jump but isn't)
                        case 0x0a: print("NZ  ", end='') # jump if not zero (used in JCXZ and LOOP)
                        case 0x0b: print("X0  ", end='') # jump if bit 3 of opcode is 1
                        case 0x0c: print("NCY ", end='') # jump if no carry
                        case 0x0d: print("F1  ", end='') # jump if either F1 flag is active
                        case 0x0e: print("INT ", end='') # jump if interrupt is pending
                        case 0x0f: print("XC  ", end='') # jump if condition based on low 4 bits of opcode
                    print("  ", end='')
                    if typ == 5: # long jump
                        typ5 = ["FARCALL", "NEARCALL", "RELJMP", "EAOFFSET", "EAFINISH", "FARCALL2", "INTR", "INT0", "RPTI", "AAEND"]
                        print(f"{typ5[d & 0xf]:8}", end='')
                    elif typ == 7: # long call
                        typ7 = [
                            "FARRET",   # 0
                            "RPTS",     # 1
                            "CORX",     # 2: unsigned multiply tmpc and tmpb, result in tmpa:tmpc
                            "CORD",     # 3: unsigned divide tmpa:tmpc by tmpb, quotient in ~tmpc, remainder in tmpa
                            "PREIMUL",  # 4: abs tmpc and tmpb, invert F1 if product negative
                            "NEGATE",   # 5: negate product tmpa:tmpc
                            "IMULCOF",  # 6: clear carry and overflow flags if product of signed multiply fits in low part, otherwise set them
                            "MULCOF",   # 7: clear carry and overflow flags if product of unsigned multiply fits in low part, otherwise set them
                            "PREIDIV",  # 8: abs tmpa:tmpc and tmpb, invert F1 if one or the other but not both were negative
                            "POSTIDIV", # 9: negate ~tmpc if F1 set
                        ]
                        print(f"{typ7[d & 0xf]:8}", end='')
                    else: # type 0: short (conditional or unconditional) jump
                        print(f"{d & 0xf:4d}    ", end='')
                case 4 if (d & 0x7f) == 0x7f:
                    print("                  ", end='')
                case 4: # misc operations
                    typ4_upper = [
                        "MAXC",     # 0: set internal counter to 15 or 7 depending on word size
                        "FLUSH",    # 1: flush prefetch queue
                        "CF1",      # 2: invert F1 flag
                        "CITF",     # 3: clear interrupt and trap flags
                        "RCY",      # 4: reset carry
                        "???",      # 5
                        "CCOF",     # 6: clear carry and overflow
                        "SCOF",     # 7: set carry and overflow
                        "WAIT",     # 8: not sure what this does
                        "???",      # 9
                        "???",      # a
                        "???",      # b
                        "???",      # c
                        "???",      # d
                        "???",      # e
                        "none",     # f
                    ]
                    typ4_lower = [
                        "RNI",      # 0: Run Next Instruction (current one is finished)
                        "WB,NX",    # 1: write back to EA, next instruction
                        "CORR",     # 2: correct PC based on number of bytes in prefetch queue (always preceded by SUSP)
                        "SUSP",     # 3: suspend prefetching
                        "RTN",      # 4: return to saved location
                        "NX",       # 5: next instruction is the last in the microcode routine, begin processing next opcode
                        "???",      # 6
                        "none",     # 7
                    ]
                    print(f"{typ4_upper[(d >> 3) & 0xf]:6}", end='') # od14 od15 od16 od17   d3 d4 d5 d6
                    print(f"{typ4_lower[d & 0x7]:8}", end='') # od18 od19 od20  d0 d1 d2
                case 1:  # select ALU operation and input register
                    alu = [
                        "ADD",      # 0
                        "OR",       # 1: not used in microcode
                        "ADC",      # 2
                        "SBB",      # 3: not used in microcode
                        "AND",      # 4: 0x09e
                        "SUBT",     # 5
                        "XOR",      # 6: not used in microcode
                        "CMP",      # 7: not used in microcode
                        "ROL",      # 8: not used in microcode
                        "ROR",      # 9: not used in microcode
                        "LRCY",     # a: rotate left through carry
                        "RRCY",     # b: rotate right through carry
                        "SHL",      # c: not used in microcode
                        "SHR",      # d: not used in microcode
                        "SETMO",    # e: not used in microcode
                        "SAR",      # f: not used in microcode
                        "PASS",     # 10: pass argument through to SIGMA
                        "XI",       # 11: opcode-dependent operation
                        "???",      # 12
                        "???",      # 13
                        "DAA",      # 14: not used in microcode
                        "DAS",      # 15: not used in microcode
                        "AAA",      # 16: not used in microcode
                        "AAS",      # 17: not used in microcode
                        "INC",      # 18
                        "DEC",      # 19
                        "COM1",     # 1a: ones complement aka NOT
                        "NEG",      # 1b: negate
                        "INC2",     # 1c
                        "DEC2",     # 1d
                    ]
                    input_reg = [ "tmpa", "tmpb",  "tmpc", "????"]
                    nx = ["    ", ", NX"] # next instruction is the last in the microcode routine, begin processing next opcode

                    print(f"{alu[d >> 3 & 0x1f]:4}  {input_reg[(d >> 1) &3]}{nx[d&1]}", end='')
                case 6: # bus operations
                    a = [
                        "R", # initiate memory read cycle
                        "?1"
                        "?2",
                        "IRQ", # initial special IRQ acknowledge bus cycle
                        "?4",
                        "w", # initiate memory write cycle
                        "W,RNI", # initiate memory write cycle
                        "?7"
                    ]
                    b = [
                        "DA", # ES
                        "D0", # segment 0 (used for interrupt vectors and port IO)
                        "DS", # DS
                        "DD"  # DS by default, overridable/
                    ]
                    c = [
                        "P2", # Increment IND by 2
                        "BL", # Adjust IND according to word size and DF
                        "M2", # Decrement IND by 2
                        "P0", # Don't adjust IND
                    ]
                    print(f"{a[(d >> 4) & 7]:5} {b[(d >> 2) & 3]},{c[d & 3]:3}  ", end='')

        if ((d >> 10) & 1) != 0:
            print(" F  ", end='') # Update flags Register
        else:
            print("    ", end='')

        if (addr % 4) == 0:
            zeros, ones = selector[addr // 4]
            for mask in [1 << 10-n for n in range(11)]:
                if mask & zeros and mask & ones:
                    print("?", end='')
                elif mask & zeros:
                    print("0", end='')
                elif mask & ones:
                    print("1", end='')
                else:
                    print("*", end='')

                if mask == 0x4:
                    print(".", end='')
        else:
            print(" " * 12, end='')
        print("  ")

if __name__ == "__main__":
    disassemble()
