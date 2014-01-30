#!/usr/bin/env python
"""
Main module for running "new and improved" python package searches with better metrics.

"""
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from datetime import datetime, time as dt_time, timedelta
from lxml.html import etree, HTMLParser
from tempfile import NamedTemporaryFile
from total_ordering import total_ordering
import csv
import dateutil.parser
import json
import logging
import os
import re
import requests
import sh
import sys

logging.getLogger().setLevel(logging.DEBUG)

ARIA2_CA_CERTIFICATE_PATH = "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem"
ARIA2_DOWNLOAD_COMPLETE_RGX = re.compile("Download complete:\\s+(?P<path>.*)$")
ARIA2C_OPTIONS = {"no-conf": True,
                  "timeout": 30,
                  "summary-interval": 2,
                  "max-connection-per-server": 1,
                  "connect-timeout": 30,
                  "max-tries": 16,
                  "max-file-not-found": 4,
                  "max-resume-failure-tries": 4,
                  "retry-wait": 8,
                  "deferred-input": True,
                  "max-concurrent-downloads": 55,
                  "enable-mmap": True,
                  "auto-file-renaming": False,
                  "allow-overwrite": True,
                  "async-dns": True,
                  "conditional-get": True,
                  "remote-time": True,
                  "http-accept-gzip": True,
                  "enable-http-pipelining": True,
                  "enable-http-keep-alive": False,
                  "ca-certificate": ARIA2_CA_CERTIFICATE_PATH,
                  "check-certificate": "false"}  # os.path.exists(ARIA2_CA_CERTIFICATE_PATH)}

DOWNLOAD_COUNT_XPATH = "//ul[@class=\"nodot\"][li[strong[starts-with(text(), \"Downloads\")]]]/li/span/text()"
LAST_UPDATE_XPATH = "//table[@class=\"list\"]/tr[@class]/td[4]/text()"
PYPI_BASE_URL = "https://pypi.python.org/pypi"
SEARCH_RESULTS_XPATH = "//table[@class=\"list\"]/tr[@class][td]"


class NamedObject(object):
    """
    Abstract class to represent a named and/or downloadable object.
    """

    @property
    def name(self):
        """
        The name of this object.
        """
        raise NotImplementedError

    def to_aria2_input_entry(self):
        """
        Generate an input file entry such that aria2c can read and download this object.

        @return: The text to insert into the input file
        @rtype: str|unicode
        """
        raise NotImplementedError

    def apply_update(self, new_content):
        """
        Update this object with the information contained within C{new_content}.

        @param new_content: The content to update this object with
        @type new_content: str|unicode
        """
        raise NotImplementedError

    def run_backup_update(self):
        """
        Run a "backup" update (in case the primary update failed).
        """
        pass


@total_ordering
class PypiSearchResult(NamedObject):
    """
    A named object representing a search result.
    """

    __slots__ = ("link", "weight", "summary", "download_counts", "last_update")

    def __repr__(self):
        repr_fmt = "<{0.name}/{0.version}, weight={0.weight}, rate={0.download_rate:.2f}, age={0.age}>"
        return repr_fmt.format(self)

    def __hash__(self):
        return hash((self.link, self.weight))

    def __eq__(self, other):
        return (self.link, self.weight) == (other.link, other.weight)

    def __lt__(self, other):
        return (self.weight, self.link) < (other.weight, other.link)

    def __init__(self, link, weight, summary, download_counts=None, last_update=None):
        self.link = link
        self.weight = weight
        self.summary = summary
        self.download_counts = download_counts or []
        self.last_update = last_update or None

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
        @return: The package version
        @rtype: basestring
        """
        return self.link.split("/")[-1]

    @property
    def name(self):
        """
        @return: The name of this named object
        @rtype: basestring
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
        return 116.8 - (45506.0 / (self.age + 397.7))

    @property
    def download_rate(self):
        return max(self.download_counts[1] / 7.0, self.download_counts[2] / 30.0) if self.download_counts else -1

    @property
    def scaled_download_rate(self):
        """
        The overall download rate, scaled by rank, is 98.21 - 742 / (6.404 + rate).
        """
        return 98.21 - (742 / (self.download_rate + 6.404))

    def has_recent_download(self, search_dir, max_days):
        """
        Return True if this file has been recently downloaded.

        @param search_dir: The directory to search in
        @type search_dir: str
        @param max_days: The maximum number of days to consider "recent"
        @type max_days: float
        @return: True if there is a file recently downloaded, otherwise False
        @rtype: bool
        """
        cur_time = (datetime.utcnow() - datetime.utcfromtimestamp(0)).total_seconds()
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
        self.download_counts = [float(count) for count in tree.xpath(DOWNLOAD_COUNT_XPATH)]
        last_update = tree.xpath(LAST_UPDATE_XPATH)
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
        xpath_arg = "//a[@href][starts-with(., \'{0}\')]".format(self.name)
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

        @param search_term: the specific search term to compare
        @type search_term: basestring
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

    def to_csv(self):
        """
        Return a line of CSV for this result.
        """
        return "\"{0.name}\",\"{0.version}\",{0.weight},{0.download_rate},{0.age}".format(self)

    @classmethod
    def from_csv(cls, csv_line, ref_date=None):
        """
        Given a line from a CSV file, read it and return a basic PypiSearchResult object.
        """
        ref_date = ref_date or datetime.utcnow()
        csv_parts = list(csv.reader([csv_line]))[0] if isinstance(csv_line, basestring) else csv_line
        link = "https://pypi.python.org/pypi/{0[0]}/{0[1]}".format(csv_parts)
        weight = int(csv_parts[2])
        rates = [float(csv_parts[3]), float(csv_parts[3]) * 7.0, float(csv_parts[3]) * 30.0]
        start_date = ref_date - timedelta(days=int(csv_parts[4]))
        return PypiSearchResult(link, weight, "", rates, start_date)


