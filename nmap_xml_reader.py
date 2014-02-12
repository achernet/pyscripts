#!/usr/bin/env python
import sys
from argparse import ArgumentParser, FileType
from lxml import etree
from lxml.etree import XMLParser
from total_ordering import total_ordering
from netaddr import IPAddress


@total_ordering
class HopInfo(object):

    def __init__(self, hop_elem):
        self.element = hop_elem

    @property
    def ipaddr(self):
        return IPAddress(self.element.get("ipaddr"))

    @property
    def time_ms(self):
        return float(self.element.get("rtt"))

    @property
    def index(self):
        return int(self.element.get("ttl")) - 1

    def __lt__(self, other):
        return (self.index, self.time_ms) < (other.index, other.time_ms)

    def __eq__(self, other):
        return (self.index, self.time_ms) == (other.index, other.time_ms)

    def __repr__(self):
        return "[{0.index}] {0.ipaddr} @ {0.time_ms}ms".format(self)

    def __str__(self):
        return repr(self)


class HostInfo(object):

    def __init__(self, host_elem):
        self.element = host_elem

    @property
    def addresses(self):
        return [IPAddress(e.get("addr")) for e in self.element.xpath("address")]

    @property
    def ports(self):
        port_elems = self.element.xpath("ports/port[state[@state=\'open\']]")
        return [int(e.get("portid")) for e in port_elems]

    @property
    def hostnames(self):
        return [e.get("name") for e in self.element.xpath("hostnames/hostname")]

    @property
    def hops(self):
        hop_elems = self.element.xpath("trace/hop")
        return sorted([HopInfo(elem) for elem in hop_elems])

    def __repr__(self):
        hostnames_str = ", ".join(self.hostnames)
        ports_str = ", ".join([str(port) for port in self.ports])
        str_parts = []
        for addr in self.addresses:
            if hostnames_str:
                next_str = "{0} <{1}> ({2})".format(addr, hostnames_str, ports_str)
            else:
                next_str = "{0} ({1})".format(addr, ports_str)
            str_parts.append(next_str)
        for hop in self.hops:
            str_parts.append("\t{0}".format(hop))
        return "\n".join(str_parts)

    def __str__(self):
        return repr(self)


def parse_nmap_xml(xml_file):
    with open(xml_file, "r") as f:
        data = f.read()
    tree = etree.fromstring(data, XMLParser(recover=True))
    host_elems = tree.xpath("//host[status[@state=\'up\']]")
    return [HostInfo(elem) for elem in host_elems]


def parse_args(args):
    ap = ArgumentParser("nmap.xml Reader")
    ap.add_argument("-a", "--all", action="store_true", help="Print all information")
    ap.add_argument("xml_file", type=FileType("r"), help="The path to the .xml file")
    parser_ns = ap.parse_args(args)
    return parser_ns


def main(args):
    parser_ns = parse_args(args)
    host_infos = parse_nmap_xml(parser_ns.xml_file.name)
    if parser_ns.all:
        print "\n".join([str(host_info) for host_info in host_infos])
    else:
        addresses = set()
        for info in host_infos:
            addresses.update(info.addresses)
            for hop in info.hops:
                addresses.add(hop.ipaddr)
        addresses = sorted(addresses)
        print "\n".join([str(addr) for addr in addresses])


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
