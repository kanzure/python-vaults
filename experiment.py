"""
Run the unit tests with:
    python3 -m unittest experiment.py

"""

import unittest
import hashlib

import bitcoin
from vaults.helpers.formatting import b2x, x, b2lx, lx

from bitcoin.wallet import CBitcoinSecret

#some_private_key = CBitcoinSecret("Kyqg1PJsc5QzLC8rv5BwC156aXBiZZuEyt6FqRQRTXBjTX96bNkW")
#CBitcoinAddress.from_bytes(some_private_key.pub)

from bitcoin import SelectParams
from bitcoin.core import b2x, lx, COIN, COutPoint, CMutableTxOut, CMutableTxIn, CMutableTransaction, Hash160
from bitcoin.core.script import CScript, OP_DUP, OP_HASH160, OP_EQUALVERIFY, OP_CHECKSIG, SignatureHash, SIGHASH_ALL
from bitcoin.core.scripteval import VerifyScript, SCRIPT_VERIFY_P2SH
from bitcoin.wallet import CBitcoinAddress, CBitcoinSecret

SelectParams("regtest")

hashdigest = hashlib.sha256(b'correct horse battery staple').digest()
secret_key = CBitcoinSecret.from_secret_bytes(hashdigest)


# TODO: create a python library for bitcoin's test_framework
import sys
sys.path.insert(0, "/home/kanzure/local/bitcoin/bitcoin/test/functional")
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import connect_nodes

#class VaultsTest(BitcoinTestFramework):
class VaultsBlah:
    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 2
        self.extra_args = [
            ["-txindex"],
            ["-txindex"],
            ["-txindex"],
        ]
        self.supports_cli = False

    def setup_network(self):
        super().setup_network()

        # TODO: verify that these parameters are right
        connect_nodes(self.nodes[0], 1)

    # TODO: finish implementation of this test. But first implement something
    # to "fill out" the tree of possible transactions with actual bitcoin
    # transactions.
    def run_test(self):
        self.log.info("Starting the vault test.")

        # mine some initial coins to play around with
        self.nodes[1].generate(2)
        self.sync_all()
        self.nodes[0].generate(110)
        self.sync_all()

        # options: legacy, p2sh-segwit, bech32
        address_BECH32 = self.nodes[0].getnewaddress("", "bech32")

        # convert some coins into segwit coins
        txid = self.nodes[0].sendtoaddress(some_segwit_address, 600)

        # make sure the segwit coins are mature
        self.nodes[0].generate(6)
        self.sync_all()

        # isolate the unspent segwit utxo
        utxos = self.nodes[0].listunspent()
        segwit_utxo = [{"txid": utxo["txid"], "vout": utxo["vout"]} for utxo in utxos if utxo["txid"] == txid][0]

        # Basic diagram:
        #
        # segwit utxo -> 2-of-2 P2WSH utxo -> pre-signed transaction (w/ 100 utxos?)
        #
        # Note: this works because the P2WSH utxo has a script spending to an
        # ephemeral key, and the pre-signed transaction is signed using that
        # ephemeral key.

        # TODO: create 2 private keys, for the 2-of-2 P2WSH multisig script.
        # Calculate their public keys. These private keys will be deleted
        # later.
        private_key1 = ""
        private_key2 = ""


        # TODO: construct the final 2-of-2 P2WSH multisig script. This script
        # should only be spendable by one of the previously-created pre-signed
        # transactions.
        input_txid = segwit_utxo["txid"]
        input_txid_vout = segwit_utxo["vout"]
        output_script = None # TODO: 2-of-2 multisig, spendable by the two private keys
        (txid1, transaction1) = createrawtransaction(inputs, outputs)

        # Make a pre-signed transaction that spends the 2-of-2 PWSH utxo txid,
        # and creates 100 UTXOs. Delete the ephemeral key after signing.
        input_txid2 = txid1
        input_txid2_vout = 0
        outputs2 = None # TODO: make 100 outputs, each with a similar script
        (txid2, transaction2) = createrawtransaction(inputs2, outputs2)
        # TODO: sign transaction2, using the two private keys


        # For each UTXO, make: (1) a push to cold storage transaction, (2) a
        # push to new identical vault (using same keys).
        for utxo in created_utxos:
            make_push_to_cold_storage_transaction_for_utxo(utxo)
            make_push_to_vault_transaction_for_utxo(utxo, splitting=False)

        # TODO: sign the tree of transactions (in any order)

        # delete the private keys
        del private_key1
        del private_key2

        # Now sign the transaction that starts the whole thing.
        self.nodes[0].signrawtransaction(transaction1)


