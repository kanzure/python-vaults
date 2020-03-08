import struct

import bitcoin

from bitcoin.core import (
    CTxOut,
    CTxIn,
    COutPoint,
    CMutableTransaction,
    CTxWitness,
    CTxInWitness,
    CScriptWitness,
)

from bitcoin.core.script import (
    CScript,
    OP_0,
    OP_ROLL,
    OP_NOP3,
    OP_NOP4,
    OP_DROP,
    OP_2DROP,
    OP_IF,
    OP_ELSE,
    OP_CHECKSIGVERIFY,
    OP_ENDIF,
)

from vaults.utils import sha256, ser_string
from vaults.loggingconfig import logger

from vaults.script_templates import (
    ColdStorageScriptTemplate,
    ShardScriptTemplate,
    BasicPresignedScriptTemplate,
)

def compute_standard_template_hash(child_transaction, nIn):
    """
    Compute the bip119 OP_CHECKTEMPLATEVERIFY StandardTemplateHash value for
    the given transaction.

    pulled from bitcoin/test/functional/test_framework/messages.py get_standard_template_hash
    """
    if child_transaction.ctv_baked == False and child_transaction.ctv_bitcoin_transaction == None:
        raise Exception("Error: child transaction is not baked.")

    bitcoin_transaction = child_transaction.ctv_bitcoin_transaction

    nVersion = 2
    nLockTime = 0

    r = b""
    r += struct.pack("<i", nVersion)
    r += struct.pack("<I", nLockTime)
    if any(inp.scriptSig for inp in bitcoin_transaction.vin):
        r += sha256(b"".join(ser_string(inp.scriptSig) for inp in bitcoin_transaction.vin))
    r += struct.pack("<I", len(bitcoin_transaction.vin))
    r += sha256(b"".join(struct.pack("<I", inp.nSequence) for inp in bitcoin_transaction.vin))
    r += struct.pack("<I", len(bitcoin_transaction.vout))
    r += sha256(b"".join(out.serialize() for out in bitcoin_transaction.vout))
    r += struct.pack("<I", nIn)

    return sha256(r)

def construct_ctv_script_fragment_and_witness_fragments(child_transactions, parameters=None):
    """
    Make a script for the OP_CHECKTEMPLATEVERIFY section.
    """

    """
    scriptPubKey: OP_0 sha256(redeemScript)
    redeemScript: <template0> <template1> <template n-1> (n) OP_ROLL OP_ROLL OP_CTV (and then all the OP_DROPs)
    witness: x
    full script when executing:  x <template0> <template1> <template n-1> (n) OP_ROLL OP_ROLL OP_CTV (and then all the OP_DROPs)
    which template gets selected? template x
    """

    # <t1> <tn> <n> OP_ROLL OP_ROLL OP_CTV (some_clever_function(n))* OP_2DROP (another_clever_function(n))*OP_DROP
    # some_clever_function
    # another_clever_function
    # number of 2drops: if n is odd, then do enough 2 drops to leave 1 item on
    # number of 2drops: If N is even, do enough 2 drops to leave 2 items on, then do 1 drop

    # actually it is just N not N+1
    # 0 OP_ROLL is just a NOP
    # 1 is the one one back,

    child_transactions = sorted(child_transactions, key=lambda x: str(x.internal_id))

    some_script = []

    for child_transaction in child_transactions:
        # Bake each of the child transactions: that is, compute standard
        # template hashes on all of the children of the current child. Set
        # skip_inputs=True so that the inputs get skipped-- when processing
        # inputs, that function looks at
        # some_input.utxo.transaction.ctv_bitcoin_transaction which doesn't
        # exist yet. Note that the standard template hash doesn't include
        # inputs (so the txids referenced by inputs don't modify the standard
        # template hash result).
        bake_ctv_transaction(child_transaction, skip_inputs=True, parameters=parameters)

        # The transaction is now ready to be convered into a standard template
        # hash for bip119.
        standard_template_hash = compute_standard_template_hash(child_transaction, nIn=0)

        some_script.append(standard_template_hash)

    if len(child_transactions) == 0:
        some_script.append(b"\x00")
    else:
        some_script.append(bitcoin.core._bignum.bn2vch(len(child_transactions)))
    some_script.extend([OP_ROLL, OP_ROLL, OP_NOP4])

    # Now append some OP_DROPs....
    # need to satisfy cleanstack for segwit (only one element left on the stack)
    num_2drops = 0
    num_1drops = 0

    if len(child_transactions) % 2 == 0:
        num_2drops = (len(child_transactions) / 2) - 1
        num_1drops = 1
    elif len(child_transactions) % 2 == 1:
        num_2drops = len(child_transactions) - 1
        num_1drops = 0

    if num_2drops > 0:
        some_script.extend([OP_2DROP] * num_2drops)

    if num_1drops == 1:
        some_script.append(OP_DROP)
    elif num_1drops > 1:
        raise Exception("this shouldn't happen.. more than one 1drop required?")

    witness_fragments = {}
    for child_transaction in child_transactions:
        some_index = child_transactions.index(child_transaction)
        if some_index == 0:
            wit_frag = int(some_index).to_bytes(1, byteorder="big")
        elif some_index > 0:
            wit_frag = bitcoin.core._bignum.bn2vch(some_index)
        witness_fragments[str(child_transaction.internal_id)] = [wit_frag]
        #witness_fragments[str(child_transaction.internal_id)] = [some_index]
        #witness_fragments[str(child_transaction.internal_id)] = [] #[child_transactions.index(child_transaction)]

    return (some_script, witness_fragments)

