"""
Transaction tree planning
"""

import os

from bitcoin.core import COIN

from vaults.models.script_templates import (
    ScriptTemplate,
    UserScriptTemplate,
    ColdStorageScriptTemplate,
    BurnUnspendableScriptTemplate,
    BasicPresignedScriptTemplate,
    ShardScriptTemplate,
    CPFPHookScriptTemplate,
)

from vaults.models.plans import (
    PlannedUTXO,
    PlannedInput,
    PlannedTransaction,
    InitialTransaction,
)

def make_burn_transaction(incoming_utxo, parameters=None):
    """
    Extend the planned transaction tree by making a "burn" transaction that
    spends the coin and making it unspendable in the future forevermore.
    """

    if not parameters["enable_burn_transactions"] == True:
        return None

    burn_transaction = PlannedTransaction(name="Burn some UTXO")
    incoming_input = PlannedInput(
        utxo=incoming_utxo,
        witness_template_selection="presigned",
        transaction=burn_transaction,
    )
    burn_transaction.inputs.append(incoming_input)

    # TODO: Should the amount be burned to miner fee (which seems sort of
    # dangerous- incents attacks by miner-thiefs) or just perpetually unspendable.
    burn_utxo_amount = incoming_utxo.amount # unspendable
    #burn_utxo_amount = 0 # burn to miner fee

    burn_utxo = PlannedUTXO(
        name="burned UTXO",
        transaction=burn_transaction,
        script_template=BurnUnspendableScriptTemplate,
        amount=burn_utxo_amount,
    )
    burn_transaction.output_utxos.append(burn_utxo)
    incoming_utxo.child_transactions.append(burn_transaction)
    return burn_transaction

def make_push_to_cold_storage_transaction(incoming_utxo, parameters=None):
    """
    Extend the planned transaction tree with a transaction that pushes a coin
    into the cold storage layer (defined by ColdStorageScriptTemplate).

    Also make a planned transaction that can burn the cold storage UTXO as
    another possible exit from the vault.
    """

    # name was (phase 2): "push-to-cold-storage-from-sharded" But this is
    # inaccurate because only some of them are from a sharded UTXO. Others will
    # be the re-vault transaction.
    # name was: "Push (sharded?) UTXO to cold storage wallet"
    push_transaction = PlannedTransaction(name="push-to-cold-storage")
    planned_input = PlannedInput(
        utxo=incoming_utxo,
        witness_template_selection="presigned",
        transaction=push_transaction,
    )
    push_transaction.inputs.append(planned_input)

    cold_storage_utxo_amount = incoming_utxo.amount
    cold_storage_utxo = PlannedUTXO(
        name="cold storage UTXO",
        transaction=push_transaction,
        script_template=ColdStorageScriptTemplate,
        amount=cold_storage_utxo_amount,
    )
    push_transaction.output_utxos.append(cold_storage_utxo)

    # The purpose of the relative timelock before the cold storage keys are
    # able to spend is so that not all cold storage UTXOs can be spent at once.
    # The user is thus given an option of burning the other UTXOs if they think
    # that an adversary is about to steal the remaining UTXOs after observing
    # the theft of a single UTXO.

    # Make a possible transaction: burn/donate the cold storage UTXO.
    burn_transaction = make_burn_transaction(cold_storage_utxo, parameters=parameters)

    incoming_utxo.child_transactions.append(push_transaction)
    return push_transaction

def make_sweep_to_cold_storage_transaction(incoming_utxos, parameters=None):
    """
    Create a transaction that sweeps some input coins into the cold storage layer.
    """

    # name was: "Sweep UTXOs to cold storage wallet"
    # phase 2 name was: Sharded UTXO sweep transaction
    push_transaction = PlannedTransaction(name="Sharded UTXO sweep transaction")

    for incoming_utxo in incoming_utxos:
        # Inputs
        planned_input = PlannedInput(
            utxo=incoming_utxo,
            witness_template_selection="presigned",
            transaction=push_transaction,
        )
        push_transaction.inputs.append(planned_input)

        # Outputs
        amount = incoming_utxo.amount
        cold_storage_utxo = PlannedUTXO(
            name="cold storage UTXO",
            transaction=push_transaction,
            script_template=ColdStorageScriptTemplate,
            amount=amount,
        )
        push_transaction.output_utxos.append(cold_storage_utxo)
        burn_transaction = make_burn_transaction(cold_storage_utxo, parameters=parameters)

    return push_transaction

