import Tkinter as tk

root = tk.Tk()
prompt = "Click a button or press any key"
label = tk.Label(root, text=prompt, width=len(prompt))
label.pack()


def key(event):
    if event.char == event.keysym:
        msg = "Normal Key {0!r}".format(event.char)
    elif len(event.char) == 1:
        msg = "Punctuation Key {0!r} {1!r}".format(event.keysym, event.char)
    else:
        msg = "Special Key {0!r}".format(event.keysym)
    label.config(text=msg)

label.bind_all("<Key>", key)


def do_mouse(event_name):

    def mouse_binding(event):
        msg = "Mouse event {0!r}".format(event_name)
        label.config(text=msg)

    label.bind_all("<{0}>".format(event_name), mouse_binding)


for i in xrange(1, 4):
    do_mouse("Button-{0}".format(i))
    do_mouse("ButtonRelease-{0}".format(i))
    do_mouse("Double-Button-{0}".format(i))

root.mainloop()
