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
from vaults.exceptions import VaultException
from vaults.loggingconfig import logger
from vaults.graphics import generate_graphviz
from vaults.vaultfile import check_vaultfile_existence, make_vaultfile
from vaults.utils import sha256

from vaults.config import (
    TRANSACTION_STORE_FILENAME,
    TEXT_RENDERING_FILENAME,
)

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

from vaults.bip119_ctv import make_planned_transaction_tree_using_bip119_OP_CHECKTEMPLATEVERIFY

from bitcoin.core import COIN, CTxOut, COutPoint, CTxIn, CMutableTransaction, CTxWitness, CTxInWitness, CScriptWitness
from bitcoin.core.script import CScript, OP_0, Hash160, OP_NOP3
from bitcoin.core.key import CPubKey
from bitcoin.wallet import CBitcoinAddress, CBitcoinSecret, P2WSHBitcoinAddress, P2WPKHBitcoinAddress
import bitcoin.rpc

# TODO: VerifyScript doesn't work with segwit yet...
#from bitcoin.core.scripteval import VerifyScript
# python-bitcointx just farms this out to libbitcoinconsensus, so that's an
# option...

def make_burn_transaction(incoming_utxo, parameters=None):
    """
    Extend the planned transaction tree by making a "burn" transaction that
    spends the coin and making it unspendable in the future forevermore.
    """

    if not parameters["enable_burn_transactions"] == True:
        return None

    burn_transaction = PlannedTransaction(name="Burn some UTXO")
    incoming_input = PlannedInput(
        utxo=incoming_utxo,
        witness_template_selection="presigned",
        transaction=burn_transaction,
    )
    burn_transaction.inputs.append(incoming_input)

    # TODO: Should the amount be burned to miner fee (which seems sort of
    # dangerous- incents attacks by miner-thiefs) or just perpetually unspendable.
    burn_utxo_amount = incoming_utxo.amount # unspendable
    #burn_utxo_amount = 0 # burn to miner fee

    burn_utxo = PlannedUTXO(
        name="burned UTXO",
        transaction=burn_transaction,
        script_template=BurnUnspendableScriptTemplate,
        amount=burn_utxo_amount,
    )
    burn_transaction.output_utxos.append(burn_utxo)
    incoming_utxo.child_transactions.append(burn_transaction)
    return burn_transaction

def make_push_to_cold_storage_transaction(incoming_utxo, parameters=None):
    """
    Extend the planned transaction tree with a transaction that pushes a coin
    into the cold storage layer (defined by ColdStorageScriptTemplate).

    Also make a planned transaction that can burn the cold storage UTXO as
    another possible exit from the vault.
    """

    # name was (phase 2): "push-to-cold-storage-from-sharded" But this is
    # inaccurate because only some of them are from a sharded UTXO. Others will
    # be the re-vault transaction.
    # name was: "Push (sharded?) UTXO to cold storage wallet"
    push_transaction = PlannedTransaction(name="push-to-cold-storage")
    planned_input = PlannedInput(
        utxo=incoming_utxo,
        witness_template_selection="presigned",
        transaction=push_transaction,
    )
    push_transaction.inputs.append(planned_input)

    cold_storage_utxo_amount = incoming_utxo.amount
    cold_storage_utxo = PlannedUTXO(
        name="cold storage UTXO",
        transaction=push_transaction,
        script_template=ColdStorageScriptTemplate,
        amount=cold_storage_utxo_amount,
    )
    push_transaction.output_utxos.append(cold_storage_utxo)

    # The purpose of the relative timelock before the cold storage keys are
    # able to spend is so that not all cold storage UTXOs can be spent at once.
    # The user is thus given an option of burning the other UTXOs if they think
    # that an adversary is about to steal the remaining UTXOs after observing
    # the theft of a single UTXO.

    # Make a possible transaction: burn/donate the cold storage UTXO.
    burn_transaction = make_burn_transaction(cold_storage_utxo, parameters=parameters)

    incoming_utxo.child_transactions.append(push_transaction)
    return push_transaction

