"""
Main module for running "new and improved" python package searches with better metrics.

"""
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from datetime import datetime, time as dt_time
from lxml.html import etree, HTMLParser
from tempfile import NamedTemporaryFile
from total_ordering import total_ordering
import dateutil.parser
import logging
import os
import re
import requests
import sh
import sys

logging.getLogger().setLevel(logging.DEBUG)

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
                  "max-concurrent-downloads": 33,
                  "enable-mmap": True,
                  "auto-file-renaming": False,
                  "allow-overwrite": True,
                  "async-dns": True,
                  "conditional-get": True,
                  "remote-time": True,
                  "http-accept-gzip": True,
                  "enable-http-pipelining": True,
                  "enable-http-keep-alive": False}

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
        return max(self.download_counts[1] / 7.0, self.download_counts[2] / 30.0)
    
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

    def run_aria2(self, max_age_days):
        """
        Run aria2c to execute all the downloads and save their file paths.
        @param max_age_days: The maximum age a file should be in order to be considered "recent" (and skipped over)
        @type max_age_days: float
        """
        if self.paths:
            log_fmt = "Download mapper has already run or is currently running! (%d paths came back)"
            logging.error(log_fmt, len(self.paths))  # TODO:ABC: make this raise some kind of exception?
            return
        total = len(self.nrmap)

        # make temporary input file
        with NamedTemporaryFile(delete=False) as ntf:
            ntf_dir = os.path.dirname(ntf.name)
            for result in self.nrmap.values():
                # Skip results that have already been downloaded recently.
                if result.has_recent_download(ntf_dir, max_age_days):
                    self.paths.append(os.path.join(ntf_dir, result.name))
                    continue
                ntf.write(result.to_aria2_input_entry())
        logging.info("aria2c input file saved to %s", ntf.name)

        # run the command
        local_aria2c_options = {"input-file": ntf.name,
                                "dir": ntf_dir,
                                "max-download-result": len(self.nrmap)}
        aria2_cmd = sh.Command("aria2c").bake(ARIA2C_OPTIONS).bake(local_aria2c_options)
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
        result_obj = PypiSearchResult(link=lxml_element[0][0].get("href"),
                                      weight=int(lxml_element[1].text),
                                      summary=lxml_element[2].text)
        results.append(result_obj)
    return results


def search_packages(search_term, collect_stats=True, backup_search=False, max_age_days=0.5):
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
    @return: The resulting search results
    @rtype: list[PypiSearchResult]
    """
    initial_results = query_initial_packages(search_term)
    if not collect_stats:
        return initial_results
    stats_downloader = DownloadMapper(initial_results)
    stats_downloader.run_aria2(max_age_days)
    stats_downloader.update_objects()
    if not backup_search:
        return stats_downloader.named_objects
    stats_downloader.update_required_backups()
    return stats_downloader.named_objects


def make_gui():
    gui_kw = {
        "VL": {
            "HL": [
                {
                    "type": "label",
                    "text": "Collect Stats?",
                    "tooltip": ("Check to run statistics collection after the initial search.\n"
                                "Required for computing the download rate and last update age of packages.")
                },
                {
                    "type": "checkbox",
                    "checked": True,
                    "action": "collect_stats"
                }

            ]
        }
    }


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
    parser.add_argument("-o", "--output_file",
                        dest="output_file",
                        type=str,
                        help="The output file")
    parser_ns = parser.parse_args(args)
    packages = search_packages(parser_ns.search_term, parser_ns.collect_stats,
                               parser_ns.backup_search, parser_ns.max_age_days)
    packages.sort()
    bad_indexes = []
    for i, pkg in enumerate(packages):
        if pkg.age is None:
            logging.warning("The age of package %r is unknown!", pkg.name)
            bad_indexes.append(i)
            continue
    bad_indexes.sort(reverse=True)
    for index in bad_indexes:
        packages.pop(index)
    out_path = "{0}.csv".format(parser_ns.output_file or parser_ns.search_term)
    logging.info("Saving CSV entries to {0}".format(os.path.abspath(out_path)))
    with open(out_path, "w") as f:
        for package in packages:
            f.write(package.to_csv())
            f.write(os.linesep)


if __name__ == "__main__":
    main(sys.argv[1:])
