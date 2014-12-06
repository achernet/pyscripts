#!/usr/bin/env python
from argparse import ArgumentParser
try:
    import sh
    SUFFIX = ""
except ImportError:
    import pbs as sh
    SUFFIX = ".exe"
import os
import logging
import re
from os import path as osp
import urlparse
from lxml.html import etree, HTMLParser
import sys
import requests

WINPYTHON_LIBS_URL = "http://www.lfd.uci.edu/~gohlke/pythonlibs/"
logging.getLogger().setLevel(logging.DEBUG)


def fetch_winpython_lib_page():
    """
    Fetch the Windows Python compiled libraries page and return the parsed element tree.
    """
    resp = requests.get(WINPYTHON_LIBS_URL, timeout=30)
    tree = etree.fromstring(resp.content, HTMLParser())
    tree.make_links_absolute(resp.url)
    return tree


class WinPythonLibFinder(object):

    JS_CALL_RGX = re.compile("javascript:dl[(](?P<char_codes>\\S+)\\s+\"(?P<encoded_link>[^\"]+)\"[)]")

    def __init__(self, tree=None):
        if tree is None:
            tree = fetch_winpython_lib_page()
        self.element = tree

    def get_links_for_package(self, package_name):
        xpath_arg = "//li[a[@id={0!r}]]/ul/li/a[@href]".format(package_name.lower())
        elems = self.element.xpath(xpath_arg)
        links_dict = {}
        for elem in elems:
            decoded_url = self.decode_link(elem)
            complete_url = urlparse.urljoin(WINPYTHON_LIBS_URL, decoded_url)
            elem.set("href", complete_url)
            links_dict[elem.text] = elem.get("href")
        return links_dict

    def decode_link(self, link_element):
        js_call = link_element.get("onclick")
        js_call_dict = self.JS_CALL_RGX.match(js_call).groupdict()
        js_call_dict["char_codes"] = eval(js_call_dict["char_codes"].rstrip(","))
        decoded_chars = []
        for char in js_call_dict["encoded_link"]:
            decoded_char = js_call_dict["char_codes"][ord(char) - 48]
            decoded_chars.append(chr(decoded_char))
        decoded_link = "".join(decoded_chars)
        return decoded_link


class RemoteSender(object):

    def __init__(self, password, command, link):
        self.aggregated = ""
        self.unbuffered_stdout = os.fdopen(sys.stdout.fileno(), "wb", 0)
        self.command = command
        self.link = link
        self.password = password
        self.remote_finished = False
        self.ssh_finished = False

    def ssh_interact(self, char, stdin):
        self.unbuffered_stdout.write(char.encode())
        self.aggregated += char
        if self.aggregated.lower().endswith("password: "):
            stdin.put(self.password)
            stdin.put("\n")
            return
        if self.aggregated.lower().endswith("$") and not self.remote_finished and not self.ssh_finished:
            stdin.put(self.command)
            stdin.put(" ")
            stdin.put(repr(self.link))
            stdin.put("\n")
            self.remote_finished = True
            return
        if self.aggregated.lower().endswith("$") and self.remote_finished and not self.ssh_finished:
            stdin.put("exit")
            stdin.put("\n")
            self.ssh_finished = True
            self.remote_finished = False
            return


def parse_args(args):

    def parse_site(remote_site):
        site_parts = remote_site.split(":")
        if site_parts[-1].isdigit():
            return ["-p", site_parts[-1], ":".join(site_parts[:-1])]
        else:
            return [":".join(site_parts)]

    ap = ArgumentParser("Proxy a download via SSH from a given server")
    # ap.add_argument("-s", "--source", help="The source (local) path")
    # ap.add_argument("-d", "--dest", help="The destination (remote) path")
    ap.add_argument("-u", "--user", help="The remote user name")
    ap.add_argument("-p", "--password", help="The remote user password")
    ap.add_argument("-r", "--remote", help="The remote site, in the form of host:port", type=parse_site)
    ap.add_argument("-l", "--link", help="The link to the download to proxy")
    ap.add_argument("-c", "--command", default="aria2c",
                    help="The command to run on the proxy server to download the file")
    ap.add_argument("-S", "--skip-ssh", default=False, action="store_true",
                    help="Set this to true if the remote server already has the file")
    parser_ns = ap.parse_args(args)
    parser_ns.url = "{0}@{1}".format(parser_ns.user, parser_ns.remote[-1])
    return parser_ns


def main(args):
    parser_ns = parse_args(args)
    sender = RemoteSender(parser_ns.password, parser_ns.command, parser_ns.link)
    ssh_arg = "\"{0.command} {0.link!r}\"".format(parser_ns)
    command = sh.Command("ssh" + SUFFIX).bake(parser_ns.remote[:-1],
                                              "--user-agent", "Mozilla/5.0",
                                              parser_ns.url)
    logging.info("Running command: %s", command)
    ssh_proc = command(_out=sender.ssh_interact, _out_bufsize=0, _tty_in=True)
    ssh_proc.wait()
    scp_remote_args = parser_ns.remote[:-1]
    scp_remote_args.append("-v")
    if '-p' in scp_remote_args:
        arg_index = scp_remote_args.index("-p")
        scp_remote_args[arg_index] = "-P"
    scp_remote_path = repr(osp.split(urlparse.urlsplit(parser_ns.link).path)[-1])
    scp_command = sh.Command("scp" + SUFFIX).bake(scp_remote_args,
                                                  ":".join([parser_ns.url, scp_remote_path]),
                                                  scp_remote_path)
    scp_proc = scp_command(_out=sender.ssh_interact, _out_bufsize=0, _tty_in=True)
    scp_proc.wait()


if __name__ == "__main__":
    main(sys.argv[1:])
