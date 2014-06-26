#!/usr/bin/env python
from argparse import ArgumentParser
import os
import sys
from datetime import datetime


def parse_args(args):
    ap = ArgumentParser()
    ap.add_argument("-i", "--int-date",
                    action="store_true",
                    default=False,
                    help="Print dates as integers")
    ap.add_argument("paths", nargs="*",
                    help="A list of 1+ paths")
    parser_ns = ap.parse_args(args)
    return parser_ns


def main(args):
    ns = parse_args(args)
    for path in (ns.paths or []):
        if not os.path.exists(path):
            continue
        try:
            statObj = os.stat(path)
        except Exception as e:
            errorFmt = "File {0!r} raised an exception: {1}"
            errorMsg = errorFmt.format(path, e)
            print >> sys.stderr, errorMsg
            continue
        statTime = max(statObj.st_ctime, statObj.st_mtime)
        if ns.int_date:
            statDt = statTime
        else:
            statDt = datetime.fromtimestamp(statTime)
        print "{0}\t\t{1}".format(path, statDt)


if __name__ == "__main__": # pragma: no cover
    main(sys.argv[1:])
