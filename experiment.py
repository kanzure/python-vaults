"""
Run the unit tests with:
    python3 -m unittest experiment.py

"""

import uuid
import unittest
import hashlib
from copy import copy

import bitcoin
from vaults.helpers.formatting import b2x, x, b2lx, lx
from vaults.exceptions import VaultException

from bitcoin.wallet import CBitcoinSecret

#some_private_key = CBitcoinSecret("Kyqg1PJsc5QzLC8rv5BwC156aXBiZZuEyt6FqRQRTXBjTX96bNkW")
#CBitcoinAddress.from_bytes(some_private_key.pub)

from bitcoin import SelectParams
import bitcoin.core
#from bitcoin.core import b2x, lx, COIN, COutPoint, CMutableTxOut, CMutableTxIn, CMutableTransaction, Hash160
#from bitcoin.core.script import CScript, OP_DUP, OP_HASH160, OP_EQUALVERIFY, OP_CHECKSIG, SignatureHash, SIGHASH_ALL
#from bitcoin.core.scripteval import VerifyScript, SCRIPT_VERIFY_P2SH
from bitcoin.core import COIN
from bitcoin.wallet import CBitcoinAddress, CBitcoinSecret

SelectParams("regtest")

hashdigest = hashlib.sha256(b'correct horse battery staple').digest()
secret_key = CBitcoinSecret.from_secret_bytes(hashdigest)


# TODO: create a python library for bitcoin's test_framework
import sys
sys.path.insert(0, "/home/kanzure/local/bitcoin/bitcoin/test/functional")
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import connect_nodes


# from the python-bitcoin-utils library
from bitcoinutils.setup import setup as setup_bitcoin_utils
from bitcoinutils.transactions import Transaction, TxInput, TxOutput, Sequence
from bitcoinutils.keys import P2pkhAddress, P2shAddress, PrivateKey, P2wshAddress, P2wpkhAddress
from bitcoinutils.script import Script
from bitcoinutils.constants import TYPE_RELATIVE_TIMELOCK



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

class ScriptTemplate(object):

    miniscript_policy_definitions = {}
    relative_timelocks = {}

    #@classmethod
    #def parameterize(cls, parameters):
    #    """
    #    Take a bag of parameters and populate the script template with those
    #    parameters. Return the parameterized script.
    #    """
    #    # TODO: Use witness_template_map and witness_template to construct a
    #    # valid witness for this input. Use the key from the parameters to make
    #    # a valid signature, and inject it into the witness template where
    #    # appropriate.
    #    parameter_names = list(cls.miniscript_policy_definitions.keys())
    #    parameterized_script = cls.script_template

    #    for parameter_name in parameter_names:
    #        parameterized_script = parameterized_script.replace(parameter_name, parameters[parameter_name])
    #
    #    return parameterized_script

    @classmethod
    def get_required_parameters(cls):
        required_parameters = []
        subclasses = cls.__subclasses__()
        for subclass in subclasses:
            if hasattr(subclass, "miniscript_policy_definitions"):
                required_parameters.extend(list(subclass.miniscript_policy_definitions.keys()))
        return list(set(required_parameters))

class UserScriptTemplate(ScriptTemplate):
    """
    Represents a script that the user picks. This is the input UTXO that gets
    sent into the vault. The user is responsible for specifying this script,
    and then signing the send-to-vault transaction.

    This is spendable by some user-provided signature. The vault is not
    responsible for producing this signature, but it is responsible for
    producing a scriptpubkey for where the coins are going to be sent to.
    """

    miniscript_policy = "pk(user_key)"
    miniscript_policy_definitions = {"user_key": "user public key"}

    script_template = "<user_key> OP_CHECKSIG"
    witness_template_map = {"user_key_sig": "user_key"}
    witness_templates = {
        "user": "<user_key_sig>",
    }

