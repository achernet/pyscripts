#!/usr/bin/env python
"""
pip search returns a filtered subset of the results that PyPI returns.
    On PyPI, the "weight" of the search must be at least 2 for pip to return it.
    If the "weight" is 2, the description must match the search term for pip to return it.
    If the "weight" is 3+, pip will return it irrespective of any other properties.

Unfortunately, pip search doesn't work from behind a proxy due to known bugs. This script
should fix that and also provide better metrics for matching packages so that the highest
scores only go to the most popular and most frequently maintained packages.

Right now, parallel downloading is built-in and depends on having ARIA2 somewhere in your
PATH. It might be useful to have options like interfacing with gevent or just running it
(slowly) in pure Python mode if nothing else works on a given system.
"""
import requests
from lxml.html import etree, HTMLParser
import sys
import logging
from dateutil.parser import parse as parse_date
import sh
import re
import os
from tempfile import NamedTemporaryFile
from functools import total_ordering

logging.getLogger().setLevel(logging.DEBUG)

PYPI_BASE_URL = "https://pypi.python.org/pypi"

DOWNLOAD_COUNT_XPATH = "//ul[@class=\"nodot\"][li[strong[starts-with(text(), \"Downloads\")]]]/li/span/text()"
SEARCH_RESULTS_XPATH = "//table[@class=\"list\"]/tr[@class][td]"
LAST_UPDATE_XPATH = "//table[@class=\"list\"]/tr[@class]/td[4]/text()"

ARIA2_DOWNLOAD_COMPLETE_RGX = re.compile("Download complete:\\s+(?P<path>.*)$")
ARIA2_DOWNLOAD_MISSED_RGX = re.compile("Download GID#[a-z0-9]+ not complete:\\s+(?P<path>.*)$")


@total_ordering
class PypiSearchResult(object):

    __slots__ = ("link", "weight", "summary", "download_rate", "last_update")

    def __repr__(self):
        repr_fmt = "<{0.name}/{0.version}, weight={0.weight}, rate={0.download_rate}, last={0.last_update}>"
        return repr_fmt.format(self)

    def __hash__(self):
        return hash((self.link, self.weight))

    def __eq__(self, other):
        return (self.link, self.weight) == (other.link, other.weight)

    def __lt__(self, other):
        return (self.weight, self.link) < (other.weight, other.link)

    def __init__(self, link, weight, summary, download_rate=None, last_update=None):
        self.link = link
        self.weight = weight
        self.summary = summary
        self.download_rate = download_rate or None
        self.last_update = last_update or None

    @classmethod
    def from_element(cls, lxml_element):
        return PypiSearchResult(link=lxml_element[0][0].get("href"),
                                weight=int(lxml_element[1].text),
                                summary=lxml_element[2].text)

    @classmethod
    def from_dict(cls, data_dict):
        return PypiSearchResult(link=data_dict["link"],
                                weight=data_dict["weight"],
                                summary=data_dict["summary"],
                                download_rate=data_dict.get("download_rate"),
                                last_update=data_dict.get("last_update"))

    def to_dict(self):
        return {"link": self.link,
                "weight": self.weight,
                "summary": self.summary,
                "download_rate": self.download_rate,
                "last_update": self.last_update.isoformat() if self.last_update is not None else None}

    @property
    def name(self):
        return self.link.split("/")[-2]

    @property
    def version(self):
        return self.link.split("/")[-1]

    def add_download_stats_from_index_page(self, page_content):
        """
        From the given page content, parse and add the download statistics to this search result.
        """
        tree = etree.fromstring(page_content, HTMLParser())
        download_counts = [float(count) for count in tree.xpath(DOWNLOAD_COUNT_XPATH)]
        self.download_rate = max(download_counts[0], download_counts[1] / 7.0, download_counts[2] / 30.0)
        last_update = tree.xpath(LAST_UPDATE_XPATH)
        if last_update not in [None, []]:
            self.last_update = parse_date(last_update[0], ignoretz=True)
        else:
            self.last_update = None
        return self

    def is_pip_result(self, search_term):
        """
        Return True if this result would be expected in the list from pip search, otherwise False.

        @param search_term: the specific search term to compare
        """
        if self.weight == 2:
            return search_term.lower() in " ".join([self.name.lower(), self.summary.lower()])
        else:
            return self.weight > 2

    def to_aria2_input_entry(self):
        """
        Return this result formatted as an aria2c input file entry.
        """
        return "{0.link}\n out={0.name}\n".format(self)


def run_aria2(search_results, **aria2c_kwargs):
    total = len(search_results)

    # make temporary input file
    with NamedTemporaryFile(delete=False) as ntf:
        ntf.write("".join([result.to_aria2_input_entry() for result in search_results]))

    logging.info("aria2c input file saved to %s", ntf.name)

    # run the command
    ntf_dir = os.path.dirname(ntf.name)
    aria2c_options = {"no-conf": True,
                      "dir": ntf_dir,
                      "input-file": ntf.name,
                      "timeout": 30,
                      "connect-timeout": 30,
                      "max-tries": 8,
                      "retry-wait": 8,
                      "deferred-input": True,
                      "max-concurrent-downloads": 33,
                      "max-download-result": len(search_results),
                      "auto-file-renaming": False,
                      "allow-overwrite": True,
                      "conditional-get": True,
                      "remote-time": True,
                      "http-accept-gzip": True,
                      "enable-http-pipelining": True,
                      "enable-http-keep-alive": True}
    aria2c_options.update(**aria2c_kwargs)

    aria2_cmd = sh.Command("aria2c").bake(aria2c_options)
    logging.info("Command to execute: %s", aria2_cmd)
    paths_done = []
    try:
        for line in aria2_cmd(_iter_noblock=True, _ok_code=1):
            if not isinstance(line, basestring):
                continue
            sys.stdout.write(line)

            # Process lines representing finished files
            done_match = ARIA2_DOWNLOAD_COMPLETE_RGX.search(line)
            if done_match is not None:
                paths_done.append(done_match.group("path"))
                percent_done = 100.0 * float(len(paths_done)) / float(total)
                logging.info("Download %d of %d (%.3f%%) complete", len(paths_done), total, percent_done)

    except sh.ErrorReturnCode as err:
        logging.exception("Download failed! Printing stack...\n%s%s",  err.stdout, err.stderr)

    return paths_done


def search_packages(search_term, collect_stats=True):
    """
    Search PyPI for all packages matching search_term.
    """
    result_page = requests.get(PYPI_BASE_URL, params={":action": "search", "term": search_term})
    result_tree = etree.fromstring(result_page.content, HTMLParser())
    result_tree.make_links_absolute(PYPI_BASE_URL)
    result_tags = result_tree.xpath(SEARCH_RESULTS_XPATH)
    results = [PypiSearchResult.from_element(tag) for tag in result_tags]
    if not collect_stats:
        return results
    results_by_name = dict(zip([res.name for res in results], results))
    package_page_paths = run_aria2(results)
    new_results = []
    for path in package_page_paths:
        with open(path, "r") as f:
            original_name = os.path.split(path)[-1]
            original_result = results_by_name[original_name]
            new_result = original_result.add_download_stats_from_index_page(f.read())
            new_results.append(new_result)
    return new_results


def main(args):
    search_term = args[0]
    package_results = search_packages(search_term)
    pip_results = [result for result in package_results if result.is_pip_result(search_term)]
    return pip_results


if __name__ == "__main__":
    main(sys.argv[1:])
