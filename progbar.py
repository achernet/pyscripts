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


class GenericProgressBar(ttk.Frame):

    DEFAULT_TITLE = "Downloading package information from PyPI..."
    DEFAULT_MAXIMUM = 100
    DEFAULT_START_VALUE = 0
    DEFAULT_STATUS = "Downloading..."
    DEFAULT_THREAD_CREATOR = lambda queue: None

    @property
    def maximum(self):
        return self._maximum

    @maximum.setter
    def maximum(self, new_value):
        self._maximum = new_value
        if self.bar_mover is not None:
            self.after_cancel(self.bar_mover)
        if new_value <= 0:
            self.progressbar.configure(mode="indeterminate", maximum=self.DEFAULT_MAXIMUM)
            self.bar_mover = self.after(int(1e3 / self.DEFAULT_MAXIMUM), self.move_bar)
        else:
            self.progressbar.configure(mode="determinate", maximum=self._maximum)
            self.bar_mover = None
        self.percent_label.configure(text=self.percent_text)

    def move_bar(self):
        if self.is_ascending:
            next_value = (self.value + 1)
            if next_value % self.DEFAULT_MAXIMUM == 0:
                self.is_ascending = False
            else:
                self.value = next_value % self.DEFAULT_MAXIMUM
        else:
            next_value = (self.value - 1)
            if next_value % self.DEFAULT_MAXIMUM == 0:
                self.is_ascending = True
            else:
                self.value = next_value % self.DEFAULT_MAXIMUM
        self.after(int(1e3 / self.DEFAULT_MAXIMUM), self.move_bar)

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = new_value
        self.progressbar.configure(value=self._value)
        self.percent_label.configure(text=self.percent_text)

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, new_status):
        self._status = new_status
        self.status_label.configure(text=self._status)

    @property
    def percent_text(self):
        if self.maximum <= 0 or self.value < 0:
            return ""
        else:
            return "{0:.1f}%".format(self.value * 100.0 / self.maximum)

    def __init__(self, master=None, title=None, maximum=None, value=None, status=None, thread_creator=None):
        """
        :param master: The master top-level form to place this progress bar in (or None to make a new one)
        :type master: :class:`ttk.Frame`
        :param str title: The title this progress bar widget should have.
        :param float maximum: The maximum value for the progress bar. Zero or less means it's indeterminate.
        :param float value: The starting (and "current") value for the progress bar.
        :param str status: The text to assign to the status label.
        :param func thread_creator: A callback function that takes a queue and returns a queuing thread
        """
        # Coerce parameters to defaults as necessary.
        title = title or self.DEFAULT_TITLE
        maximum = maximum or self.DEFAULT_MAXIMUM
        value = value or self.DEFAULT_START_VALUE
        status = status or self.DEFAULT_STATUS
        thread_creator = thread_creator or self.DEFAULT_THREAD_CREATOR

        # Call the parent constructor.
        master = master or tk.Tk()
        ttk.Frame.__init__(self, master)

        # Set up member variables (non-GUI first).
        self.queue = Queue()
        self.thread = None
        self.bar_mover = None
        self.is_ascending = True
        self.thread_creator = thread_creator
        self._maximum = maximum
        self._value = value
        self._status = status

        # Set up GUI member variables.
        self.status_label = ttk.Label(self.master, text=status, width=64)
        prog_frame = ttk.Frame(self.master)
        self.progressbar = ttk.Progressbar(prog_frame,
                                           orient=Tkc.HORIZONTAL,
                                           mode="determinate",
                                           maximum=maximum,
                                           value=value)
        self.percent_label = ttk.Label(prog_frame, text=" ")
        button_frame = ttk.Frame(self.master)
        self.cancel_button = ttk.Button(button_frame, text="Cancel", command=self.cancel_download)
        self.cancel_button.configure(state=Tkc.DISABLED)
        # Set up packing for the GUI.
        self.status_label.pack(padx=5, pady=5)
        self.progressbar.pack(anchor=Tkc.W, expand=True, fill=Tkc.X, padx=5, side=Tkc.LEFT)
        self.percent_label.pack(anchor=Tkc.E, side=Tkc.RIGHT)
        self.cancel_button.pack(padx=5, pady=5)
        prog_frame.pack(fill=Tkc.X, ipadx=5, padx=5, pady=5)
        button_frame.pack(fill=Tkc.X, ipadx=5, padx=5, pady=5)
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.master.title(title)
        self.configure(maximum=self.maximum, value=self.value, status=self.status)

    def __enter__(self):
        self.cancel_button.configure(state=Tkc.ACTIVE)
        self.thread = self.thread_creator(self.queue)
        self.thread.start()
        self.call_periodically()
        return self

    def __exit__(self, *args):
        while self.thread.is_alive():
            self.update()
        # self.cancel_download()
        self.destroy()
        return False

    def configure(self, cnf=None, **kwargs):
        """
        Update this progress bar with the provided keyword arguments. Valid keys include:

            maximum:: Configures the progress bar with a new maximum.
            title:: Configures the widget with a new title.
            value:: Updates the progress bar, adjusting the value as given.
            status:: Updates the status label.
        """
        maximum = kwargs.pop("maximum", None)
        if maximum is not None:
            self.maximum = maximum
        value = kwargs.pop("value", None)
        if value is not None:
            self.value = value
        title = kwargs.pop("title", None)
        if title is not None:
            self.master.title(title)
        status = kwargs.pop("status", None)
        if status is not None:
            self.status = status
        return ttk.Frame.configure(self, cnf, **kwargs)

    def on_closing(self, event=None):
        if self.thread is not None:
            self.thread.cancel()
        self.destroy()

    def cancel_download(self):
        if self.thread is not None:
            self.thread.cancel()
        self.cancel_button.configure(state=Tkc.DISABLED)
        self.status = "Cancelling..."
        self.progressbar.configure(value=0)
        while self.queue.qsize():
            self.queue.get()

    def call_periodically(self, wait_time_ms=50):
        self.checkqueue()
        if self.thread.is_alive():
            self.after(wait_time_ms, self.call_periodically)
        else:
            self.cancel_button.configure(state=Tkc.DISABLED)
            self.progressbar.configure(value=0)

    def checkqueue(self):
        while self.queue.qsize():
            try:
                msg = self.queue.get()
                self.configure(**msg)
            except Exception as e:
                logging.exception("Error in checkqueue(): %s", e)