class ColdStorageScriptTemplate(ScriptTemplate):
    """
    spendable by: cold wallet keys (after a relative timelock) OR immediately
    burnable (gated by ephemeral multisig)
    """

    miniscript_policy = "or(and(pk(ephemeral_key_1),pk(ephemeral_key_2)),and(pk(cold_key1),and(pk(cold_key2),older(144))))"
    miniscript_policy_definitions = {"ephemeral_key_1": "...", "ephemeral_key_2": "...", "cold_key1": "...", "cold_key2": "..."}

    script_template = """
<ephemeral_key_1> OP_CHECKSIG OP_NOTIF
  <cold_key1> OP_CHECKSIGVERIFY <cold_key2> OP_CHECKSIGVERIFY
  <TIMELOCK1> OP_CHECKSEQUENCEVERIFY
OP_ELSE
  <ephemeral_key_2> OP_CHECKSIG
OP_ENDIF
    """

    witness_template_map = {"ephemeral_sig_1": "ephemeral_key_1", "ephemeral_sig_2": "ephemeral_key_2", "cold_key1_sig": "cold_key1", "cold_key2_sig": "cold_key2"}
    witness_templates = {
        "presigned": "<ephemeral_sig_2> <ephemeral_sig_1>",
        "cold-wallet": "<cold_key2_sig> <cold_key1_sig>",
    }
    # TODO: Note that the "cold-wallet" witness template cannot be used to make
    # a valid witness unless the cold keys's private keys are accessed. In
    # contrast, the "presigned" witness can be parameterized and correct before
    # secure key deletion occurs.

    relative_timelocks = {
        "replacements": {
            "TIMELOCK1": 144,
        },
        "selections": {
            "cold-storage": "TIMELOCK1",
        },
    }

class BurnUnspendableScriptTemplate(ScriptTemplate):
    """
    unspendable (burned)
    """

    miniscript_policy = "pk(unspendable_key_1)"
    miniscript_policy_definitions = {"unspendable_key_1": "some unknowable key"}

    script_template = "<unspendable_key_1> OP_CHECKSIG"

    witness_template_map = {}
    witness_templates = {} # (intentionally empty)

class BasicPresignedScriptTemplate(ScriptTemplate):
    """
    Represents a script that can only be spent by one child transaction,
    which is pre-signed.

    spendable by: n-of-n ephemeral multisig after relative timelock
    """

    # TODO: pick an appropriate relative timelock
    miniscript_policy = "and(pk(ephemeral_key_1),and(pk(ephemeral_key_2),older(144)))"
    miniscript_policy_definitions = {"ephemeral_key_1": "...", "ephemeral_key_2": "..."}

    script_template = "<ephemeral_key_1> OP_CHECKSIGVERIFY <ephemeral_key_2> OP_CHECKSIGVERIFY <TIMELOCK1> OP_CHECKSEQUENCEVERIFY"

    witness_template_map = {"ephemeral_sig_1": "ephemeral_key_1", "ephemeral_sig_2": "ephemeral_key_2"}
    witness_templates = {
        "presigned": "<ephemeral_sig_2> <ephemeral_sig_1>",
    }
    relative_timelocks = {
        "replacements": {
            "TIMELOCK1": 144,
        },
        "selections": {
            "presigned": "TIMELOCK1",
        },
    }

class ShardScriptTemplate(ScriptTemplate):
    """
    spendable by: push to cold storage (gated by ephemeral multisig) OR
    spendable by hot wallet after timeout
    """

    ephemeral_multisig_gated = BasicPresignedScriptTemplate.miniscript_policy
    # TODO: pick an appropriate timelock length (also, it should be variable
    # increasing in each sharded UTXO).
    miniscript_policy = f"or(and(pk(hot_wallet_key),older(144)),{ephemeral_multisig_gated})"
    miniscript_policy_definitions = {"hot_wallet_key": "...", "ephemeral_key_1": "...", "ephemeral_key_2": "..."}
    # or(and(pk(hot_wallet_key),older(144)),and(pk(ephemeral_key_1),and(pk(ephemeral_key_2),older(144))))

    script_template = """
<hot_wallet_key> OP_CHECKSIG OP_NOTIF
  <ephemeral_key_1> OP_CHECKSIGVERIFY <ephemeral_key_2> OP_CHECKSIGVERIFY
OP_ELSE
  <TIMELOCK1> OP_CHECKSEQUENCEVERIFY
OP_ENDIF
    """

    witness_template_map = {"ephemeral_sig_1": "ephemeral_key_1", "ephemeral_sig_2": "ephemeral_key_2", "hot_wallet_key_sig": "hot_wallet_key"}
    witness_templates = {
        "presigned": "<ephemeral_sig_2> <ephemeral_sig_1>",
        "hot-wallet": "<hot_wallet_key_sig>",
    }
    relative_timelocks = {
        "replacements": {
            "TIMELOCK1": 144,
        },
        "selections": {
            #"presigned": None,
            "hot-wallet": "TIMELOCK1",
        },
    }

