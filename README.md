# Bitcoin vaults

This project provides a prototype for bitcoin vaults based around the concept
of sharding and pre-signed transactions. The advantage of sharding into many
UTXOs with different relative timelocks is that it gives the user an
opportunity to observe on-chain thefts and react to them, without losing 100%
of the funds.

See a
**[visualization](https://diyhpl.us/~bryan/irc/graphviz-transaction-tree.png)**
of the planned transaction tree:

<a href="https://diyhpl.us/~bryan/irc/graphviz-transaction-tree.png"><img src="https://diyhpl.us/~bryan/irc/graphviz-transaction-tree.png" width=510 height=401></a>

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
[signing.py](vaults/signing.py) file. In practical usage, `vault init` calls
the entrypoint [commands/initialize.py](vaults/commands/initialize.py) which
calls the subsequent functions.

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
```

**vault init** turns the current working directory into a new vault with new
parameters. It creates all of the pre-signed transaction trees and also creates
the signatures. Note that `vault init` does not broadcast the transaction
putting the coins into the vault-- that is the user's responsibility using the
other commands, as are any other broadcast actions- again using the other
available commands.

**vault info** gives information about the current status of the vault.

**vault broadcast** transmits a pre-signed bitcoin transaction to the bitcoin
network.

# Filesystem

The `vault init` should be run after creating a new directory via the `mkdir`
command. Inside of the directory, run `vault init` and it will check for the
presence of a `vaultfile` file. The purpose of the `vaultfile` is to place a
marker on the filesystem indicating that the folder already contains a vault
and that the program should not overwrite it. Inside the file is some
versioning information for future upgrade and file format version management
reasons.

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

For regtest testing, some setup is required (and this changes based on the
secret key, and also based on the amount that is being inserted into the vault
as defined in the initialization function):

```
bitcoin-cli -regtest generatetoaddress 100 bcrt1q08alc0e5ua69scxhvyma568nvguqccrvah6ml0
bitcoin-cli -regtest sendtoaddress bcrt1q08alc0e5ua69scxhvyma568nvguqccrvah6ml0 5
```

# Private key

Pre-signed vaults are reliant on secure key deletion of a private key.

In python-vaults, the prototype has two ways to provide a private key-- one way
is the default private key is constructed using the "correct horse battery
staple" passphrase, and the other way is to pass
`--private-key=$regtestprivatekey` to the `vault init` command.

In the prototype, all of the keys- including for cold storage- are equal to the
given private key. In the future, this needs to be updated and configured to
include real values for the user's cold storage system and the other required
keys.

The default private key is not secure. Instead of passing an override private
key, another option (in the future) would be to implement something that uses
system entropy to generate keys. However, the keys for cold storage and the hot
wallet should be from other machines.

# License

BSD

# Is this ready for production?

No, this software is not ready for production. There are a number of things
that need to be done before this could be used in production. This list is a
good starting point, but it is not exhaustive.

**Private keys**: The way that private keys are handled should be improved.
Secure key deletion is currently not happening. Private keys could be generated
from some entropy- or from dice rolls- but this is also currently not
occurring.

**Multi-client protocol**: Right now the prototype assumes control of two
private keys for the pre-signed transaction tree. However, in practice, there
should be multiple clients that pass data off to each other.

**Extensive testing**: There should be substantial more unit testing of all the
various functions, and a test framework to simulate many thousands of different
scenarios with different initial configurations or parameters. Also, these
tests should all be performed on not just the regtest network but also signet
and testnet, and only then moving on to small-scale mainnet tests.

**Improved initialization**: The current workflow for working with Bitcoin Core
wallets is a little weird-- based on using RPC against a bitcoin wallet with
bitcoin stored on the wallet. Instead, the initial transaction should be
constructed another way, perhaps with some steps that the user has to manually
run to feed in a txid, vout, etc.

**User guides**: User documentation should be written for all procedures and
operations, including information about how to operate airgapped devices and
how to store the key material.

**Watchtower**: A watchtower implementation is required. This also needs to be
tested and setup for production use.

**Rust implementation**: Using python in production may not be a good idea.
Evaluate which segments of the source code should be written in rust, and then
build a rust implementation. Also convert all appropriate tests.

**Code review**: This work should be extensively reviewed for best practices
with a deep knowledge of bitcoin software development.

The burn transactions are pretty dangerous. Users should store those in either
their cold storage system or in a similar secure offline system.

# See also

* [bip119 OP\_CHECKTEMPLATEVERIFY workshop transcript](https://diyhpl.us/wiki/transcripts/ctv-bip-review-workshop/)

## Other pre-signed vault implementations

* [python-vaults](https://github.com/kanzure/python-vaults) (you are here)
* <https://github.com/fmr-llc/Vault-mbed>
* <https://github.com/JSwambo/bitcoin-vault> (see also the [dynamic fee allocation](https://github.com/JSwambo/bitcoin-vault/pull/2) pull request)
* kloaec's implementation [re-vault](https://github.com/re-vault/re-vault) --  see a [comparison video](https://www.youtube.com/watch?v=kmb2UDcbi50&t=21m38s)

There are also two related upcoming manuscripts presently nearing final draft
status. (As of 2020-03-28)


