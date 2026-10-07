"""Run Waitress in a thread, without spawning a second Python process."""
import threading
from waitress import create_server
from waitress import wasyncore
from meshcorestation.config import HOST, PORT
from meshcorestation.web.app import create_app


class WebServer:
    def __init__(self):
        # A private socket map makes shutdown independent of other networking code.
        self.sockets = {}
        self.server = create_server(create_app().server, host=HOST, port=PORT, threads=4, map=self.sockets, asyncore_loop_timeout=0.2)
        self.thread = threading.Thread(target=self.server.run, name='meshcorestation-http', daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.server.task_dispatcher.shutdown(timeout=5)
        wasyncore.close_all(self.sockets)
        self.thread.join(timeout=5)
