#!/usr/bin/env python
# PYTHON_ARGCOMPLETE_OK
"""
Main module for running "new and improved" python package searches with better metrics.

"""
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from datetime import datetime, time as dt_time, timedelta
from lxml.html import etree, HTMLParser
from tempfile import NamedTemporaryFile
from namedlist import namedlist
import argcomplete
import csv
import dateutil.parser
import json
import logging
import os
import re
import requests
import sys
import time
import progbar
from generic_download_queue import GenericDownloadQueue
from queuing_thread import QueuingThread

try:
    import sh
except ImportError:
    import pbs as sh  # On Windows, pbs takes the place of sh

logging.getLogger().setLevel(logging.DEBUG)

ARIA2C_OPTIONS = {"no-conf": True,
                  "timeout": 5,
                  "connect-timeout": 5,
                  "lowest-speed-limit": 256,
                  "file-allocation": "falloc",
                  "min-split-size": 1048576,
                  "summary-interval": 3,
                  "max-connection-per-server": 2,
                  "max-tries": 21,
                  "max-file-not-found": 5,
                  "max-resume-failure-tries": 5,
                  "retry-wait": 1,
                  "deferred-input": True,
                  "max-concurrent-downloads": 34,
                  "auto-file-renaming": False,
                  "allow-overwrite": True,
                  # "async-dns": True,
                  "conditional-get": True,
                  "remote-time": True,
                  "http-accept-gzip": True,
                  "enable-http-pipelining": True,
                  "enable-http-keep-alive": True,
                  "log-level": "notice",
                  "console-log-level": "notice",
                  "ca-certificate": "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem"}
ARIA2C_OPTIONS["check-certificate"] = os.path.exists(ARIA2C_OPTIONS["ca-certificate"])

_PypiSearchResult = namedlist("_PypiSearchResult", ["link", "weight", "summary",
                                                    ("download_counts", []),
                                                    ("last_update", None)])


