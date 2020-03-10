"""
Experimental prototype of bitcoin vaults based on pre-signed transactions,
using trusted key deletion.
"""

import os
import sys
from copy import copy
import json
import struct

import bitcoin
from bitcoin import SelectParams
# configure bitcoinlib as soon as possible
SelectParams("regtest")

from vaults.helpers.formatting import b2x, x, b2lx, lx
from vaults.helpers.prototyping import make_private_keys
from vaults.exceptions import VaultException
from vaults.loggingconfig import logger
from vaults.graphics import generate_graphviz
from vaults.vaultfile import check_vaultfile_existence, make_vaultfile
from vaults.utils import sha256

from vaults.config import (
    TRANSACTION_STORE_FILENAME,
    TEXT_RENDERING_FILENAME,
)

from vaults.rpc import get_bitcoin_rpc_connection

from vaults.persist import (
    to_dict,
    from_dict,
    save,
    load,
)

from vaults.models.script_templates import (
    ScriptTemplate,
    UserScriptTemplate,
    ColdStorageScriptTemplate,
    BurnUnspendableScriptTemplate,
    BasicPresignedScriptTemplate,
    ShardScriptTemplate,
    CPFPHookScriptTemplate,
)

from vaults.models.plans import (
    PlannedUTXO,
    PlannedInput,
    PlannedTransaction,
    InitialTransaction,
)

from vaults.planner import setup_vault, safety_check
from vaults.bip119_ctv import make_planned_transaction_tree_using_bip119_OP_CHECKTEMPLATEVERIFY
from vaults.signing import sign_transaction_tree

from bitcoin.core import COIN, CTxOut, COutPoint, CTxIn, CMutableTransaction, CTxWitness, CTxInWitness, CScriptWitness
from bitcoin.core.script import CScript, OP_0, Hash160, OP_NOP3
from bitcoin.core.key import CPubKey
from bitcoin.wallet import CBitcoinAddress, P2WSHBitcoinAddress, P2WPKHBitcoinAddress
import bitcoin.rpc

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

def render_planned_tree_to_text_file(some_utxo, filename=TEXT_RENDERING_FILENAME):
    """
    Dump some text describing the planned transaction tree to a text file. This
    is primarily for human debugging.
    """
    logger.info("Rendering to text...")
    output = some_utxo.to_text()
    filename = TEXT_RENDERING_FILENAME
    fd = open(os.path.join(os.getcwd(), filename), "w")
    fd.write(output)
    fd.close()
    logger.info(f"Wrote to {filename}")
    return

def main():

    check_vaultfile_existence()

    #amount = random.randrange(0, 100 * COIN)
    #amount = 7084449357
    amount = 2 * COIN

    some_private_keys = make_private_keys()

    parameter_names = [
        "user_key",
        "ephemeral_key_1",
        "ephemeral_key_2",
        "cold_key1",
        "cold_key2",
        "hot_wallet_key",
    ]

    parameters = {
        "num_shards": 5,
        "enable_burn_transactions": True,
        "enable_graphviz": True,
        "enable_graphviz_popup": False,
        "amount": amount,
        "unspendable_key_1": CPubKey(x("0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")),
    }

    for some_name in parameter_names:
        private_key = some_private_keys.pop()
        public_key = private_key.pub
        parameters[some_name] = {"private_key": private_key, "public_key": public_key}

    parameters["user_key_hash160"] = b2x(Hash160(parameters["user_key"]["public_key"]))

    # consistency check against required parameters
    required_parameters = ScriptTemplate.get_required_parameters()

    missing_parameters = False
    for required_parameter in required_parameters:
        if required_parameter not in parameters.keys():
            logger.error(f"Missing parameter: {required_parameter}")
            missing_parameters = True
    if missing_parameters:
        logger.error("Missing parameters!")
        sys.exit(1)

    # connect to bitcoind (ideally, regtest)
    connection = get_bitcoin_rpc_connection()

    # setup the user private key (for P2WPKH)
    connection._call("importprivkey", str(parameters["user_key"]["private_key"]), "user")

    # Mine some coins into the "user_key" P2WPKH address
    #user_address = "bcrt1qrnwea7zc93l5wh77y832wzg3cllmcquqeal7f5"
    # parsed_address = P2WPKHBitcoinAddress(user_address)
    user_address = P2WPKHBitcoinAddress.from_scriptPubKey(CScript([OP_0, Hash160(parameters["user_key"]["public_key"])]))
    blocks = 110
    if connection._call("getblockchaininfo")["blocks"] < blocks:
        try:
            connection._call("sendtoaddress", user_address, 50)
        except Exception:
            pass
        connection._call("generatetoaddress", blocks, str(user_address))

    # Now find an unspent UTXO.
    unspent = connection._call("listunspent", 6, 9999, [str(user_address)], True, {"minimumAmount": amount / COIN})
    if len(unspent) == 0:
        raise Exception("can't find a good UTXO for amount {}".format(amount))

    # pick the first UTXO
    utxo_details = unspent[0]
    txid = utxo_details["txid"]

    # have to consume the whole UTXO
    amount = int(utxo_details["amount"] * COIN)

    initial_tx_txid = lx(utxo_details["txid"])
    initial_tx = InitialTransaction(txid=initial_tx_txid)

    segwit_utxo = PlannedUTXO(
        name="segwit input coin",
        transaction=initial_tx,
        script_template=UserScriptTemplate,
        amount=amount,
    )
    segwit_utxo._vout_override = utxo_details["vout"]
    initial_tx.output_utxos = [segwit_utxo] # for establishing vout

    # ===============
    # Here's where the magic happens.
    vault_initial_utxo = setup_vault(segwit_utxo, parameters)
    # ===============

    # Check that the tree is conforming to applicable rules.
    safety_check(segwit_utxo.transaction)

    # To test that the sharded UTXOs have the right amounts, do the following:
    # assert (second_utxo_amount * 99) + first_utxo_amount == amount

    # Display all UTXOs and transactions-- render the tree of possible
    # transactions.
    render_planned_tree_to_text_file(segwit_utxo, filename=TEXT_RENDERING_FILENAME)

    # stats
    logger.info("*** Stats and numbers")
    logger.info(f"{PlannedUTXO.__counter__} UTXOs, {PlannedTransaction.__counter__} transactions")

    sign_transaction_tree(segwit_utxo, parameters)

    save(segwit_utxo)

    # TODO: Delete the ephemeral keys.

    # (graph generation can wait until after key deletion)
    if parameters["enable_graphviz"] == True:
        generate_graphviz(segwit_utxo, parameters, output_filename="output.gv")

    # Create another planned transaction tree this time using
    # OP_CHECKTEMPLATEVERIFY from bip119. This can be performed after key
    # deletion because OP_CTV standard template hashes are not based on keys
    # and signatures.
    make_planned_transaction_tree_using_bip119_OP_CHECKTEMPLATEVERIFY(initial_tx, parameters=parameters)
    save(segwit_utxo, filename="transaction-store.ctv.json")

    # A vault has been established. Write the vaultfile.
    make_vaultfile()

if __name__ == "__main__":
    main()
