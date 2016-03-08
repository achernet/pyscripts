#!/usr/bin/env python
import requests
from lxml.html import etree, HTMLParser
import re
import urlparse
import os
from collections import Iterable
import sys
import argparse
from sh import aria2c
import retrying


class SearchWrapper(object):

    def __init__(self, search_term):
        self.search_term = search_term
        self.session = requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.session.close()
        return False  # propagate any exceptions

    @retrying.retry(wait_fixed=50, stop_max_attempt_number=3,
                    retry_on_exception=lambda exc: isinstance(exc, requests.Timeout))
    def search_rpm_page(self, page=1):
        url = 'http://rpm.pbone.net/index.php3'
        cookie_dict = {'cookie_lang': '2',
                       'cookie_srodzaj': '4',
                       'cookie_dl': '100',
                       'cookie_simple': '1',
                       'cookies_accepted': 'T'}
        post_data = {'stat': 3,
                     'search': self.search_term,
                     'simple': 1,
                     'srodzaj': 4,
                     'limit': page}
        resp = self.session.post(url, data=post_data, cookies=cookie_dict,
                                 timeout=(5, 21))
        tree = etree.fromstring(resp.content, HTMLParser())
        tree.make_links_absolute(resp.url)
        return tree

    @staticmethod
    def parse_count(tree):
        match = tree.xpath('//div/br/following-sibling::text()')
        rgx = re.compile('of\\s+(\\d+)\\.')
        if match:
            count = rgx.search(' '.join(match))
        else:
            count = rgx.search(etree.tostring(tree))
        if not count:
            return 0
        return int(count.group(1))

    @staticmethod
    def parse_page_links(tree):
        links = tree.xpath('//center//@href')
        return sorted(set(links))

    @staticmethod
    def parse_rpm_links(tree, rpm_dict=None):
        links = tree.xpath('//div/table//a/@href')
        rpm_dict = rpm_dict or {}
        for link in links:
            pr = urlparse.urlparse(link)
            file_name = os.path.basename(pr.path)
            rpm_dict.setdefault(file_name, set()).add(pr.geturl())
        # remove redundant HTML entries
        for fname, flinks in rpm_dict.items():
            if os.path.splitext(fname)[-1] == '.rpm':
                rpm_html = '{0}.html'.format(fname)
                rpm_dict.pop(rpm_html, None)
        return rpm_dict


def _split_dotted(dstr):
    dparts = dstr.split('.')
    for i, dpart in enumerate(dparts):
        dsplitnums = [p for p in re.split('([^0-9]+)', dpart) if p]
        for j, dsplit in enumerate(dsplitnums):
            if dsplit.isdigit():
                dsplitnums[j] = int(dsplit)
        dparts[i] = tuple(dsplitnums)  # dsplitnums[0] if len(dsplitnums) == 1 else
    return tuple(dparts)


def name_key(*args):
    all_args = []
    for arg in args:
        if isinstance(arg, basestring):
            narg = [arg]
        elif isinstance(arg, Iterable):
            narg = arg
        else:
            narg = [arg]
        all_args.extend(narg)
    name = all_args[0].lower()
    major_parts = name.split('-')
    for i, major_part in enumerate(major_parts):
        if '.' not in major_part:
            continue
        major_parts[i] = _split_dotted(major_part)
    return major_parts


def do_download(mirrors):
    mirrors = sorted(mirrors) if not isinstance(mirrors, list) else mirrors
    name = mirrors[0]
    print('Downloading {0}...'.format(name))
    for line in aria2c(mirrors, _iter_noblock=True):
        if isinstance(line, basestring):
            sys.stdout.write(line)
            sys.stdout.flush()


def main(args=None):
    args = args or sys.argv[1:]
    ap = argparse.ArgumentParser(
        prog='search_rpms',
        description='Search rpm.pbone.net for RPMs matching a given query.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    ap.add_argument('query', help='The query to search for')
    ns = ap.parse_args(args)
    print('Searching for {0}...'.format(ns.query))
    rpm_dict = {}
    with SearchWrapper(ns.query) as sw:
        page = sw.search_rpm_page()
        count = sw.parse_count(page)
        num_pages = (count / 100) + bool(count % 100)
        print('Found {0} matches'.format(count))
        rpm_dict = sw.parse_rpm_links(page, rpm_dict)
        for index in xrange(2, num_pages + 1):
            print('Getting page {0} of results...'.format(index))
            page = sw.search_rpm_page(index)
            rpm_dict = sw.parse_rpm_links(page, rpm_dict)
    if len(rpm_dict) == 1:
        mirrors = rpm_dict.values()[0]
        do_download(mirrors)
    else:
        print('List of matching RPMs:')
        for k, v in sorted(rpm_dict.items(), key=name_key):
            print k, len(v)


if __name__ == '__main__':  # pragma: no cover
    main()