class CPFPHookScriptTemplate(ScriptTemplate):
    """
    OP_TRUE -- a simple script for anyone-can-spend.
    """

    # TODO: does miniscript policy language support this? andytoshi says no,
    # although miniscript does support this.

    script_template = "OP_TRUE"

    # TODO: What is a good witness for this script? Can it be empty? I would
    # know this if I actually knew anything about bitcoin scripting.....
    witness_template_map = {}
    witness_templates = {} # (intentionally empty)

class PlannedUTXO(object):
    __counter__ = 0

    def __init__(self, name=None, transaction=None, script_template=None, amount=None, timelock_multiplier=1):
        self.name = name
        self.script_template = script_template

        # This is the transaction that created this UTXO.
        self.transaction = transaction

        # These are the different potential transactions that reference (spend)
        # this UTXO.
        self.child_transactions = []

        self.amount = amount

        self.timelock_multiplier = timelock_multiplier

        self.__class__.__counter__ += 1
        self.internal_id = uuid.uuid4()

        self.is_finalized = False

    @property
    def vout(self):
        return self.transaction.output_utxos.index(self)

    def crawl(self):
        """
        Return a tuple that contains two items: a list of UTXOs and a list of
        transactions.
        """
        utxos = set([self])
        transactions = set([self.transaction])

        for child_transaction in self.child_transactions:
            transactions.add(child_transaction)

            for child_utxo in child_transaction.output_utxos:
                utxos.add(child_utxo)

                (more_utxos, more_transactions) = child_utxo.crawl()
                utxos.update(more_utxos)
                transactions.update(more_transactions)

        return (utxos, transactions)

    def to_text(self, depth=0, cache=[]):
        output = ""

        prefix = "-" * depth

        output += f"{prefix} UTXO {self.name} amount = {self.amount}\n"

        possible_children = len(self.child_transactions)

        if possible_children == 0:
            output += f"{prefix} UTXO {self.name} has no children.\n"
        else:
            output += f"{prefix} UTXO {self.name} has {possible_children} possible child transactions. They are:\n\n"

            for child_transaction in self.child_transactions:
                output += f"{prefix} UTXO {self.name} -> {child_transaction.name} (start)\n"
                output += child_transaction.to_text(depth=depth+1, cache=cache)
                output += f"{prefix} UTXO {self.name} -> {child_transaction.name} (end)\n"

            output += f"{prefix} UTXO {self.name} (end)\n\n"

        return output

