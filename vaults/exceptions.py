class VaultException(Exception):
    """
    Represents a general exception or error from the vaults library.
    """
    pass

class VaultNotImplementedError(VaultException):
    """
    Identical to a NotImplementedError.
    """
    pass

