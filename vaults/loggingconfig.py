"""
Setup python logging system- log to a file in the current working directory
(for each vault), and also log to console stdout and stderr.
"""

import os
import logging

logger = logging.getLogger("vault")
logger.setLevel(logging.DEBUG)

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

fh = logging.FileHandler(os.path.join(os.getcwd(), "log.txt"))
fh.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

ch.setFormatter(formatter)
fh.setFormatter(formatter)

logger.addHandler(ch)
logger.addHandler(fh)