def bake_ctv_output(some_planned_utxo, parameters=None):
    """
    The bake_ctv_output function computes the witness that an input spending
    said output would need to provide. Since these transactions use P2WSH, this
    witness can only be computed once the redeemScript is calculated, which
    requires calculating the standard template hash-- which requires knowing
    what the rest of the planned transaction tree looks like. Thus,
    bake_ctv_output will recursively travel down the tree until it is able to
    collect certainty and begin computing the recursively-referential standard
    template hashes.

    The standard template hash can only be determined by performing these same
    calculations on the rest of the pre-planned transaction tree.

    Note that bake_ctv_output calls bake_ctv_transaction somewhere in another
    subsequent function.
    """

    utxo = some_planned_utxo

    # Note that the CTV fragment of the script isn't the only part. There might
    # be some other branches, like for hot wallet spending or something.

    # Which ones require multiple branches?
    #   ColdStorageScriptTemplate (branch: cold wallet key spend)
    #   ShardScriptTemplate (branch: hot wallet key spend)
    # which don't?
    #   BasicPresignedScriptTemplate

    # For the script templates that have branching:
    #   scriptPubKey: OP_0 <H(redeemScript)>
    #   redeemScript: OP_IF {ctv_fragment} OP_ELSE <pubkey> OP_CHECKSIGVERIFY <timelock> OP_CSV OP_ENDIF
    #   witness: 5 true <redeemScript>

    script_template_class = utxo.script_template

    has_extra_branch = None
    if script_template_class in [ColdStorageScriptTemplate, ShardScriptTemplate]:
        has_extra_branch = True
    else:
        has_extra_branch = False

    # Recurse down the tree and calculate the ScriptTemplateHash values for
    # OP_CHECKTEMPLATEVERIFY.
    (ctv_script_fragment, witness_fragments) = construct_ctv_script_fragment_and_witness_fragments(utxo.child_transactions, parameters=parameters)

    # The remaining work of the current function is to setup the inputs that
    # spend the current output, and make sure they have the appropriate witness
    # values (as determined by the output's script template and output's
    # script).

    # By convention, the key spends are in the first part of the OP_IF block.
    if has_extra_branch:
        for (some_key, witness_fragment) in witness_fragments.items():
            #witness_fragment.append(OP_0) # OP_FALSE
            # TODO: Why can't we just use OP_0 ?
            witness_fragment.append(b"\x00")

    # Note that we're not going to construct any witness_fragments for the key
    # spend scenario. It is up to the user to create a valid witness script on
    # their own for that situation. But it's pretty simple, it's just:
    #   OP_1 <sig1> <sig2> etc..

    # Make the appropriate script template. Parameterize the script template.

    coldkey1 = parameters["cold_key1"]["public_key"]
    coldkey2 = parameters["cold_key2"]["public_key"]
    hotkey1 = parameters["hot_wallet_key"]["public_key"]

    # TODO: use a variable for the OP_CSV value. Use the
    # ScriptTemplate.relative_timelocks.

    script = None
    if script_template_class == ColdStorageScriptTemplate:
        script = [OP_IF, coldkey1, OP_CHECKSIGVERIFY, coldkey2, OP_CHECKSIGVERIFY, bitcoin.core._bignum.bn2vch(144*2), OP_NOP3, OP_ELSE] + ctv_script_fragment + [OP_ENDIF]
    elif script_template_class == ShardScriptTemplate:
        script = [OP_IF, hotkey1, OP_CHECKSIGVERIFY, bitcoin.core._bignum.bn2vch(144*2), OP_NOP3, OP_ELSE] + ctv_script_fragment + [OP_ENDIF]
    elif script_template_class == BasicPresignedScriptTemplate:
        script = ctv_script_fragment
    else:
        # TODO: For these kinds (CPFP, burn, ...), just implement a basic
        # witness on those transactions. The witness is just the number of the
        # transaction in the list (it's based on ordering).

        utxo.ctv_bypass = True

        if utxo.name == "vault initial UTXO":
            raise Exception("Should have been processed earlier...")

        return

    # Store this data on the UTXO object. It gets used later.
    utxo.ctv_script = CScript(script)
    utxo.ctv_witness_fragments = witness_fragments
    utxo.ctv_p2wsh_redeem_script = utxo.ctv_script
    utxo.ctv_scriptpubkey = CScript([OP_0, sha256(bytes(utxo.ctv_p2wsh_redeem_script))])

    # Copy over the witnesses to the PlannedInput objects.
    for child_transaction in utxo.child_transactions:
        appropriate_witness = witness_fragments[str(child_transaction.internal_id)]

        # Push the bytes for the redeemScript into the witness.
        appropriate_witness.append(utxo.ctv_p2wsh_redeem_script)

        specific_input = None
        for some_input in child_transaction.inputs:
            if some_input.utxo == utxo:
                specific_input = some_input
                break
        else:
            raise Exception("Couldn't find a relevant input. Why is this considered a child transaction...?")

        specific_input.ctv_witness = CScript(appropriate_witness)
        specific_input.ctv_p2wsh_redeem_script = script

