"""
A basic outline of what a logging server API might look like.

The logging server is used in two ways. First, it is used by the watchtower to
record information about watchtower activities. Second, it is used during vault
setup to remember pre-signed transactions.

The logging server deals with regular logging messages and statements, as well
as pre-signed bitcoin transaction information and vault configuration
information.

The logging server can optionally be used to store dangerous transaction data
such as burn transactions. These dangerous transactions could be stored
somewhere else instead, though.
"""

class LoggingServer(object):

    def __init__(self):
        """
        Create and setup a new instance of LoggingServer.
        """
        raise NotImplementedError

    def mainloop(self):
        """
        Main loop for listening to and handling logging requests.
        """
        raise NotImplementedError

    def log_message(self, logging_request):
        """
        Handle an incoming logging request.
        """
        raise NotImplementedError

    def dump_logs(self):
        """
        Retrieve all logged messages.
        """
        raise NotImplementedError

    def retrieve_transaction_by_internal_id(self, internal_id):
        """
        Retrieve a pre-signed vault transaction, by internal id.
        """
        raise NotImplementedError

    def retrieve_transaction_by_txid(self, txid):
        """
        Retrieve a pre-signed vault transaction, by txid.
        """
        raise NotImplementedError

    def store_transaction(self, transaction):
        """
        Store an individual transaction.
        """
        raise NotImplementedError

    def store_vault(self, vault_data):
        """
        Store a vault and all the associated pre-signed transactions.
        """
        raise NotImplementedError
