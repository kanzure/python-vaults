from vaults.helpers.formatting import b2x, x, b2lx, lx

import bitcoin.rpc

def get_bitcoin_rpc_connection():
    """
    Establish an RPC connection.
    """
    # by default uses ~/.bitcoin/bitcoin.conf so be careful.
    btcproxy = bitcoin.rpc.Proxy()

    # sanity check
    assert btcproxy._call("getblockchaininfo")["chain"] == "regtest"

    return btcproxy

# unused?
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


