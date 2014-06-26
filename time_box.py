#!/usr/bin/env python
from PyQt4 import QtGui
import re
from datetime import timedelta


class TimeBox(QtGui.QAbstractSpinBox):

    TIMES = (0, 15, 30, 45, 60, 90, 120, 180, 300, 600, 900, 1200, 1800, 2700, 3600, 5400, 7200, 10800,
             14400, 21600, 28800, 43200, 86400, 129600, 172800, 259200, 432000, 604800)

    DEFAULT_TIME = 300

    def __init__(self, parent=None):
        QtGui.QAbstractSpinBox.__init__(self, parent)
        self.setReadOnly(True)
        self.setWrapping(False)
        self._index = self.TIMES.index(self.DEFAULT_TIME)
        self.lineEdit().setText(self.text())

    def stepEnabled(self):
        if self.value == self.TIMES[-1]:
            return QtGui.QAbstractSpinBox.StepDownEnabled
        elif self.value == self.TIMES[0]:
            return QtGui.QAbstractSpinBox.StepUpEnabled
        return QtGui.QAbstractSpinBox.StepDownEnabled | QtGui.QAbstractSpinBox.StepUpEnabled

    def stepBy(self, steps):
        cur_index = self.TIMES.index(self.value)
        next_index = max(0, min(len(self.TIMES) - 1, cur_index + steps))
        self._index = next_index
        self.lineEdit().setText(self.text())

    @property
    def value(self):
        return self.TIMES[self._index]

    def text(self):
        timeDelta = timedelta(seconds=self.value)
        timeStr = str(timeDelta)
        hourRep = "\\1:0" if 0 <= (timeDelta.seconds / 3600) < 10 else "\\1:"
        timeStr = re.sub("([0-9-]+) days?, ", hourRep, timeStr)
        timeStr = re.sub("[.]([0-9]{0,3}).*", ".\\1", timeStr)
        return timeStr


def main():
    app = QtGui.QApplication([])
    dlg = QtGui.QDialog()
    layout = QtGui.QVBoxLayout()
    dlg.setLayout(layout)
    layout.addWidget(TimeBox())
    dlg.setModal(True)
    dlg.show()
    app.exec_()


if __name__ == "__main__":
    main()
