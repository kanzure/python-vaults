import os
import sys

from vaults.loggingconfig import logger

def check_vaultfile_existence(die=True):
    """
    Check whether a "vaultfile" file is present.
    """
    existence = os.path.exists(os.path.join(os.getcwd(), VAULTFILE_FILENAME))
    if existence and die:
        logger.error("Error: vaultfile already exists. Is this an active vault? Don't re-initialize.")
        sys.exit(1)
    else:
        return existence

def make_vaultfile():
    """
    Create a "vaultfile" file that has a file format version for later
    inspection and the possibility of migrations/upgrades in the future.
    """
    filepath = os.path.join(os.getcwd(), VAULTFILE_FILENAME)
    with open(filepath, "w") as fd:
        fd.write(json.dumps({"version": VAULT_FILE_FORMAT_VERSION}))
        fd.write("\n")
