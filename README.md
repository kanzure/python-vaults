# Sharding Vaults

This project provides some tools and a prototype for bitcoin vaults based
around the concept of sharding and pre-signed transactions.

# WARNING

This is not production-ready code. Do not use this on bitcoin mainnet or any other mainnet.

# Background (summary)

A **vault** is an on-chain construct that keeps coins locked up until someone
opens the vault. Upon opening the vault, the user has the option of sending
coins back into a new vault configured with identical keys, sweeping the coins
to a cold storage wallet or more-deep cold storage vault, or allowing the coins
to exit the vault and be used by some hot wallet.

**Sharding** refers to a policy recommendation of splitting a bitcoin UTXO into
multiple new UTXOs that can each become un-vaulted only on a specific schedule.
The purpose of sharding is to minimize the total amount lost due to theft. By
sampling the hot wallet with only one sharded UTXO at a time, the user can
immediately push the remaining UTXOs to cold storage the moment a theft on the
hot wallet is detected. Without this feature, a user might keep 100% of their
funds in a single UTXO which can be stolen by that same kind of thief.

Additional background:

<https://www.coindesk.com/the-vault-is-back-bitcoin-coder-to-revive-plan-to-shield-wallets-from-theft>

<https://bitcoinmagazine.com/articles/revamped-idea-bitcoin-vaults-may-end-exchange-hacks-good>

<https://lists.linuxfoundation.org/pipermail/bitcoin-dev/2019-August/017229.html>

<https://lists.linuxfoundation.org/pipermail/bitcoin-dev/2019-August/017231.html>

# Installation

```
# clone the repository
git clone ...

# setup a new virtualenv to avoid system-wide installation
python3 -m venv venv/

# enter into the virtualenv
source ./venv/bin/activate

# install all python requirements
pip3 install -r requirements.txt

# Use install to copy the code into the virtualenv's python modules directory,
# or "develop" to use symlinks such that updates to the code propagate without
# requiring re-installation.
python3 setup.py install
```

# What's in here?

This repository contains an experimental prototype of Bitcoin vaults using
pre-signed transactions.

All of the interesting work is in [experiment.py](experiment.py) for now.

It works by connecting to bitcoind using RPC, mining some BTC to a specific
address, and then begins planning an entire tree of pre-signed transactions
that implement the vault. After tree planning, the tree is signed.

For now it is recommended to capture stdout to file, like:

```
python3 experiment.py > output.txt
```

Then scroll to the line that starts with "Start" and those will be the signed
transactions ready for broadcast.

----

Internal details... let's see.. Well, everything begins in `__main__` at the
end. The two magic functions are `setup_vault` and `sign_transaction_tree`.

`PlannedInput`, `PlannedOutput`, and `PlannedTransaction` are custom classes
that represent the transaction tree. The real bitcoin transactions are
assembled in place hanging off of these objects. `child_outputs` is for the
outputs on the current transaction, while `child_transactions` are a list of
possible child transactions. Obviously, because double spending is forbidden,
only one of those child transactions can make it into the blockchain.

`ScriptTemplate` and its descendents are how UTXOs can describe themselves.
Each UTXO in the planned transaction tree can use one of a limited number of
scripts that were used to design the transaction tree. `ScriptTemplate` is used
to derive the `scriptPubKey` value and the witness necessary to spend that
UTXO. The witness is obviously applied to the input that spends the UTXO.

`PlannedInput.parameterize_witness_template_by_signing` is responsible for
parsing a witness template, signing, and producing a valid witness. This is
based off of one of those `ScriptTemplate` classes that each UTXO picks: the
input has to have a witness that satisfies that UTXO's script template and
script.

Run the `AbstractPlanningTests` tests with `python3 -m unittest experiment.py`
I think? They don't test much, right now....


# Usage (not working yet)

This package installs the `vault` command, which is an interface for working
with the vault library based on vault files stored in the current working
directory. The vault subcommands are as follows:

```
vault init (or vault clone)
vault info
vault lock
vault sync
vault unlock single
vault sync
vault unlock all
vault sync
vault rotate
vault burn
```

**vault init** turns the current working directory into a new vault with new
parameters.

**vault info** gives information about the current status of the vault.

**vault lock** takes a user-given UTXO and locks the UTXO and its amount into a
new vault with the parameters defined by the current working directory.

**vault unlock single** gives a single shard UTXO and makes it available to the
first layer hot wallet. The remaining amount is put back into the vault in a
new vault UTXO.

**vault sync** synchronizes the vault's internal database with the bitcoin
blockchain by communicating with a bitcoind node over RPC.

**vault unlock many** starts the pre-determined stipend. This creates many
sharded UTXOs.

**vault rotate** sends all of the UTXOs and coins to the cold storage layer.

**vault burn** broadcasts transactions that will burn coins. These transactions
are very dangerous and it is important to think carefully about where they are
stored. They are nearly as dangerous as a private key, and although the
possibilities are constrained compared to a thief stealing a private key, the
end result is the same (loss of funds).

# bitcoin.conf

bitcoind configuration must include:

```
regtest=1

# Data directory: where should this regtest blockchain live?
#datadir=/tmp/bitcoin/regtest/

txindex=1

debug=1
logtimestamps=1
printtoconsole=1

server=1
listen=1
maxconnections=500
noconnec=1

# Override fallback fee estimation.
# (perhaps it can be disabled with =0?)
fallbackfee=0.0001

# To allow for creating zero-value CPFP hook outputs.
acceptnonstdtxn=1

# To allow for zero-fee transactions.
minrelaytxfee=0

# To mine zero-fee transactions (CPFP not implemented yet)
blockmintxfee=0
```

Run with `bitcoind -regtest` if this is your `~/.bitcoin/bitcoin.conf` file,
otherwise you will have to run with `-conf=/path/to/bitcoin.conf` each time.

```
bitcoin-cli -regtest getblockchaininfo
```

# Follow-up

* Check status of segwit example: <https://github.com/petertodd/python-bitcoinlib/pull/227>



