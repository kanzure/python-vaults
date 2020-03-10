"""
get_info - A function for displaying information about the vault and checking
the current state of the vault on the blockchain.
"""

from vaults.helpers.formatting import b2x, x, b2lx, lx
from vaults.config import TRANSACTION_STORE_FILENAME
from vaults.persist import load
from vaults.state import get_current_confirmed_transaction

def render_planned_output(planned_output, depth=0):
    """
    Describe an output object, in text.
    """
    prefix = "\t" * depth

    output_text  = prefix + "Output:\n"
    output_text += prefix + "\tname: {}\n".format(planned_output.name)
    output_text += prefix + "\tinternal id: {}\n".format(planned_output.internal_id)

    return output_text

def render_planned_transaction(planned_transaction, depth=0):
    """
    Render a planned transaction into text for use in the get_info command.
    """
    prefix = "\t" * depth

    output_text  = prefix + "Transaction:\n"
    output_text += prefix + "\tname: {}\n".format(planned_transaction.name)
    output_text += prefix + "\tinternal id: {}\n".format(planned_transaction.internal_id)
    output_text += prefix + "\ttxid: {}\n".format(b2lx(planned_transaction.txid))
    output_text += prefix + "\tnum inputs: {}\n".format(len(planned_transaction.inputs))
    output_text += prefix + "\tnum outputs: {}\n".format(len(planned_transaction.output_utxos))

    output_text += "\n"
    output_text += prefix + "\tOutputs:\n"

    for output in planned_transaction.output_utxos:
        output_text += render_planned_output(output, depth=depth+2)

    return output_text

def get_info(transaction_store_filename=TRANSACTION_STORE_FILENAME, connection=None):
    """
    Render information about the state of the vault based on (1) pre-computed
    vault data and (2) the current state of the blockchain and most recently
    broadcasted transaction from the vault.
    """
    initial_tx = load(transaction_store_filename=transaction_store_filename)

    latest_info = get_current_confirmed_transaction(initial_tx)
    current_tx = latest_info["current"]

    output_text = "\n\nLatest transaction:\n"
    output_text += render_planned_transaction(current_tx, depth=1)

    output_text += "\n\nPossible transactions:\n\n"

    for some_tx in latest_info["next"]:
        output_text += render_planned_transaction(some_tx, depth=1)
        output_text += "\n"

    output_text += "\nTo broadcast the next transaction, run:\n\tvault broadcast <internal_id>\n"

    return output_text


