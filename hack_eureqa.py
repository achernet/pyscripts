#!/usr/bin/env python
import struct
import sys
from cStringIO import StringIO
from argparse import ArgumentParser

MAX_COLUMNS = 420
MAX_ROWS = 8675309
COL_BYTES = struct.pack("I", MAX_COLUMNS)
ROW_BYTES = struct.pack("I", MAX_ROWS)

'''
PATCHES = [{"start": 0xD68F9, "old": "\xc7\x02\x05\x00\x00\x00", "new": "\xc7\x02" + COL_BYTES},
           {"start": 0xD68FF, "old": "\x41\xc7\x00\xc8\x00\x00\x00", "new": "\x41\xc7\x00" + ROW_BYTES},
           {"start": 0xDD706, "old": "\xb9\xc8\x00\x00\x00\x33\xd2", "new": "\xb9" + ROW_BYTES + "\x33\xd2"},
           {"start": 0xF363D, "old": "\xc7\x44\x24\x40\x05\x00\x00\x00", "new": "\xc7\x44\x24\x40" + COL_BYTES},
           {"start": 0xF3645, "old": "\xc7\x44\x24\x20\xc8\x00\x00\x00", "new": "\xc7\x44\x24\x20" + ROW_BYTES},
           {"start": 0x10D530, "old": "\xc7\x44\x24\x24\x05\x00\x00\x00", "new": "\xc7\x44\x24\x24" + COL_BYTES},
           {"start": 0x10D538, "old": "\xc7\x44\x24\x2c\xc8\x00\x00\x00", "new": "\xc7\x44\x24\x2c" + ROW_BYTES}]
'''

PATCHES = [{"start": 0x40619E, "old": "\xc7\x06\x05\x00\x00\x00", "new": "\xc7\x06" + COL_BYTES},
           {"start": 0x4061AB, "old": "\xc7\x02\xc8\x00\x00\x00", "new": "\xc7\x02" + ROW_BYTES},
           {"start": 0x97BE6, "old": "\xc7\x85\x9c\xfb\xff\xff\xc8\x00\x00\x00", "new": "\xc7\x85\x9c\xfb\xff\xff" + ROW_BYTES},
           {"start": 0x97C3C, "old": "\xc7\x85\x9c\xfb\xff\xff\x05\x00\x00\x00", "new": "\xc7\x85\x9c\xfb\xff\xff" + COL_BYTES}]

def apply_patches(buf, patches):
    for patch in patches:
        first_index = patch["start"]
        last_index = patch["start"] + len(patch["old"]) - 1
        if len(patch["old"]) != len(patch["new"]):
            raise Exception("Lengths of old and new patches must be equal (patch: {0:#x}".format(first_index))
        buf.seek(first_index, 0)
        bufData = buf.read(last_index + 1 - first_index)
        if bufData not in (patch['old'], patch['new']):
            exc_fmt = "Unexpected data found for patch {0:#x} - must match old or new data"
            raise Exception(exc_fmt.format(first_index))
        buf.seek(first_index, 0)
        buf.write(patch["new"])
    return buf


def main(args=None):
    args = args or sys.argv[1:]
    parser = ArgumentParser(prog="hack_eureqa.py",
                            description="Self-explanatory. Use at your own risk!")
    parser.add_argument('-i', '--input-file', help='The input file')
    parser.add_argument('-o', '--output-file', help='The output file')
    parser_ns = parser.parse_args(args)
    with open(parser_ns.input_file, 'rb') as f:
        file_buffer = StringIO()
        file_buffer.write(f.read())
    file_buffer = apply_patches(file_buffer, PATCHES)
    with open(parser_ns.output_file, 'wb') as f:
        f.write(file_buffer.getvalue())


if __name__ == "__main__":  # pragma: no cover
    main()
