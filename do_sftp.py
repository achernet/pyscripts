#!/usr/bin/env python
from argparse import ArgumentParser
try:
    import sh
    SUFFIX = ""
except ImportError:
    import pbs as sh
    SUFFIX = ".exe"
import os
import sys


class RemoteSender(object):

    def __init__(self, source_file, dest_file, password):
        self.aggregated = ""
        self.unbuffered_stdout = os.fdopen(sys.stdout.fileno(), "wb", 0)
        self.source_file = source_file
        self.dest_file = dest_file
        self.state = 0
        self.password = password

    def ssh_interact(self, char, stdin):
        self.unbuffered_stdout.write(char.encode())
        self.aggregated += char
        if self.aggregated.endswith("password: "):
            stdin.put(self.password)
            stdin.put("\n")
            self.state = 1
        elif self.aggregated.endswith("sftp> ") and self.state == 1:
            stdin.put("put {0!r} {1!r}\n".format(self.source_file, self.dest_file))
            self.state = 2
        elif self.aggregated.endswith("sftp> ") and self.state == 2:
            stdin.put("exit\n")
            self.state = 3


def parse_args(args):

    def parse_site(remote_site):
        site_parts = remote_site.split(":")
        if site_parts[-1].isdigit():
            return ["-P", site_parts[-1], ":".join(site_parts[:-1])]
        else:
            return [":".join(site_parts)]

    ap = ArgumentParser("SFTP uploader for my site!")
    ap.add_argument("-s", "--source", help="The source (local) path")
    ap.add_argument("-d", "--dest", help="The destination (remote) path")
    ap.add_argument("-u", "--user", help="The remote user name")
    ap.add_argument("-p", "--password", help="The remote user password")
    ap.add_argument("-r", "--remote", help="The remote site, in the form of host:port", type=parse_site)
    parser_ns = ap.parse_args(args)
    parser_ns.url = "{0}@{1}".format(parser_ns.user, parser_ns.remote[-1])
    return parser_ns


def main(args):
    parser_ns = parse_args(args)
    sender = RemoteSender(parser_ns.source, parser_ns.dest, parser_ns.password)
    command = sh.Command('sftp' + SUFFIX).bake(parser_ns.remote[:-1], parser_ns.url)
    process = command(_out=sender.ssh_interact, _out_bufsize=0, _tty_in=True)
    process.wait()


if __name__ == "__main__":
    main(sys.argv[1:])
