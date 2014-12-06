#!/usr/bin/env python
import Tkinter as tk
import Tkconstants as Tkc
import ttk
import time
import random
import sys
from threading import Thread
import os.path as osp
import os
import re
import logging
import sh
from Queue import Queue
import netaddr as NA

logging.getLogger().setLevel(logging.DEBUG)


class InvalidGuiError(Exception):

    def __init__(self, msg):
        Exception.__init__(self, msg)


class MinimumPacketRateSelector(ttk.Frame):

    def __init__(self, parent=None, callbacks=None):
        ttk.Frame.__init__(self, parent)
        self.callbacks = callbacks or {}
        self.label = ttk.Label(self)
        self.selector = tk.Spinbox(self)

        self.label.configure(text="Minimum packet rate: ")
        self.selector.configure(values=[128, 256, 512, 1024, 2048, 4096], command=self.on_activate)
        self.label.pack(side=Tkc.LEFT, expand=Tkc.X)
        self.selector.pack(side=Tkc.RIGHT, expand=Tkc.X)

    def on_activate(self, event=None):
        print self.selector
        if "activate" not in self.callbacks:
            return
        self.callbacks["activate"](event)


class IPRangeArgPanel(ttk.Frame):

    def __init__(self, parent=None, iprange_arg=None, callbacks=None):
        ttk.Frame.__init__(self, parent)
        self.callbacks = callbacks or {}
        self.label_entry_frame = ttk.Frame(self)
        self.start_end_frame = ttk.Frame(self)
        self.label = ttk.Label(self.label_entry_frame, text="IP Address or Range:")
        self.iprange_var = tk.StringVar(self, value=iprange_arg or "")
        self.iprange_var.trace("w", self.on_changed)
        self.entry = ttk.Entry(self.label_entry_frame, textvariable=self.iprange_var)
        self.entry.bind("<Return>", self.on_activate)
        self.label.pack(side=Tkc.LEFT)
        self.entry.pack(side=Tkc.RIGHT)
        self.start_label = ttk.Label(self.start_end_frame, text="Start: ", foreground="blue")
        self.end_label = ttk.Label(self.start_end_frame, text="End: ", foreground="blue")
        self.start_label.pack(side=Tkc.LEFT, padx=5)
        self.end_label.pack(side=Tkc.RIGHT, padx=5)
        self.label_entry_frame.pack(side=Tkc.TOP, pady=5)
        self.start_end_frame.pack(side=Tkc.BOTTOM, pady=5)

    @property
    def iprange_arg(self):
        return self.iprange_var.get()

    def set_state(self, state):
        if state in (True, Tkc.ACTIVE):
            self.entry.configure(state=Tkc.ACTIVE)
        elif state in (False, Tkc.DISABLED):
            self.entry.configure(state=Tkc.DISABLED)
        else:
            raise InvalidGuiError("Invalid state {0!r}".format(state))

    def on_changed(self, name, index, mode, var=None):
        var = var or self.iprange_var
        iprange_arg = var.get()
        if NA.valid_nmap_range(iprange_arg):
            ipranges = list(NA.iter_nmap_range(iprange_arg))
            ipranges.append(ipranges[-1])
            iprange_arg = NA.spanning_cidr(ipranges)
        elif NA.valid_glob(iprange_arg):
            iprange_arg = NA.spanning_cidr(NA.glob_to_iprange(iprange_arg))
        else:
            try:
                iprange_arg = NA.IPNetwork(iprange_arg).cidr
            except:
                iprange_arg = None
        if iprange_arg is not None:
            self.start_label.configure(text="Start: {0}".format(NA.IPAddress(iprange_arg.first)))
            self.end_label.configure(text="End: {0}".format(NA.IPAddress(iprange_arg.last)))
        if "changed" in self.callbacks:
            self.callbacks["changed"](name, index, mode, var)

    def on_activate(self, event=None):
        if "activate" in self.callbacks:
            self.callbacks["activate"](event)


