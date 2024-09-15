import logging
from types import FrameType


def create_logger_with_frame(frame: FrameType | None, fallback: str) -> logging.Logger:
    if frame is None:
        return create_logger(fallback)

    return create_logger(frame.f_code.co_name)


def create_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    import sys

    logger = logging.Logger(name)
    ch = logging.StreamHandler(sys.stdout)

    formatting = f"[{name}] %(asctime)s\t%(levelname)s\t%(module)s.%(funcName)s#%(lineno)d | %(message)s"
    formatter = logging.Formatter(formatting)
    ch.setFormatter(formatter)

    logger.addHandler(ch)
    logger.setLevel(level)

    return logger