def make_sweep_to_cold_storage_transaction(incoming_utxos, parameters=None):
    """
    Create a transaction that sweeps some input coins into the cold storage layer.
    """

    # name was: "Sweep UTXOs to cold storage wallet"
    # phase 2 name was: Sharded UTXO sweep transaction
    push_transaction = PlannedTransaction(name="Sharded UTXO sweep transaction")

    for incoming_utxo in incoming_utxos:
        # Inputs
        planned_input = PlannedInput(
            utxo=incoming_utxo,
            witness_template_selection="presigned",
            transaction=push_transaction,
        )
        push_transaction.inputs.append(planned_input)

        # Outputs
        amount = incoming_utxo.amount
        cold_storage_utxo = PlannedUTXO(
            name="cold storage UTXO",
            transaction=push_transaction,
            script_template=ColdStorageScriptTemplate,
            amount=amount,
        )
        push_transaction.output_utxos.append(cold_storage_utxo)
        burn_transaction = make_burn_transaction(cold_storage_utxo, parameters=parameters)

    return push_transaction

def make_telescoping_subsets(some_set):
    """
    Creates a list of lists where each list at the second level is a subset of
    the function's input each time minus one additional element.

    The original purpose of this function was to produce a list of different
    UTXO sets. These could then be used to construct alternative-possible sweep
    transactions, such as sweep transactions for each of the scenarios where
    the first UTXO is spent or not spent, the first and second UTXO are spent
    or not spent, etc. Ultimately the sweep transactions are not enabled by
    default in this prototype, because they combinatorially explode the planned
    transaction tree size.
    """
    item_sets = []
    for x in range(0, len(some_set)-1):
        item_sets.append(some_set[x:len(some_set)])
    return item_sets

def make_sharding_transaction(per_shard_amount=1 * COIN, num_shards=100, first_shard_extra_amount=0, incoming_utxo=None, original_num_shards=None, make_sweeps=False, parameters=None):
    """
    Make a new sharding transaction. A sharding transaction is one that takes
    some coin and splits the coin into many UTXOs each with a fraction of the
    original amount. Each coin will have a script that includes a monotonically
    increasing relative timelock so that each UTXO becomes spendable
    one-at-a-time and a watchtower can later take some action if more than one
    of these UTXOs is spendable at any given time.
    """

    if num_shards < original_num_shards:
        partial ="(partial) "
    elif num_shards == original_num_shards:
        partial = ""

    sharding_transaction = PlannedTransaction(name=f"Vault {partial}stipend start transaction.")
    incoming_utxo.child_transactions.append(sharding_transaction)

    planned_input = PlannedInput(
        utxo=incoming_utxo,
        witness_template_selection="presigned",
        transaction=sharding_transaction,
    )
    sharding_transaction.inputs.append(planned_input)

    shard_utxos = []
    for shard_id in range(0, num_shards):
        amount = per_shard_amount
        if shard_id == 0 and first_shard_extra_amount != None:
            amount += first_shard_extra_amount

        sharded_utxo_name = "shard fragment UTXO {shard_id}/{num_shards}".format(
            shard_id = shard_id + 1,
            num_shards=num_shards,
        )

        # Note: can't re-vault from this point. Must pass through the cold
        # wallet or the hot wallet before it can get back into a vault.
        sharded_utxo = PlannedUTXO(
            name=sharded_utxo_name,
            transaction=sharding_transaction,
            script_template=ShardScriptTemplate,
            amount=amount,
            timelock_multiplier=shard_id,
        )
        shard_utxos.append(sharded_utxo)
        sharding_transaction.output_utxos.append(sharded_utxo)

        make_push_to_cold_storage_transaction(incoming_utxo=sharded_utxo, parameters=parameters)

    # Make a variety of push-to-cold-storage (sweep) transactions that
    # each take 2 or more UTXOs. Note that the UTXOs get spent in order, so
    # this fortunately limits the total number of transactions to generate.
    #
    # Without these sweep transactions, the user would have to individually
    # broadcast up to 100 transactions that each individually move each UTXO
    # into cold storage. By aggregating it into these sweep transactions, they
    # don't need to do that anymore.
    #
    # Note: this makes the transaction tree planner pretty slow. It's
    # unreasonably slow. By comparison, having 100 separate transactions that
    # need to be CPFPed would be easier to deal with.
    if make_sweeps == True:
        subsets = make_telescoping_subsets(shard_utxos)
        # Iteration over all the possible subsets substantially and negatively
        # impacts the runtime of the program.
        #sweep_transactions = []
        for some_subset in subsets:
            sweep_transaction = make_sweep_to_cold_storage_transaction(some_subset, parameters=parameters)
            #sweep_transactions.append(sweep_transaction)

            for utxo in some_subset:
                utxo.child_transactions.append(sweep_transaction)

    return sharding_transaction

