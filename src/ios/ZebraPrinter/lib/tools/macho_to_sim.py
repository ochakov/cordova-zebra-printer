#!/usr/bin/env python3
"""Rewrite a 64-bit Mach-O object file so the linker treats it as built for the
iOS *simulator*: LC_VERSION_MIN_IPHONEOS (16 bytes) is replaced by
LC_BUILD_VERSION{platform=IOSSIMULATOR} (24 bytes).  Because object files have
no slack after the load commands, every file offset after them is shifted.

usage: macho_to_sim.py <in.o> <out.o>
"""
import struct, sys

MH_MAGIC_64 = 0xfeedfacf
MH_OBJECT = 1
LC_SEGMENT_64 = 0x19
LC_SYMTAB = 0x2
LC_DYSYMTAB = 0xb
LC_UUID = 0x1b
LC_VERSION_MIN_IPHONEOS = 0x25
LC_SOURCE_VERSION = 0x2a
LC_LINKER_OPTION = 0x2d
LC_BUILD_VERSION = 0x32
LINKEDIT_DATA = {0x1d, 0x1e, 0x26, 0x29, 0x2b, 0x2e, 0x80000033, 0x80000034}
NO_OFFSETS = {LC_UUID, LC_SOURCE_VERSION, LC_LINKER_OPTION, LC_VERSION_MIN_IPHONEOS, LC_BUILD_VERSION}
PLATFORM_IOS = 2
PLATFORM_IOSSIMULATOR = 7


def convert(data: bytes) -> bytes:
    magic, cputype, cpusub, filetype, ncmds, sizeofcmds, flags, _ = struct.unpack_from('<8I', data, 0)
    if magic != MH_MAGIC_64:
        raise SystemExit('not a 64-bit little-endian Mach-O (magic 0x%x)' % magic)
    if filetype != MH_OBJECT:
        raise SystemExit('not an MH_OBJECT file')
    hdr = 32
    cmds_end = hdr + sizeofcmds
    cmds, off = [], hdr
    for _ in range(ncmds):
        cmd, cmdsize = struct.unpack_from('<II', data, off)
        cmds.append((off, cmd, cmdsize))
        off += cmdsize
    assert off == cmds_end, 'load command sizes do not add up'

    vm = [c for c in cmds if c[1] == LC_VERSION_MIN_IPHONEOS]
    bv = [c for c in cmds if c[1] == LC_BUILD_VERSION]
    if bv and not vm:                      # modern object: patch platform in place
        out = bytearray(data)
        for (o, _, _) in bv:
            if struct.unpack_from('<I', out, o + 8)[0] == PLATFORM_IOS:
                struct.pack_into('<I', out, o + 8, PLATFORM_IOSSIMULATOR)
        return bytes(out)
    if len(vm) != 1 or bv:
        raise SystemExit('unexpected version load commands: vm=%d bv=%d' % (len(vm), len(bv)))

    vm_off, _, vm_size = vm[0]
    assert vm_size == 16
    minos, sdk = struct.unpack_from('<II', data, vm_off + 8)
    new_cmd = struct.pack('<6I', LC_BUILD_VERSION, 24, PLATFORM_IOSSIMULATOR, minos, sdk, 0)
    grow = 24 - 16

    # keep the file-offset alignment of the most aligned section
    max_align = 8
    for (o, cmd, cmdsize) in cmds:
        if cmd == LC_SEGMENT_64:
            nsects = struct.unpack_from('<I', data, o + 64)[0]
            for s in range(nsects):
                max_align = max(max_align, 1 << struct.unpack_from('<I', data, o + 72 + s * 80 + 52)[0])
    unit = min(max_align, 4096)
    shift = ((grow + unit - 1) // unit) * unit
    pad = shift - grow

    def bump32(buf, pos):
        v = struct.unpack_from('<I', buf, pos)[0]
        if v:
            assert v >= cmds_end, 'offset %d inside the header' % v
            struct.pack_into('<I', buf, pos, v + shift)

    def bump64(buf, pos):
        v = struct.unpack_from('<Q', buf, pos)[0]
        if v:
            assert v >= cmds_end, 'offset %d inside the header' % v
            struct.pack_into('<Q', buf, pos, v + shift)

    new_cmds = bytearray()
    for (o, cmd, cmdsize) in cmds:
        chunk = bytearray(data[o:o + cmdsize])
        if cmd == LC_VERSION_MIN_IPHONEOS:
            chunk = bytearray(new_cmd)
        elif cmd == LC_SEGMENT_64:
            bump64(chunk, 40)                                   # fileoff
            nsects = struct.unpack_from('<I', chunk, 64)[0]
            for s in range(nsects):
                so = 72 + s * 80
                bump32(chunk, so + 48)                          # offset (0 for zerofill)
                if struct.unpack_from('<I', chunk, so + 60)[0]:  # nreloc
                    bump32(chunk, so + 56)                      # reloff
        elif cmd == LC_SYMTAB:
            bump32(chunk, 8)                                    # symoff
            bump32(chunk, 16)                                   # stroff
        elif cmd == LC_DYSYMTAB:
            for pos in (32, 40, 48, 56, 64, 72):                # tocoff .. locreloff
                bump32(chunk, pos)
        elif cmd in LINKEDIT_DATA:
            bump32(chunk, 8)                                    # dataoff
        elif cmd in NO_OFFSETS:
            pass
        else:
            raise SystemExit('unhandled load command 0x%x' % cmd)
        new_cmds += chunk

    out = bytearray(data[:hdr])
    struct.pack_into('<I', out, 20, sizeofcmds + grow)
    out += new_cmds + b'\0' * pad + data[cmds_end:]
    return bytes(out)


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    with open(src, 'rb') as f:
        blob = f.read()
    with open(dst, 'wb') as f:
        f.write(convert(blob))
