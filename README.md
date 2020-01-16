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

# Usage

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