class PlannedInput(object):
    def __init__(self, utxo, witness_template_selection, transaction):
        self.utxo = utxo
        self.witness_template_selection = witness_template_selection
        self.transaction = transaction

        # sanity check
        if witness_template_selection not in utxo.script_template.witness_templates.keys():
            raise VaultException("Invalid witness selection")

        # There might be multiple separate relative timelocks specified for
        # this UTXO. There are different routes for spending. Some of them have
        # different timelocks. The spending path was put on the PlannedUTXO
        # object.
        self.sequence = None
        timelock_multiplier = utxo.timelock_multiplier
        if self.utxo.script_template.relative_timelocks != None:
            timelock_data = self.utxo.script_template.relative_timelocks

            # Some script templates don't have any timelocks.
            if len(timelock_data.keys()) == 0:
                pass
            elif witness_template_selection in timelock_data["selections"].keys():
                var_name = timelock_data["selections"][witness_template_selection]
                relative_timelock_value = timelock_data["replacements"][var_name]

                # Some PlannedUTXO objects have a "timelock multiplier", like
                # if they are a sharded UTXO and have a variable-rate timelock.
                relative_timelock_value = relative_timelock_value * timelock_multiplier
                self.sequence = Sequence(TYPE_RELATIVE_TIMELOCK, relative_timelock_value)
                # Note that timelock_multiplier should appear again in another
                # place, when inserting the timelocks into the script itself.

        self.is_finalized = False

    def parameterize_witness_template_by_signing(self, parameters):
        """
        Take a specific witness template, a bag of parameters, and a
        transaction, and then produce a parameterized witness (including all
        necessary valid signatures).

        Make a sighash for the bitcoin transaction.
        """
        p2wsh_redeem_script = self.utxo.p2wsh_redeem_script
        tx = self.transaction.bitcoin_transaction
        txin_index = self.transaction.inputs.index(self)

        # P2WSH: start with OP_0 ...
        computed_witness = ["OP_0"]

        selection = self.witness_template_selection
        script_template = self.utxo.script_template
        witness_template = script_template.witness_templates[selection]

        # TODO: Don't use floats... python-bitcoin-utils uses floats. Blargh. I
        # have submitted a pull request to fix this but I will probably just
        # migrate over to python-bitcoinlib instead.
        amount = self.utxo.amount / COIN
        # COIN == 1e8

        # TODO: Might have to update the witness_templates values to give a
        # correct ordering for which signature should be supplied first.

        witness_tmp = witness_template.split(" ")
        for (idx, section) in enumerate(witness_tmp):
            if idx > 0:
                computed_witness.append(" ")

            if section[0] == "<" and section[-1] == ">":
                if section not in script_template.witness_template_map.keys():
                    raise Exception("Missing key mapping for {}".format(section))

                key_param_name = script_template.witness_template_map[section]
                private_key = parameters[key_param_name]
                private_key = PrivateKey(private_key)

                signature = private_key.sign_segwit_input(tx, txin_idx, p2wsh_redeem_script, amount)
                computed_witness.append(signature)

            else:
                # dunno what to do with this, probably just pass it on really..
                computed_witness.append(section)

        # Append the p2wsh redeem script.
        computed_witness.append(p2wsh_redeem_script.to_hex())

        computed_witness = Script(computed_witness)
        return computed_witness

class PlannedTransaction(object):
    __counter__ = 0

    def __init__(self, name=None):
        self.name = name

        cpfp_hook_utxo = PlannedUTXO(
            name="CPFP hook",
            transaction=self,
            script_template=CPFPHookScriptTemplate,
            amount=0,
        )

        self.inputs = []
        self.output_utxos = [cpfp_hook_utxo]

        self.__class__.__counter__ += 1
        self.internal_id = uuid.uuid4()

        self.bitcoin_transaction = None
        self.is_finalized = False

    @property
    def input_utxos():
        return [some_input.utxo for some_input in self.inputs]

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

    @property
    def txid(self):
        # It's important to note that the txid can only be calculated after the
        # rest of the transaction has been finalized, and it is possible to
        # serialize the transaction.
        return self.bitcoin_transaction.get_txid()

    def serialize(self):
        return self.bitcoin_transaction.serialize()

    def check_inputs_outputs_are_finalized(self):
        """
        Check whether the inputs and outputs are ready.
        """

        for some_input in self.inputs:
            if not some_input.is_finalized:
                return False

        for some_output in self.output_utxos:
            if not some_output.is_finalized:
                return False

        return True

    def to_text(self, depth=0, cache=[]):
        output = ""

        prefix = "-" * depth

        num_utxos = len(self.output_utxos)

        if num_utxos == 0:
            output += f"{prefix} Transaction {self.internal_id} ({self.name}) has no UTXOs.\n\n"
        else:
            if self.internal_id in cache:
                output += f"{prefix} Transaction {self.internal_id} ({self.name}) previously rendered. (Another input)\n"
            else:
                cache.append(self.internal_id)

                output += f"{prefix} Transaction {self.internal_id} ({self.name}) has {num_utxos} UTXOs. They are:\n\n"

                for utxo in self.output_utxos:
                    output += f"{prefix} Transaction ({self.name}) - UTXO {utxo.name} (start)\n"
                    output += utxo.to_text(depth=depth+1, cache=cache)
                    output += f"{prefix} Transaction ({self.name}) - UTXO {utxo.name} (end)\n"

                output += f"{prefix} Transaction {self.internal_id} ({self.name}) end\n\n"

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
        utxo1 = PlannedUTXO(name="some UTXO", transaction=None, script_template=ScriptTemplate)
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

    def test_planned_transaction_cpfp_hook_utxo(self):
        planned_transaction = PlannedTransaction(name="name goes here")
        self.assertEqual(len(planned_transaction.output_utxos), 1)
        self.assertEqual(planned_transaction.output_utxos[0].name, "CPFP hook")


