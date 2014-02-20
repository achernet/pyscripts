#!/usr/bin/env python
import copy
import csv
import logging
import os
import platform
import Tkinter as tk
import ttk
import Tkconstants as Tkc
import tkFileDialog as Tkfc
import tkFont as Tkf
import tkMessageBox as Tkmb
import webbrowser
import sys

logging.getLogger().setLevel(logging.DEBUG)


class MultiListbox(ttk.Frame):

    def __init__(self, parent, lists):
        ttk.Frame.__init__(self, parent)
        self.lists = []
        self.colmapping = {}
        self.orig_data = None
        self.fonts = {}
        self.y_sel = None
        for label, width in lists:
            frame = tk.Frame(self)
            frame.pack(side=Tkc.LEFT, expand=Tkc.YES, fill=Tkc.BOTH)

            sort_button = tk.Button(frame, text=label, borderwidth=1, relief=Tkc.RAISED)
            sort_button.pack(fill=Tkc.X)
            sort_button.bind("<Button-1>", self._sort)
            sort_button.config(font=self.header_font)

            self.colmapping[sort_button] = (len(self.lists), 1)
            list_box = tk.Listbox(frame, width=width, borderwidth=0, selectborderwidth=0,
                                  relief=Tkc.FLAT, exportselection=Tkc.FALSE)
            list_box.pack(expand=Tkc.YES, fill=Tkc.BOTH)
            self.lists.append(list_box)
            list_box.bind("<B1-Motion>", lambda e, s=self: s._select(e.y))
            list_box.bind("<Button-1>", lambda e, s=self: s._select(e.y))
            list_box.bind("<Leave>", lambda e: "break")
            list_box.bind("<B2-Motion>", lambda e, s=self: s._b2motion(e.x, e.y))
            list_box.bind("<Button-2>", lambda e, s=self: s._button2(e.x, e.y))
            list_box.bind("<Double-Button-1>", lambda e, s=self: s._activate(e.y))

        frame = tk.Frame(self)
        frame.pack(side=Tkc.LEFT, fill=Tkc.Y)
        frame_label = tk.Label(frame, borderwidth=1, relief=Tkc.RAISED)
        frame_label.pack(fill=Tkc.X)
        scroll_bar = tk.Scrollbar(frame, orient=Tkc.VERTICAL, command=self._scroll)
        scroll_bar.pack(expand=Tkc.YES, fill=Tkc.Y)
        self.lists[0]["yscrollcommand"] = scroll_bar.set

        # Configure scrolling by arrow keys and Page Up/Down.
        self.bind_all("<Up>", lambda e, s=self: s._scroll("scroll", "-1", "units", select=True))
        self.bind_all("<Down>", lambda e, s=self: s._scroll("scroll", "1", "units", select=True))
        self.bind_all("<Next>", lambda e, s=self: s._scroll("scroll", "1", "pages", select=True))
        self.bind_all("<Prior>", lambda e, s=self: s._scroll("scroll", "-1", "pages", select=True))
        self.bind_all("<Return>", lambda e, s=self: s._activate(e.y))

        self.master.protocol("WM_DELETE_WINDOW", self.master.destroy)

    @property
    def header_font(self):
        if "header" in self.fonts:
            return self.fonts["header"]
        font_families = sorted(Tkf.families(self.master))
        if "Liberation Sans" in font_families:
            family = "Liberation Sans"
        else:
            family = "Tahoma"
        font = Tkf.Font(family=family, size=13, weight=Tkf.BOLD)
        self.fonts["header"] = font
        return font

    def _sort(self, event):

        # Get the listbox to sort by (mapped by the header buttons)
        originating_button = event.widget
        column, direction = self.colmapping[originating_button]

        # Make an in-memory copy of all the table data.
        table_data = self.get(0, Tkc.END)
        if self.orig_data is None:
            self.orig_data = copy.deepcopy(table_data)
        row_count = len(table_data)

        # Remove any old sort indicators (if they exist)
        for button in self.colmapping:
            button_text = button.cget("text")
            if button_text[0] == "[":
                button.config(text=button_text[4:])

        # Sort data based on direction.
        button_label = originating_button.cget("text")
        if direction == 0:
            table_data = self.orig_data
        elif direction == 1:
            originating_button.config(text="[+] {0}".format(button_label))
            table_data.sort(key=lambda obj: obj[column], reverse=False)
        else:  # direction == -1
            originating_button.config(text="[-] {0}".format(button_label))
            table_data.sort(key=lambda obj: obj[column], reverse=True)

        # Clear and refill the widget.
        self.delete(0, Tkc.END)
        for row in xrange(row_count):
            self.insert(Tkc.END, table_data[row])

        # Finally, toggle the direction flag.
        if direction == 1:
            direction = -1
        else:
            direction += 1
        self.colmapping[originating_button] = column, direction

    def _activate(self, y):
        item_info = self.get(self.curselection()[0])
        logging.info("Opening PyPI web page for item: %s", item_info)
        pypi_url = "https://pypi.python.org/pypi/{0[0]}".format(item_info)
        webbrowser.open_new(pypi_url)

    def _select(self, y):
        row = self.lists[0].nearest(y)
        logging.info("Selecting Y point %s (got row %s)", y, row)
        return self._select_row(row)

    def _select_row(self, row):
        logging.info("Selecting row %d", row)
        self.selection_clear(0, Tkc.END)
        self.selection_set(row)
        # self.see(row)
        return "break"

    def _button2(self, x, y):
        logging.info("Button 2 at (%d, %d)", x, y)
        for list_widget in self.lists:
            list_widget.scan_mark(x, y)
        return "break"

    def _b2motion(self, x, y):
        logging.info("B2 Motion to (%d, %d)", x, y)
        for list_widget in self.lists:
            list_widget.scan_dragto(x, y)
        return "break"

    def _scroll(self, *args, **kwargs):
        select = kwargs.pop("select", False)
        logging.info("Scrolling -- args: %s, select: %s", args, select)

        if select and self.curselection():
            new_index, should_do_scroll = self.get_new_selection(args)
            if new_index is None:
                logging.debug("No selection change for args: %s - scrolling...", args)
                should_do_scroll = True
            else:
                old_index = int(self.curselection()[0])
                logging.debug("Changing selection from index %d to %d", old_index, new_index)
                self._select_row(new_index)
        else:
            should_do_scroll = True

        if should_do_scroll:
            for list_widget in self.lists:
                list_widget.yview(*args)

    def get_new_selection(self, scroll_args):
        """
        If selection change upon scrolling is enabled, return the new index that should be selected after the
        scroll operation finishes. If the new index is currently visible, just select it and skip the actual
        scrolling process entirely.

        :param list scroll_args: The arguments passed to the scrollbar widget
        :return tuple: The index that should be selected afterward, followed by its current "selectability"
        """
        cur_selection = self.curselection()

        # If the scrollbar is being dragged, or if nothing is currently selected, then do not select anything.
        if scroll_args[0] != "scroll" or not cur_selection:
            return None, False
        amount = int(scroll_args[1])
        pixel_dict = self.get_pixel_dict()
        page_size = len(pixel_dict) - 2 if scroll_args[2] == "pages" else 1
        scroll_diff = amount * page_size
        old_index = int(cur_selection[0])
        new_index = max(0, min(self.lists[0].size() - 1, old_index + scroll_diff))
        return new_index, new_index not in pixel_dict

    def curselection(self):
        return self.lists[0].curselection()

    def delete(self, first, last=None):
        for list_widget in self.lists:
            list_widget.delete(first, last)

    def get(self, first, last=None):
        result = []
        for list_widget in self.lists:
            result.append(list_widget.get(first, last))
        if last:
            return map(*[None] + result)
        return result

    def index(self, index):
        self.lists[0].index(index)

    def insert(self, index, *elements):
        for elem in elements:
            i = 0
            for list_widget in self.lists:
                list_widget.insert(index, elem[i])
                i += 1

    def size(self):
        return self.lists[0].size()

    def see(self, index):
        for list_widget in self.lists:
            list_widget.see(index)

    def selection_anchor(self, index):
        for list_widget in self.lists:
            list_widget.selection_anchor(index)

    def selection_clear(self, first, last=None):
        for list_widget in self.lists:
            list_widget.selection_clear(first, last)

    def selection_includes(self, index):
        return self.lists[0].selection_includes(index)

    def selection_set(self, first, last=None):
        for list_widget in self.lists:
            list_widget.selection_set(first, last)

    def get_pixel_dict(self):
        list_box = self.lists[0]
        height = list_box.winfo_height() + 1
        pixel_dict = {list_box.nearest(height): height}
        for pixel in xrange(height, 0, -1):
            pixel_dict[list_box.nearest(pixel)] = pixel
        max_index, bottom_y = max(pixel_dict.items())
        item_height = bottom_y - pixel_dict.get(max_index - 1, 1)
        while bottom_y + item_height < height:
            max_index += 1
            bottom_y += item_height
            pixel_dict[max_index] = bottom_y
        pixel_dict.pop(max_index)
        return pixel_dict