def make_telescoping_subsets(some_set):
    """
    Creates a list of lists where each list at the second level is a subset of
    the function's input each time minus one additional element.

    The original purpose of this function was to produce a list of different
    UTXO sets. These could then be used to construct alternative-possible sweep
    transactions, such as sweep transactions for each of the scenarios where
    the first UTXO is spent or not spent, the first and second UTXO are spent
    or not spent, etc. Ultimately the sweep transactions are not enabled by
    default in this prototype, because they combinatorially explode the planned
    transaction tree size.
    """
    item_sets = []
    for x in range(0, len(some_set)-1):
        item_sets.append(some_set[x:len(some_set)])
    return item_sets

def make_sharding_transaction(per_shard_amount=1 * COIN, num_shards=100, first_shard_extra_amount=0, incoming_utxo=None, original_num_shards=None, make_sweeps=False, parameters=None):
    """
    Make a new sharding transaction. A sharding transaction is one that takes
    some coin and splits the coin into many UTXOs each with a fraction of the
    original amount. Each coin will have a script that includes a monotonically
    increasing relative timelock so that each UTXO becomes spendable
    one-at-a-time and a watchtower can later take some action if more than one
    of these UTXOs is spendable at any given time.
    """

    if num_shards < original_num_shards:
        partial ="(partial) "
    elif num_shards == original_num_shards:
        partial = ""

    sharding_transaction = PlannedTransaction(name=f"Vault {partial}stipend start transaction.")
    incoming_utxo.child_transactions.append(sharding_transaction)

    planned_input = PlannedInput(
        utxo=incoming_utxo,
        witness_template_selection="presigned",
        transaction=sharding_transaction,
    )
    sharding_transaction.inputs.append(planned_input)

    shard_utxos = []
    for shard_id in range(0, num_shards):
        amount = per_shard_amount
        if shard_id == 0 and first_shard_extra_amount != None:
            amount += first_shard_extra_amount

        sharded_utxo_name = "shard fragment UTXO {shard_id}/{num_shards}".format(
            shard_id = shard_id + 1,
            num_shards=num_shards,
        )

        # Note: can't re-vault from this point. Must pass through the cold
        # wallet or the hot wallet before it can get back into a vault.
        sharded_utxo = PlannedUTXO(
            name=sharded_utxo_name,
            transaction=sharding_transaction,
            script_template=ShardScriptTemplate,
            amount=amount,
            timelock_multiplier=shard_id,
        )
        shard_utxos.append(sharded_utxo)
        sharding_transaction.output_utxos.append(sharded_utxo)

        make_push_to_cold_storage_transaction(incoming_utxo=sharded_utxo, parameters=parameters)

    # Make a variety of push-to-cold-storage (sweep) transactions that
    # each take 2 or more UTXOs. Note that the UTXOs get spent in order, so
    # this fortunately limits the total number of transactions to generate.
    #
    # Without these sweep transactions, the user would have to individually
    # broadcast up to 100 transactions that each individually move each UTXO
    # into cold storage. By aggregating it into these sweep transactions, they
    # don't need to do that anymore.
    #
    # Note: this makes the transaction tree planner pretty slow. It's
    # unreasonably slow. By comparison, having 100 separate transactions that
    # need to be CPFPed would be easier to deal with.
    if make_sweeps == True:
        subsets = make_telescoping_subsets(shard_utxos)
        # Iteration over all the possible subsets substantially and negatively
        # impacts the runtime of the program.
        #sweep_transactions = []
        for some_subset in subsets:
            sweep_transaction = make_sweep_to_cold_storage_transaction(some_subset, parameters=parameters)
            #sweep_transactions.append(sweep_transaction)

            for utxo in some_subset:
                utxo.child_transactions.append(sweep_transaction)

    return sharding_transaction

