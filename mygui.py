import Tkinter as tk
import Tkconstants as Tkc
import logging


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


class GuiQuery(object):

    def __init__(self, parent=None):
        parent = parent or tk.Tk()

        self.query_frame = tk.Frame(parent)
        self.query_frame.pack(side=Tkc.TOP, fill=Tkc.X)
        self.options_frame = tk.Frame(parent)
        self.options_frame.pack(side=Tkc.TOP, fill=Tkc.X)
        self.days_frame = tk.Frame(parent)
        self.days_frame.pack(side=Tkc.TOP, fill=Tkc.X)

        self.query_var = tk.StringVar(self.query_frame)
        self.query_var.trace("w", self.on_write)
        self.stats_var = tk.IntVar(self.options_frame)
        self.stats_var.trace("w", self.on_stats_checked)
        self.backup_var = tk.IntVar(self.options_frame)
        self.backup_var.trace("w", self.on_backup_checked)

        self.label = tk.Label(self.query_frame, text="Search Query:")
        self.label.pack(side=Tkc.LEFT)
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

        self.max_age = GuiMaxAge(self.days_frame)

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
        return self.max_age.days

    def run_query(self, event=None):
        query_config = {"query": self.query,
                        "stats": self.should_do_stats,
                        "backup": self.should_do_backup,
                        "max_cache_age": self.max_cache_age}
        print "Query will run with {0}".format(query_config)

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
        print "Backup search: {0}".format(self.backup_var.get())


class GuiLogger(logging.Handler):

    def __init__(self, parent=None):
        logging.Handler.__init__(self)
        self.setLevel(logging.DEBUG)

        parent = parent or tk.Tk()
        self.rsb = tk.Scrollbar(parent)
        self.rsb.pack(side=Tkc.RIGHT, fill=Tkc.Y)
        self.bsb = tk.Scrollbar(parent)
        self.bsb.pack(side=Tkc.BOTTOM, fill=Tkc.X)
        self.widget = tk.Listbox(parent, xscrollcommand=self.bsb.set, yscrollcommand=self.rsb.set, bg="white")
        self.widget.pack(fill=Tkc.BOTH, expand=True)
        self.rsb.config(command=self.widget.yview)
        self.bsb.config(command=self.widget.xview)
        self.widget.config(state=Tkc.DISABLED)

    def emit(self, record):
        self.widget.config(state=Tkc.NORMAL)
        self.widget.insert(Tkc.END, self.format(record) + "\n")
        self.widget.see(Tkc.END)
        self.widget.config(state=Tkc.DISABLED)


class MyGui(object):

    TITLE = "PyPI Pip Search with Statistics (v.0.1.3)"

    def __init__(self, root=None):
        self.root = root or tk.Tk()
        self.root.title(self.TITLE)

        self.options_panel = tk.Frame(self.root)
        self.options_panel.pack(side=Tkc.TOP, fill=Tkc.BOTH, expand=True)
        self.log_panel = tk.Frame(self.root)
        self.log_panel.pack(side=Tkc.TOP, fill=Tkc.BOTH, expand=True)
        self.results_panel = tk.Frame(self.root)
        self.results_panel.pack(side=Tkc.TOP, fill=Tkc.BOTH, expand=True)

        self.log_box = GuiLogger(parent=self.log_panel)