# The vault UTXO can have 1/100th spent at a time, the rest goes back into a
# vault. So you can either do the stipend-spend, or the one-at-a-time spend.
# So if the user knows they only want a small amount, they use the one-time
# spend. If they know they want more, then they can use the stipend (or migrate
# out of the vault by first broadcasting the stipend setup transaction).
def make_one_shard_possible_spend(incoming_utxo, per_shard_amount, num_shards, original_num_shards=None, first_shard_extra_amount=None, parameters=None):
    """
    Make a possible transaction for the vault UTXO that has two possibilities
    hanging off of it: one to spend a single sharded UTXO (either to the cold
    storage layer, or to the hot wallet), and then a second vault UTXO that has
    the remaining funds minus that one sharded UTXO, and then the typical vault
    possibilities hanging off of that.
    """
    # Spend initial vault UTXO into two UTXOs- one for the hot wallet/push to
    # cold storage, one for re-vaulting the remaining amount- and then all the
    # appropriate child transactions too. The re-vaulted path should not split
    # up the UTXOs into 100 pieces, but rather the remaining number of pieces
    # based on the amount already spent into the hot wallet.
    #
    # This path is another route of possible transactions, as a
    # possible-sibling to the vault stipend initiation transaction.

    # phase 2 name: There was no equivalent name for this transaction discussed
    # in phase 2. This transaction was added in phase 3.
    vault_spend_one_shard_transaction = PlannedTransaction(name="Vault transaction: spend one shard, re-vault the remaining shards")
    incoming_utxo.child_transactions.append(vault_spend_one_shard_transaction)

    planned_input = PlannedInput(
        utxo=incoming_utxo,
        witness_template_selection="presigned",
        transaction=vault_spend_one_shard_transaction,
    )
    vault_spend_one_shard_transaction.inputs.append(planned_input)

    # Next, add two UTXOs to vault_spend_one_shard transaction.

    amount = per_shard_amount
    if first_shard_extra_amount != None:
        amount += first_shard_extra_amount

    # phase 2 name: k% sharded UTXO
    exiting_utxo = PlannedUTXO(
        name="shard fragment UTXO",
        transaction=vault_spend_one_shard_transaction,
        script_template=ShardScriptTemplate,
        amount=amount,
    )
    vault_spend_one_shard_transaction.output_utxos.append(exiting_utxo)

    # For the exit UTXO, it should also be posisble to send that UTXO to cold
    # storage instead of letting the multisig hot wallet control it.
    make_push_to_cold_storage_transaction(exiting_utxo, parameters=parameters)
    # The hot wallet spend transaction is not represented here because t's not
    # a pre-signed transaction. It can be created at a later time, by the hot
    # wallet keys.

    if num_shards == 1:
        return
    else:
        # TODO: should this be num_shards or (num_shards - 1) ?
        remaining_amount = (num_shards - 1) * per_shard_amount

        # Second UTXO attached to vault_spend_one_shard_transaction.
        # phase 2 name: funding/commitment UTXO, kind of... But this wasn't
        # really in the original phase 2 proposal.
        revault_utxo = PlannedUTXO(
            name="vault UTXO",
            transaction=vault_spend_one_shard_transaction,
            script_template=BasicPresignedScriptTemplate,
            amount=remaining_amount,
        )
        vault_spend_one_shard_transaction.output_utxos.append(revault_utxo)

        # The vault UTXO can also be spent directly to cold storage.
        make_push_to_cold_storage_transaction(revault_utxo, parameters=parameters)

        # The re-vault UTXO can be sharded into "100" pieces (but not really 100..
        # it should be 100 minus the depth).
        make_sharding_transaction(
            per_shard_amount=per_shard_amount,
            num_shards=num_shards - 1,
            incoming_utxo=revault_utxo,
            original_num_shards=original_num_shards,
            first_shard_extra_amount=None,
            parameters=parameters,
        )

        # The re-vault UTXO can also be spent using the one-shard possible spend
        # method.
        make_one_shard_possible_spend(
            incoming_utxo=revault_utxo,
            per_shard_amount=per_shard_amount,
            num_shards=num_shards - 1,
            original_num_shards=original_num_shards,
            first_shard_extra_amount=None,
            parameters=parameters,
        )