class QueuingThread(Thread):
    """
    An abstract thread with a message queue that can run a shell command.
    """

    def __init__(self, queue):
        Thread.__init__(self)
        self.queue = queue
        self.running_command = None

    def run(self):
        command = self.build_command()
        logging.info("Command to execute: %s", command)
        try:

            self.running_command = command()
            for line in self.running_command:
                if not isinstance(line, basestring):
                    continue
                progress_rgx = self.compile_progress_regex()
                progress_match = progress_rgx.search(line)
                sys.stdout.write(line)
                if progress_match is not None:
                    self.enqueue_progress_match(progress_match)
        except sh.SignalException as cancel_exc:
            logging.info("Command was cancelled: %s", cancel_exc)
        except sh.ErrorReturnCode as err:
            logging.exception("Command failed in some way. Printing stack...\n%s%s", err.stdout, err.stderr)
        self.running_command = None

    def build_command(self):
        """
        Abstract function to build and return a :class:`sh.Command` object.

        :return: The command object to run
        :rtype: :class:`sh.Command`
        """
        raise NotImplementedError

    def compile_progress_regex(self):
        """
        Abstract function to compile and return a regex capable of reporting some type of progress.

        :return: The compiled progress regex
        :rtype: :class:`_sre.SRE_Pattern`
        """
        raise NotImplementedError

    def enqueue_progress_match(self, progress_match):
        """
        Abstract function to process and enqueue a regex match indicating a progress update.
        """
        raise NotImplementedError


    def cancel(self):
        """
        Cancel the command currently running, if there is one.
        """
        if self.running_command is not None:
            self.running_command.process.kill()
            self.running_command.process.terminate()
            self.running_command = None


class NmapCommandThread(QueuingThread):

    def __init__(self, queue, iprange_arg, stats_update_interval=0.5, verbosity_level=3, debugging_level=1):
        QueuingThread.__init__(self, queue)
        self.iprange_arg = iprange_arg
        self.stats_update_interval = "{0:0.3f}s".format(stats_update_interval)
        self.verbosity_level = verbosity_level
        self.debugging_level = debugging_level

    def build_command(self):
        command = sh.nmap.bake("-T4",
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
