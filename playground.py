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

"""

sw UTXO -> 2-of-2 vault UTXO -> (100 UTXOs)
                                             -> OR(2-of-2 vault UTXO, cold storage UTXO, hot wallet UTXO)

send_utxo_to_2of2_vault_utxo(input_utxo, splitting=True):

    if splitting:
        utxo_value = value / 100
        utxo_count = 100
    else:
        utxo_value = value
        utxo_count = 1

    for utxo_id in range(0, utxo_count):

        output = "spendable by key-sending-to-2-of-2-vault-UTXO, key-spending-to-cold-storage-UTXO, or hot-wallet-key"

        send_utxo_to_2of2_vault_utxo(......

        outputs.append(output)

"""


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

class Transaction(object):
    def __init__(self, name=None):
        self.name = name

        self.input_utxos = []
        self.output_utxos = []

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

class UTXO(object):
    def __init__(self, name=None, transaction=None, script_description_text="OP_TRUE"):
        self.name = name
        self.script_description_text = script_description_text

        # This is the transaction that created this UTXO.
        self.transaction = transaction

        # These are the transactions that reference this UTXO.
        self.child_transactions = []


segwit_coin = UTXO(name="segwit input coin", transaction=None, script_description_text="spendable by user single-sig")

vault_locking_transaction = Transaction(name="Vault locking transaction")
vault_locking_transaction.input_utxos = [segwit_coin]

vault_initial_utxo = UTXO(name="vault initial UTXO", transaction=vault_locking_transaction, script_description_text="spendable by 2-of-2 ephemeral multisig")
vault_locking_transaction.output_utxos = [vault_initial_utxo]
# TODO: vault_initial_utxo can also be spent by another transaction, which pushes the whole amount to cold storage.

vault_stipend_start_transaction = Transaction(name="Vault stipend start transaction")
vault_stipend_start_transaction.input_utxos = [vault_initial_utxo]
vault_stipend_start_transaction.output_utxos = [] # TODO: 100 UTXOs....




