#!/usr/bin/env python
import urlparse
import sys
import time
from datetime import timedelta
from contextdecorator import ContextDecorator  # package: contextdecorator >= 0.1.0
import socket
from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter  # package: argparse >= 1.2.1


class SocketTimer(ContextDecorator):

    def __init__(self, title="Working...", time_func=time.time):
        self.title = "{0}...".format(title.rstrip("."))
        self.time_func = time_func
        self.start_time = None
        self.end_time = None

    @property
    def time_taken(self):
        if self.start_time is None:
            return None
        end_time = self.end_time or self.time_func()
        return end_time - self.start_time

    def __enter__(self):
        self.start_time = self.time_func()
        sys.stdout.write(self.title)
        sys.stdout.flush()
        return self

    def __exit__(self, *args):
        self.end_time = self.time_func()
        time_taken = timedelta(seconds=self.time_taken)
        sys.stdout.write(" done (time: {0})".format(time_taken))
        sys.stdout.write("\r\n")
        sys.stdout.flush()
        return False


def get_ip_dict(site_dicts):
    ip_dict = {}
    for i, site_dict in enumerate(site_dicts):
        parsed_site = urlparse.urlparse(site_dict["href"])
        ip_addr = ip_dict.get(parsed_site.netloc)
        if ip_addr is None:
            with SocketTimer("Looking up IP for {0}...".format(parsed_site.netloc)):
                ip_dict[parsed_site.netloc] = socket.gethostbyname(parsed_site.netloc)
        print "Finished site {0} of {1}".format(i + 1, len(site_dicts))
    return ip_dict


def ping_site(site_dict, ip_dict, num_times):
    parsed_site = urlparse.urlparse(site_dict["href"])
    scheme_map = {"ftp": 21, "http": 80, "https": 443, "rsync": 873}
    ip_addr = ip_dict[parsed_site.netloc]
    port = scheme_map[parsed_site.scheme]
    times = []
    for i in xrange(num_times):
        st = SocketTimer("Pinging {0}:{1} ({2} of {3})...".format(ip_addr, port, i + 1, num_times))
        with st:
            conn = socket.create_connection((ip_addr, port))
            conn.close()
        times.append(st.time_taken)
    return times


def ping_sites(site_dicts, ip_dict, num_times):
    for site_dict in site_dicts:
        ping_times = ping_site(site_dict, ip_dict, num_times)