class PlannedTransaction(object):
    __counter__ = 0

    def __init__(self, name=None):
        self.name = name

        self.input_utxos = []
        self.output_utxos = []

        self.__class__.__counter__ += 1

    @property
    def parent_transactions():
        _parent_transactions = []
        for some_utxo in self.input_utxos:
            _parent_transactions.append(some_utxo.transaction)
        return _parent_transactions

    @property
    def child_transactions():
        _child_transactions = []
        for some_utxo in self.output_utxos:
            _child_transactions.extend(some_utxo.child_transactions)
        return _child_transactions

    def to_text(self, depth=0):
        output = ""

        prefix = "--" * depth

        num_utxos = len(self.output_utxos)
        output += f"{prefix} Transaction ({self.name}) has {num_utxos} UTXOs. They are:\n\n"

        for utxo in self.output_utxos:
            output += f"{prefix} Transaction ({self.name}) - UTXO {utxo.name} (start)\n"
            output += utxo.to_text(depth=depth+1)
            output += f"{prefix} Transaction ({self.name}) - UTXO {utxo.name} (end)\n"

        output += f"{prefix} Transaction ({self.name}) end\n"

        return output

class PlannedUTXO(object):
    __counter__ = 0

    def __init__(self, name=None, transaction=None, script_description_text="OP_TRUE"):
        self.name = name
        self.script_description_text = script_description_text

        # This is the transaction that created this UTXO.
        self.transaction = transaction

        # These are the different potential transactions that reference (spend)
        # this UTXO.
        self.child_transactions = []

        self.__class__.__counter__ += 1

    def to_text(self, depth=0):
        output = ""

        prefix = "--" * depth

        possible_children = len(self.child_transactions)
        output += f"{prefix} UTXO {self.name} has {possible_children} possible child transactions. They are:\n\n"

        for child_transaction in self.child_transactions:
            output += f"{prefix} UTXO {self.name} -> {child_transaction.name} (start)\n"
            output += child_transaction.to_text(depth=depth+1)
            output += f"{prefix} UTXO {self.name} -> {child_transaction.name} (end)\n"

        output += f"{prefix} UTXO {self.name} (end)\n"

        return output

class AbstractPlanningTests(unittest.TestCase):
    def test_planned_transaction(self):
        planned_transaction1 = PlannedTransaction(name="name goes here")
        planned_transaction2 = PlannedTransaction(name="")
        planned_transaction3 = PlannedTransaction(name=None)
        del planned_transaction3
        del planned_transaction2
        del planned_transaction1

    def test_planned_transaction_counter(self):
        counter_start = int(PlannedTransaction.__counter__)
        planned_transaction1 = PlannedTransaction(name="name goes here")
        planned_transaction2 = PlannedTransaction(name="")
        planned_transaction3 = PlannedTransaction(name=None)
        counter_end = int(PlannedTransaction.__counter__)

        self.assertEqual(counter_end - counter_start, 3)
        del planned_transaction3
        del planned_transaction2
        del planned_transaction1
        self.assertEqual(counter_end - counter_start, 3)

    def test_planned_utxo(self):
        utxo1 = PlannedUTXO(name="some UTXO", transaction=None, script_description_text="blah")
        utxo2 = PlannedUTXO(name="second UTXO", transaction=None)
        utxo3 = PlannedUTXO(name="another UTXO")
        del utxo3
        del utxo2
        del utxo1

    def test_planned_utxo_counter(self):
        counter_start = int(PlannedUTXO.__counter__)
        utxo1 = PlannedUTXO(name="some UTXO")
        counter_end = int(PlannedUTXO.__counter__)

        self.assertEqual(counter_end - counter_start, 1)
        del utxo1
        self.assertEqual(counter_end - counter_start, 1)

