# mutual_fund_backtester/utils/logger.py

import logging
import os
from datetime import datetime


def setup_logger(name="backtester", log_dir="logs"):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_filename = os.path.join(
        log_dir, f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # File Handler
    fh = logging.FileHandler(log_filename)
    fh.setLevel(logging.DEBUG)

    # Console Handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # Adding handlers
    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
