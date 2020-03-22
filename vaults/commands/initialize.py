"""
Experimental prototype of bitcoin vaults based on pre-signed transactions,
using trusted key deletion.

The primary entrypoint is the "initialize" function in this file.
"""

import os
import sys
from copy import copy
import json
import struct

# use python-bitcoinlib for bitcoin primitives
import bitcoin

# configure bitcoinlib as soon as possible
from bitcoin import SelectParams
SelectParams("regtest")

from vaults.config import TEXT_RENDERING_FILENAME
from vaults.loggingconfig import logger
from vaults.exceptions import VaultException
from vaults.helpers.formatting import b2x, x, b2lx, lx
from vaults.utils import sha256
from vaults.vaultfile import check_vaultfile_existence, make_vaultfile
from vaults.graphics import generate_graphviz

from vaults.rpc import get_bitcoin_rpc_connection
from vaults.persist import save

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

from vaults.planner import setup_vault, safety_check, render_planned_tree_to_text_file
from vaults.bip119_ctv import make_planned_transaction_tree_using_bip119_OP_CHECKTEMPLATEVERIFY
from vaults.signing import sign_transaction_tree
from vaults.state import get_current_confirmed_transaction

from bitcoin.core import COIN
from bitcoin.core.script import CScript, OP_0, Hash160, OP_NOP3
from bitcoin.core.key import CPubKey
from bitcoin.wallet import P2WPKHBitcoinAddress, CBitcoinSecret

def check_private_key_is_conformant(private_key):
    """
    Raise an exception if the format of the private key is in the wrong format.
    """
    CBitcoinSecret(private_key)

def initialize(private_key=None):
    """
    Setup and initialize a new vault in the current working directory. This is
    the primary entrypoint for the prototype.
    """

    check_vaultfile_existence()
    check_private_key_is_conformant(private_key)

    #amount = random.randrange(0, 100 * COIN)
    #amount = 7084449357
    amount = 2 * COIN

    # TODO: A more sophisticated private key system is required, for any real
    # production use.
    some_private_keys = [CBitcoinSecret(private_key)] * 6

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
    # transactions. Mostly helpful for debugging purposes.
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
