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
        private_key1 = ...
        private_key2 = ...

        # TODO: construct the final 2-of-2 P2WSH multisig script. This script
        # should only be spendable by one of the previously-created pre-signed
        # transactions.
        input_txid = segwit_utxo["txid"]
        input_txid_vout = segwit_utxo["vout"]
        output_script = # TODO: 2-of-2 multisig, spendable by the two private keys
        (txid1, transaction1) = createrawtransaction(inputs, outputs)

        # Make a pre-signed transaction that spends the 2-of-2 PWSH utxo txid,
        # and creates 100 UTXOs. Delete the ephemeral key after signing.
        input_txid2 = txid1
        input_txid2_vout = 0
        outputs2 = ... # TODO: make 100 outputs, each with a similar script
        (txid2, transaction2) = createrawtransaction(inputs2, outputs2)
        # TODO: sign transaction2, using the two private keys


        # For each UTXO, make: (1) a push to cold storage transaction, (2) a push to new identical vault (using same keys).


        # TODO: sign the tree of transactions (in any order)

        # delete the private keys
        del private_key1
        del private_key2

        # Now sign the transaction that starts the whole thing.
        self.nodes[0].signrawtransaction(transaction1)

# start a new bitcoind instance, in regtest mode
# mine 110 blocks
# send 500 BTC into a segwit address (P2WSH)
# mine 10 blocks
#
# Now that we have segwit outputs, proceed with the protocol.
#
# Construct a 2-of-2 P2WSH script for the pre-signed transaction tree. All of
# the deleted keys should be at least 2-of-2.
#
# After signing all of those transactions (including the one spending the
# 2-of-2 root P2SH), delete the key.
#
# Then move the segwit coins into that top-level P2WSH scriptpubkey.







