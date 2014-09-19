from Queue import Queue
import time
import logging


class GenericDownloadQueue(object):

    DEFAULT_MAXIMUM = 100

    def __init__(self, thread_creator=None, call_interval=50):
        if not thread_creator:
            self.thread_creator = lambda _: None
        else:
            self.thread_creator = thread_creator
        self.call_interval = call_interval
        self.queue = Queue()
        self.thread = None

    def __enter__(self):
        self.thread = self.thread_creator(self.queue)
        self.thread.start()
        self.call_periodically()
        return self

    def __exit__(self, *args):
        while self.thread.is_alive():
            self.update()
        return False

    def shutdown(self):
        if self.thread is not None:
            self.thread.cancel()

    def cancel_download(self):
        self.shutdown()
        while self.queue.qsize():
            self.queue.get()

    def call_periodically(self):
        self.checkqueue()
        if self.thread.is_alive():
            time.sleep(self.call_interval * 1.0e-3)
            self.call_periodically()

    def checkqueue(self):
        while self.queue.qsize():
            try:
                msg = self.queue.get()
                self.configure(**msg)
            except Exception as e:
                logging.exception("Error in checkqueue(): %s", e)

    def configure(self, **kwargs):
        pass

    def update(self):
        pass
