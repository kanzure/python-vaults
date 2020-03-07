"""
This file describes an unused test. Could be deleted.
"""

import os

from vaults.loggingconfig import logger

# TODO: create a python library for bitcoin's test_framework
try:

    if os.environ.get("BITCOIN_CORE_PATH", None) == None:
        raise ImportError("Can't find Bitcoin Core source code")

    import sys
    sys.path.insert(0, os.path.join(os.environ["BITCOIN_CORE_PATH"], "/test/functional"))

    from test_framework.test_framework import BitcoinTestFramework
    from test_framework.util import connect_nodes
except ImportError:
    logger.error("Unable to import BitcoinTestFramework")

    class BitcoinTestFramework(object):
        pass

class VaultsTest(BitcoinTestFramework):
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


