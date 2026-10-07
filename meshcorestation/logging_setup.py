
import logging
from logging.handlers import TimedRotatingFileHandler
from meshcorestation.config import DATA_DIR

LEVEL = logging.WARNING

class Logger:
    def __init__(self):
        log_directory = DATA_DIR / "logs"
        log_directory.mkdir(parents=True, exist_ok=True)
        self.logger_obj = logging.getLogger("meshcorestation")
        self.logger_obj.setLevel(logging.INFO)
        self.logger_obj.propagate = False

        if not self.logger_obj.handlers:
            handler = TimedRotatingFileHandler(log_directory / "logs.log", when="midnight", interval=1, backupCount=30, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
            self.logger_obj.addHandler(handler)

        self.logger_obj.info('\n\n##################################\n# MeshcoreStation\n##################################\n')

    def set_log_level(self):
        self.logger_obj.setLevel(LEVEL)

    def info(self, message, *args):
        self.logger_obj.info(message, *args)

    def warning(self, message, *args):
        self.logger_obj.warning(message, *args)

    def error(self, message, *args):
        self.logger_obj.error(message, *args)