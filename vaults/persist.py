"""
Persistence functions - save, load, convert to and from dictionaries for saving
and loading.
"""

import os
import json

from vaults.loggingconfig import logger
from vaults.config import TRANSACTION_STORE_FILENAME

from vaults.models.plans import (
    InitialTransaction,
    PlannedTransaction,
)

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

    # Second pass to add back object-to-object references. Maybe I should have
    # just used an ORM tool....
    for some_utxo in outputs:
        some_utxo.connect_objects(inputs, outputs, transactions)

    for some_transaction in transactions:
        some_transaction.connect_objects(inputs, outputs, transactions)

    return transactions[0]

def load(path=None, transaction_store_filename=TRANSACTION_STORE_FILENAME):
    """
    Read and deserialize a saved planned transaction tree from file.
    """
    if path == None:
        path = os.path.join(os.getcwd(), transaction_store_filename)
    transaction_store_fd = open(path, "r")
    content = transaction_store_fd.read()
    data = json.loads(content)
    initial_tx = from_dict(data)
    transaction_store_fd.close()
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