# The vault UTXO can have 1/100th spent at a time, the rest goes back into a
# vault. So you can either do the stipend-spend, or the one-at-a-time spend.
# So if the user knows they only want a small amount, they use the one-time
# spend. If they know they want more, then they can use the stipend (or migrate
# out of the vault by first broadcasting the stipend setup transaction).
def make_one_shard_possible_spend(incoming_utxo, per_shard_amount, num_shards, original_num_shards=None, first_shard_extra_amount=None, parameters=None):
    """
    Make a possible transaction for the vault UTXO that has two possibilities
    hanging off of it: one to spend a single sharded UTXO (either to the cold
    storage layer, or to the hot wallet), and then a second vault UTXO that has
    the remaining funds minus that one sharded UTXO, and then the typical vault
    possibilities hanging off of that.
    """
    # Spend initial vault UTXO into two UTXOs- one for the hot wallet/push to
    # cold storage, one for re-vaulting the remaining amount- and then all the
    # appropriate child transactions too. The re-vaulted path should not split
    # up the UTXOs into 100 pieces, but rather the remaining number of pieces
    # based on the amount already spent into the hot wallet.
    #
    # This path is another route of possible transactions, as a
    # possible-sibling to the vault stipend initiation transaction.

    # phase 2 name: There was no equivalent name for this transaction discussed
    # in phase 2. This transaction was added in phase 3.
    vault_spend_one_shard_transaction = PlannedTransaction(name="Vault transaction: spend one shard, re-vault the remaining shards")
    incoming_utxo.child_transactions.append(vault_spend_one_shard_transaction)

    planned_input = PlannedInput(
        utxo=incoming_utxo,
        witness_template_selection="presigned",
        transaction=vault_spend_one_shard_transaction,
    )
    vault_spend_one_shard_transaction.inputs.append(planned_input)

    # Next, add two UTXOs to vault_spend_one_shard transaction.

    amount = per_shard_amount
    if first_shard_extra_amount != None:
        amount += first_shard_extra_amount

    # phase 2 name: k% sharded UTXO
    exiting_utxo = PlannedUTXO(
        name="shard fragment UTXO",
        transaction=vault_spend_one_shard_transaction,
        script_template=ShardScriptTemplate,
        amount=amount,
    )
    vault_spend_one_shard_transaction.output_utxos.append(exiting_utxo)

    # For the exit UTXO, it should also be posisble to send that UTXO to cold
    # storage instead of letting the multisig hot wallet control it.
    make_push_to_cold_storage_transaction(exiting_utxo, parameters=parameters)
    # The hot wallet spend transaction is not represented here because t's not
    # a pre-signed transaction. It can be created at a later time, by the hot
    # wallet keys.

    if num_shards == 1:
        return
    else:
        # TODO: should this be num_shards or (num_shards - 1) ?
        remaining_amount = (num_shards - 1) * per_shard_amount

        # Second UTXO attached to vault_spend_one_shard_transaction.
        # phase 2 name: funding/commitment UTXO, kind of... But this wasn't
        # really in the original phase 2 proposal.
        revault_utxo = PlannedUTXO(
            name="vault UTXO",
            transaction=vault_spend_one_shard_transaction,
            script_template=BasicPresignedScriptTemplate,
            amount=remaining_amount,
        )
        vault_spend_one_shard_transaction.output_utxos.append(revault_utxo)

        # The vault UTXO can also be spent directly to cold storage.
        make_push_to_cold_storage_transaction(revault_utxo, parameters=parameters)

        # The re-vault UTXO can be sharded into "100" pieces (but not really 100..
        # it should be 100 minus the depth).
        make_sharding_transaction(
            per_shard_amount=per_shard_amount,
            num_shards=num_shards - 1,
            incoming_utxo=revault_utxo,
            original_num_shards=original_num_shards,
            first_shard_extra_amount=None,
            parameters=parameters,
        )

        # The re-vault UTXO can also be spent using the one-shard possible spend
        # method.
        make_one_shard_possible_spend(
            incoming_utxo=revault_utxo,
            per_shard_amount=per_shard_amount,
            num_shards=num_shards - 1,
            original_num_shards=original_num_shards,
            first_shard_extra_amount=None,
            parameters=parameters,
        )

