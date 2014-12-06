#!/usr/bin/env python
import Tkinter as tk
import Tkconstants as Tkc
import logging
import ttk

logging.getLogger().setLevel(logging.DEBUG)


class GuiMaxAge(object):
    """
    GUI Tkinter spinbox to configure a maximum age in days.
    """

    def __init__(self, parent=None):
        parent = parent or tk.Tk()
        self.cache_days_var = tk.StringVar(parent)
        self.cache_days_var.set("0")

        self.label = tk.Label(parent, text="Days to cache package information:")
        self.label.pack(side=Tkc.LEFT)
        self.cache_days = tk.Spinbox(parent, from_=0.0, to=30.0, increment=1.0, textvariable=self.cache_days_var,
                                     validate=Tkc.ALL, format="%0.1f", validatecommand=self.validate, value=0.5)
        self.cache_days.pack(side=Tkc.LEFT)

    @property
    def days(self):
        try:
            return float(self.cache_days_var.get())
        except Exception as e:
            return -1.0

    def validate(self, *args):
        return 0.0 <= self.days <= 30.0


class GuiQuery(ttk.Frame):

    def __init__(self, parent=None):
        ttk.Frame.__init__(self, parent, padding=2)

        self.query_frame = ttk.Frame(parent)
        self.query_frame.pack(side=Tkc.TOP, fill=Tkc.X)
        self.options_frame = ttk.Frame(parent)
        self.options_frame.pack(side=Tkc.TOP, fill=Tkc.X)
        self.days_frame = ttk.Frame(parent)
        self.days_frame.pack(side=Tkc.TOP, fill=Tkc.X)

        self.query_var = tk.StringVar(self.query_frame)
        self.query_var.trace("w", self.on_write)
        self.stats_var = tk.IntVar(self.options_frame)
        self.stats_var.trace("w", self.on_stats_checked)
        self.backup_var = tk.IntVar(self.options_frame)
        self.backup_var.trace("w", self.on_backup_checked)
        self.days_var = tk.StringVar(self.days_frame)
        self.days_var.trace("w", self.on_days_changed)

        self.search_label = tk.Label(self.query_frame, text="Search Query:")
        self.search_label.pack(side=Tkc.LEFT)
        self.entry = tk.Entry(self.query_frame, textvariable=self.query_var, bg="white")
        self.entry.bind("<Return>", self.run_query)
        self.entry.pack(side=Tkc.LEFT, expand=True, fill=Tkc.X)
        self.button = tk.Button(self.query_frame, text="Search", command=self.run_query)
        self.button.pack(side=Tkc.LEFT)
        self.button.config(state=Tkc.DISABLED)

        self.stats = tk.Checkbutton(self.options_frame, text="Collect statistics?", variable=self.stats_var)
        self.stats.pack(side=Tkc.LEFT, expand=True, fill=Tkc.X)
        self.backup = tk.Checkbutton(self.options_frame, text="Enable backup search?", variable=self.backup_var)
        self.backup.pack(side=Tkc.LEFT, expand=True, fill=Tkc.X)
        self.stats.select()

        self.age_label = tk.Label(self.days_frame, text="Days to cache package information:")
        self.age_label.pack(side=Tkc.LEFT)
        self.max_age = tk.Spinbox(self.days_frame, from_=0.0, to=30.0, increment=0.5, format="%0.3f",
                                  textvariable=self.days_var)
        self.max_age.pack(side=Tkc.LEFT)
        self.max_age.config(state="readonly")

    @property
    def query(self):
        return self.query_var.get()

    @property
    def should_do_stats(self):
        return bool(self.stats_var.get())

    @property
    def should_do_backup(self):
        return bool(self.backup_var.get())

    @property
    def max_cache_age(self):
        return float(self.days_var.get())

    def run_query(self, event=None):
        query_config = {"query": self.query,
                        "stats": self.should_do_stats,
                        "backup": self.should_do_backup,
                        "max_cache_age": self.max_cache_age}
        logging.info("Query will run with %s", query_config)

    def on_write(self, name, index, mode, var=None):
        var = var or self.query_var
        query_text = self.query
        search_state = Tkc.DISABLED if not query_text.strip() else Tkc.NORMAL
        self.button.config(state=search_state)

    def on_stats_checked(self, name, index, mode, var=None):
        var = var or self.stats_var
        do_stats = self.should_do_stats
        if not do_stats:
            self.backup.config(state=Tkc.DISABLED)
            self.backup_var.set(False)
        else:
            self.backup.config(state=Tkc.NORMAL)

    def on_backup_checked(self, name, index, mode, var=None):
        var = var or self.backup_var
        do_backup = self.should_do_backup
        logging.info("Backup search: %s", self.backup_var.get())

    def on_days_changed(self, name, index, mode, var=None):
        var = var or self.days_var

    def on_max_age_change(self, old_value, new_value):
        logging.info("Changing max age from %0.3f to %0.3f", old_value, new_value)

    def on_max_age_validate(self, old_value, new_value):
        logging.info("Validating max age (%0.3f -> %0.3f)", old_value, new_value)

    def quit(self, event=None):
        print "Quitting... (event: {0})".format(event)
        self.master.destroy()


class GuiLogger(logging.Handler):

    def __init__(self, parent=None):
        logging.Handler.__init__(self)
        self.setLevel(logging.DEBUG)

        parent = parent or tk.Tk()
        self.rsb = tk.Scrollbar(parent)
        self.rsb.pack(side=Tkc.RIGHT, fill=Tkc.Y)
        self.widget = tk.Listbox(parent, yscrollcommand=self.rsb.set, bg="white")
        self.widget.pack(fill=Tkc.BOTH, expand=True)
        self.rsb.config(command=self.widget.yview)
        self.widget.configure(state=Tkc.DISABLED)

    def emit(self, record):
        self.widget.configure(state=Tkc.NORMAL)
        self.widget.insert(Tkc.END, self.format(record) + "\n")
        self.widget.see(Tkc.END)
        # self.widget.configure(state=Tkc.DISABLED)


class MyGui(object):

    TITLE = "Logging GUI"

    def __init__(self, root=None):
        self.root = root or tk.Tk()
        self.root.title(self.TITLE)

        self.options_panel = ttk.Frame(self.root)
        self.options_panel.pack(side=Tkc.TOP, fill=Tkc.BOTH, expand=True)
        self.log_panel = ttk.Frame(self.root)
        self.log_panel.pack(side=Tkc.TOP, fill=Tkc.BOTH, expand=True)
        self.results_panel = ttk.Frame(self.root)
        self.results_panel.pack(side=Tkc.TOP, fill=Tkc.BOTH, expand=True)

        self.log_box = GuiLogger(parent=self.log_panel)
        self.log_box.pack(side=Tkc.BOTTOM, fill=Tkc.BOTH, expand=True)


def main():
    root = tk.Tk()
    root.withdraw()
    root.title("PyPI Pip Search with Statistics (v.0.2.0)")
    root.option_add("*tearOff", False)

    gui_query = GuiQuery(root)

    root.protocol("WM_DELETE_WINDOW", gui_query.quit)
    root.deiconify()
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