def make_burn_transaction(incoming_utxo):
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

def make_push_to_cold_storage_transaction(incoming_utxo):
    push_transaction = PlannedTransaction(name="Push (sharded?) UTXO to cold storage wallet")
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
    burn_transaction = make_burn_transaction(cold_storage_utxo)

    incoming_utxo.child_transactions.append(push_transaction)
    return push_transaction

def make_sweep_to_cold_storage_transaction(incoming_utxos):
    push_transaction = PlannedTransaction(name="Sweep UTXOs to cold storage wallet")

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
        burn_transaction = make_burn_transaction(cold_storage_utxo)

    return push_transaction

def make_telescoping_subsets(some_set):
    item_sets = []
    for x in range(0, len(some_set)-1):
        item_sets.append(some_set[x:len(some_set)])
    return item_sets

def make_sharding_transaction(per_shard_amount=1 * COIN, num_shards=100, first_shard_extra_amount=0, incoming_utxo=None, original_num_shards=None, make_sweeps=False):
    """
    Make a new sharding transaction.
    """

    if num_shards < original_num_shards:
        partial ="(partial) "
    elif num_shards == original_num_shards:
        partial = ""

    sharding_transaction = PlannedTransaction(name=f"Vault {partial}stipend start transaction.")
    incoming_utxo.child_transactions.append(sharding_transaction)

    shard_utxos = []
    for shard_id in range(0, num_shards):
        amount = per_shard_amount
        if shard_id == 0 and first_shard_extra_amount != None:
            amount += first_shard_extra_amount

        sharded_utxo_name = f"shard fragment UTXO {shard_id}/{num_shards}"

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

        make_push_to_cold_storage_transaction(incoming_utxo=sharded_utxo)

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
        #sweep_transactions = []
        for some_subset in subsets:
            sweep_transaction = make_sweep_to_cold_storage_transaction(some_subset)
            #sweep_transactions.append(sweep_transaction)

            for utxo in some_subset:
                utxo.child_transactions.append(sweep_transaction)

    return sharding_transaction

# The vault UTXO can have 1/100th spent at a time, the rest goes back into a
# vault. So you can either do the stipend-spend, or the one-at-a-time spend.
# So if the user knows they only want a small amount, they use the one-time
# spend. If they know they want more, then they can use the stipend (or migrate
# out of the vault by first broadcasting the stipend setup transaction).
def make_one_shard_possible_spend(incoming_utxo, per_shard_amount, num_shards, original_num_shards=None, first_shard_extra_amount=None):
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

    exiting_utxo = PlannedUTXO(
        name="shard fragment UTXO",
        transaction=vault_spend_one_shard_transaction,
        script_template=ShardScriptTemplate,
        amount=amount,
    )
    vault_spend_one_shard_transaction.output_utxos.append(exiting_utxo)

    # For the exit UTXO, it should also be posisble to send that UTXO to cold
    # storage instead of letting the multisig hot wallet control it.
    make_push_to_cold_storage_transaction(exiting_utxo)
    # The hot wallet spend transaction is not represented here because t's not
    # a pre-signed transaction. It can be created at a later time, by the hot
    # wallet keys.

    if num_shards == 1:
        return
    else:
        # TODO: should this be num_shards or (num_shards - 1) ?
        remaining_amount = (num_shards - 1) * per_shard_amount

        # Second UTXO attached to vault_spend_one_shard_transaction.
        revault_utxo = PlannedUTXO(
            name="vault UTXO",
            transaction=vault_spend_one_shard_transaction,
            script_template=BasicPresignedScriptTemplate,
            amount=remaining_amount,
        )
        vault_spend_one_shard_transaction.output_utxos.append(revault_utxo)

        # The vault UTXO can also be spent directly to cold storage.
        make_push_to_cold_storage_transaction(revault_utxo)

        # The re-vault UTXO can be sharded into "100" pieces (but not really 100..
        # it should be 100 minus the depth).
        make_sharding_transaction(
            per_shard_amount=per_shard_amount,
            num_shards=num_shards - 1,
            incoming_utxo=revault_utxo,
            original_num_shards=original_num_shards,
            first_shard_extra_amount=None,
        )

        # The re-vault UTXO can also be spent using the one-shard possible spend
        # method.
        make_one_shard_possible_spend(
            incoming_utxo=revault_utxo,
            per_shard_amount=per_shard_amount,
            num_shards=num_shards - 1,
            original_num_shards=original_num_shards,
            first_shard_extra_amount=None,
        )