def setup_vault(segwit_utxo, parameters):
    """
    Generate a pre-signed transaction tree using the segwit_utxo as the coins
    to be inserted into the vault. The pre-signed transaction tree is
    constructed in this function, but not signed. Signing occurs in another
    independent function.

    The movement of the given coins (from segwit_utxo) into the vault should
    only be signed once the user has looked at and signed-off on the entire
    planned transaction tree. This sign-off should be predicated on secure key
    deletion of the keys used to create the pre-signed transactions in the
    planned transaction tree.
    """

    # name was: Vault locking transaction
    # phase 2 name: Funding commitment transaction
    vault_locking_transaction = PlannedTransaction(name="Funding commitment transaction")
    segwit_utxo.child_transactions.append(vault_locking_transaction)

    planned_input = PlannedInput(
        utxo=segwit_utxo,
        witness_template_selection="user",
        transaction=vault_locking_transaction,
    )
    vault_locking_transaction.inputs.append(planned_input)

    vault_initial_utxo_amount = segwit_utxo.amount
    vault_initial_utxo = PlannedUTXO(
        name="vault initial UTXO",
        transaction=vault_locking_transaction,
        script_template=BasicPresignedScriptTemplate,
        amount=vault_initial_utxo_amount,
    )
    vault_locking_transaction.output_utxos.append(vault_initial_utxo)

    # Optional transaction: Push the whole amount to cold storage.
    make_push_to_cold_storage_transaction(incoming_utxo=vault_initial_utxo, parameters=parameters)

    # The number of shards that we made at this level of the transaction tree.
    # Inside the make_one_shard_possible_spend function, this amount will be
    # decremented before it is used to create the next sharding/stipend-setup
    # transaction.
    num_shards = parameters["num_shards"]

    amount_per_shard = int(vault_initial_utxo.amount / num_shards)
    first_shard_extra_amount = vault_initial_utxo.amount - (int(vault_initial_utxo.amount/num_shards)*num_shards)
    assert (amount_per_shard * num_shards) + first_shard_extra_amount == vault_initial_utxo.amount

    # Optional transaction: split the UTXO up into 100 shards, when it's time
    # to start spending the coins.
    # Make a transaction that sets up 100 UTXOs (with appropriate relative
    # timelocks).
    make_sharding_transaction(
        per_shard_amount=amount_per_shard,
        num_shards=num_shards,
        first_shard_extra_amount=first_shard_extra_amount,
        incoming_utxo=vault_initial_utxo,
        original_num_shards=num_shards,
        parameters=parameters,
    )

    # Another optional transaction
    # Make a transaction that lets the user spend one shard, but re-vaults
    # everything else.
    make_one_shard_possible_spend(
        incoming_utxo=vault_initial_utxo,
        per_shard_amount=amount_per_shard,
        num_shards=num_shards,
        first_shard_extra_amount=first_shard_extra_amount,
        original_num_shards=num_shards,
        parameters=parameters,
    )

    return vault_initial_utxo

def safety_check(initial_tx=None):
    """
    Check that the planned transaction tree conforms to some specific rules.
    """

    if initial_tx == None:
        initial_tx = load()

    initial_utxo = initial_tx.output_utxos[0]

    (planned_utxos, planned_transactions) = initial_utxo.crawl()

    # Every transaction should have at least one output, including the burner
    # transactions (unless they are burning to miner fee...).
    counter = 0
    for some_transaction in planned_transactions:
        counter += 1
        if len(some_transaction.output_utxos) == 0:
            raise VaultException("Transaction {} has no outputs".format(str(some_transaction.internal_id)))

        # The sum of the input amounts should equal the sum of the output
        # amounts.
        input_amounts = sum([some_input.utxo.amount for some_input in some_transaction.inputs])
        output_amounts = sum([some_output.amount for some_output in some_transaction.output_utxos])
        if input_amounts != output_amounts and some_transaction.id != -1:
            raise VaultException("Transaction {} takes {} and spends {}, not equal".format(str(some_transaction.internal_id), input_amounts, output_amounts))

        for some_output in some_transaction.output_utxos:
            if some_output.name in ["CPFP hook", "burned UTXO"]:
                continue
            elif len(some_output.child_transactions) == 0:
                raise VaultException("UTXO {} has no child transactions".format(str(some_output.internal_id)))

        # TODO: There should be other rule checks as well, possibly including
        # things like "does this transaction have the correct scripts and
        # correct outputs" and "does this UTXO have any scripts at all".

    if counter < 1 or counter < len(planned_transactions):
        raise VaultException("Length of the list of planned transactions is too low.")

    return True


