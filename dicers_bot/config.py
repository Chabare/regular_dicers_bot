import json
from json import JSONDecodeError

from .logger import create_logger


class Config(dict):
    def __init__(self, filename: str, **kwargs):
        logger = create_logger("config")
        try:
            logger.debug(f"Open {filename}")
            with open(filename, "r") as file:
                logger.debug("Load file content as json")
                content = json.load(file)
                logger.debug("Update config")
                self.update(content)
        except OSError:
            logger.error(f"Couldn't open {filename} due to an OS error", exc_info=True)
        except JSONDecodeError:
            logger.error(f"Couldn't open {filename} due to json decoding error", exc_info=True)

        super().__init__(**kwargs)