class PypiJsonSearchResult(PypiSearchResult):

    @property
    def version(self):
        """
        @return: The package version
        @rtype: basestring
        """
        return self.link.split("/")[-2]

    @property
    def name(self):
        """
        @return: The name of this named object
        @rtype: basestring
        """
        return self.link.split("/")[-3]

    @classmethod
    def from_csv(cls, csv_line, ref_date=None):
        ref_date = ref_date or datetime.utcnow()
        csv_parts = list(csv.reader([csv_line]))[0] if isinstance(csv_line, basestring) else csv_line
        link = "https://pypi.python.org/pypi/{0[0]}/{0[1]}/json".format(csv_parts)
        weight = int(csv_parts[2])
        rates = [float(csv_parts[3]), float(csv_parts[3]) * 7.0, float(csv_parts[3]) * 30.0]
        start_date = ref_date - timedelta(days=int(csv_parts[4]))
        return PypiJsonSearchResult(link, weight, "", rates, start_date)

    def apply_update(self, new_content):
        json_dict = json.loads(new_content)
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


class DownloadMapper(object):
    """
    Class to handle the parallel downloading of named objects.
    """

    def __init__(self, named_objects):
        """
        @param named_objects: The list of named objects
        @type named_objects: [NamedObject]
        """
        self.nrmap = {}
        for nobj in named_objects:
            self.nrmap[nobj.name] = nobj
        self.paths = []
        self.backups_needed = []

    def get_proper_path(self, file_path):
        """
        Get the "proper" format for C{file_path} by removing Cygwin-specific formatting, if it exists.
        This is necessary because aria2c.exe won't recognize Cygwin-formatted paths if it was built with MinGW.

        @param file_path: The path to convert if deemed necessary
        @type file_path: str or unicode
        @return: The converted file path
        @rtype: str or unicode
        """
        if "cygwin" in sys.platform.lower():
            file_path = sh.cygpath("-w", file_path).stdout.strip()
            print file_path
        return file_path

    def run_aria2(self, max_age_days, aria2c_path):
        """
        Run aria2c to execute all the downloads and save their file paths.

        @param max_age_days: The maximum age a file should be in order to be considered "recent" (and skipped over)
        @type max_age_days: float
        @param aria2c_path: The path to the aria2c(.exe) executable, or None to search for it in the PATH environment
        @type aria2c_path: str or None
        """
        if self.paths:
            log_fmt = "Download mapper has already run or is currently running! (%d paths came back)"
            logging.error(log_fmt, len(self.paths))  # TODO:ABC: make this raise some kind of exception?
            return
        total = len(self.nrmap)

        # Make a (temporary) input file in the default TEMP directory, populating it with each URL and output path.
        with NamedTemporaryFile(delete=False) as ntf:
            ntf_dir = self.get_proper_path(os.path.dirname(ntf.name))
            for result in self.nrmap.values():

                # Skip results that have already been downloaded recently.
                if result.has_recent_download(ntf_dir, max_age_days):
                    self.paths.append(os.path.join(ntf_dir, result.name))
                    continue
                ntf.write(result.to_aria2_input_entry())
        logging.info("aria2c input file saved to %r (dir: %r)", ntf.name, ntf_dir)

        # If a path to aria2c(.exe) was passed in, try to use it. Otherwise, try to resolve that path using the
        # current environment (specifically, the PATH variable).
        aria2c_path = aria2c_path or sh.resolve_program("aria2c")
        if aria2c_path is None:
            logging.error("aria2c is missing from the current configuration!")
            return
        aria2_cmd = sh.Command(aria2c_path)

        # Run and observe the above aria2c executable, reporting download progress to the appropriate logger.
        local_aria2c_options = {"input-file": self.get_proper_path(ntf.name),
                                "dir": ntf_dir,
                                "max-download-result": len(self.nrmap)}
        aria2_cmd = aria2_cmd.bake(ARIA2C_OPTIONS).bake(local_aria2c_options)
        logging.info("Command to execute: %s", aria2_cmd)
        try:
            for line in aria2_cmd(_iter=True, _ok_code=1, _err_to_out=True, _tty_out=False, _bg=True):
                if not isinstance(line, (str, unicode)):
                    continue
                sys.stdout.write(line)

                # Process lines representing finished files
                done_match = ARIA2_DOWNLOAD_COMPLETE_RGX.search(line)
                if done_match is not None:
                    self.paths.append(done_match.group("path"))
                    percent_done = 100.0 * float(len(self.paths)) / float(total)
                    logging.info("Download %d of %d (%.3f%%) complete", len(self.paths), total, percent_done)

        except sh.ErrorReturnCode as err:
            logging.exception("Download failed! Printing stack...\n%s%s", err.stdout, err.stderr)

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
        """
        @rtype: NamedObject
        """
        return self.nrmap.values()

    @property
    def names(self):
        return self.nrmap.keys()


