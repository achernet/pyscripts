#!/usr/bin/env python
import os
import sys


def main(args):
    mingw_paths = []
    while args:
        next_arg = args.pop()
        if next_arg == "mingw32":
            mingw_paths.append("/usr/i686-w64-mingw32/sys-root/mingw/bin")
        elif next_arg == "mingw64":
            mingw_paths.append("/usr/x86_64-w64-mingw32/sys-root/mingw/bin")
    env_paths = os.environ["PATH"].split(":")
    paths = mingw_paths[:]
    for path in env_paths:
        if path not in paths and "mingw" not in path:
            paths.append(path)
    print ":".join(paths)


if __name__ == "__main__":
    main(sys.argv[1:])
