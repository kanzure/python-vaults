"""
Run the unit tests with:
    python3 -m unittest experiment.py

"""

import uuid
import unittest
import hashlib
from copy import copy
import json

# pip3 install graphviz
from graphviz import Digraph

import bitcoin
from vaults.helpers.formatting import b2x, x, b2lx, lx
from vaults.exceptions import VaultException

from bitcoin.wallet import CBitcoinSecret

from bitcoin import SelectParams
from bitcoin.core import COIN, CTxOut, COutPoint, CTxIn, CMutableTransaction, CTxWitness, CTxInWitness, CScriptWitness
from bitcoin.core.script import CScript, OP_0, SignatureHash, SIGHASH_ALL, SIGVERSION_WITNESS_V0, Hash160
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
                print("input not finalized: ", some_input.name)
                return False

        for some_output in self.output_utxos:
            if not some_output.is_finalized:
                print("output not finalized: ", some_output.name, some_output.internal_id)
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

        print("UTXO name: ", planned_utxo.name)
        print("final script: {}".format(script))
        #print("p2wsh_redeem_script: ", b2x(planned_utxo.p2wsh_redeem_script))
        #print("p2wsh_redeem_script: ", CScript(planned_utxo.p2wsh_redeem_script))

    print("======== Start")

    # Finalize each transaction by creating a set of bitcoin objects (including
    # a bitcoin transaction) representing the planned transaction.
    for (counter, planned_transaction) in enumerate(planned_transactions):
        print("--------")
        print("current transaction name: ", planned_transaction.name)
        print("counter: ", counter)

        for planned_input in planned_transaction.inputs:
            print("parent transaction name: ", planned_input.utxo.transaction.name)

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

        if len(bitcoin_inputs) == 0 and planned_transaction.name != "fake transaction (from user)":
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

        if planned_transaction.name == "fake transaction (from user)":
            # serialization function fails, so just skip
            continue

        serialized_transaction = planned_transaction.serialize()
        print("tx len: ", len(serialized_transaction))
        print("txid: ", b2lx(planned_transaction.bitcoin_transaction.GetTxid()))
        print("Serialized transaction: ", b2x(serialized_transaction))

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

class FakeTransaction(object):
    """
    Nothing too "fake" about this... But it doesn't have to be a full
    representation of a planned transaction, since this is going to be created
    and signed by the user's wallet. As long as it conforms to the given shape.
    (Also there's _vout_override at play).
    """

    def __init__(self, txid=None):
        self.name = "fake transaction (from user)"
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
        transaction.txid = data["txid"]
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
            # Special case. This is the FakeTransaction object.
            transaction = FakeTransaction.from_dict(some_transaction)
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

def load(transaction_store_filename="output-auto.txt"):
    transaction_store_fd = open(transaction_store_filename, "r")
    content = transaction_store_fd.read()
    data = json.loads(content)
    initial_tx = from_dict(data)
    return initial_tx

def generate_graphviz(some_utxo, parameters):
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
    if connection == None:
        connection = get_bitcoin_rpc_connection()

    if not check_blockchain_has_transaction(current_transaction.txid):
        return current_transaction

    possible_transactions = get_next_possible_transactions_by_walking_tree(current_transaction, connection=connection)
    #print("possible_transactions: ", [b2lx(possible_tx.txid) for possible_tx in possible_transactions])
    assert all([len(possible_tx.parent_transactions) == 1 for possible_tx in possible_transactions])
    parents = [possible_tx.parent_transactions[0] for possible_tx in possible_transactions]
    assert len(set(parents)) == 1
    parent = parents[0]
    current_transaction = parent

    return {"current": current_transaction, "next": possible_transactions}

def render_planned_output(planned_output, depth=0):
    prefix = "\t" * depth

    output_text  = prefix + "Output:\n"
    output_text += prefix + "\tname: {}\n".format(planned_output.name)
    output_text += prefix + "\tinternal id: {}\n".format(planned_output.internal_id)

    return output_text

def render_planned_transaction(planned_transaction, depth=0):
    prefix = "\t" * depth

    output_text  = prefix + "Transaction:\n"
    output_text += prefix + "\tname: {}\n".format(planned_transaction.name)
    output_text += prefix + "\tinternal id: {}\n".format(planned_transaction.internal_id)
    output_text += prefix + "\ttxid: {}\n".format(b2lx(planned_transaction.bitcoin_transaction.GetTxid()))
    output_text += prefix + "\tnum inputs: {}\n".format(len(planned_transaction.inputs))
    output_text += prefix + "\tnum outputs: {}\n".format(len(planned_transaction.output_utxos))

    output_text += "\n"
    output_text += prefix + "\tOutputs:\n"

    for output in planned_transaction.output_utxos:
        output_text += render_planned_output(output, depth=depth+2)

    return output_text

def get_info(transaction_store_filename="output-auto.txt", connection=None):
    initial_tx = load(transaction_store_filename=transaction_store_filename)

    latest_info = get_current_confirmed_transaction(initial_tx)
    current_tx = latest_info["current"]

    output_text = "\n\nLatest transaction:\n"
    output_text += render_planned_transaction(current_tx, depth=1)

    output_text += "\n\nPossible transactions:\n\n"

    for some_tx in latest_info["next"]:
        output_text += render_planned_transaction(some_tx, depth=1)
        output_text += "\n"

    return output_text

if __name__ == "__main__":

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
        "enable_graphviz_popup": True,
        "amount": amount,
        "unspendable_key_1": CPubKey(x("0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")),
    }

    for some_name in parameter_names:
        private_key = some_private_keys.pop()
        public_key = private_key.pub
        parameters[some_name] = {"private_key": private_key, "public_key": public_key}

    # TODO: might be without b2x?
    parameters["user_key_hash160"] = b2x(Hash160(parameters["user_key"]["public_key"]))

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

    fake_tx_txid = lx(utxo_details["txid"])
    fake_tx = FakeTransaction(txid=fake_tx_txid)

    segwit_utxo = PlannedUTXO(
        name="segwit input coin",
        transaction=fake_tx,
        script_template=UserScriptTemplate,
        amount=amount,
    )
    segwit_utxo._vout_override = utxo_details["vout"]
    fake_tx.output_utxos = [segwit_utxo] # for establishing vout

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

    #sign_transaction_tree(vault_initial_utxo, parameters)
    sign_transaction_tree(segwit_utxo, parameters)

    # TODO: Persist the pre-signed transactions to persistant storage system.

    output_data = to_dict(segwit_utxo)
    output_json = json.dumps(output_data, sort_keys=False, indent=4, separators=(',', ': '))

    filename = "output-auto.txt"
    with open(filename, "w") as fd:
        fd.write(output_json)
    print(f"Wrote to {filename}!")

    # TODO: Delete the ephemeral keys.


    generate_graphviz(segwit_utxo, parameters)