def query_initial_packages(search_term):
    """
    Perform an initial package search on PyPI with the given C{search_term}, and return a list of
    C{PypiSearchResult} named objects.

    @param search_term: The initial search query
    @type search_term: str
    @return: The list of search results
    @rtype: list[PypiSearchResult]
    """
    result_page = requests.get(PYPI_BASE_URL, params={":action": "search", "term": search_term})
    result_tree = etree.fromstring(result_page.content, HTMLParser())
    result_tree.make_links_absolute(PYPI_BASE_URL)
    result_tags = result_tree.xpath(SEARCH_RESULTS_XPATH)
    results = []
    for lxml_element in result_tags:
        result_obj = PypiJsonSearchResult(link="{0}/json".format(lxml_element[0][0].get("href")),
                                          weight=int(lxml_element[1].text),
                                          summary=lxml_element[2].text)
        results.append(result_obj)
    return results


def search_packages(search_term, collect_stats=True, backup_search=False,
                    max_age_days=0.5, aria2c_path=None):
    """
    Search for packages matching C{search_term}, optionally collecting stats
    and/or running backup updates for any packages whose age was not determined
    initially.

    @param search_term: The search term
    @type search_term: str|unicode
    @param collect_stats: True to collect stats, otherwise False
    @type collect_stats: bool
    @param backup_search: True to run backup searches, otherwise False
    @type backup_search: bool
    @param max_age_days: The maximum days of age files should be
    @type max_age_days: float
    @param aria2c_path: The path to the aria2c executable
    @type aria2c_path: str or None
    @return: The resulting search results
    @rtype: list[PypiSearchResult]
    """
    initial_results = query_initial_packages(search_term)
    if not collect_stats:
        return initial_results
    stats_downloader = DownloadMapper(initial_results)
    stats_downloader.run_aria2(max_age_days, aria2c_path)
    stats_downloader.update_objects()
    if not backup_search:
        return stats_downloader.named_objects
    stats_downloader.update_required_backups()
    return stats_downloader.named_objects


class OutputFile(object):

    def __init__(self, search_term):
        self.search_term = search_term

    def __repr__(self):
        return "{0.__class__.__name__}({0.search_term})".format(self)

    def __str__(self):
        return repr(self)

    @property
    def file_name(self):
        return "{0.search_term}.csv".format(self)

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
        return age_td.total_seconds() / 86400.0


def main(args):
    """
    @type args: list
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
