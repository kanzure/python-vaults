# Bitcoin vaults

This project provides a prototype for bitcoin vaults based around the concept
of sharding and pre-signed transactions. The advantage of sharding into many
UTXOs with different relative timelocks is that it gives the user an
opportunity to observe on-chain thefts and react to them, without losing 100%
of the funds.

See a
**[visualization](https://diyhpl.us/~bryan/irc/graphviz-transaction-tree.png)**
of the planned transaction tree.

# WARNING

This is not production-ready code. Do not use this on bitcoin mainnet or any
other mainnet. In fact, the private keys are static and hard coded into the
prototype. Don't use this right now. It's only been used for about ~50 vaults,
and before any real-world usage there should be many thousands of tested
vaults.

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

The main entry point is in [initialize.py](vaults/commands/initialize.py) in
the `commands/` directory.

It works by connecting to bitcoind using RPC, mining some BTC to a specific
address, and then begins planning an entire tree of pre-signed transactions
that implement the vault. After tree planning, the tree is signed.

To run the vault program do something like:

```
mkdir -p /tmp/vaults/001/
cd /tmp/vaults/001/

vault init
```

This will produce a few files. The interesting one is `log.txt` and
`transaction-store.json` which has the list of transactions.

In `log.txt` or `text-rendering.txt` scroll to the line that starts with
"Start" and those will be the signed transactions ready for broadcast.

Modules:

* [vaults](vaults/) - primary python source code
* [vaults.commands](vaults/commands/) - functions for command line interface
  (see also [cli.py](vaults/cli.py)).
* [vaults.models](vaults/models/) - script templates and transaction tree
  modeling
* [vaults.tests](vaults/tests/) - basic tests, nothing special

Source code:

* [models/plans.py](vaults/models/plans.py) - transaction tree models
* [models/script_templates.py](vaults/models/script_templates.py) - script templates
  defining scriptpubkeys and witness templates
* [planner.py](vaults/planner.py) - transaction tree generator
* [signing.py](vaults/signing.py) - sign the planned transaction tree
* [state.py](vaults/state.py) - tools to check vault state on blockchain
* [bip119_ctv.py](vaults/bip119_ctv.py) - bip119 OP_CHECKTEMPLATEVERIFY
  implementation
* [persist.py](vaults/persist.py) - save/load data
* [graphics.py](vaults/graphics.py) - graphviz visualization for the planned
  transaction tree
* [rpc.py](vaults/rpc.py) - bitcoind RPC
* [cli.py](vaults/cli.py) - command line interface, main wrapper
* [config.py](vaults/config.py) - static configuration, not interesting
* [loggingconfig.py](vaults/loggingconfig.py) - python logging configuration
* [exceptions.py](vaults/exceptions.py) - vault-related exception definitions
* [utils.py](vaults/utils.py) - miscellaneous functions (see also
  [helpers](vaults/helpers/))
* [vaultfile.py](vaults/vaultfile.py) - safety check for current working
  directory
* [loggingserver.py](vaults/loggingserver.py) - a sketch of what a logging
  server might look like
* [watchtower.py](vaults/watchtower.py) - a sketch of what a watchtower might
  look like

# Internal details


The two main entrypoints of interest are `setup_vault` in the
[planner.py](vaults/planner.py) file and `sign_transaction_tree` in the
[signing.py](vaults/signing.py) file.

The project can only be run if `bitcoind -regtest` is running in the background.
It currently looks for `~/bitcoin/bitcoin.conf` to figure out the bitcoin RPC
parameters. (TODO: Spin up regtest nodes automatically, especially for tests.)

`PlannedInput`, `PlannedOutput`, and `PlannedTransaction` are custom classes
that represent the transaction tree, as defined in the
[models](vaults/models/). The real bitcoin transactions are assembled in place
hanging off of these objects. `output_utxos` is for the outputs on the current
transaction, while `child_transactions` on a `PlannedUTXO` are a list of
possible child transactions. Obviously, because double spending is forbidden,
only one of those child transactions can make it into the blockchain.

`ScriptTemplate` and its [descendents](vaults/models/script_templates.py) are
how UTXOs can describe themselves.  Each UTXO in the planned transaction tree
can use one of a limited number of scripts that were used to design the
transaction tree. `ScriptTemplate` is used to derive the `scriptPubKey` value
and the witness necessary to spend that UTXO. The witness is obviously applied
to the input that spends the UTXO.

`PlannedInput.parameterize_witness_template_by_signing` is responsible for
parsing a witness template, signing, and producing a valid witness. This is
based off of one of those `ScriptTemplate` classes that each UTXO picks: the
input has to have a witness that satisfies that UTXO's script template and
script.

After running `vault init`, to load the serialized data, do the following:

```
from vaults.experiment import *
initial_planned_transaction = load()
```

But it is probably simpler to do a one-liner like:

```
from experiment import *; initial_tx = from_dict(json.loads(open("output-auto.txt", "r").read()));

initial_tx.name
initial_tx.output_utxos
initial_tx.output_utxos[0].name
initial_tx.output_utxos[0].child_transactions
name = initial_tx.output_utxos[0].child_transactions[0].name
assert name == "Vault locking transaction"
```

# Usage

This package installs the `vault` command, which is an interface for working
with the vault library based on vault files stored in the current working
directory. The vault subcommands are as follows:

```
vault init
vault info
vault broadcast

# The following don't work yet.
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

**vault broadcast** transmits a pre-signed bitcoin transaction to the bitcoin
network.

The following commands don't quite work yet:

**vault lock** takes a user-given UTXO and locks the UTXO and its amount into a
new vault with the parameters defined by the current working directory.

**vault unlock single** gives a single shard UTXO and makes it available to the
first layer hot wallet. The remaining amount is put back into the vault in a
new vault UTXO.

**vault sync** synchronizes the vault's internal database with the bitcoin
blockchain by communicating with a bitcoind node over RPC. (*This may be
unnecessary now that bitcoind is responsible for syncing.*)

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

# Testing

Run the tests like this:

```
python3 -m unittest
```

# Other pre-signed vault implementations

* [python-vaults](https://github.com/kanzure/python-vaults) (you are here)
* <https://github.com/fmr-llc/Vault-mbed>
* <https://github.com/JSwambo/bitcoin-vault>
* kloaec's implementation?


