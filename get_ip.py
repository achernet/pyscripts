#!/usr/bin/env python
import requests
import sys
from lxml.html import etree, HTMLParser


def main(args=None):
    """
    Get the IP of the machine calling this function.

    :return str: The IP of the caller
    """
    resp = requests.get("http://www.ip-details.com", timeout=5)
    resp.raise_for_status()
    tree = etree.fromstring(resp.content, HTMLParser())
    tree.make_links_absolute(resp.url)
    ipAddrText = tree.xpath("//div/h1[@class]/text()")
    try:
        return ipAddrText[0].split(":")[-1].strip()
    except Exception as e:
        print >> sys.stderr, "Error parsing URL content at {0!r}".format(resp.url)
        raise e

if __name__ == "__main__":
    print main()
