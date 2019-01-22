import logging


def create_logger(name: str, level: int = logging.DEBUG):
    import sys
    logger = logging.Logger(name)
    ch = logging.StreamHandler(sys.stdout)

    formatting = "[{}] %(levelname)s\t%(module)s.%(funcName)s\tLine=%(lineno)d | %(message)s".format(name)
    formatter = logging.Formatter(formatting)
    ch.setFormatter(formatter)

    logger.addHandler(ch)
    logger.setLevel(level)

    return logger