class PypiSearchResult(_PypiSearchResult):
    """
    A named object representing a search result.
    """

    @classmethod
    def from_dict(cls, data_dict):
        return PypiSearchResult(link=data_dict["link"],
                                weight=data_dict["weight"],
                                summary=data_dict["summary"],
                                download_counts=data_dict.get("download_counts"),
                                last_update=data_dict.get("last_update"))

    def to_dict(self):
        return {"link": self.link,
                "weight": self.weight,
                "summary": self.summary,
                "download_rate": self.download_rate,
                "last_update": self.last_update.isoformat() if self.last_update is not None else None}

    @property
    def version(self):
        """
        :return: The package version
        :rtype: str
        """
        return self.link.split("/")[-1]

    @property
    def name(self):
        """
        :return: The name of this named object
        :rtype: str
        """
        return self.link.split("/")[-2]

    @property
    def ftp_page_url(self):
        return "https://pypi.python.org/packages/source/{0[0]}/{0}/".format(self.name)

    @property
    def age(self):
        if self.last_update is None:
            return 3488
        return (datetime.now().date() - self.last_update.date()).days

    @property
    def scaled_age(self):
        """
        The age, scaled by rank, is 116.8 - 45506 / (397.7 + age).
        """
        return 45506.0 / (self.age + 397.7) - 16.8

    @property
    def download_rate(self):
        return max(self.download_counts[1] / 7.0, self.download_counts[2] / 30.0) if self.download_counts else -1

    @property
    def scaled_download_rate(self):
        """
        The overall download rate, scaled by rank, is 98.21 - 742 / (6.404 + rate).
        """
        return 98.21 - (742 / (self.download_rate + 6.404))

    @property
    def scaled_weight(self):
        return (self.weight - 1) * 0.1

    @property
    def score(self):
        """
        The total score of this search result, scaled by category. The weight (according to PyPI) is worth 2,
        the age is worth 3, and the download rate is worth 5.

        :return: The total score for this search result
        :rtype: float
        """
        return self.scaled_weight * 2.0 + self.scaled_age * 3.0e-2 + self.scaled_download_rate * 5.0e-2

    def has_recent_download(self, search_dir, max_days):
        """
        Return True if this file has been recently downloaded.

        :param search_dir: The directory to search in
        :type search_dir: str
        :param max_days: The maximum number of days to consider "recent"
        :type max_days: float
        :return: True if there is a file recently downloaded, otherwise False
        :rtype: bool
        """
        cur_time = time.time()
        target_file = os.path.join(search_dir, self.name)
        if not os.path.exists(target_file):
            return False
        stats = os.stat(target_file)
        file_time = max(stats.st_ctime, stats.st_mtime)
        return cur_time - file_time < (max_days * 86400.0)

    def apply_update(self, page_content):
        """
        From the given page content, parse and add the download statistics to this search result.
        """
        tree = etree.fromstring(page_content, HTMLParser())
        counts = tree.xpath("//ul[@class='nodot'][li[strong[starts-with(text(), 'Downloads')]]]/li/span/text()")
        self.download_counts = [float(count) for count in counts]
        last_update = tree.xpath("//table[@class='list']/tr[@class]/td[4]/text()")
        if last_update not in [None, []]:
            self.last_update = dateutil.parser.parse(last_update[0], ignoretz=True)
            return True
        self.last_update = None
        return False

    def add_latest_date_from_ftp_page(self, page_content):
        """
        From the given page content, parse and add the latest date listed.
        """
        tree = etree.fromstring(page_content, HTMLParser())
        xpath_arg = "//a[@href][starts-with(., '{0}')]".format(self.name)
        link_elems = tree.xpath(xpath_arg)
        max_date = datetime.min
        for elem in link_elems:
            date_size_parts = (elem.tail or "").strip().split()
            if not date_size_parts:
                continue
            date_str = " ".join(date_size_parts[:-1])
            date_val = dateutil.parser.parse(date_str, ignoretz=True)

            # If parser returns default date, it's most likely an error, so skip over it.
            default_date = datetime.combine(datetime.now().date(), dt_time.min)
            if date_val == default_date:
                continue
            max_date = max(date_val, max_date)
        self.last_update = max_date

    def run_backup_update(self):
        """
        Run a secondary update method in order to get the timestamp for the last project update, in case the primary
        update method (via parsing the PyPI project main page) fails.

        Basically this entails trying to navigate to 2 possible PyPI FTP sites and finding the latest date(s) listed.
        """
        if self.last_update is not None:
            return
        ftp_url = self.ftp_page_url
        ftp_resp = requests.get(ftp_url)
        if not ftp_resp.ok:
            orig_part = "/{0[0]}/{0[0]}".format(self.name)
            capitalized_url = ftp_url.replace(orig_part, orig_part.upper())
            ftp_resp = requests.get(capitalized_url)
        self.add_latest_date_from_ftp_page(ftp_resp.content)

    def is_pip_result(self, search_term):
        """
        Return True if this result would be expected in the list from pip search, otherwise False.

        :param search_term: the specific search term to compare
        :type search_term: str
        """
        if self.weight >= 4:
            return True
        if self.weight in (2, 3):
            return search_term.lower() in self.summary.lower()
        return False

    def to_aria2_input_entry(self):
        """
        Return this result formatted as an aria2c input file entry.
        """
        return "{0.link}\n out={0.name}\n".format(self)

    def to_csv(self):
        """
        Return a line of CSV for this result.
        """
        csv_fmt = "\"{0.name}\",\"{0.version}\",{0.weight},{0.download_rate:0.2f},{0.age},{0.score:0.3f}"
        return csv_fmt.format(self)

    @classmethod
    def from_csv(cls, csv_line, ref_date=None):
        """
        Given a line from a CSV file, read it and return a basic :class:`PypiSearchResult` object.
        """
        ref_date = ref_date or datetime.utcnow()
        csv_parts = list(csv.reader([csv_line]))[0] if isinstance(csv_line, (str, unicode)) else csv_line
        link = "https://pypi.python.org/pypi/{0[0]}/{0[1]}".format(csv_parts)
        weight = int(csv_parts[2])
        rates = [float(csv_parts[3]), float(csv_parts[3]) * 7.0, float(csv_parts[3]) * 30.0]
        start_date = ref_date - timedelta(days=int(csv_parts[4]))
        return PypiSearchResult(link, weight, "", rates, start_date)