def setup_vault(segwit_utxo, parameters):
    """
    Generate a pre-signed transaction tree using the segwit_utxo as the coins
    to be inserted into the vault. The pre-signed transaction tree is
    constructed in this function, but not signed. Signing occurs in another
    independent function.

    The movement of the given coins (from segwit_utxo) into the vault should
    only be signed once the user has looked at and signed-off on the entire
    planned transaction tree. This sign-off should be predicated on secure key
    deletion of the keys used to create the pre-signed transactions in the
    planned transaction tree.
    """

    # name was: Vault locking transaction
    # phase 2 name: Funding commitment transaction
    vault_locking_transaction = PlannedTransaction(name="Funding commitment transaction")
    segwit_utxo.child_transactions.append(vault_locking_transaction)

    planned_input = PlannedInput(
        utxo=segwit_utxo,
        witness_template_selection="user",
        transaction=vault_locking_transaction,
    )
    vault_locking_transaction.inputs.append(planned_input)

    vault_initial_utxo_amount = segwit_utxo.amount
    vault_initial_utxo = PlannedUTXO(
        name="vault initial UTXO",
        transaction=vault_locking_transaction,
        script_template=BasicPresignedScriptTemplate,
        amount=vault_initial_utxo_amount,
    )
    vault_locking_transaction.output_utxos.append(vault_initial_utxo)

    # Optional transaction: Push the whole amount to cold storage.
    make_push_to_cold_storage_transaction(incoming_utxo=vault_initial_utxo, parameters=parameters)

    # The number of shards that we made at this level of the transaction tree.
    # Inside the make_one_shard_possible_spend function, this amount will be
    # decremented before it is used to create the next sharding/stipend-setup
    # transaction.
    num_shards = parameters["num_shards"]

    amount_per_shard = int(vault_initial_utxo.amount / num_shards)
    first_shard_extra_amount = vault_initial_utxo.amount - (int(vault_initial_utxo.amount/num_shards)*num_shards)
    assert (amount_per_shard * num_shards) + first_shard_extra_amount == vault_initial_utxo.amount

    # Optional transaction: split the UTXO up into 100 shards, when it's time
    # to start spending the coins.
    # Make a transaction that sets up 100 UTXOs (with appropriate relative
    # timelocks).
    make_sharding_transaction(
        per_shard_amount=amount_per_shard,
        num_shards=num_shards,
        first_shard_extra_amount=first_shard_extra_amount,
        incoming_utxo=vault_initial_utxo,
        original_num_shards=num_shards,
        parameters=parameters,
    )

    # Another optional transaction
    # Make a transaction that lets the user spend one shard, but re-vaults
    # everything else.
    make_one_shard_possible_spend(
        incoming_utxo=vault_initial_utxo,
        per_shard_amount=amount_per_shard,
        num_shards=num_shards,
        first_shard_extra_amount=first_shard_extra_amount,
        original_num_shards=num_shards,
        parameters=parameters,
    )

    return vault_initial_utxo

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