def make_burn_transaction(incoming_utxo):
    burn_transaction = PlannedTransaction(name="Burn some UTXO")
    burn_transaction.input_utxos = [incoming_utxo]
    burn_utxo = PlannedUTXO(name="burned UTXO", transaction=burn_transaction, script_description_text="unspendable (burned)")
    burn_transaction.output_utxos = [burn_utxo]
    incoming_utxo.child_transactions.append(burn_transaction)
    return burn_transaction

def make_push_to_cold_storage_transaction(incoming_utxo):
    push_transaction = PlannedTransaction(name="Push (sharded?) UTXO to cold storage wallet")
    push_transaction.input_utxos = [incoming_utxo]

    cold_storage_utxo = PlannedUTXO(name="cold storage UTXO", transaction=push_transaction, script_description_text="spendable by cold wallet keys (after a relative timelock) OR immediately burnable")
    push_transaction.output_utxos = [cold_storage_utxo]

    # The purpose of the relative timelock before the cold storage keys are
    # able to spend is so that not all cold storage UTXOs can be spent at once.
    # The user is thus given an option of burning the other UTXOs if they think
    # that an adversary is about to steal the remaining UTXOs after observing
    # the theft of a single UTXO.


    # Make a possible transaction: burn/donate the cold storage UTXO.
    burn_transaction = make_burn_transaction(cold_storage_utxo)

    incoming_utxo.child_transactions.append(push_transaction)
    return push_transaction

def make_sharding_transaction(per_shard_amount=1, num_shards=100, incoming_utxo=None):
    """
    Make a new sharding transaction.
    """

    if num_shards < 100:
        partial ="(partial) "
    elif num_shards == 100:
        partial = ""

    sharding_transaction = PlannedTransaction(name=f"Vault {partial}stipend start transaction.")
    incoming_utxo.child_transactions.append(sharding_transaction)

    for shard_id in range(0, num_shards):
        sharded_utxo_name = f"shard fragment UTXO {shard_id}/{num_shards}"

        # Note: can't re-vault from this point. Must pass through the cold
        # wallet or the hot wallet before it can get back into a vault.
        sharded_utxo = PlannedUTXO(name=sharded_utxo_name, transaction=sharding_transaction, script_description_text="spendable by: push to cold storage OR spendable by hot wallet after timeout")
        sharding_transaction.output_utxos.append(sharded_utxo)

        make_push_to_cold_storage_transaction(incoming_utxo=sharded_utxo)

    # TODO: make a variety of push-to-cold-storage (sweep) transactions that
    # each take 2 or more UTXOs. Note that the UTXOs get spent in order, so
    # this fortunately limits the total number of transactions to generate.

    return sharding_transaction

