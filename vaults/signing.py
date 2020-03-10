"""
Make signatures for every transaction in the planned transaction tree.

entrypoint: sign_transaction_tree
"""

from copy import copy

from vaults.helpers.formatting import b2x, x, b2lx, lx
from vaults.exceptions import VaultException
from vaults.loggingconfig import logger
from vaults.utils import sha256

from vaults.models.script_templates import UserScriptTemplate

import bitcoin.core.script
from bitcoin.core import CTxOut, COutPoint, CTxIn, CMutableTransaction, CTxWitness, CTxInWitness, CScriptWitness
from bitcoin.core.script import CScript, OP_0, OP_NOP3
from bitcoin.wallet import P2WSHBitcoinAddress

# TODO: VerifyScript doesn't work with segwit yet...
#from bitcoin.core.scripteval import VerifyScript
# python-bitcointx just farms this out to libbitcoinconsensus, so that's an
# option...

def parameterize_planned_utxo(planned_utxo, parameters=None):
    """
    Parameterize a PlannedUTXO based on the runtime parameters. Populate and
    construct the output scripts based on the assigned script templates.
    """
    script_template = planned_utxo.script_template
    miniscript_policy_definitions = script_template.miniscript_policy_definitions
    script = copy(planned_utxo.script_template.script_template)

    for some_variable in miniscript_policy_definitions.keys():
        some_param = parameters[some_variable]
        if type(some_param) == dict:
            some_public_key = b2x(some_param["public_key"])
        elif script_template == UserScriptTemplate and type(some_param) == str and some_variable == "user_key_hash160":
            some_public_key = some_param
        else:
            # some_param is already the public key
            some_public_key = b2x(some_param)
        script = script.replace("<" + some_variable + ">", some_public_key)

    # Insert the appropriate relative timelocks, based on the timelock
    # multiplier.
    relative_timelocks = planned_utxo.script_template.relative_timelocks
    timelock_multiplier = planned_utxo.timelock_multiplier
    if relative_timelocks not in [{}, None]:
        replacements = relative_timelocks["replacements"]

        # Update these values to take into account the timelock multiplier.
        replacements = dict((key, value*timelock_multiplier) for (key, value) in replacements.items())

        # Insert the new value into the script. The value has to be
        # converted to the right value (vch), though.
        for (replacement_name, replacement_value) in replacements.items():
            replacement_value = bitcoin.core._bignum.bn2vch(replacement_value)
            replacement_value = b2x(replacement_value)

            script = script.replace("<" + replacement_name + ">", replacement_value)

            # For testing later:
            #   int.from_bytes(b"\x40\x38", byteorder="little") == 144*100
            #   b2x(bitcoin.core._bignum.bn2vch(144*100)) == "4038"
            #   bitcoin.core._bignum.vch2bn(b"\x90\x00") == 144

    # There might be other things in the script that need to be replaced.
    #script = script.replace("<", "")
    #script = script.replace(">", "")
    if "<" in script:
        raise VaultException("Script not finished cooking? {}".format(script))

    # remove newlines
    script = script.replace("\n", " ")
    # reduce any excess whitespace
    while (" " * 2) in script:
        script = script.replace("  ", " ")

    # remove whitespace at the front, like for the cold storage UTXO script
    if script[0] == " ":
        script = script[1:]

    # remove trailing whitespace
    if script[-1] == " ":
        script = script[0:-1]

    # hack for python-bitcoinlib
    # see https://github.com/petertodd/python-bitcoinlib/pull/226
    # TODO: this shouldn't be required anymore (v0.11.0 was released)
    script = script.replace("OP_CHECKSEQUENCEVERIFY", "OP_NOP3")

    # convert script into a parsed python object
    script = script.split(" ")
    script_items = []
    for script_item in script:
        if script_item in bitcoin.core.script.OPCODES_BY_NAME.keys():
            parsed_script_item = bitcoin.core.script.OPCODES_BY_NAME[script_item]
            script_items.append(parsed_script_item)
        else:
            script_items.append(x(script_item))

    p2wsh_redeem_script = CScript(script_items)

    scriptpubkey = CScript([OP_0, sha256(bytes(p2wsh_redeem_script))])
    p2wsh_address = P2WSHBitcoinAddress.from_scriptPubKey(scriptpubkey)

    planned_utxo.scriptpubkey = scriptpubkey
    planned_utxo.p2wsh_redeem_script = p2wsh_redeem_script
    planned_utxo.p2wsh_address = p2wsh_address

    amount = planned_utxo.amount
    planned_utxo.bitcoin_output = CTxOut(amount, scriptpubkey)
    planned_utxo.is_finalized = True

    logger.info("UTXO name: {}".format(planned_utxo.name))
    logger.info("final script: {}".format(script))
    #logger.info("p2wsh_redeem_script: ".format(b2x(planned_utxo.p2wsh_redeem_script)))
    #logger.info("p2wsh_redeem_script: ".format(CScript(planned_utxo.p2wsh_redeem_script)))

def parameterize_planned_utxos(planned_utxos, parameters=None):
    """
    Parameterize each PlannedUTXO's script template, based on the given
    config/parameters. Loop through all of the PlannedUTXOs in any order.
    """
    for planned_utxo in planned_utxos:
        parameterize_planned_utxo(planned_utxo, parameters=parameters)

