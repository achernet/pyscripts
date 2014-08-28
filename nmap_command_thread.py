import os.path as osp
import re
import sh
import logging
from queuing_thread import QueuingThread


class NmapCommandThread(QueuingThread):

    def __init__(self, queue, iprange_arg, stats_update_interval=0.5, verbosity_level=3, debugging_level=1):
        QueuingThread.__init__(self, queue)
        self.iprange_arg = iprange_arg
        self.stats_update_interval = "{0:0.3f}s".format(stats_update_interval)
        self.verbosity_level = verbosity_level
        self.debugging_level = debugging_level

    def build_command(self):
        command = sh.Command("nmap")
        command = command.bake("-T4",
                               "--traceroute",
                               "-oA",
                               osp.join("/tmp", self.iprange_arg.replace("/", "_")),
                               {"stats-every": self.stats_update_interval},
                               self.iprange_arg,
                               "-{0}".format('v' * self.verbosity_level),
                               "-{0}".format('d' * self.debugging_level),
                               {"max-scan-delay": "8s", "max-retries": 13, "min-rate": 256},
                               {"_iter_noblock": True, "_err_to_out": True, "_tty_out": False})
        return command

    def compile_progress_regex(self):
        progress_rgx = "(?P<status>.*?) Timing: About (?P<percent_done>[0-9.]+)% done"
        return re.compile(progress_rgx, flags=re.M | re.I)

    def enqueue_progress_match(self, progress_match):
        group_dict = progress_match.groupdict()
        percent_done = float(group_dict.pop("percent_done"))
        group_dict["maximum"] = 100.0
        group_dict["value"] = percent_done
        self.queue.put(group_dict)
        logging.info("Progress line matches! Groupdict: %r", group_dict)
