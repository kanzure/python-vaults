"""
Classes for representing planned transaction trees, transactions, inputs, and
outputs.
"""

import uuid
from copy import copy

from bitcoin.core import CMutableTransaction
from bitcoin.core.script import CScript, OP_0, SignatureHash, SIGHASH_ALL, SIGVERSION_WITNESS_V0, Hash160

from vaults.helpers.formatting import b2x, x, b2lx, lx
from vaults.loggingconfig import logger
from vaults.rpc import get_bitcoin_rpc_connection
from vaults.exceptions import VaultException

from vaults.models.script_templates import (
    ScriptTemplate,
    CPFPHookScriptTemplate,
    UserScriptTemplate,
)

class PlannedUTXO(object):
    """
    Represents a planned transaction output (txout), and connects to the rest
    of the tree by linking to the current transaction and any possible child
    transactions.
    """

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
        """
        Identify what the vout value should be for this particular output coin
        on a transaction. Check the output's index by looking at the
        transaction that created this output. This is useful for populating
        inputs (txid, vout).
        """
        if self._vout_override == None:
            return self.transaction.output_utxos.index(self)
        else:
            return self._vout_override

    def crawl(self):
        """
        Return a tuple that contains two items: a list of UTXOs and a list of
        transactions. Crawl the entire planned transaction tree starting from
        "self", and return a list of all the UTXOs and all the transactions.
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
        """
        Make a text representation of this UTXO suitable for human reading.
        """
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
        """
        Convert the current coin to a formatted dictionary object.
        """
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
        """
        Convenience method: format self as a dictionary, and then produce json.
        """
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data):
        """
        Instantiate a planned output from a dictionary.
        """
        planned_utxo = cls()
        planned_utxo.internal_id = data["internal_id"]
        planned_utxo.id = data["counter"]
        planned_utxo.name = data["name"]
        planned_utxo.is_finalized = True

        script_template_lookup = dict([(klass.__name__, klass) for klass in ScriptTemplate.__subclasses__()])
        planned_utxo.script_template = script_template_lookup[data["script_template_name"]]

        planned_utxo.amount = data["amount"]
        planned_utxo.timelock_multiplier = data["timelock_multiplier"]

        planned_utxo._transaction_internal_id = data["transaction_internal_id"]
        planned_utxo._child_transaction_internal_ids = data["child_transaction_internal_ids"]

        if "_vout_override" in data.keys():
            planned_utxo._vout_override = data["_vout_override"]

        return planned_utxo

    @classmethod
    def from_json(cls, payload):
        """
        Convenience method: parse json and then instantiate a planned output
        from that dictionary data.
        """
        data = json.loads(payload)
        return cls.from_dict(data)

    def reconnect_deserialized_objects(self, inputs, outputs, transactions):
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
            raise VaultException("Failed to break")

class PlannedInput(object):
    """
    Represents a planned input to a planned bitcoin transaction, and links to
    the coin that the input is consuming.
    """

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
                    raise VaultException("Timelock {} exceeds max timelock {}".format(relative_timelock_value, 0xfff))

                # Note that timelock_multiplier should appear again in another
                # place, when inserting the timelocks into the script itself.

    def to_dict(self):
        """
        Convert the current planned input to a formatted dictionary.
        """
        data = {
            "internal_id": str(self.internal_id),
            "transaction_internal_id": str(self.transaction.internal_id),
            "utxo_internal_id": str(self.utxo.internal_id),
            "utxo_name": self.utxo.name,
            "witness_template_selection": self.witness_template_selection,
        }

        return data

    def to_json(self):
        """
        Convenience method: convert the current planned input to a formatted
        dictionary, and then convert to json format.
        """
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data):
        """
        Instantiate a planned input from formatted dictionary data.
        """
        planned_input = cls()
        planned_input.internal_id = data["internal_id"]
        planned_input.witness_template_selection = data["witness_template_selection"]
        planned_input.is_finalized = True

        planned_input._transaction_internal_id = data["transaction_internal_id"]
        planned_input._utxo_name = data["utxo_name"]
        planned_input._utxo_internal_id = data["utxo_internal_id"]

        return planned_input

    @classmethod
    def from_json(cls, payload):
        """
        Convenience method: instantiate a planned input from json.
        """
        data = json.loads(payload)
        return cls.from_dict(data)

    def reconnect_deserialized_objects(self, inputs, outputs, transactions):
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
            raise VaultException("can't find UTXO {}".format(self._utxo_internal_id))

class PlannedTransaction(object):
    """
    Represents a planned transaction. Has a list of planned inputs and a list
    of planned outputs. This transaction can also become pre-signed, even if
    there is no plan to presently broadcast this pre-signed transaction.

    The planned transaction links to a number of possible child transactions,
    each of which are linked through the different output coins on the planned
    transaction.
    """

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
        """
        A list of planned UTXOs corresponding to each of the inputs on this
        planned transaction.
        """
        return [some_input.utxo for some_input in self.inputs]

    @property
    def parent_transactions(self):
        """
        A list of all the transactions that create each of the input coins
        consumed by this planned transaction.
        """
        _parent_transactions = []
        for some_utxo in self.input_utxos:
            _parent_transactions.append(some_utxo.transaction)
        return _parent_transactions

    @property
    def child_transactions(self):
        """
        A list of all the different possible child transactions hanging off of
        each of the UTXOs created by this planned transaction.
        """
        _child_transactions = []
        for some_utxo in self.output_utxos:
            _child_transactions.extend(some_utxo.child_transactions)
        return _child_transactions

    @property
    def txid(self):
        """
        Get a byte representation of the txid of the planned transaction. Note
        that this is only helpful once the transaction is "finished".
        """
        # It's important to note that the txid can only be calculated after the
        # rest of the transaction has been finalized, and it is possible to
        # serialize the transaction.
        return self.bitcoin_transaction.GetTxid()

    def serialize(self):
        """
        Convenience function: serialize the bitcoin transaction to bytes.
        """
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
        """
        Make a text representation of this planned transaction suitable for
        human reading.
        """
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
        """
        Convert the current planned transaction to a formatted dictionary.
        """
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
        """
        Convenience method: serialize this planned transaction as json.
        """
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data):
        """
        Instantiate a planned transaction using data from a formatted
        dictionary.
        """
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
        """
        Convenience method: instantiate a planned transaction from json.
        """
        data = json.loads(payload)
        return cls.from_dict(data)

    def reconnect_deserialized_objects(self, inputs, outputs, transactions):
        """
        Upgrade the inputs and outputs and connect them to the existing
        objects.
        """
        for some_input in self.inputs:
            some_input.reconnect_deserialized_objects(inputs, outputs, transactions)

        for some_output in self.output_utxos:
            some_output.reconnect_deserialized_objects(inputs, outputs, transactions)

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
        # The transaction was already created by the user's wallet, so just
        # retrieve it from the wallet.
        connection = get_bitcoin_rpc_connection()
        return connection.getrawtransaction(self.txid)

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

    def reconnect_deserialized_objects(self, inputs, outputs, transactions):
        for some_utxo in self.output_utxos:
            some_utxo.reconnect_deserialized_objects(inputs, outputs, transactions)
