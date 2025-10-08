import logging
import os

def get_logger(name=__name__):
    """Return a configured logger for the package."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        fmt = "[%(asctime)s] %(levelname)s %(name)s - %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)
    # Enable DEBUG when DEBUG=1 in environment; otherwise keep INFO
    logger.setLevel(logging.DEBUG if os.environ.get("DEBUG", "0") == "1" else logging.INFO)
    return logger