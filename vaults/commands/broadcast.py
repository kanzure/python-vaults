"""
broadcast_next_transaction - Check the database to see what are the
valid/available next transactions, and then broadcast the user-selected
transaction to the bitcoin p2p network.
"""

import sys

from vaults.helpers.formatting import b2x, x, b2lx, lx

from vaults.loggingconfig import logger
from vaults.config import TRANSACTION_STORE_FILENAME

from vaults.persist import load
from vaults.rpc import get_bitcoin_rpc_connection
from vaults.state import get_current_confirmed_transaction

def broadcast_next_transaction(internal_id):
    """
    Broadcast a transaction, but only if it is one of the valid next
    transactions.
    """
    transaction_store_filename = TRANSACTION_STORE_FILENAME
    initial_tx = load(transaction_store_filename=transaction_store_filename)
    recentdata = get_current_confirmed_transaction(initial_tx)

    internal_id = str(internal_id)
    internal_ids = [str(blah.internal_id) for blah in recentdata["next"]]

    if internal_id not in internal_ids:
        logger.error(f"Error: internal_id {internal_id} is an invalid next step")
        sys.exit(1)

    internal_map = dict([(str(blah.internal_id), blah) for blah in recentdata["next"]])
    requested_tx = internal_map[str(internal_id)]
    bitcoin_transaction = requested_tx.bitcoin_transaction

    connection = get_bitcoin_rpc_connection()
    result = connection.sendrawtransaction(bitcoin_transaction)

    if type(result) == bytes:
        result = b2lx(result)
    logger.info("Broadcasted, txid: {}".format(result))

    return result


