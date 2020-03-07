"""
Run the unit tests with:
    python3 -m unittest experiment.py

"""

import os
import uuid
import unittest
import hashlib
from copy import copy
import json
import struct

# pip3 install graphviz
from graphviz import Digraph

import bitcoin
from vaults.helpers.formatting import b2x, x, b2lx, lx
from vaults.exceptions import VaultException
from vaults.loggingconfig import logger

from bitcoin.wallet import CBitcoinSecret

from bitcoin import SelectParams
from bitcoin.core import COIN, CTxOut, COutPoint, CTxIn, CMutableTransaction, CTxWitness, CTxInWitness, CScriptWitness
from bitcoin.core.script import CScript, OP_0, SignatureHash, SIGHASH_ALL, SIGVERSION_WITNESS_V0, Hash160, OP_ROLL, OP_NOP4, OP_DROP, OP_2DROP, OP_IF, OP_ELSE, OP_ENDIF, OP_CHECKSIGVERIFY, OP_NOP3
from bitcoin.core.key import CPubKey
from bitcoin.wallet import CBitcoinAddress, CBitcoinSecret, P2WSHBitcoinAddress, P2WPKHBitcoinAddress
import bitcoin.rpc

# TODO: VerifyScript doesn't work with segwit yet...
#from bitcoin.core.scripteval import VerifyScript

SelectParams("regtest")


# TODO: create a python library for bitcoin's test_framework
import sys
sys.path.insert(0, "/home/kanzure/local/bitcoin/bitcoin/test/functional")
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import connect_nodes
from test_framework.messages import ser_string

TRANSACTION_STORE_FILENAME ="transaction-store.json"
TEXT_RENDERING_FILENAME = "text-rendering.txt"
VAULTFILE_FILENAME = "vaultfile"

VAULT_FILE_FORMAT_VERSION = "0.0.1"

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

    # TODO: move parameterization into ScriptTemplate?

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
    miniscript_policy_definitions = {"user_key_hash160": "hash160 of user public key"}

    #script_template = "<user_key> OP_CHECKSIG"
    #witness_template_map = {"user_key_sig": "user_key"}
    #witness_templates = {
    #    "user": "<user_key_sig>",
    #}

    # Bitcoin Core wallet uses P2WPKH by default.
    script_template = "<user_key_hash160>"
    witness_template_map = {"user_key_sig": "user_key"}
    witness_templates = {
        "user": "<user_key_sig> <user_key>",
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

    # python-bitcoinlib doesn't know that OP_TRUE==OP_1 so just set to OP_1
    # directly.
    # https://github.com/petertodd/python-bitcoinlib/issues/225
    script_template = "OP_1"

    # For OP_TRUE scriptpubkeys, witness stack can be empty, according to Bob.
    # But we might just upgrade this to use a hot wallet key CHECKSIG anyway.
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

        self.id = copy(self.__class__.__counter__)
        self.__class__.__counter__ += 1
        self.internal_id = uuid.uuid4()

        self.is_finalized = False
        self._vout_override = None

    @property
    def vout(self):
        if self._vout_override == None:
            return self.transaction.output_utxos.index(self)
        else:
            return self._vout_override

    def crawl(self):
        """
        Return a tuple that contains two items: a list of UTXOs and a list of
        transactions.
        """
        utxos = [self]
        transactions = [self.transaction]

        for child_transaction in self.child_transactions:
            transactions.append(child_transaction)

            for child_utxo in child_transaction.output_utxos:
                utxos.append(child_utxo)

                (more_utxos, more_transactions) = child_utxo.crawl()
                utxos.extend(more_utxos)
                transactions.extend(more_transactions)

        utxos = list(set(utxos))
        transactions = list(set(transactions))

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

    def to_dict(self):
        data = {
            "counter": self.id,
            "internal_id": str(self.internal_id),
            "name": self.name,
            "script_template_name": self.script_template.__name__,
            "amount": self.amount,
            "timelock_multiplier": self.timelock_multiplier,
            "transaction_internal_id": str(self.transaction.internal_id),
            "child_transaction_internal_ids": [str(ctx.internal_id) for ctx in self.child_transactions],
        }

        if self._vout_override != None:
            data["_vout_override"] = self._vout_override

        return data

    def to_json(self):
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data):
        planned_utxo = cls()
        planned_utxo.internal_id = data["internal_id"]
        planned_utxo.id = data["counter"]
        planned_utxo.name = data["name"]
        planned_utxo.is_finalized = True

        script_template_lookup = dict([(klass.__name__, klass) for klass in ScriptTemplate.__subclasses__()])
        planned_utxo.script_template = script_template_lookup[data["script_template_name"]]

        planned_utxo.amount = data["amount"]
        planned_utxo.timelock_multiplier = data["timelock_multiplier"]

        # TODO: second pass to add back object references
        planned_utxo._transaction_internal_id = data["transaction_internal_id"]
        planned_utxo._child_transaction_internal_ids = data["child_transaction_internal_ids"]

        if "_vout_override" in data.keys():
            planned_utxo._vout_override = data["_vout_override"]

        return planned_utxo

    @classmethod
    def from_json(cls, payload):
        data = json.loads(payload)
        return cls.from_dict(data)

    def connect_objects(self, inputs, outputs, transactions):
        """
        Upgrades _transaction_internal_id to self.transaction association.
        """
        internal_id_requirement = False
        child_count = 0
        for transaction in transactions:
            if str(transaction.internal_id) == self._transaction_internal_id:
                self.transaction = transaction
                internal_id_requirement = True

            if str(transaction.internal_id) in self._child_transaction_internal_ids:
                self.child_transactions.append(transaction)
                child_count += 1

            if internal_id_requirement and child_count==len(self._child_transaction_internal_ids):
                break
        else:
            raise Exception("Failed to break")

