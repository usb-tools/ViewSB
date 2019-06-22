"""
ViewSB frontend class defintions -- defines the abstract base for things that display USB data
"""

import io
import os
import sys
import queue
import multiprocessing



class ViewSBFrontendProcess:
    """ Class that controls and communicates with a ViewSB UI running in another process. """

    def __init__(self, frontend_class, *frontend_arguments):

        # Create our output queue and our termination-signaling event.
        self.input_queue       = multiprocessing.Queue()
        self.termination_event = multiprocessing.Event()

        # Capture stdin; we'll hand it over to the frontend.
        self.stdin             = self._capture_stdin()

        # And put together our frontend arguments.
        self.frontend_arguments  = \
             (frontend_class, frontend_arguments, self.input_queue, self.termination_event, self.stdin)


    def start(self):
        """ Start the foreground process, and begin to display. """

        # Ensure our termination event isn't set.
        self.termination_event.clear()

        # Generate a name for our capture process.
        name = "{} UI process".format(self.frontend_arguments[0].__name__)

        # Create and start our background process.
        self.foreground_process = \
            multiprocessing.Process(target=self._subordinate_process_entry, args=self.frontend_arguments, name=name)
        self.foreground_process.start()

        # Now that we've started the frontend process, we shouldn't use stdin anymore.
        # We'll close our local copy.
        self.stdin.close()


    def issue_packet(self, packet):
        """ Consumes packets from the analyzer, and sends them over to the frontend process. """
        self.input_queue.put(packet)


    def stop(self):
        """ 
        Request that the frontend process stop. 
        Usually only used at the frontend's request.  
        """
        self.termination_event.set()
        self.foreground_process.join()


    def _capture_stdin(self):
        """ 
        Currently, the multiprocessing module kills stdin on any newly-spawned processes; and doesn't
        allow us to configure which of the multiple processe retains a living stdin.

        To work around this, we'll break stdin away from python's control, and manually pass it to
        the subordinate processes.
        rdinate
        """

        # Create a duplicate handle onto the standard input.
        # This effectively increases the file's refcount, preventing python from disposing of it.
        fd_stdin = sys.stdin.fileno()
        return os.fdopen(os.dup(fd_stdin))


    @staticmethod
    def _subordinate_process_entry(frontend_class, arguments, input_queue, termination_event, stdin):
        """
        Helper function for running a frontend with a UI 'thread'. This method should usually be called in a subordinate
        process managed by multiprocessing. You probably want the public API of ViewSBFrontendProcess.
        """

        # Create a new instance of the frontend class.
        frontend = frontend_class(*arguments)

        # Pass the frontend our IPC mechanisms, and then standard input.
        frontend.set_up_ipc(input_queue, termination_event, stdin)

        # Finally, run our frontend class until it terminates.
        frontend.run()



class ViewSBFrontend:
    """ Generic parent class for sources that display USB data. """

    PACKET_READ_TIMEOUT = 0.01

    def __init__(self):
        """
        Function that initializes the relevant frontend. In most cases, this objects won't be instantiated
        directly -- but instead instantiated by the `run_asynchronously` / 'run_frontend_asynchronously` helpers.
        """
        pass


    def set_up_ipc(self, input_queue, termination_event, stdin):
        """
        Function that accepts the synchronization objects we'll use for input. Must be called prior to
        calling run().

        Args:
            input_queue -- The Queue object that will feed up analyzed packets for display.
            termination_event -- A synchronization event that is set when a capture is terminated.
        """

        # Store our IPC primitives, ready for future use.
        self.input_queue       = input_queue
        self.termination_event = termination_event

        # Retrieve our use of the standard input from the parent thread.
        self.stdin = sys.stdin = stdin



    def read_packet(self, blocking=True, timeout=None):
        """ Reads a packet from the analyzer process.

        Args:
            blocking -- If set, the read will block until a packet is available.
            timeout -- The longest time to wait on a blocking read, in floating-point seconds.
        """
        return self.input_queue.get(blocking, timeout=timeout)


    def handle_events(self):
        pass


    def handle_incoming_packet(self, packet):
        pass


    def fetch_packet_from_analyzer(self):
        """
        Fetch any packets the analyzer has to offer. Blocks for a short period if no packets are available,
        to minimize CPU busy-waiting.
        """

        try:
            # Read a packet from the backend, and add it to our analysis queue.
            return self.read_packet(timeout=self.PACKET_READ_TIMEOUT, blocking=False)

        except queue.Empty:
            # If no packets were available, return without error; we'll wait again next time.
            return None


    def handle_communications(self):
        """ 
        Function that handles communications with our analyzer process.
        Should be called repeatedly during periods when the UI thread is not busy;
        if you override run(). it's your responsibility to call this function.
        """

        packet = True

        while packet:

            # Try to fetch a packet from the analyzer.
            packet = self.fetch_packet_from_analyzer()
            
            # If we got one, handle using it in our UI.
            if not packet:
                break

            self.handle_incoming_packet(packet)


    def run(self):
        """ Runs the given frontend until either side requests termination. """

        # Capture infinitely until our termination signal is set.
        while not self.termination_event.is_set():
            self.handle_communications()

        # Allow the subclass to handle any cleanup it needs to do.
        self.handle_termination()


    def handle_termination(self):
        """ Called once the capture is terminated; gives the frontend the ability to clean up. """
        pass