# Now that we have segwit outputs, proceed with the protocol.
#
# Construct a 2-of-2 P2WSH script for the pre-signed transaction tree. All of
# the deleted keys should be at least 2-of-2.
#
# After signing all of those transactions (including the one spending the
# 2-of-2 root P2SH), delete the key.
#
# Then move the segwit coins into that top-level P2WSH scriptpubkey.
def setup_vault(segwit_utxo, parameters):
    vault_locking_transaction = PlannedTransaction(name="Vault locking transaction")
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
    make_push_to_cold_storage_transaction(incoming_utxo=vault_initial_utxo)

    # The number of shards that we made at this level of the transaction tree.
    # Inside the make_one_shard_possible_spend function, this amount will be
    # decremented before it is used to create the next sharding/stipend-setup
    # transaction.
    num_shards = 100

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
    )

    return vault_initial_utxo



def sign_transaction_tree(initial_utxo, parameters):
    """
    Walk the planned transaction tree and convert everything into bitcoin
    transactions. Convert the script templates and witness templates into real
    values.
    """

    # for python-bitcoin-utils, probably like python-bitcoinlib's SelecParams()
    setup_bitcoin_utils("testnet")

    # Crawl the planned transaction tree and get a list of all planned
    # transactions and all planned UTXOs.
    (planned_utxos, planned_transactions) = initial_utxo.crawl()

    #if len(planned_transactions) < PlannedTransaction.__counter__:
    #    raise Exception("Counted {} transactions but only found {}".format(PlannedTransaction.__counter__, len(planned_transactions)))
    #
    #if len(planned_utxos) < PlannedUTXO.__counter__:
    #    raise Exception("Counted {} UTXOs but only found {}".format(PlannedUTXO.__counter__, len(planned_utxos)))


    # also get a list of all inputs
    planned_inputs = set()
    for planned_transaction in planned_transactions:
        planned_inputs.update(planned_transaction.inputs)

    # Parameterize each PlannedUTXO's script template, based on the given
    # config/parameters. Loop through all of the PlannedUTXOs in any order.
    for planned_utxo in planned_utxos:
        script_template = planned_utxo.script_template
        miniscript_policy_definitions = script_template.miniscript_policy_definitions
        script = copy(planned_utxo.script_template.script_template)

        for some_variable in miniscript_policy_definitions.keys():
            script = script.replace("<" + some_variable + ">", parameters[some_variable])

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
            raise Exception("Script not finished cooking? {}".format(script))

        # remove newlines
        script = script.replace("\n", " ")
        # reduce any excess whitespace
        while (" " * 2) in script:
            script = script.replace("  ", " ")

        # convert script into a parsed python object
        p2wsh_redeem_script = Script(script.split(" "))

        p2wsh_address = P2wshAddress.from_script(p2wsh_redeem_script)
        scriptpubkey = p2wsh_address.to_script_pub_key()
        assert type(scriptpubkey) == Script

        planned_utxo.scriptpubkey = scriptpubkey
        planned_utxo.p2wsh_redeem_script = p2wsh_redeem_script

        planned_utxo.bitcoin_output = TxOutput(amount, scriptpubkey)
        planned_utxo.is_finalized = True

    # Finalize each transaction by creating a set of bitcoin objects (including
    # a bitcoin transaction) representing the planned transaction.
    #
    # TODO: In theory, this should be correctly ordered.
    for planned_transaction in planned_transactions:

        for planned_input in planned_transaction.inputs:
            # Sanity test: all parent transactions should already be finalized
            assert planned_input.utxo.transaction.is_finalized == True

            planned_utxo = planned_input.utxo
            witness_template_selection = planned_input.witness_template_selection

            # sanity check
            if witness_template_selection not in planned_utxo.script_template.witness_templates.keys():
                raise Exception("UTXO {} is missing witness template \"{}\"".format(planned_utxo.internal_id, witness_template_selection))

            witness_template = planned_utxo.script_template.witness_templates[witness_template_selection]

            # Would use transaction.bitcoin_transaction.get_txid() but for the
            # very first utxo, the txid is going to be mocked for testing
            # purposes. So it's better to just use the txid property...
            txid = planned_utxo.transaction.txid
            vout = planned_utxo.vout

            # Note that it's not enough to just have the relative timelock in the
            # script; you also have to set it on the TxInput object.
            #   seq = Sequence(TYPE_RELATIVE_TIMELOCK, 144)
            #   TxInput(txid, vout, sequence=self.seq.for_input_sequence())
            sequence = planned_input.sequence

            # TODO: implement bitcoin_input on PlannedInput
            planned_input.bitcoin_input = TxInput(txid, vout, sequence=sequence)
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
        planned_transaction.bitcoin_transaction = Transaction(bitcoin_inputs, bitcoin_outputs, has_segwit=True)

        # Now that the inputs are finalized, it should be possible to sign each
        # input on this transaction and add to the list of witnesses.
        for planned_input in planned_transaction.inputs:
            witness = planned_input.parameterize_witness_template_by_signing(parameters)
            planned_transaction.bitcoin_transaction.witnesses.append(witness)

        planned_transaction.is_finalized = True

        print("Serialized transaction: " + planned_transaction.serialize())
        print("txid: " + planned_transaction.bitcoin_transaction.get_txid())

    return

