"""
Functions for checking the state of the vault on the blockchain by querying
bitcoind over RPC.
"""

from vaults.rpc import (
    get_bitcoin_rpc_connection,
    check_blockchain_has_transaction,
)

def get_next_possible_transactions_by_walking_tree(current_transaction, connection=None):
    """
    Walk the planned transaction tree and find which transaction is not yet in
    the blockchain. Recursively check child transactions until an unconfirmed
    tree node is found.
    """
    if connection == None:
        connection = get_bitcoin_rpc_connection()

    # This is an intentionally simple implementation: it will not work when
    # there are multiple possible non-interfering transactions hanging off of
    # this transaction. For example, two separate transactions might spend two
    # separate UTXOs produced by the current transaction. The current
    # implementation does not account for this. Instead, it assumes that there
    # is only one possible choice.

    possible_transactions = []
    for some_transaction in current_transaction.child_transactions:
        if not check_blockchain_has_transaction(some_transaction.txid):
            # If none of them are confirmed, then they are all possible
            # options.
            possible_transactions.append(some_transaction)
        else:
            # One of them was confirmed, so reset the possible transaction list
            # and find the next possible transactions.
            possible_transactions = get_next_possible_transactions_by_walking_tree(some_transaction, connection=connection)
            break

    return list(set(possible_transactions))

def get_current_confirmed_transaction(current_transaction, connection=None):
    """
    Find the most recently broadcasted-and-confirmed  pre-signed transaction
    from the vault, by walking the tree starting from the root (the first
    transaction) and checking each transaction for inclusion in the blockchain.

    The "current confirmed transaction" is the transaction where no child
    transactions are broadcasted or confirmed.
    """
    if connection == None:
        connection = get_bitcoin_rpc_connection()

    if not check_blockchain_has_transaction(current_transaction.txid):
        return current_transaction

    possible_transactions = get_next_possible_transactions_by_walking_tree(current_transaction, connection=connection)
    #logger.info("possible_transactions: {}".format([b2lx(possible_tx.txid) for possible_tx in possible_transactions]))
    assert all([len(possible_tx.parent_transactions) == 1 for possible_tx in possible_transactions])
    parents = [possible_tx.parent_transactions[0] for possible_tx in possible_transactions]
    assert len(set(parents)) == 1
    parent = parents[0]
    current_transaction = parent

    return {"current": current_transaction, "next": possible_transactions}


