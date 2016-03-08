#!/usr/bin/env python
import argparse
from collections import Iterable
import contextlib
import fnmatch
import logging
import os
import re
import requests
import socket
import sys
import urllib2
import urlparse
from lxml.html import etree, HTMLParser
from sh import aria2c
import retrying
from path import Path

if not logging.root.handlers:
    logging.basicConfig(format='%(asctime)s [%(levelname)s]: %(message)s')
logger = logging.getLogger('search_rpms')
logger.setLevel(logging.DEBUG)


class TimeoutContext(object):

    def __init__(self, timeout):
        self.new_timeout = timeout
        self.old_timeout = socket.getdefaulttimeout()

    def __enter__(self):
        logger.info('Setting socket timeout to %.3fs...', self.new_timeout)
        socket.setdefaulttimeout(self.new_timeout)
        return self

    def __exit__(self, *exc_info):
        socket.setdefaulttimeout(self.old_timeout)
        return False


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
        with TimeoutContext(5):
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
            logger.error('Failed to count links in search page, returning 0')
            return 0
        links = int(count.group(1))
        logger.info('Number of links found in search page: %d', links)
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
        # show any HTML entries left over as full links
        for fname, flinks in rpm_dict.items():
            if os.path.splitext(fname)[-1] == '.html':
                rpm_dict.pop(fname)
                for flink in flinks:
                    rpm_dict[flink] = set([flink])
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


def _find_valid_file(mirror_file, mirror_data):
    valid_file = None
    for i in xrange(0, mirror_file.count('-') + 1):
        search_term = '{0}-*'.format('-'.join(mirror_file.split('-')[:i + 1]))
        if mirror_file in search_term:
            search_term = mirror_file
        search_pat = fnmatch.translate(search_term)
        search_pat = '(?m){0}'.format(search_pat.replace('\\Z(?ms)', ''))
        rgx = re.compile(search_pat)
        matches = rgx.findall(mirror_data)
        if len(matches) == 1:
            valid_file = matches[0].rstrip()
            break
    return valid_file


def find_valid_mirrors(mirrors):
    valid_file = None
    for mirror in mirrors:
        mpr = urlparse.urlparse(mirror)._asdict()
        mirror_file = Path(mpr['path']).basename()
        mpr['path'] = Path(mpr['path']).dirname()
        parent_url = urlparse.ParseResult(**mpr).geturl()
        try:
            with TimeoutContext(5):
                with contextlib.closing(urllib2.urlopen(parent_url)) as f:
                    data = f.read()
        except Exception as e:
            logger.exception('Error opening mirror site: %s', e.__class__.__name__)
            data = ''
        valid_file = _find_valid_file(mirror_file, data)
        if valid_file is not None:
            break
    if valid_file is None:
        logger.error('Error validating mirrors: No valid file was found\n%s', mirrors)
        return []
    for i, m in enumerate(mirrors):
        mpr = urlparse.urlparse(m)._asdict()
        mpr['path'] = Path(mpr['path']).dirname().joinpath(valid_file)
        mirrors[i] = urlparse.ParseResult(**mpr).geturl()
    return mirrors


def do_download(mirrors):
    mirrors = sorted(mirrors) if not isinstance(mirrors, list) else mirrors
    logger.info('List of mirrors: %s', mirrors)
    valid_mirrors = find_valid_mirrors(mirrors)
    name = valid_mirrors[0]
    logger.info('Downloading %s...', name)
    for line in aria2c(valid_mirrors, _iter_noblock=True):
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
    logger.info('Searching for %s...', ns.query)
    rpm_dict = {}
    with SearchWrapper(ns.query) as sw:
        page = sw.search_rpm_page()
        count = sw.parse_count(page)
        num_pages = (count / 100) + bool(count % 100)
        logger.info('Found %d matches', count)
        rpm_dict = sw.parse_rpm_links(page, rpm_dict)
        for index in xrange(2, num_pages + 1):
            logger.info('Getting page %d/%d of results...', index, num_pages)
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