def sha256(data):
    """
    Compute the sha256 digest of the given data.
    """
    return hashlib.sha256(data).digest()

def make_private_keys():
    """
    Convert a list of passphrases into a list of private keys.
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

    for passphrase in passphrases:
        hashed = sha256(passphrase)

        # compressed=True is default
        bitcoin_secret = CBitcoinSecret.from_secret_bytes(hashed, compressed=True)

        private_key = str(bitcoin_secret)

        # Might as well convert them into python-bitcoin-utils objects...
        private_key = PrivateKey(private_key)

        private_keys.append(private_key)

    return private_keys

if __name__ == "__main__":
    #amount = random.randrange(0, 100 * COIN)
    amount = 7084449357

    # TODO: come up with a way to define both the public key and the private
    # key... update everywhere that "parameters" is used. Sometimes the public
    # key is required, sometimes the private key is required.

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
        "amount": amount,
        "unspendable_key_1": PublicKey("0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"),
    }

    for some_name in parameter_names:
        private_key = some_private_keys.pop()
        public_key = private_key.get_public_key()
        parameters[some_name] = {"private_key": private_key, "public_key": public_key}

    # consistency check against required parameters
    required_parameters = ScriptTemplate.get_required_parameters()

    missing_parameters = False
    for required_parameter in required_parameters:
        if required_parameter not in parameters.keys():
            print(f"Missing parameter: {required_parameter}")
            missing_parameters = True
    if missing_parameters:
        print("Missing parameters!")
        sys.exit(1)

    segwit_utxo = PlannedUTXO(
        name="segwit input coin",
        transaction=None,
        script_template=UserScriptTemplate,
        amount=amount,
    )

    # ===============
    # Here's where the magic happens.
    vault_initial_utxo = setup_vault(segwit_utxo, parameters)
    # ===============

    # To test that the sharded UTXOs have the right amounts, do the following:
    # assert (second_utxo_amount * 99) + first_utxo_amount == amount

    # Display all UTXOs and transactions-- render the tree of possible
    # transactions.
    if False:
        output = segwit_utxo.to_text()
        print(output)

    # stats
    print("*** Stats and numbers")
    print(f"{PlannedUTXO.__counter__} UTXOs, {PlannedTransaction.__counter__} transactions")

    sign_transaction_tree(vault_initial_utxo, parameters)
    #sign_transaction_tree(segwit_utxo, parameters)

    # TODO: Persist the pre-signed transactions to persist storage system.

    # TODO: Delete the ephemeral keys.