def make_private_keys():
    """
    Convert a list of passphrases into a list of private keys. For the purposes
    of prototyping, the passphrases are static values. System random should be
    used for the real deal, though.
    """
    # Note that this function uses python-bitcoinlib CBitcoinSecret objects.

    private_keys = []

    passphrases = [
        "password",
        "passphrase",
        "hello world",
        "hello cruel world",
        "correct horse battery staple",
        "correct horse battery staple 1",
        "correct horse battery staple 2",
        "correct horse battery staple 3",
        "correct horse battery staple 4",
    ]
    passphrases = [bytes(each, "utf-8") for each in passphrases]

    for passphrase in passphrases:
        hashed = sha256(passphrase)

        # compressed=True is default
        private_key = CBitcoinSecret.from_secret_bytes(hashed, compressed=True)

        private_keys.append(private_key)

    return private_keys

def get_bitcoin_rpc_connection():
    """
    Establish an RPC connection.
    """
    # by default uses ~/.bitcoin/bitcoin.conf so be careful.
    btcproxy = bitcoin.rpc.Proxy()

    # sanity check
    assert btcproxy._call("getblockchaininfo")["chain"] == "regtest"

    return btcproxy

def setup_regtest_blockchain(connection=None):
    """
    Ensure the regtest blockchain has at least some minimal amount of setup.
    """

    if not connection:
        connection = get_bitcoin_rpc_connection()

    blockheight = connection._call("getblockchaininfo")["blocks"]
    if blockheight < 110:
        connection.generate(110)

def check_blockchain_has_transaction(txid, connection=None):
    """
    Check whether a given transaction id (txid) is present in the bitcoin
    blockchain with at least one confirmation.
    """
    if connection == None:
        connection = get_bitcoin_rpc_connection()

    if type(txid) == bytes:
        txid = b2lx(txid)

    try:
        rawtransaction = connection._call("getrawtransaction", txid, True)

        if "confirmations" in rawtransaction.keys() and rawtransaction["confirmations"] > 0:
            return True
        else:
            return False
    except bitcoin.rpc.InvalidAddressOrKeyError:
        return False

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

def safety_check(initial_tx=None):
    """
    Check that the planned transaction tree conforms to some specific rules.
    """

    if initial_tx == None:
        initial_tx = load()

    initial_utxo = initial_tx.output_utxos[0]

    (planned_utxos, planned_transactions) = initial_utxo.crawl()

    # Every transaction should have at least one output, including the burner
    # transactions (unless they are burning to miner fee...).
    counter = 0
    for some_transaction in planned_transactions:
        counter += 1
        if len(some_transaction.output_utxos) == 0:
            raise VaultException("Transaction {} has no outputs".format(str(some_transaction.internal_id)))

        # The sum of the input amounts should equal the sum of the output
        # amounts.
        input_amounts = sum([some_input.utxo.amount for some_input in some_transaction.inputs])
        output_amounts = sum([some_output.amount for some_output in some_transaction.output_utxos])
        if input_amounts != output_amounts and some_transaction.id != -1:
            raise VaultException("Transaction {} takes {} and spends {}, not equal".format(str(some_transaction.internal_id), input_amounts, output_amounts))

        for some_output in some_transaction.output_utxos:
            if some_output.name in ["CPFP hook", "burned UTXO"]:
                continue
            elif len(some_output.child_transactions) == 0:
                raise VaultException("UTXO {} has no child transactions".format(str(some_output.internal_id)))

        # TODO: There should be other rule checks as well, possibly including
        # things like "does this transaction have the correct scripts and
        # correct outputs" and "does this UTXO have any scripts at all".

    if counter < 1 or counter < len(planned_transactions):
        raise VaultException("Length of the list of planned transactions is too low.")

    return True

def render_planned_tree_to_text_file(some_utxo, filename=TEXT_RENDERING_FILENAME):
    """
    Dump some text describing the planned transaction tree to a text file.
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
