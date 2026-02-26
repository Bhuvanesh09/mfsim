"""
Logging configuration for mfsim.

Sets up a dual-output logger that writes to both the console (INFO level)
and a timestamped log file (DEBUG level). Log files are stored in the
``logs/`` directory.
"""

import logging
import os
from datetime import datetime


def setup_logger(name="backtester", log_dir="logs"):
    """Create and configure a logger with file and console handlers.

    If a logger with the given name already has handlers attached,
    returns it as-is to avoid duplicate log output.

    Args:
        name: Logger name. Default ``'backtester'``.
        log_dir: Directory for log files. Created if it doesn't exist.
            Default ``'logs'``.

    Returns:
        A configured ``logging.Logger`` instance.

    Log output:
        - **Console**: INFO level and above (purchases, SIP, rebalancing).
        - **File**: DEBUG level and above (everything, including detailed
          metric calculations). File is named
          ``{name}_{YYYYMMDD_HHMMSS}.log``.
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = logging.getLogger(name)

    # If logger already has handlers, don't add more to avoid duplicate logs
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    log_filename = os.path.join(log_dir, f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

    # File Handler
    fh = logging.FileHandler(log_filename)
    fh.setLevel(logging.DEBUG)

    # Console Handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # Formatter
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)

    # Adding handlers
    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger
