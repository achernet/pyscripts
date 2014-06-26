"""
A set of queries to run for a particular maven search. The timings can be grouped together.
"""
import random
import requests
import simplejson
from collections import namedtuple

QuerySet = namedtuple("QuerySet", ("query", "rows", "count", "extra"))
QUERY_SETS = [QuerySet("StaticLoggerBinder", 151, 20, 0),
              QuerySet("CollectionUtils", 137, 51, 0),
              QuerySet("ObjectMapper", 104, 21, 0)]


def generate_queries(query_sets=None):
    query_sets = query_sets or QUERY_SETS
    queries = {}
    for qs in query_sets:
        for i in xrange(qs.count):
            next_query = {"start": i * qs.rows, "rows": qs.rows, "q": "c:\"{0}\"".format(qs.query), "wt": "json"}
            queries.setdefault(qs.query, []).append(next_query)
        queries[qs.query][-1]["rows"] += qs.extra
    return queries


class QueryWrapper(object):

    def __init__(self, query_map):
        self.query_map = query_map

    def queries(self):
        allQueries = []
        for name, qlist in self.query_map.items():
            allQueries.extend(qlist)
        random.shuffle(allQueries)
        return allQueries

    @classmethod
    def from_query_sets(cls, query_sets):
        return QueryWrapper(generate_queries(query_sets))