class PlannedInput(object):

    def __init__(self, utxo=None, witness_template_selection=None, transaction=None):
        self.utxo = utxo
        self.witness_template_selection = witness_template_selection
        self.transaction = transaction
        self.internal_id = uuid.uuid4()
        self.is_finalized = False

        if not utxo:
            return

        # sanity check
        if witness_template_selection not in utxo.script_template.witness_templates.keys():
            raise VaultException("Invalid witness selection")

        # There might be multiple separate relative timelocks specified for
        # this UTXO. There are different routes for spending. Some of them have
        # different timelocks. The spending path was put on the PlannedUTXO
        # object.
        self.relative_timelock = None
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
                self.relative_timelock = relative_timelock_value

                if relative_timelock_value > 0xfff:
                    raise Exception("Timelock {} exceeds max timelock {}".format(relative_timelock_value, 0xfff))

                # Note that timelock_multiplier should appear again in another
                # place, when inserting the timelocks into the script itself.

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

        computed_witness = []

        selection = self.witness_template_selection
        script_template = self.utxo.script_template
        witness_template = script_template.witness_templates[selection]

        amount = self.utxo.amount

        # TODO: Might have to update the witness_templates values to give a
        # correct ordering for which signature should be supplied first.
        # (already did this? Re-check for VerifyScript errors)

        witness_tmp = witness_template.split(" ")
        for (idx, section) in enumerate(witness_tmp):
            if section[0] == "<" and section[-1] == ">":
                section = section[1:-1]
                if section == "user_key":
                    computed_witness.append(parameters["user_key"]["public_key"])
                    continue
                elif section not in script_template.witness_template_map.keys():
                    raise VaultException("Missing key mapping for {}".format(section))

                key_param_name = script_template.witness_template_map[section]
                private_key = parameters[key_param_name]["private_key"]

                if script_template != UserScriptTemplate:
                    # This is a P2WSH transaction.
                    redeem_script = p2wsh_redeem_script
                elif script_template == UserScriptTemplate:
                    # This is a P2WPKH transaction.
                    user_address = P2WPKHBitcoinAddress.from_scriptPubKey(CScript([OP_0, Hash160(parameters["user_key"]["public_key"])]))
                    redeem_script = user_address.to_redeemScript()
                    # P2WPKH redeemScript: OP_DUP OP_HASH160 ....

                sighash = SignatureHash(redeem_script, tx, txin_index, SIGHASH_ALL, amount=amount, sigversion=SIGVERSION_WITNESS_V0)
                signature = private_key.sign(sighash) + bytes([SIGHASH_ALL])
                computed_witness.append(signature)

            else:
                # dunno what to do with this, probably just pass it on really..
                computed_witness.append(section)

        if script_template == UserScriptTemplate:
            # P2WPKH
            # Witness already completed. No redeem_script to append.
            pass
        else:
            # P2WSH
            # Append the p2wsh redeem script.
            computed_witness.append(p2wsh_redeem_script)

        computed_witness = CScript(computed_witness)
        self.witness = computed_witness
        return computed_witness

    def to_dict(self):
        data = {
            "internal_id": str(self.internal_id),
            "transaction_internal_id": str(self.transaction.internal_id),
            "utxo_internal_id": str(self.utxo.internal_id),
            "utxo_name": self.utxo.name,
            "witness_template_selection": self.witness_template_selection,
        }

        return data

    def to_json(self):
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data):
        planned_input = cls()
        planned_input.internal_id = data["internal_id"]
        planned_input.witness_template_selection = data["witness_template_selection"]
        planned_input.is_finalized = True

        # TODO: second pass to add back object references
        planned_input._transaction_internal_id = data["transaction_internal_id"]
        planned_input._utxo_name = data["utxo_name"]
        planned_input._utxo_internal_id = data["utxo_internal_id"]

        return planned_input

    @classmethod
    def from_json(cls, payload):
        data = json.loads(payload)
        return cls.from_dict(data)

    def connect_objects(self, inputs, outputs, transactions):
        """
        Upgrades _transaction_internal_id to self.transaction association.
        """
        for transaction in transactions:
            if transaction.internal_id == self._transaction_internal_id:
                self.transaction = transaction
                break

        for some_utxo in outputs:
            if some_utxo.internal_id == self._utxo_internal_id:
                self.utxo = some_utxo
                break
        else:
            raise Exception("can't find UTXO {}".format(self._utxo_internal_id))

