#!/usr/bin/env python
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import logging
import re
import requests
import os
import urlparse
from lxml.html import etree, HTMLParser
import sys

WINPYTHON_LIBS_URL = "http://www.lfd.uci.edu/~gohlke/pythonlibs/"
JS_CALL_RGX = re.compile("javascript:dl[(](?P<char_codes>\\S+)\\s+\"(?P<encoded_link>[^\"]+)\"[)]")
PKG_NAME_RGX = re.compile("^(.*?)-(?:[0-9]|Py)")
LINK_XPATH = "//a[@href][@onclick][@title]"

logging.getLogger().setLevel(logging.DEBUG)


def fetch_winpython_lib_page():
    """
    Fetch the Windows Python compiled libraries page and return the parsed element tree.

    :return: The parsed element tree
    :rtype: :class:`lxml.html.Element`
    """
    resp = requests.get(WINPYTHON_LIBS_URL, timeout=30)
    tree = etree.fromstring(resp.content, HTMLParser())
    tree.make_links_absolute(resp.url)
    return tree


class WinPythonLibFinder(object):

    def __init__(self, element):
        self.element = element

    def get_matching_links(self, py_version=None, py_arch=None):
        py_version = py_version or '{0}.{1}'.format(*sys.version_info)
        py_arch = py_arch or len('{0:x}'.format(sys.maxint)) * 4
        other_arch = {"64": "32", "32": "64"}[py_arch]
        link_dict = {}
        for match in self.element.xpath(LINK_XPATH):
            title = match.get("title")
            if any(("Python {0}".format(py_version) not in title,
                    "{0} bit".format(py_arch) not in title,
                    "{0} bit".format(other_arch) in title)):
                continue
            file_name = match.text.replace(u"\u2011", "-")
            pkg_name_match = PKG_NAME_RGX.search(file_name)
            if pkg_name_match is None:
                continue
            package_name = pkg_name_match.group(1)
            link_dict[package_name] = self.decode_link(match)
        return link_dict

    def decode_link(self, link_element):
        js_call = link_element.get("onclick")
        js_call_dict = JS_CALL_RGX.match(js_call).groupdict()
        js_call_dict["char_codes"] = eval(js_call_dict["char_codes"].rstrip(","))
        decoded_chars = []
        for char in js_call_dict["encoded_link"]:
            decoded_char = js_call_dict["char_codes"][ord(char) - 48]
            decoded_chars.append(chr(decoded_char))
        decoded_link = "".join(decoded_chars)
        actual_link = urlparse.urljoin(WINPYTHON_LIBS_URL, decoded_link)
        return actual_link

    def list_packages(self, py_version=None, py_arch=None):
        matching_links = self.get_matching_links(py_version, py_arch)
        for package_name, package_url in sorted(matching_links.items()):
            print "Package {0!r} -> {1!r}".format(package_name, package_url)

    def download_package(self, package_name, no_proxies=False, py_version=None, py_arch=None):
        matching_links = self.get_matching_links(py_version, py_arch)
        if package_name not in matching_links:
            raise Exception("ERROR: Package {0!r} not in available packages!".format(package_name))
        package_url = matching_links[package_name]
        package_filename = os.path.split(urlparse.urlparse(package_url).path)[-1]
        dest_path = os.path.abspath(os.path.join(os.path.curdir, package_filename))
        print "Downloading package {0!r} to {1}".format(package_name, dest_path)
        request_args = {"url": package_url, "headers": {"User-Agent": "Mozilla/5.0"}}
        if no_proxies:
            request_args["proxies"] = {"http": None, "https": None, "ftp": None}
        resp = requests.get(**request_args)
        with open(dest_path, "wb") as f:
            f.write(resp.content)
        print "Download completed successfully!"


def main(args=None):
    args = args or sys.argv[1:]
    parser = ArgumentParser(prog="WinPython Library Finder",
                            description="Finds binary Python modules for specific Python versions and architectures",
                            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("-p", "--pyver",
                        dest="py_version",
                        default="{0}.{1}".format(*sys.version_info),
                        choices=["2.6", "2.7", "3.1", "3.2", "3.3", "3.4"],  # TODO: Use the web page to find these
                        help="The Python version to get libraries for")
    parser.add_argument("-a", "--pyarch",
                        dest="py_arch",
                        default=len("{0:x}".format(sys.maxint)) * 4,
                        choices=["32", "64"],
                        help="The architecture of the Python build being targeted")
    parser.add_argument("-l", "--list",
                        dest="list_only",
                        action="store_true",
                        default=False,
                        help="List the names of available libraries")
    parser.add_argument("-z", "--zero-out-proxies",
                        dest="no_proxies",
                        action="store_true",
                        default=False,
                        help="Zero out/undefine any proxies defined in the current environment")
    parser.add_argument("libraries",
                        nargs="*",
                        metavar="LIB",
                        help="The names of libraries to download")
    parser_ns = parser.parse_args(args)
    print "Fetching initial index page..."
    finder = WinPythonLibFinder(fetch_winpython_lib_page())
    if parser_ns.list_only or not parser_ns.libraries:
        finder.list_packages(py_version=parser_ns.py_version, py_arch=parser_ns.py_arch)
        return
    for lib_name in parser_ns.libraries:
        finder.download_package(lib_name,
                                no_proxies=parser_ns.no_proxies,
                                py_version=parser_ns.py_version,
                                py_arch=parser_ns.py_arch)


if __name__ == "__main__":  # pragma: no cover
    main()