class PypiJsonSearchResult(PypiSearchResult):

    @property
    def version(self):
        """
        :return: The package version
        :rtype: str
        """
        return self.link.split("/")[-2]

    @property
    def name(self):
        """
        :return: The name of this named object
        :rtype: str
        """
        return self.link.split("/")[-3]

    @classmethod
    def from_csv(cls, csv_line, ref_date=None):
        ref_date = ref_date or datetime.utcnow()
        csv_parts = list(csv.reader([csv_line]))[0] if isinstance(csv_line, str) else csv_line
        link = "https://pypi.python.org/pypi/{0[0]}/{0[1]}/json".format(csv_parts)
        weight = int(csv_parts[2])
        rates = [float(csv_parts[3]), float(csv_parts[3]) * 7.0, float(csv_parts[3]) * 30.0]
        start_date = ref_date - timedelta(days=int(csv_parts[4]))
        return PypiJsonSearchResult(link, weight, "", rates, start_date)

    def apply_update(self, new_content):
        try:
            json_dict = json.loads(new_content)
        except ValueError as e:
            logging.exception("Error parsing JSON content update:\n%r", new_content)
            self.download_counts = [-1.0, -1.0, -1.0]
            self.last_update = None
            return False
        dl_info = json_dict["info"]["downloads"]
        self.download_counts = [float(dl_info[k]) for k in ["last_day", "last_week", "last_month"]]
        upload_time_strs = [url_info["upload_time"] for url_info in json_dict["urls"]]
        upload_times = [dateutil.parser.parse(up_time, ignoretz=True) for up_time in upload_time_strs]
        if upload_times:
            self.last_update = max(upload_times)
            return True
        else:
            self.last_update = None
            return False