def sign_planned_transaction(planned_transaction, parameters=None):
    """
    Sign a planned transaction by parameterizing each of the witnesses based on
    the script templates from their predecesor coins.
    """
    for planned_input in planned_transaction.inputs:
        logger.info("parent transaction name: {}".format(planned_input.utxo.transaction.name))

        # Sanity test: all parent transactions should already be finalized
        assert planned_input.utxo.transaction.is_finalized == True

        planned_utxo = planned_input.utxo
        witness_template_selection = planned_input.witness_template_selection

        # sanity check
        if witness_template_selection not in planned_utxo.script_template.witness_templates.keys():
            raise VaultException("UTXO {} is missing witness template \"{}\"".format(planned_utxo.internal_id, witness_template_selection))

        witness_template = planned_utxo.script_template.witness_templates[witness_template_selection]

        # Would use transaction.bitcoin_transaction.get_txid() but for the
        # very first utxo, the txid is going to be mocked for testing
        # purposes. So it's better to just use the txid property...
        txid = planned_utxo.transaction.txid
        vout = planned_utxo.vout

        relative_timelock = planned_input.relative_timelock

        if relative_timelock != None:
            # Note that it's not enough to just have the relative timelock
            # in the script; you also have to set it on the CTxIn object.
            planned_input.bitcoin_input = CTxIn(COutPoint(txid, vout), nSequence=relative_timelock)
        else:
            planned_input.bitcoin_input = CTxIn(COutPoint(txid, vout))

        # TODO: is_finalized is misnamed here.. since the signature isn't
        # there yet.
        planned_input.is_finalized = True

        # Can't sign the input yet because the other inputs aren't finalized.

    # sanity check
    finalized = planned_transaction.check_inputs_outputs_are_finalized()
    assert finalized == True

    bitcoin_inputs = [planned_input.bitcoin_input for planned_input in planned_transaction.inputs]
    bitcoin_outputs = [planned_output.bitcoin_output for planned_output in planned_transaction.output_utxos]
    witnesses = []

    planned_transaction.bitcoin_inputs = bitcoin_inputs
    planned_transaction.bitcoin_outputs = bitcoin_outputs

    # Must be a mutable transaction because the witnesses are added later.
    planned_transaction.bitcoin_transaction = CMutableTransaction(bitcoin_inputs, bitcoin_outputs, nLockTime=0, nVersion=2, witness=None)

    # python-bitcoin-utils had a bug where the witnesses weren't
    # initialized blank.
    #planned_transaction.bitcoin_transaction.witnesses = []

    if len(bitcoin_inputs) == 0 and planned_transaction.name != "initial transaction (from user)":
        raise VaultException("Can't have a transaction with zero inputs")

    # Now that the inputs are finalized, it should be possible to sign each
    # input on this transaction and add to the list of witnesses.
    witnesses = []
    for planned_input in planned_transaction.inputs:
        # sign!
        # Make a signature. Use some code defined in the PlannedInput model.
        witness = planned_input.parameterize_witness_template_by_signing(parameters)
        witnesses.append(witness)

    # Now take the list of CScript objects and do the needful.
    ctxinwitnesses = [CTxInWitness(CScriptWitness(list(witness))) for witness in witnesses]
    witness = CTxWitness(ctxinwitnesses)
    planned_transaction.bitcoin_transaction.wit = witness

    planned_transaction.is_finalized = True

    if planned_transaction.name == "initial transaction (from user)":
        # serialization function fails, so just skip
        return

    serialized_transaction = planned_transaction.serialize()
    logger.info("tx len: {}".format(len(serialized_transaction)))
    logger.info("txid: {}".format(b2lx(planned_transaction.bitcoin_transaction.GetTxid())))
    logger.info("Serialized transaction: {}".format(b2x(serialized_transaction)))

def sign_planned_transactions(planned_transactions, parameters=None):
    logger.info("======== Start")

    # Finalize each transaction by creating a set of bitcoin objects (including
    # a bitcoin transaction) representing the planned transaction.
    for (counter, planned_transaction) in enumerate(planned_transactions):
        logger.info("--------")
        logger.info("current transaction name: {}".format(planned_transaction.name))
        logger.info(f"counter: {counter}")

        sign_planned_transaction(planned_transaction, parameters=parameters)

def sign_transaction_tree(initial_utxo, parameters):
    """
    Walk the planned transaction tree and convert everything into bitcoin
    transactions. Convert the script templates and witness templates into real
    values.
    """

    # Crawl the planned transaction tree and get a list of all planned
    # transactions and all planned UTXOs.
    (planned_utxos, planned_transactions) = initial_utxo.crawl()

    # also get a list of all inputs
    planned_inputs = set()
    for planned_transaction in planned_transactions:
        planned_inputs.update(planned_transaction.inputs)

    # Sort the objects such that the lowest IDs get processed first.
    planned_utxos = sorted(planned_utxos, key=lambda utxo: utxo.id)
    planned_transactions = sorted(planned_transactions, key=lambda tx: tx.id)

    # Parameterize each PlannedUTXO's script template, based on the given
    # config/parameters. Loop through all of the PlannedUTXOs in any order.
    parameterize_planned_utxos(planned_utxos, parameters=parameters)

    # Sign each planned transaction by parameterizing the inputs, which can be
    # done by referencing the script template object for the output being
    # consumed by each input.
    sign_planned_transactions(planned_transactions, parameters=parameters)

    return