def browse_csv(csv_file_path=None):
    if csv_file_path is None:
        valid_filetypes = (("CSV files", "*.csv"), ("All files", "*.*"))
        file_path = Tkfc.askopenfilename(filetypes=valid_filetypes, initialdir=".")
    else:
        file_path = csv_file_path
    csv_lines = []
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
        reader = csv.reader(lines)
        for line in reader:
            csv_lines.append((line[0], line[1], int(line[2]), float(line[3]), int(line[4]), float(line[5])))
    except Exception as exc:
        Tkmb.showerror(title=str(type(exc)), message="Could not read CSV file {0!r}".format(file_path))
        csv_lines = []
    return file_path, csv_lines


def main(args):
    if platform.system() not in ("Windows", "Java"):
        os.environ.setdefault("DISPLAY", ":0")
    csv_file_path = args[0] if args else None
    file_path, csv_lines = browse_csv(csv_file_path)
    col_widths = (("Package", 40), ("Version", 10), ("Weight", 9),
                  ("DL Rate", 10), ("Age", 7), ("Score", 8))
    mlb = MultiListbox(None, col_widths)
    mlb.master.title("Viewing {0}".format(file_path))
    for csv_line in csv_lines:
        mlb.insert(Tkc.END, csv_line)
    mlb.pack(expand=Tkc.YES, fill=Tkc.BOTH)
    mlb.master.mainloop()


if __name__ == "__main__":
    main(sys.argv[1:])