def bake_ctv_transaction(some_transaction, skip_inputs=False, parameters=None):
    """
    Create a OP_CHECKTEMPLATEVERIFY version transaction for the planned
    transaction tree. This version uses a hash-based covenant opcode instead of
    using pre-signed transactions with trusted key deletion.

    This function does two passes over the planned transaction tree, consisting
    of (1) crawling the whole tree and generating standard template hashes
    (starting with the deepest elements in the tree and working backwards
    towards the root of the tree), and then (2) crawling the whole tree and
    assigning txids to the inputs. This is possible because
    OP_CHECKTEMPLATEVERIFY does not include the hash of the inputs in the
    standard template hash, otherwise there would be a recursive hash
    commitment dependency loop error.

    See the docstring for bake_ctv_output too.
    """

    if hasattr(some_transaction, "ctv_baked") and some_transaction.ctv_baked == True:
        return some_transaction.ctv_bitcoin_transaction

    # Bake each UTXO. Recurse down the tree and compute StandardTemplateHash
    # values (to be placed in scriptpubkeys) for OP_CHECKTEMPLATEVERIFY. These
    # standard template hashes can only be computed once the descendant tree is
    # computed, so it must be done recursively.
    for utxo in some_transaction.output_utxos:
        bake_ctv_output(utxo, parameters=parameters)

    # Construct python-bitcoinlib bitcoin transactions and attach them to the
    # PlannedTransaction objects, once all the UTXOs are ready.

    logger.info("Baking a transaction with name {}".format(some_transaction.name))

    bitcoin_inputs = []
    if not skip_inputs:
        for some_input in some_transaction.inputs:

            # When computing the standard template hash for a child transaction,
            # the child transaction needs to be only "partially" baked. It doesn't
            # need to have the inputs yet.

            # TODO: don't use string comparison for type detection....
            if str(some_input.utxo.transaction.__class__) == "InitialTransaction" or some_input.transaction.name == "Burn some UTXO":
                txid = some_input.utxo.transaction.txid
            else:
                logger.info("The parent transaction name is: {}".format(some_input.utxo.transaction.name))
                logger.info("Name of the UTXO being spent: {}".format(some_input.utxo.name))
                logger.info("Current transaction name: {}".format(some_input.transaction.name))

                # This shouldn't happen... We should be able to bake transactions
                # in a certain order and be done with this.
                #if not hasattr(some_input.utxo.transaction, "ctv_bitcoin_transaction"):
                #    bake_ctv_transaction(some_input.utxo.transaction, parameters=parameters)
                # TODO: this creates an infinite loop....

                txid = some_input.utxo.transaction.ctv_bitcoin_transaction.GetTxid()

            vout = some_input.utxo.transaction.output_utxos.index(some_input.utxo)

            relative_timelock = None
            if some_input.utxo.script_template.__class__ in [ColdStorageScriptTemplate, ShardScriptTemplate]:
                # TODO: This should be controlled by the template or whole
                # program parameters.
                relative_timelock = 144

            if relative_timelock:
                bitcoin_input = CTxIn(COutPoint(txid, vout), nSequence=relative_timelock)
            else:
                bitcoin_input = CTxIn(COutPoint(txid, vout))

            bitcoin_inputs.append(bitcoin_input)

    bitcoin_outputs = []
    for some_output in some_transaction.output_utxos:
        amount = some_output.amount

        # For certain UTXOs, just use the previous UTXO script templates,
        # instead of the CTV version. (utxo.ctv_bypass == True)
        if hasattr(some_output, "ctv_bypass"):
            scriptpubkey = some_output.scriptpubkey
        else:
            scriptpubkey = some_output.ctv_scriptpubkey

        bitcoin_output = CTxOut(amount, scriptpubkey)
        bitcoin_outputs.append(bitcoin_output)

    bitcoin_transaction = CMutableTransaction(bitcoin_inputs, bitcoin_outputs, nLockTime=0, nVersion=2, witness=None)

    if not skip_inputs:
        witnesses = []
        for some_input in some_transaction.inputs:
            logger.info("Transaction name: {}".format(some_transaction.name))
            logger.info("Spending UTXO with name: {}".format(some_input.utxo.name))
            logger.info("Parent transaction name: {}".format(some_input.utxo.transaction.name))

            if some_transaction.name in ["Burn some UTXO", "Funding commitment transaction"]:
                witness = some_input.witness
            else:
                witness = some_input.ctv_witness

            #logger.info("Appending witness: {}".format(list(witness)))
            witnesses.append(witness)

        ctxinwitnesses = [CTxInWitness(CScriptWitness(list(witness))) for witness in witnesses]
        witness = CTxWitness(ctxinwitnesses)
        bitcoin_transaction.wit = witness
    else:
        bitcoin_transaction.wit = CTxWitness()

    some_transaction.ctv_bitcoin_transaction = bitcoin_transaction

    if not skip_inputs:
        some_transaction.ctv_baked = True

    return bitcoin_transaction

def make_planned_transaction_tree_using_bip119_OP_CHECKTEMPLATEVERIFY(initial_tx, parameters=None):
    """
    Mutate the planned transaction tree in place and convert it to a planned
    transaction tree that uses OP_CHECKTEMPLATEVERIFY.
    """
    assert len(initial_tx.output_utxos[0].child_transactions) == 1
    vault_commitment_transaction = initial_tx.output_utxos[0].child_transactions[0]

    initial_utxo = initial_tx.output_utxos[0]
    (planned_utxos, planned_transactions) = initial_utxo.crawl()

    #planned_transactions = reversed(sorted(planned_transactions, key=lambda tx: tx.id))
    planned_transactions = sorted(planned_transactions, key=lambda tx: tx.id)

    #bake_ctv_output(initial_utxo, parameters=parameters)

    for planned_transaction in planned_transactions:
        bake_ctv_transaction(planned_transaction, parameters=parameters)

    # The top level transaction should be fine now.
    return bake_ctv_transaction(vault_commitment_transaction, parameters=parameters)
