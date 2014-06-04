#!/usr/bin/env python
import requests
import sys
from datetime import datetime
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import logging

logging.basicConfig()
logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


class ResponseWrapper(object):

    def __init__(self, response):
        self.response = response

    @property
    def total_time(self):
        return self.response.elapsed.seconds * 1.0e3 + self.response.elapsed.microseconds * 1e-3

    @property
    def query_time(self):
        return self.response.json()['responseHeader']['QTime']

    @property
    def total(self):
        return self.response.json()['response']['numFound']

    def maven_docs(self):
        try:
            return sorted(self.response.json()['response']['docs'], key=lambda d: d['timestamp'], reverse=True)
        except Exception as e:
            return []

    def latest_versions(self):
        docs = self.maven_docs()
        latest_versions = {}
        for doc in docs:
            latest_versions.setdefault((doc['g'], doc['a']), []).append(doc)
        return latest_versions


def query_maven(search_term, num_rows, start):
    query_url = "http://search.maven.org/solrsearch/select"
    query_params = {"q": search_term, "rows": num_rows, "wt": "json", "start": start}
    resp = requests.get(query_url, params=query_params)
    wrapper = ResponseWrapper(resp)
    logger.info("Maven query took %0.0f ms", wrapper.total_time)
    return {"docs": wrapper.maven_docs(),
            "latest": wrapper.latest_versions(),
            "total": wrapper.total,
            "query_time": wrapper.query_time}


def parse_args(args):
    ap = ArgumentParser("Maven Finder", formatter_class=ArgumentDefaultsHelpFormatter)
    ap.add_argument("-n", "--num-rows", type=int, default=512,
                    help="The maximum number of rows to return")
    ap.add_argument("-s", "--start", type=int, default=0,
                    help="The index to start at")
    ap.add_argument("-cp", "--class-path", action="store_true", default=False,
                    help="Enable exact Java classpath searches")
    ap.add_argument("-c", "--class-name", action="store_true", default=False,
                    help="Enable searches by Java class name")
    ap.add_argument("search_term")
    parser_ns = ap.parse_args(args)
    return parser_ns


def main(args):
    parser_ns = parse_args(args)
    if parser_ns.class_path:
        search_term = "fc:\"{0}\"".format(parser_ns.search_term)
    elif parser_ns.class_name:
        search_term = "c:\"{0}\"".format(parser_ns.search_term)
    else:
        search_term = parser_ns.search_term
    maven_dict = query_maven(search_term, parser_ns.num_rows, parser_ns.start)
    docs_by_key = maven_dict['latest'].items()
    docs_by_key.sort(key=lambda (k, vs): max([v['timestamp'] for v in vs]), reverse=True)
    logger.info("Maven Central found %d matches (%d unique!)", maven_dict['total'], len(docs_by_key))
    for key, docs in docs_by_key:
        print "{0[0]} - {0[1]}:".format(key)
        for doc in docs:
            version = doc.get('v', doc.get('latestVersion'))
            print "\t{0} @ {1}".format(version, datetime.fromtimestamp(doc['timestamp'] / 1000.))


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
