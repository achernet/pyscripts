import copy
import csv
import Tkinter as tk
import Tkconstants as Tkc
import tkFileDialog as Tkfc


class MultiListbox(tk.Frame):

    def __init__(self, parent, lists):
        tk.Frame.__init__(self, parent)
        self.lists = []
        self.colmapping = {}
        self.orig_data = None
        for label, width in lists:
            frame = tk.Frame(self)
            frame.pack(side=Tkc.LEFT, expand=Tkc.YES, fill=Tkc.BOTH)
            sort_button = tk.Button(frame, text=label, borderwidth=1, relief=Tkc.RAISED)
            sort_button.pack(fill=Tkc.X)
            sort_button.bind("<Button-1>", self._sort)
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
        frame = tk.Frame(self)
        frame.pack(side=Tkc.LEFT, fill=Tkc.Y)
        frame_label = tk.Label(frame, borderwidth=1, relief=Tkc.RAISED)
        frame_label.pack(fill=Tkc.X)
        scroll_bar = tk.Scrollbar(frame, orient=Tkc.VERTICAL, command=self._scroll)
        scroll_bar.pack(expand=Tkc.YES, fill=Tkc.Y)
        self.lists[0]["yscrollcommand"] = scroll_bar.set

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

    def _select(self, y):
        row = self.lists[0].nearest(y)
        self.selection_clear(0, Tkc.END)
        self.selection_set(row)
        return "break"

    def _button2(self, x, y):
        for list_widget in self.lists:
            list_widget.scan_mark(x, y)
        return "break"

    def _b2motion(self, x, y):
        for list_widget in self.lists:
            list_widget.scan_dragto(x, y)
        return "break"

    def _scroll(self, *args):
        for list_widget in self.lists:
            list_widget.yview(*args)

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


def main():
    valid_filetypes = (("CSV files", "*.csv"), ("All files", "*.*"))
    file_path = Tkfc.askopenfilename(filetypes=valid_filetypes, initialdir=".")
    reader = csv.reader(open(file_path).readlines())
    csv_lines = []
    for line in reader:
        csv_lines.append((line[0], line[1], int(line[2]), float(line[3]), int(line[4]), float(line[5])))
    root = tk.Tk()
    top_label = tk.Label(root, text="MultiListbox")
    top_label.pack()
    col_widths = (("Package", 40), ("Version", 10), ("Weight", 9),
                  ("DL Rate", 10), ("Age", 7), ("Score", 8))
    mlb = MultiListbox(root, col_widths)
    for csv_line in csv_lines:
        mlb.insert(Tkc.END, csv_line)
    mlb.pack(expand=Tkc.YES, fill=Tkc.BOTH)
    root.mainloop()


if __name__ == "__main__":
    main()
