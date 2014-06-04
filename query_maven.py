#!/usr/bin/env python
import requests
import sys
from datetime import datetime
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
import logging

logging.basicConfig()
logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)


def query_maven(search_term, num_rows, start):
    query_url = "http://search.maven.org/solrsearch/select"
    query_params = {"q": search_term, "rows": num_rows, "wt": "json", "start": start}
    resp = requests.get(query_url, params=query_params)
    time_taken = resp.elapsed.seconds * 1e3 + resp.elapsed.microseconds * 1e-3
    print "Maven query took {0:0.0f} ms".format(time_taken)
    try:
        maven_docs = resp.json()["response"]["docs"]
    except:
        print >> sys.stderr, "Invalid data came back! Make sure proxy is configured properly."
        maven_docs = []
    maven_docs.sort(key=lambda md: md["timestamp"], reverse=True)
    latest_versions = {}
    for doc in maven_docs:
        latest_versions.setdefault((doc['g'], doc['a']), []).append(doc)
    return {"docs": maven_docs,
            "latest": latest_versions}


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
    print "Maven Central found {0} matches ({1} unique)!\n".format(len(maven_dict["docs"]), len(docs_by_key))
    for key, docs in docs_by_key:
        print "{0[0]} - {0[1]}:".format(key)
        for doc in docs:
            version = doc.get('v', doc.get('latestVersion'))
            print "\t{0} @ {1}".format(version, datetime.fromtimestamp(doc['timestamp'] / 1000.))


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