# The vault UTXO can have 1/100th spent at a time, the rest goes back into a
# vault. So you can either do the stipend-spend, or the one-at-a-time spend.
# So if the user knows they only want a small amount, they use the one-time
# spend. If they know they want more, then they can use the stipend (or migrate
# out of the vault by first broadcasting the stipend setup transaction).
def make_one_shard_possible_spend(incoming_utxo, per_shard_amount, num_shards):
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

    vault_spend_one_shard_transaction = PlannedTransaction(name="Vault transaction: spend one shard, re-vault the remaining shards")
    incoming_utxo.child_transactions.append(vault_spend_one_shard_transaction)
    vault_spend_one_shard_transaction.input_utxos = [incoming_utxo]

    # Next, add two UTXOs to vault_spend_one_shard transaction.

    exiting_utxo = PlannedUTXO(name="shard fragment UTXO", transaction=vault_spend_one_shard_transaction, script_description_text="spendable by: push to cold storage OR spendable by hot wallet after timeout")
    vault_spend_one_shard_transaction.output_utxos.append(exiting_utxo)

    # For the exit UTXO, it should also be posisble to send that UTXO to cold
    # storage instead of letting the multisig hot wallet control it.
    make_push_to_cold_storage_transaction(exiting_utxo)
    # The hot wallet spend transaction is not represented here because t's not
    # a pre-signed transaction. It can be created at a later time, by the hot
    # wallet keys.

    # Second UTXO attached to vault_spend_one_shard_transaction.
    revault_utxo = PlannedUTXO(name="vault UTXO", transaction=vault_spend_one_shard_transaction, script_description_text="spendable by 2-of-2 ephemeral multisig (after some relative timelock)")
    vault_spend_one_shard_transaction.output_utxos.append(revault_utxo)

    # The vault UTXO can also be spent directly to cold storage.
    make_push_to_cold_storage_transaction(revault_utxo)

    if num_shards == 1:
        return
    else:
        # The re-vault UTXO can be sharded into "100" pieces (but not really 100..
        # it should be 100 minus the depth).
        make_sharding_transaction(per_shard_amount=per_shard_amount, num_shards=num_shards - 1, incoming_utxo=revault_utxo)
        # The re-vault UTXO can also be spent using the one-shard possible spend
        # method.
        make_one_shard_possible_spend(incoming_utxo=revault_utxo, per_shard_amount=per_shard_amount, num_shards=num_shards - 1)

# Now that we have segwit outputs, proceed with the protocol.
#
# Construct a 2-of-2 P2WSH script for the pre-signed transaction tree. All of
# the deleted keys should be at least 2-of-2.
#
# After signing all of those transactions (including the one spending the
# 2-of-2 root P2SH), delete the key.
#
# Then move the segwit coins into that top-level P2WSH scriptpubkey.
def setup_vault(segwit_utxo):
    vault_locking_transaction = PlannedTransaction(name="Vault locking transaction")
    vault_locking_transaction.input_utxos = [segwit_utxo]
    segwit_utxo.child_transactions.append(vault_locking_transaction)

    vault_initial_utxo = PlannedUTXO(name="vault initial UTXO", transaction=vault_locking_transaction, script_description_text="spendable by 2-of-2 ephemeral multisig")
    vault_locking_transaction.output_utxos = [vault_initial_utxo]

    # Optional transaction: Push the whole amount to cold storage.
    make_push_to_cold_storage_transaction(incoming_utxo=vault_initial_utxo)

    # The number of shards that we made at this level of the transaction tree.
    # Inside the make_one_shard_possible_spend function, this amount will be
    # decremented before it is used to create the next sharding/stipend-setup
    # transaction.
    shard_fragment_count = 100

    # Optional transaction: split the UTXO up into 100 shards, when it's time
    # to start spending the coins.
    # Make a transaction that sets up 100 UTXOs (with appropriate relative
    # timelocks).
    make_sharding_transaction(per_shard_amount=1, num_shards=100, incoming_utxo=vault_initial_utxo)

    # Another optional transaction
    # Make a transaction that lets the user spend one shard, but re-vaults
    # everything else.
    make_one_shard_possible_spend(incoming_utxo=vault_initial_utxo, per_shard_amount=1, num_shards=100)

    return vault_initial_utxo

if __name__ == "__main__":
    segwit_utxo = PlannedUTXO(name="segwit input coin", transaction=None, script_description_text="spendable by user single-sig")
    setup_vault(segwit_utxo)

    # Display all UTXOs and transactions-- render the tree of possible
    # transactions.
    print(segwit_utxo.to_text())

    # stats
    print("*** Stats and numbers")
    print(f"{PlannedUTXO.__counter__} UTXOs, {PlannedTransaction.__counter__} transactions")

