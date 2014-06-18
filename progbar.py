#!/usr/bin/env python
import Tkinter as tk
import Tkconstants as Tkc
import ttk
import logging
from generic_download_queue import GenericDownloadQueue

logging.getLogger().setLevel(logging.DEBUG)


class GenericProgressBar(ttk.Frame, GenericDownloadQueue):
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
        title = title or "Downloading package information from PyPI..."
        maximum = maximum or 100
        value = value or 0
        status = status or "Downloading..."
        GenericDownloadQueue.__init__(self, thread_creator=thread_creator)

        # Call the parent constructors.
        GenericDownloadQueue.__init__(self, thread_creator=thread_creator)
        master = master or tk.Tk()
        ttk.Frame.__init__(self, master)

        # Set up member variables (non-GUI first).
        self.bar_mover = None
        self.is_ascending = True
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
        return GenericDownloadQueue.__enter__(self)

    def __exit__(self, *args):
        threadStatus = GenericDownloadQueue.__exit__(self, *args)
        self.destroy()
        return threadStatus

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
        self.shutdown()
        self.destroy()

    def cancel_download(self):
        GenericDownloadQueue.cancel_download(self)
        self.cancel_button.configure(state=Tkc.DISABLED)
        self.status = "Cancelling..."
        self.progressbar.configure(value=0)
        while self.queue.qsize():
            self.queue.get()

    def call_periodically(self, wait_time_ms=50):
        self.checkqueue()
        if self.thread.is_alive():
            self.after(wait_time_ms, self.call_periodically)
            return
        self.cancel_button.configure(state=Tkc.DISABLED)
        self.progressbar.configure(value=0)
