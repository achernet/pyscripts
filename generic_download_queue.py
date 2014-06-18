from Queue import Queue
import time
import logging


class GenericDownloadQueue(object):

    def __init__(self, thread_creator=None):
        if not thread_creator:
            self.thread_creator = lambda queue: None
        else:
            self.thread_creator = thread_creator
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

    def call_periodically(self, wait_time_ms=50):
        self.checkqueue()
        if self.thread.is_alive():
            time.sleep(wait_time_ms)
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
