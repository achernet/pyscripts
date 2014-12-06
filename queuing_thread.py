from threading import Thread
import logging
import sys
import sh


class QueuingThread(Thread):
    """
    An abstract thread with a message queue that can run a shell command.
    """

    def __init__(self, queue):
        Thread.__init__(self)
        self.queue = queue
        self.running_command = None

    def run(self):
        command = self.build_command()
        logging.info("Command to execute: %s", command)
        try:

            self.running_command = command()
            for line in self.running_command:
                if not isinstance(line, basestring):
                    continue
                progress_rgx = self.compile_progress_regex()
                progress_match = progress_rgx.search(line)
                sys.stdout.write(line)
                if progress_match is not None:
                    self.enqueue_progress_match(progress_match)
        except sh.SignalException as cancel_exc:
            logging.info("Command was cancelled: %s", cancel_exc)
        except sh.ErrorReturnCode as err:
            logging.exception("Command failed in some way. Printing stack...\n%s%s", err.stdout, err.stderr)
        self.running_command = None

    def build_command(self):
        """
        Abstract function to build and return a :class:`sh.Command` object.

        :return: The command object to run
        :rtype: :class:`sh.Command`
        """
        raise NotImplementedError

    def compile_progress_regex(self):
        """
        Abstract function to compile and return a regex capable of reporting some type of progress.

        :return: The compiled progress regex
        :rtype: :class:`_sre.SRE_Pattern`
        """
        raise NotImplementedError

    def enqueue_progress_match(self, progress_match):
        """
        Abstract function to process and enqueue a regex match indicating a progress update.
        """
        raise NotImplementedError

    def cancel(self):
        """
        Cancel the command currently running, if there is one.
        """
        if self.running_command is not None:
            self.running_command.process.kill()
            self.running_command.process.terminate()
            self.running_command = None