class PlannedTransaction(object):
    __counter__ = 0

    def __init__(self, name=None, enable_cpfp_hook=True):
        self.name = name

        self.inputs = []
        self.output_utxos = []

        if enable_cpfp_hook:
            cpfp_hook_utxo = PlannedUTXO(
                name="CPFP hook",
                transaction=self,
                script_template=CPFPHookScriptTemplate,
                amount=0,
            )
            self.output_utxos.append(cpfp_hook_utxo)

        self.id = copy(self.__class__.__counter__)
        self.__class__.__counter__ += 1
        self.internal_id = uuid.uuid4()

        self.ctv_baked = False

        self.bitcoin_transaction = None
        self.is_finalized = False

    @property
    def input_utxos(self):
        return [some_input.utxo for some_input in self.inputs]

    @property
    def parent_transactions(self):
        _parent_transactions = []
        for some_utxo in self.input_utxos:
            _parent_transactions.append(some_utxo.transaction)
        return _parent_transactions

    @property
    def child_transactions(self):
        _child_transactions = []
        for some_utxo in self.output_utxos:
            _child_transactions.extend(some_utxo.child_transactions)
        return _child_transactions

    @property
    def txid(self):
        # It's important to note that the txid can only be calculated after the
        # rest of the transaction has been finalized, and it is possible to
        # serialize the transaction.
        return self.bitcoin_transaction.GetTxid()

    def serialize(self):
        return self.bitcoin_transaction.serialize()

    def check_inputs_outputs_are_finalized(self):
        """
        Check whether the inputs and outputs are ready.
        """

        for some_input in self.inputs:
            if not some_input.is_finalized:
                logger.warn("input not finalized: {}".format(some_input.name))
                return False

        for some_output in self.output_utxos:
            if not some_output.is_finalized:
                logger.warn("output not finalized: {} {}".format(some_output.name, some_output.internal_id))
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

    def to_dict(self):
        data = {
            "counter": self.id,
            "internal_id": str(self.internal_id),
            "name": self.name,
            "txid": b2lx(self.bitcoin_transaction.GetTxid()),
            "inputs": dict([(idx, some_input.to_dict()) for (idx, some_input) in enumerate(self.inputs)]),
            "outputs": dict([(idx, some_output.to_dict()) for (idx, some_output) in enumerate(self.output_utxos)]),
            "bitcoin_transaction": b2x(self.bitcoin_transaction.serialize()),
        }

        if hasattr(self, "ctv_bitcoin_transaction"):
            logger.info("Transaction name: {}".format(self.name))
            data["ctv_bitcoin_transaction"] = b2x(self.ctv_bitcoin_transaction.serialize())
            data["ctv_bitcoin_transaction_txid"] = b2lx(self.ctv_bitcoin_transaction.GetTxid())

        return data

    def to_json(self):
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data):
        planned_transaction = cls(enable_cpfp_hook=False)
        planned_transaction.output_utxos = [] # remove CPFP hook transaction
        planned_transaction.name = data["name"]
        planned_transaction.internal_id = data["internal_id"]
        planned_transaction.id = data["counter"]
        planned_transaction.bitcoin_transaction = CMutableTransaction.deserialize(x(data["bitcoin_transaction"]))
        planned_transaction.is_finalized = True

        for (idx, some_input) in data["inputs"].items():
            planned_input = PlannedInput.from_dict(some_input)
            planned_transaction.inputs.append(planned_input)

        for (idx, some_output) in data["outputs"].items():
            planned_output = PlannedUTXO.from_dict(some_output)
            planned_transaction.output_utxos.append(planned_output)

        return planned_transaction

    @classmethod
    def from_json(cls, payload):
        data = json.loads(payload)
        return cls.from_dict(data)

    def connect_objects(self, inputs, outputs, transactions):
        """
        Upgrade the inputs and outputs and connect them to the existing
        objects.
        """
        for some_input in self.inputs:
            some_input.connect_objects(inputs, outputs, transactions)

        for some_output in self.output_utxos:
            some_output.connect_objects(inputs, outputs, transactions)

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


def make_burn_transaction(incoming_utxo, parameters=None):
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

    # This function shouldn't be used because it makes the transaction tree
    # planner too slow.
    raise VaultException("Bad code, too slow. Not recommended.")

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
    item_sets = []
    for x in range(0, len(some_set)-1):
        item_sets.append(some_set[x:len(some_set)])
    return item_sets