class MyProgressGui(tk.Tk):

    def __init__(self, iprange_arg):
        tk.Tk.__init__(self)
        self.iprange_arg = iprange_arg
        self.queue = Queue()
        self.title(iprange_arg)
        self.iprange_panel = IPRangeArgPanel(self, iprange_arg=iprange_arg,
                                             callbacks={"changed": self.on_iprange_changed,
                                                        "activate": self.on_activate})
        self.status_label = ttk.Label(self, text="Waiting to start...")
        self.progressbar = ttk.Progressbar(self, orient=Tkc.HORIZONTAL, length=300, mode="determinate",
                                           maximum=100)
        self.button_panel = ttk.Frame(self)
        self.start_button = tk.Button(self.button_panel, text="Start", command=self.start_download)
        self.cancel_button = tk.Button(self.button_panel, text="Cancel", command=self.cancel_download)
        self.cancel_button.configure(state=Tkc.DISABLED)
        self.iprange_panel.pack(padx=10, pady=10)
        self.status_label.pack(padx=10, pady=10)
        self.progressbar.pack(padx=10, pady=10)
        self.button_panel.pack(padx=10, pady=10)
        self.start_button.pack(side=Tkc.LEFT)
        self.cancel_button.pack(side=Tkc.RIGHT)
        self.thread = None
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_iprange_changed(self, name, index, mode, var=None):
        var = var or self.iprange_panel.iprange_var
        self.iprange_arg = var.get()
        if not self.iprange_arg.strip():
            self.start_button.configure(state=Tkc.DISABLED)
            self.status_label.configure(text="Missing IP range! Enter at least 1 IP address or range.")
        else:
            self.start_button.configure(state=Tkc.ACTIVE)
            self.status_label.configure(text="Hit Start to query {0}...".format(self.iprange_arg))
            self.title(self.iprange_arg)

    def on_activate(self, event=None):
        if self.start_button.configure("state") != Tkc.DISABLED:
            self.start_download()

    def on_closing(self, event=None):
        if self.thread is not None:
            self.thread.cancel()
        self.destroy()

    def start_download(self):
        self.start_button.configure(state=Tkc.DISABLED)
        self.cancel_button.configure(state=Tkc.ACTIVE)
        self.iprange_panel.set_state(Tkc.DISABLED)
        self.thread = CommandThread(self.queue, self.iprange_arg)
        self.thread.start()
        self.call_periodically()

    def cancel_download(self):
        if self.thread is not None:
            self.thread.cancel()
        self.cancel_button.configure(state=Tkc.DISABLED)
        self.status_label.configure(text="Cancelling...")
        self.progressbar.configure(value=0)
        while self.queue.qsize():
            self.queue.get()

    def call_periodically(self, wait_time_ms=50):
        self.checkqueue()
        if self.thread.is_alive():
            self.after(wait_time_ms, self.call_periodically)
        else:
            self.start_button.configure(state=Tkc.ACTIVE)
            self.iprange_panel.set_state(Tkc.ACTIVE)
            self.cancel_button.configure(state=Tkc.DISABLED)
            self.progressbar.configure(value=0)

    def checkqueue(self):
        while self.queue.qsize():
            try:
                msg = self.queue.get()
                cur_proc, pct_done = msg.split("@")
                new_msg = "{0} is {1:2.2f}% done".format(cur_proc, float(pct_done))
                self.status_label.configure(text=new_msg)
                old_values = self.progressbar.configure("value")
                print old_values
                new_values = self.progressbar.configure(value=float(pct_done))
                print new_values
            except Exception as e:
                logging.exception("Error in checkqueue(): %s", e)


class ThreadedClient(Thread):

    def __init__(self, queue):
        Thread.__init__(self)
        self.queue = queue

    def run(self):
        for index in xrange(1, 101):
            sleep_time = random.random() * 0.3
            start_time = time.time()
            time.sleep(sleep_time)
            end_time = time.time()
            msg = "Finished function {0} in {1} ms".format(index, end_time - start_time)
            self.queue.put(msg)


class CommandThread(Thread):

    def __init__(self, queue, iprange_arg, stats_update_interval=0.5, verbosity_level=3, debugging_level=1):
        Thread.__init__(self)
        self.queue = queue
        self.iprange_arg = iprange_arg
        self.stats_update_interval = "{0:0.3f}s".format(stats_update_interval)
        self.running_command = None
        self.verbosity_level = verbosity_level
        self.debugging_level = debugging_level

    def run(self):
        output_basename = osp.join("/tmp", self.iprange_arg.replace("/", "_"))
        command = sh.nmap.bake("-T4",
                               "--traceroute",
                               "-oA",
                               output_basename,
                               {"stats-every": self.stats_update_interval},
                               self.iprange_arg,
                               "-{0}".format('v' * self.verbosity_level),
                               "-{0}".format('d' * self.debugging_level),
                               {"max-scan-delay": "8s", "max-retries": 13, "min-rate": 256})

        logging.info("Command to execute: %s", command)
        try:
            self.running_command = command(_iter_noblock=True, _err_to_out=True, _tty_out=False)
            for line in self.running_command:
                if not isinstance(line, basestring):
                    continue
                progress_rgx = "(?P<current_process_name>.*?) Timing: About (?P<percent_done>[0-9.]+)% done"
                progress_match = re.search(progress_rgx, line, flags=re.M | re.I)
                sys.stdout.write(line)
                if progress_match is not None:
                    group_dict = progress_match.groupdict()
                    self.queue.put(group_dict["current_process_name"] + "@" + group_dict["percent_done"])
                    logging.info("Progress line matches! Groupdict: %r", group_dict)
        except sh.SignalException as cancel_exc:
            logging.info("Command was cancelled: %s", cancel_exc)
        except sh.ErrorReturnCode as err:
            logging.exception("Command failed in some way. Printing stack...\n%s%s", err.stdout, err.stderr)
        self.running_command = None

    def cancel(self):
        if self.running_command is not None:
            self.running_command.process.kill()
            self.running_command.process.terminate()
            self.running_command = None


def main(args):
    app = MyProgressGui(args[0] if args else "")
    app.mainloop()


if __name__ == "__main__":
    main(sys.argv[1:])
