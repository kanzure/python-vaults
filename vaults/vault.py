from .exceptions import (
    VaultException,
    VaultNotImplementedError,
)

class Vault(object):
    """
    The **Vault** object represents all of the information necessary to create,
    use and monitor a vault.
    """

    def __init__(self, incoming_utxos=None, persistent_storage=None):
        """
        Initialize a new Vault. Either provide a list of UTXOs to put into the
        vault (using the `incoming_utxos` parameter) or load an existing vault
        from persistent storage by specifying the path.
        """

        if incoming_utxos in [None, [], set()] and persistent_storage in [None, ""]:
            raise VaultException("Incorrect parameters, can't initialize Vault object")

        raise VaultNotImplementedError("No implementation")