class DownloadMapper(QueuingThread):
    """
    Class to handle the parallel downloading of named objects.
    """

    def __init__(self, queue, named_objects, max_age_days, aria2c_path):
        """
        :param named_objects: The list of named objects
        :type named_objects: [NamedObject]
        """
        QueuingThread.__init__(self, queue)
        self.nrmap = {}
        for nobj in named_objects:
            self.nrmap[nobj.name] = nobj
        self.paths = []
        self.backups_needed = []
        self.max_age_days = max_age_days
        self.aria2c_path = aria2c_path
        self.ntf = NamedTemporaryFile(delete=False)
        self.ntf_dir = self.get_proper_path(os.path.dirname(self.ntf.name))
        for result in self.nrmap.values():
            # Skip results that have already been downloaded recently.
            if result.has_recent_download(self.ntf_dir, self.max_age_days):
                self.paths.append(os.path.join(self.ntf_dir, result.name))
                continue
            self.ntf.write(result.to_aria2_input_entry())
        self.ntf.close()
        logging.info("aria2c input file saved to %r (dir: %r)", self.ntf.name, self.ntf_dir)

    def get_proper_path(self, file_path):
        """
        Get the "proper" format for :attr:`file_path` by removing Cygwin-specific formatting, if it exists.
        This is necessary because aria2c.exe won't recognize Cygwin-formatted paths if it was built with MinGW.

        :param str file_path: The path to convert if deemed necessary
        :return str: The converted file path
        """
        if "cygwin" in sys.platform.lower():
            file_path = sh.cygpath("-w", file_path).stdout.strip()
            print file_path
        return file_path

    def build_command(self):
        aria2c_path = self.aria2c_path or sh.resolve_program("aria2c") or sh.resolve_program("aria2c.exe")
        if aria2c_path is None:
            logging.error("aria2c is missing from the current configuration!")
            return
        aria2_cmd = sh.Command(aria2c_path)

        # Run and observe the above aria2c executable, reporting download progress to the appropriate logger.
        local_aria2c_options = {"input-file": self.get_proper_path(self.ntf.name),
                                "dir": self.ntf_dir,
                                "max-download-result": len(self.nrmap)}
        aria2_cmd = aria2_cmd.bake(ARIA2C_OPTIONS).bake(local_aria2c_options)
        aria2_cmd = aria2_cmd.bake(_iter=True, _tty_out=False, _ok_code=1)
        logging.info("Command to execute: %s", aria2_cmd)
        return aria2_cmd

    def compile_progress_regex(self):
        return re.compile("Download complete:\\s+(?P<path>.*)$")

    def enqueue_progress_match(self, progress_match):
        group_dict = progress_match.groupdict()
        self.paths.append(group_dict["path"])
        msg_dict = {"value": len(self.paths),
                    "maximum": len(self.nrmap),
                    "status": "Download complete: {0}".format(group_dict["path"])}
        self.queue.put(msg_dict)

    def run(self):
        """
        Run aria2c to execute all the downloads and save their file paths.
        """
        if self.paths:
            log_fmt = "Download mapper has already run or is currently running! (%d paths came back)"
            logging.error(log_fmt, len(self.paths))  # TODO:ABC: make this raise some kind of exception?
            return
        QueuingThread.run(self)
        self.update_objects()

    def update_objects(self):
        """
        Apply the downloaded updates to all their corresponding named objects.
        """
        if not self.paths:
            logging.error("No paths to update! Make sure the download has actually been executed")
            return  # raise MyException(err_msg, errorcodes.DOWNLOAD_MAPPER_MISSING_PATHS)
        for path in self.paths:
            with open(path, 'r') as f:
                new_content = f.read()

            # Look up and apply the relevant update.
            original_name = os.path.split(path)[-1]  # TODO:ABC: mapping path to name to be done by named object?
            original_result = self.nrmap[original_name]
            update_status = original_result.apply_update(new_content)  # TODO:ABC: make this generic!
            if not update_status:
                self.backups_needed.append(original_name)

    def update_required_backups(self):
        """
        Run backup updates on any named objects that require them.
        """
        if not self.paths:
            logging.error("No paths to update! Make sure the download has actually been executed")
            return
        for backup_name in self.backups_needed:
            self.nrmap[backup_name].run_backup_update()

    @property
    def named_objects(self):
        return self.nrmap.values()

    @property
    def names(self):
        return self.nrmap.keys()


def query_initial_packages(search_term):
    """
    Perform an initial package search on PyPI with the given :attr:`search_term`, and return a list of
    :attr:`PypiSearchResult` named objects.

    :param str search_term: The initial search query
    :return: The list of search results
    :rtype: list[PypiSearchResult]
    """
    logging.info("Querying initial packages for %s...", search_term)
    result_page = requests.get("https://pypi.python.org/pypi", params={":action": "search", "term": search_term})
    result_tree = etree.fromstring(result_page.content, HTMLParser())
    result_tree.make_links_absolute(result_page.url)
    result_tags = result_tree.xpath("//table[@class='list']/tr[@class][td]")
    results = []
    for lxml_element in result_tags:
        result_obj = PypiJsonSearchResult(link="{0}/json".format(lxml_element[0][0].get("href")),
                                          weight=int(lxml_element[1].text),
                                          summary=lxml_element[2].text)
        if result_obj.is_pip_result(search_term):
            results.append(result_obj)
    return results