def make_sharding_transaction(per_shard_amount=1 * COIN, num_shards=100, first_shard_extra_amount=0, incoming_utxo=None, original_num_shards=None, make_sweeps=False, parameters=None):
    """
    Make a new sharding transaction.
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



def sign_transaction_tree(initial_utxo, parameters):
    """
    Walk the planned transaction tree and convert everything into bitcoin
    transactions. Convert the script templates and witness templates into real
    values.
    """

    # Crawl the planned transaction tree and get a list of all planned
    # transactions and all planned UTXOs.
    (planned_utxos, planned_transactions) = initial_utxo.crawl()

    #if len(planned_transactions) < PlannedTransaction.__counter__:
    #    raise VaultException("Counted {} transactions but only found {}".format(PlannedTransaction.__counter__, len(planned_transactions)))
    #
    #if len(planned_utxos) < PlannedUTXO.__counter__:
    #    raise VaultException("Counted {} UTXOs but only found {}".format(PlannedUTXO.__counter__, len(planned_utxos)))


    # also get a list of all inputs
    planned_inputs = set()
    for planned_transaction in planned_transactions:
        planned_inputs.update(planned_transaction.inputs)

    # Sort the objects such that the lowest IDs get processed first.
    planned_utxos = sorted(planned_utxos, key=lambda utxo: utxo.id)
    planned_transactions = sorted(planned_transactions, key=lambda tx: tx.id)

    # Parameterize each PlannedUTXO's script template, based on the given
    # config/parameters. Loop through all of the PlannedUTXOs in any order.
    for planned_utxo in planned_utxos:
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

    logger.info("======== Start")

    # Finalize each transaction by creating a set of bitcoin objects (including
    # a bitcoin transaction) representing the planned transaction.
    for (counter, planned_transaction) in enumerate(planned_transactions):
        logger.info("--------")
        logger.info("current transaction name: {}".format(planned_transaction.name))
        logger.info(f"counter: {counter}")

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
            witness = planned_input.parameterize_witness_template_by_signing(parameters)
            witnesses.append(witness)

        # Now take the list of CScript objects and do the needful.
        ctxinwitnesses = [CTxInWitness(CScriptWitness(list(witness))) for witness in witnesses]
        witness = CTxWitness(ctxinwitnesses)
        planned_transaction.bitcoin_transaction.wit = witness

        planned_transaction.is_finalized = True

        if planned_transaction.name == "initial transaction (from user)":
            # serialization function fails, so just skip
            continue

        serialized_transaction = planned_transaction.serialize()
        logger.info("tx len: {}".format(len(serialized_transaction)))
        logger.info("txid: {}".format(b2lx(planned_transaction.bitcoin_transaction.GetTxid())))
        logger.info("Serialized transaction: {}".format(b2x(serialized_transaction)))

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

class InitialTransaction(object):
    """
    This doesn't have to be a full representation of a planned transaction,
    since this is going to be created and signed by the user's wallet. As long
    as it conforms to the given shape.  (Also there's _vout_override at play).

    The only important thing about this transaction is the txid and the vout
    number for the output. It is otherwise not important. It's not a real
    bitcoin transaction. It was setup and provided by the bitcoin node. The
    vault only assumes that the output is a P2WPKH output.
    """

    def __init__(self, txid=None):
        self.name = "initial transaction (from user)"
        self.txid = txid
        self.is_finalized = True
        self.output_utxos = []
        self.inputs = []
        self.id = -1
        self.internal_id = -1

    @classmethod
    def check_inputs_outputs_are_finalized(cls):
        return True

    @classmethod
    def serialize(self):
        # TODO: could use getrawtransaction over RPC
        return "(not implemented)"

    @property
    def child_transactions(self):
        _child_transactions = []
        for some_utxo in self.output_utxos:
            _child_transactions.extend(some_utxo.child_transactions)
        return _child_transactions

    def to_dict(self):
        data = {
            "counter": self.id,
            "name": self.name,
            "txid": b2lx(self.txid),
            "outputs": dict([(idx, some_output.to_dict()) for (idx, some_output) in enumerate(self.output_utxos)]),
        }
        return data

    @classmethod
    def from_dict(cls, data):
        transaction = cls()
        transaction.name = data["name"]
        transaction.txid = lx(data["txid"])
        transaction.output_utxos = [PlannedUTXO.from_dict(output) for (idx, output) in data["outputs"].items()]
        transaction.is_finalized = True
        return transaction

    def connect_objects(self, inputs, outputs, transactions):
        for some_utxo in self.output_utxos:
            some_utxo.connect_objects(inputs, outputs, transactions)

def to_dict(segwit_utxo):
    """
    Dump all transactions to dictionary.
    """

    # TODO: You know... might make more sense to switch to sqlalchemy. Store
    # everything in a sqlite database.

    # The very first entry should be the planned transaction that will be spent
    # by the user's wallet to commit funds into the vault.
    #transaction_dicts = [segwit_utxo.transaction.to_dict()]
    # ... Turns out that crawl includes the parent transaction too.
    transaction_dicts = []

    (utxos, transactions) = segwit_utxo.crawl()
    for transaction in transactions:
        transaction_data = transaction.to_dict()
        transaction_dicts.append(transaction_data)

    # low-number transactions first
    transaction_dicts = sorted(transaction_dicts, key=lambda tx: tx["counter"])

    return transaction_dicts

def from_dict(transaction_dicts):
    """
    Load all transactions from a dictionary.
    """

    transactions = []
    for (idx, some_transaction) in enumerate(transaction_dicts):
        if idx == 0:
            # Special case. This is the InitialTransaction object.
            transaction = InitialTransaction.from_dict(some_transaction)
        elif idx > 0:
            transaction = PlannedTransaction.from_dict(some_transaction)

        transactions.append(transaction)

    assert transactions[0].output_utxos[0].name == "segwit input coin"

    outputs = []
    inputs = []
    for some_transaction in transactions:
        inputs.extend(some_transaction.inputs)
        outputs.extend(some_transaction.output_utxos)

    # keep only uniques
    inputs = list(set(inputs))
    outputs = list(set(outputs))

    for some_utxo in outputs:
        some_utxo.connect_objects(inputs, outputs, transactions)

    for some_transaction in transactions:
        some_transaction.connect_objects(inputs, outputs, transactions)

    return transactions[0]

def load(transaction_store_filename=TRANSACTION_STORE_FILENAME):
    """
    Read and deserialize a saved planned transaction tree from file.
    """
    transaction_store_fd = open(os.path.join(os.getcwd(), transaction_store_filename), "r")
    content = transaction_store_fd.read()
    data = json.loads(content)
    initial_tx = from_dict(data)
    return initial_tx

def save(some_utxo, filename=TRANSACTION_STORE_FILENAME):
    """
    Serialize the planned transaction tree (starting from some given planned
    output/UTXO) and then dump the serialization into json and write into a
    file.
    """
    output_data = to_dict(some_utxo)
    output_json = json.dumps(output_data, sort_keys=False, indent=4, separators=(',', ': '))

    with open(os.path.join(os.getcwd(), filename), "w") as fd:
        fd.write(output_json)
    logger.info(f"Wrote to {filename}")

def generate_graphviz(some_utxo, parameters):
    """
    Generate a graphviz dotfile, which can be used to create a
    pictorial/graphical representation of the planned transaction tree.

    legend:
        squares: transactions
        circles: outputs because coins are circular
    """
    (utxos, transactions) = some_utxo.crawl()

    diagram = Digraph("output", filename="output.gv")

    diagram.attr("node", shape="square")
    for transaction in transactions:
        diagram.node(str(transaction.internal_id), transaction.name)

    diagram.attr("node", shape="circle")
    for utxo in utxos:
        diagram.node(str(utxo.internal_id), utxo.name)

        diagram.edge(str(utxo.transaction.internal_id), str(utxo.internal_id))

        for child_transaction in utxo.child_transactions:
            diagram.edge(str(utxo.internal_id), str(child_transaction.internal_id))

    if parameters["enable_graphviz_popup"] == True:
        diagram.view()

    return diagram

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
        logger.error("Error: internal_id {} is an invalid next step".format(internal_id))
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

def check_vaultfile_existence(die=True):
    """
    Check whether a "vaultfile" file is present.
    """
    existence = os.path.exists(os.path.join(os.getcwd(), VAULTFILE_FILENAME))
    if existence and die:
        logger.error("Error: vaultfile already exists. Is this an active vault? Don't re-initialize.")
        sys.exit(1)
    else:
        return existence

def make_vaultfile():
    """
    Create a "vaultfile" file that has a file format version for later
    inspection and the possibility of migrations/upgrades in the future.
    """
    filepath = os.path.join(os.getcwd(), VAULTFILE_FILENAME)
    with open(filepath, "w") as fd:
        fd.write(json.dumps({"version": VAULT_FILE_FORMAT_VERSION}))
        fd.write("\n")

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

# pulled from bitcoin/test/functional/test_framework/messages.py get_standard_template_hash
def compute_standard_template_hash(child_transaction, nIn):
    if child_transaction.ctv_baked == False and child_transaction.ctv_bitcoin_transaction == None:
        raise Exception("Error: child transaction is not baked.")

    bitcoin_transaction = child_transaction.ctv_bitcoin_transaction

    nVersion = 2
    nLockTime = 0

    r = b""
    r += struct.pack("<i", nVersion)
    r += struct.pack("<I", nLockTime)
    if any(inp.scriptSig for inp in bitcoin_transaction.vin):
        r += sha256(b"".join(ser_string(inp.scriptSig) for inp in bitcoin_transaction.vin))
    r += struct.pack("<I", len(bitcoin_transaction.vin))
    r += sha256(b"".join(struct.pack("<I", inp.nSequence) for inp in bitcoin_transaction.vin))
    r += struct.pack("<I", len(bitcoin_transaction.vout))
    r += sha256(b"".join(out.serialize() for out in bitcoin_transaction.vout))
    r += struct.pack("<I", nIn)

    return sha256(r)

def construct_ctv_script_fragment_and_witness_fragments(child_transactions, parameters=None):
    """
    Make a script for the OP_CHECKTEMPLATEVERIFY section.
    """

    """
    scriptPubKey: OP_0 sha256(redeemScript)
    redeemScript: <template0> <template1> <template n-1> (n) OP_ROLL OP_ROLL OP_CTV (and then all the OP_DROPs)
    witness: x
    full script when executing:  x <template0> <template1> <template n-1> (n) OP_ROLL OP_ROLL OP_CTV (and then all the OP_DROPs)
    which template gets selected? template x
    """

    # <t1> <tn> <n> OP_ROLL OP_ROLL OP_CTV (some_clever_function(n))* OP_2DROP (another_clever_function(n))*OP_DROP
    # some_clever_function
    # another_clever_function
    # number of 2drops: if n is odd, then do enough 2 drops to leave 1 item on
    # number of 2drops: If N is even, do enough 2 drops to leave 2 items on, then do 1 drop

    # actually it is just N not N+1
    # 0 OP_ROLL is just a NOP
    # 1 is the one one back,

    child_transactions = sorted(child_transactions, key=lambda x: str(x.internal_id))

    some_script = []

    for child_transaction in child_transactions:
        bake_ctv_transaction(child_transaction, skip_inputs=True, parameters=parameters)
        standard_template_hash = compute_standard_template_hash(child_transaction, nIn=0)
        some_script.append(standard_template_hash)

    if len(child_transactions) == 0:
        some_script.append(b"\x00")
    else:
        some_script.append(bitcoin.core._bignum.bn2vch(len(child_transactions)))
    some_script.extend([OP_ROLL, OP_ROLL, OP_NOP4])

    # Now append some OP_DROPs....
    # need to satisfy cleanstack for segwit (only one element left on the stack)
    num_2drops = 0
    num_1drops = 0

    if len(child_transactions) % 2 == 0:
        num_2drops = (len(child_transactions) / 2) - 1
        num_1drops = 1
    elif len(child_transactions) % 2 == 1:
        num_2drops = len(child_transactions) - 1
        num_1drops = 0

    if num_2drops > 0:
        some_script.extend([OP_2DROP] * num_2drops)

    if num_1drops == 1:
        some_script.append(OP_DROP)
    elif num_1drops > 1:
        raise Exception("this shouldn't happen.. more than one 1drop required?")

    witness_fragments = {}
    for child_transaction in child_transactions:
        some_index = child_transactions.index(child_transaction)
        if some_index == 0:
            wit_frag = int(some_index).to_bytes(1, byteorder="big")
        elif some_index > 0:
            wit_frag = bitcoin.core._bignum.bn2vch(some_index)
        witness_fragments[str(child_transaction.internal_id)] = [wit_frag]
        #witness_fragments[str(child_transaction.internal_id)] = [some_index]
        #witness_fragments[str(child_transaction.internal_id)] = [] #[child_transactions.index(child_transaction)]

    return (some_script, witness_fragments)

def bake_output(some_planned_utxo, parameters=None):
    utxo = some_planned_utxo

    # Note that the CTV fragment of the script isn't the only part. There might
    # be some other branches, like for hot wallet spending or something.

    # Which ones require multiple branches?
    #   ColdStorageScriptTemplate (branch: cold wallet key spend)
    #   ShardScriptTemplate (branch: hot wallet key spend)
    # which don't?
    #   BasicPresignedScriptTemplate

    # For the script templates that have branching:
    #   scriptPubKey: OP_0 <H(redeemScript)>
    #   redeemScript: OP_IF {ctv_fragment} OP_ELSE <pubkey> OP_CHECKSIGVERIFY <timelock> OP_CSV OP_ENDIF
    #   witness: 5 true <redeemScript>

    script_template_class = utxo.script_template

    has_extra_branch = None
    if script_template_class in [ColdStorageScriptTemplate, ShardScriptTemplate]:
        has_extra_branch = True
    else:
        has_extra_branch = False

    (ctv_script_fragment, witness_fragments) = construct_ctv_script_fragment_and_witness_fragments(utxo.child_transactions, parameters=parameters)

    # By convention, the key spends are in the first part of the OP_IF block.
    if has_extra_branch:
        for (some_key, witness_fragment) in witness_fragments.items():
            #witness_fragment.append(OP_0) # OP_FALSE
            # TODO: Why can't we just use OP_0 ?
            witness_fragment.append(b"\x00")

    # Note that we're not going to construct any witness_fragments for the key
    # spend scenario. It is up to the user to create a valid script on their
    # own for that situation. But it's pretty simple, it's just:
    #   OP_1 <sig1> <sig2> etc..

    # Make the appropriate script template. Parameterize the script template.

    coldkey1 = parameters["cold_key1"]["public_key"]
    coldkey2 = parameters["cold_key2"]["public_key"]
    hotkey1 = parameters["hot_wallet_key"]["public_key"]

    # TODO: use a variable for the OP_CSV value. Use the
    # ScriptTemplate.relative_timelocks.

    script = None
    if script_template_class == ColdStorageScriptTemplate:
        script = [OP_IF, coldkey1, OP_CHECKSIGVERIFY, coldkey2, OP_CHECKSIGVERIFY, bitcoin.core._bignum.bn2vch(144*2), OP_NOP3, OP_ELSE] + ctv_script_fragment + [OP_ENDIF]
    elif script_template_class == ShardScriptTemplate:
        script = [OP_IF, hotkey1, OP_CHECKSIGVERIFY, bitcoin.core._bignum.bn2vch(144*2), OP_NOP3, OP_ELSE] + ctv_script_fragment + [OP_ENDIF]
    elif script_template_class == BasicPresignedScriptTemplate:
        script = ctv_script_fragment
    else:
        # TODO: For these kinds (CPFP, burn, ...), just implement a basic
        # witness on those transactions. The witness is just the number of the
        # transaction in the list (it's based on ordering).

        utxo.ctv_bypass = True

        if utxo.name == "vault initial UTXO":
            raise Exception("Should have been processed earlier...")

        return

    # Store this data on the UTXO object. It gets used later.
    utxo.ctv_script = CScript(script)
    utxo.ctv_witness_fragments = witness_fragments
    utxo.ctv_p2wsh_redeem_script = utxo.ctv_script
    utxo.ctv_scriptpubkey = CScript([OP_0, sha256(bytes(utxo.ctv_p2wsh_redeem_script))])

    # Copy over the witnesses to the PlannedInput objects.
    for child_transaction in utxo.child_transactions:
        appropriate_witness = witness_fragments[str(child_transaction.internal_id)]

        # Push the bytes for the redeemScript into the witness.
        appropriate_witness.append(utxo.ctv_p2wsh_redeem_script)

        specific_input = None
        for some_input in child_transaction.inputs:
            if some_input.utxo == utxo:
                specific_input = some_input
                break
        else:
            raise Exception("Couldn't find a relevant input. Why is this considered a child transaction...?")

        specific_input.ctv_witness = CScript(appropriate_witness)
        specific_input.ctv_p2wsh_redeem_script = script

def bake_ctv_transaction(some_transaction, skip_inputs=False, parameters=None):
    """
    Create a CTV transaction for the planned transaction tree.

    This is done in two passes: bake_output (looped) and bake_ctv_transaction
    (also looped). The bake_ctv_transaction function is called on an ordered
    list of all transactions, starting with the "first" transaction of all the
    planned transactions. For each transaction, all of the transaction outputs
    get "baked": they are assigned a txid based on the hash of the parent
    transaction (the txid) which commits to a certain standard template hash.
    However, that standard template hash can only be determined by rendering
    the rest of the pre-planned transaction tree.

    Note that bake_output calls bake_ctv_transaction somewhere in another
    subsequent function.

    Hence the two passes are about (1) crawling the whole tree and generating
    standard template hashes (starting with the deepest elements in the tree
    and working backwards), and then (2) crawling the whole tree and assigning
    txids to the inputs. This is possible because OP_CHECKTEMPLATEVERIFY does
    not include the hash of the inputs in the standard template hash, otherwise
    there would be a recursive hash commitment dependency loop error.
    """

    if hasattr(some_transaction, "ctv_baked") and some_transaction.ctv_baked == True:
        return some_transaction.ctv_bitcoin_transaction

    # Bake each UTXO.
    for utxo in some_transaction.output_utxos:
        bake_output(utxo, parameters=parameters)

    # Construct python-bitcoinlib bitcoin transactions and attach them to the
    # PlannedTransaction objects, once all the UTXOs are ready.

    logger.info("Baking a transaction with name {}".format(some_transaction.name))

    bitcoin_inputs = []
    if not skip_inputs:
        for some_input in some_transaction.inputs:

            # When computing the standard template hash for a child transaction,
            # the child transaction needs to be only "partially" baked. It doesn't
            # need to have the inputs yet.

            if some_input.utxo.transaction.__class__ == InitialTransaction or some_input.transaction.name in ["Burn some UTXO", ]:
                txid = some_input.utxo.transaction.txid
            else:
                logger.info("The parent transaction name is: {}".format(some_input.utxo.transaction.name))
                logger.info("Name of the UTXO being spent: {}".format(some_input.utxo.name))
                logger.info("Current transaction name: {}".format(some_input.transaction.name))

                # This shouldn't happen... We should be able to bake transactions
                # in a certain order and be done with this.
                #if not hasattr(some_input.utxo.transaction, "ctv_bitcoin_transaction"):
                #    bake_ctv_transaction(some_input.utxo.transaction, parameters=parameters)
                # TODO: this creates an infinite loop....

                txid = some_input.utxo.transaction.ctv_bitcoin_transaction.GetTxid()

            vout = some_input.utxo.transaction.output_utxos.index(some_input.utxo)

            relative_timelock = None
            if some_input.utxo.script_template.__class__ in [ColdStorageScriptTemplate, ShardScriptTemplate]:
                relative_timelock = 144

            if relative_timelock:
                bitcoin_input = CTxIn(COutPoint(txid, vout), nSequence=relative_timelock)
            else:
                bitcoin_input = CTxIn(COutPoint(txid, vout))

            bitcoin_inputs.append(bitcoin_input)

    bitcoin_outputs = []
    for some_output in some_transaction.output_utxos:
        amount = some_output.amount

        # For certain UTXOs, just use the previous UTXO script templates,
        # instead of the CTV version. (utxo.ctv_bypass == True)
        if hasattr(some_output, "ctv_bypass"):
            scriptpubkey = some_output.scriptpubkey
        else:
            scriptpubkey = some_output.ctv_scriptpubkey

        bitcoin_output = CTxOut(amount, scriptpubkey)
        bitcoin_outputs.append(bitcoin_output)

    bitcoin_transaction = CMutableTransaction(bitcoin_inputs, bitcoin_outputs, nLockTime=0, nVersion=2, witness=None)

    if not skip_inputs:
        witnesses = []
        for some_input in some_transaction.inputs:
            logger.info("Transaction name: {}".format(some_transaction.name))
            logger.info("Spending UTXO with name: {}".format(some_input.utxo.name))
            logger.info("Parent transaction name: {}".format(some_input.utxo.transaction.name))

            if some_transaction.name in ["Burn some UTXO", "Funding commitment transaction"]:
                witness = some_input.witness
            else:
                witness = some_input.ctv_witness

            #logger.info("Appending witness: {}".format(list(witness)))
            witnesses.append(witness)

        ctxinwitnesses = [CTxInWitness(CScriptWitness(list(witness))) for witness in witnesses]
        witness = CTxWitness(ctxinwitnesses)
        bitcoin_transaction.wit = witness
    else:
        bitcoin_transaction.wit = CTxWitness()

    some_transaction.ctv_bitcoin_transaction = bitcoin_transaction

    if not skip_inputs:
        some_transaction.ctv_baked = True

    return bitcoin_transaction

def make_planned_transaction_tree_using_bip119_OP_CHECKTEMPLATEVERIFY(initial_tx, parameters=None):
    """
    Mutate the planned transaction tree in place and convert it to a planned
    transaction tree that uses OP_CHECKTEMPLATEVERIFY.
    """
    assert len(initial_tx.output_utxos[0].child_transactions) == 1
    vault_commitment_transaction = initial_tx.output_utxos[0].child_transactions[0]

    initial_utxo = initial_tx.output_utxos[0]
    (planned_utxos, planned_transactions) = initial_utxo.crawl()

    #planned_transactions = reversed(sorted(planned_transactions, key=lambda tx: tx.id))
    planned_transactions = sorted(planned_transactions, key=lambda tx: tx.id)

    #bake_output(initial_utxo, parameters=parameters)

    for planned_transaction in planned_transactions:
        bake_ctv_transaction(planned_transaction, parameters=parameters)

    # The top level transaction should be fine now.
    return bake_ctv_transaction(vault_commitment_transaction, parameters=parameters)

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
    logger.info("Rendering to text...")
    output = segwit_utxo.to_text()
    filename = TEXT_RENDERING_FILENAME
    fd = open(os.path.join(os.getcwd(), filename), "w")
    fd.write(output)
    fd.close()
    logger.info(f"Wrote to {filename}")

    # stats
    logger.info("*** Stats and numbers")
    logger.info(f"{PlannedUTXO.__counter__} UTXOs, {PlannedTransaction.__counter__} transactions")

    sign_transaction_tree(segwit_utxo, parameters)

    save(segwit_utxo)

    # TODO: Delete the ephemeral keys.

    # (graph generation can wait until after key deletion)
    if parameters["enable_graphviz"] == True:
        generate_graphviz(segwit_utxo, parameters)

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
