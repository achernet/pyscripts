from PyQt4.QtGui import QHBoxLayout, QWidget, QLayout, QSpacerItem, \
    QLayoutItem, QVBoxLayout, QPushButton, QApplication, QLabel, QSpinBox, \
    QCheckBox, QLineEdit
from PyQt4.QtCore import pyqtSlot as Slot, pyqtSignal as Signal, Qt
import pprint
import query_maven
import sys


class QHL(QHBoxLayout):

    def __init__(self, widget_layout_items, parent=None, **kwargs):
        super(QHL, self).__init__(**kwargs)
        if parent is not None:
            self.setParent(parent)
        for item in widget_layout_items:
            if isinstance(item, QWidget):
                self.addWidget(item)
            elif isinstance(item, QLayout):
                self.addLayout(item)
            elif isinstance(item, QSpacerItem):
                self.addSpacerItem(item)
            elif isinstance(item, QLayoutItem):
                self.addItem(item)


class QVL(QVBoxLayout):

    def __init__(self, widget_layout_items, parent=None, **kwargs):
        super(QVL, self).__init__(**kwargs)
        if parent is not None:
            self.setParent(parent)
        for item in widget_layout_items:
            if isinstance(item, QWidget):
                self.addWidget(item)
            elif isinstance(item, QLayout):
                self.addLayout(item)
            elif isinstance(item, QSpacerItem):
                self.addSpacerItem(item)
            elif isinstance(item, QLayoutItem):
                self.addItem(item)


class QButton(QPushButton):

    def __init__(self, icon=None, text='', parent=None, onClick=None,
                 **kwargs):
        super(QButton, self).__init__(**kwargs)
        if icon is not None:
            self.setIcon(icon)
        self.setText(text)
        if parent is not None:
            self.setParent(parent)
        self.callbacks = {'clicked': onClick}
        self.clicked.connect(self.handle_clicked)

    def handle_clicked(self, *args, **kw):
        print "handle_clicked(args: {0!r}, kw: {1!r})".format(args, kw)
        cb = self.callbacks.get('clicked')
        if callable(cb):
            cb(self, *args, **kw)


def find_child(name):
    app = QApplication.instance()
    if app is None:
        return None
    return next((w for w in app.allWidgets() if w.objectName() == name), None)


def run_query(*args, **kwargs):
    print "run_query(args: {0!r}, kwargs: {1!r})".format(args, kwargs)
    tlw = args[0].topLevelWidget()

    query_args = ['-n', str(find_child('max_results_qsb').value()),
                  '-s', str(find_child('start_index_qsb').value())]
    if find_child('exact_java_qcb').checkState() == Qt.Checked:
        query_args.append('-cp')
    if find_child('class_name_qcb').checkState() == Qt.Checked:
        query_args.append('-c')
    query = str(find_child('search_term_qle').text())
    query_args.append(query)
    print "Query args: {0!r}".format(query_args)
    pprint.pprint(query_maven.main(query_args))


def close_window(*args, **kwargs):
    print "close_window(args: {0!r}, kwargs: {1!r})".format(args, kwargs)
    tlw = args[0].topLevelWidget()
    tlw.close()


def main():
    w = QWidget(windowTitle='Run a Maven query', objectName='query_qw')
    main_layout = QVL([
        QHL([
            QLabel(text='Search term:', objectName='search_term_ql'),
            QLineEdit(text='', placeholderText='Enter Maven query...',
                      objectName='search_term_qle')
        ]),
        QHL([
            QLabel(text='Maximum number of results:',
                   objectName='max_results_ql'),
            QSpinBox(minimum=16,
                     singleStep=16,
                     value=512,
                     maximum=2048,
                     objectName='max_results_qsb')
        ]),
        QHL([
            QLabel(text='Starting index:',
                   objectName='start_index_ql'),
            QSpinBox(minimum=0,
                     value=0,
                     maximum=2048,
                     objectName='start_index_qsb')
        ]),
        QHL([
            QLabel(text='Search for exact Java classpath?',
                   objectName='exact_java_ql'),
            QCheckBox(objectName='exact_java_qcb')
        ]),
        QHL([
            QLabel(text='Search by Java class name?',
                   objectName='class_name_ql'),
            QCheckBox(objectName='class_name_qcb')
        ]),
        QHL([
            QButton(text='OK',
                    onClick=run_query,
                    objectName='run_query_qpb'),
            QButton(text='Cancel',
                    onClick=close_window,
                    objectName='close_window_qpb')
        ])
    ])
    w.setLayout(main_layout)
    w.setWindowFlags(Qt.WindowStaysOnTopHint)
    w.setWindowModality(Qt.ApplicationModal)
    w.show()
    return w


if __name__ == '__main__':  # pragma: no cover
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    w = main()
    print find_child('search_term_qle')
    app.exec_()