def search_packages(search_term, collect_stats=True, backup_search=False,
                    max_age_days=0.5, aria2c_path=None):
    """
    Search for packages matching :attr:`search_term`, optionally collecting stats
    and/or running backup updates for any packages whose age was not determined
    initially.

    :param str search_term: The search term
    :param bool collect_stats: True to collect stats, otherwise False
    :param bool backup_search: True to run backup searches, otherwise False
    :param float max_age_days: The maximum days of age files should be
    :param str aria2c_path: The path to the aria2c executable, or None to look for it on PATH
    :return: The resulting search results
    :rtype: list[:class:`PypiSearchResult`]
    """
    initial_results = query_initial_packages(search_term)
    if not collect_stats:
        return initial_results
    thread_creator = lambda queue: DownloadMapper(queue, initial_results, max_age_days, aria2c_path)
    # Create a generic progress bar dialog for monitoring the download progress.
    try:
        stats_progbar = progbar.GenericProgressBar(title="Downloading packages...",
                                                   maximum=len(initial_results),
                                                   value=0,
                                                   status="Starting aria2c...",
                                                   thread_creator=thread_creator)
    except Exception as e:
        logging.exception("Exception was raised drawing progress bar: %s", e)
        stats_progbar = GenericDownloadQueue(thread_creator=thread_creator)

    with stats_progbar:
        pass
    if not backup_search:
        return stats_progbar.thread.named_objects
    stats_progbar.thread.update_required_backups()
    return stats_progbar.thread.named_objects


class OutputFile(object):

    def __init__(self, search_term):
        self.search_term = search_term

    def __repr__(self):
        return "{0.__class__.__name__}({0.search_term})".format(self)

    def __str__(self):
        return repr(self)

    @property
    def file_name(self):
        return "{0}.csv".format(self.search_term)

    @property
    def path(self):
        return os.path.abspath(self.file_name)

    @property
    def ref_date(self):
        try:
            file_stats = os.stat(self.path)
            cm_time = max(file_stats.st_mtime, file_stats.st_ctime)
        except OSError:
            cm_time = -1
        return datetime.utcfromtimestamp(cm_time)

    @property
    def age(self):
        age_td = datetime.utcnow() - self.ref_date
        return age_td.days + age_td.seconds / 86.4e3


def main(args):
    """
    :type args: list
    """
    parser = ArgumentParser(description="Search for python packages using better metrics",
                            formatter_class=ArgumentDefaultsHelpFormatter)
    parser.add_argument("search_term",
                        type=str,
                        help="The search term or phrase to query")
    parser.add_argument("-S", "--disable-stats",
                        dest="collect_stats",
                        action="store_false",
                        help="Disable extra stats collection (i.e. revert to old behavior)")
    parser.add_argument("-s", "--enable-stats",
                        dest="collect_stats",
                        action="store_true",
                        help="Enable extra stats collection (i.e. the default)")
    parser.set_defaults(collect_stats=True)
    parser.add_argument("-B", "--disable-backup-search",
                        dest="backup_search",
                        action="store_false",
                        help="Disable backup search for last update (i.e. the default)")
    parser.add_argument("-b", "--enable-backup-search",
                        dest="backup_search",
                        action="store_true",
                        help="Enable backup search for last update (can be slow!)")
    parser.set_defaults(backup_search=False)
    parser.add_argument("-d", "--max-age-days",
                        dest="max_age_days",
                        type=float,
                        help="Max days to consider recent when downloading already-existing files")
    parser.set_defaults(max_age_days=0.5)
    parser.add_argument("-p", "--path-to-aria2c",
                        dest="aria2c_path",
                        type=str,
                        help="The path to aria2c(.exe) if not in current PATH environment")
    parser.set_defaults(aria2c_path=None)
    argcomplete.autocomplete(parser)
    parser_ns = parser.parse_args(args)

    out_obj = OutputFile(parser_ns.search_term)
    if out_obj.age < parser_ns.max_age_days:
        with open(out_obj.path, 'r') as f:
            csv_lines = f.read().splitlines()
        packages = [PypiSearchResult.from_csv(line, ref_date=out_obj.ref_date) for line in csv_lines]
    else:
        packages = search_packages(parser_ns.search_term, parser_ns.collect_stats,
                                   parser_ns.backup_search, parser_ns.max_age_days,
                                   parser_ns.aria2c_path)
        packages.sort()
        logging.info("Saving CSV entries to %s", out_obj.path)
        with open(out_obj.path, "w") as f:
            for package in packages:
                f.write(package.to_csv())
                f.write(os.linesep)


if __name__ == "__main__":
    main(sys.argv[1:])
