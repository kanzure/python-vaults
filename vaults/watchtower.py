"""
A basic proposal for how to interact with and use a watchtower.
"""

class WatchtowerServer(object):

    def __init__(self):
        """
        Initialize an instance of WatchtowerServer.
        """
        raise NotImplementedError

    def mainloop(self):
        """
        Main blockchain-watching and server-request-handling routines go here.
        """
        raise NotImplementedError

    def register_notification_rule(self, notification_rule):
        """
        Add a user-requested notification to the notifications table.
        """
        raise NotImplementedError

    def register_bitcoin_reaction_rule(self, delta, reaction_rule):
        """
        Register a "rule" that the watchtower should follow- automatically-
        when some situation arises. This is most likely some action like
        "broadcast a certain transaction".
        """
        raise NotImplementedError

    def handle_user_request(self, request):
        """
        Handle and process a user request (probably over HTTPs or RPC).
        """
        raise NotImplementedError

    def sync_against_blockchain(self):
        """
        Sync against the current state of the blockchain. Handle any necessary
        rollbacks too.
        """
        raise NotImplementedError

    def process_onchain_vault_change(self, delta_details):
        """
        Handle a new difference on the blockchain. Some transaction was
        confirmed or broadcasted. Process this update, and then decide what to
        do based on it.
        """
        raise NotImplementedError

    def notify(self, notification_details):
        """
        Notify a user about something happening on the blockchain, or some
        other watchtower-related update.
        """
        raise NotImplementedError

    def broadcast(self, bitcoin_transaction):
        """
        Broadcast a transaction to the bitcoin p2p network.
        """
        raise NotImplementedError

    def continuous_cpfp_bumpfee(self, bitcoin_transaction):
        """
        Continously monitor whether some transaction is getting into the
        blockchain, and bump the CPFP fee on the child transaction to pay for
        the parent transaction if necessary.
        """
        raise NotImplementedError

    def get_vault_state(self, vault):
        """
        Reconcile the given vault against the blockchain. Determine where in
        the vault transaction tree the latest current transaction is.
        """
        raise NotImplementedError

