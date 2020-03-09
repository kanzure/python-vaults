class ScriptTemplate(object):

    miniscript_policy_definitions = {}
    relative_timelocks = {}

    # TODO: move parameterization into ScriptTemplate?

    @classmethod
    def get_required_parameters(cls):
        required_parameters = []
        subclasses = cls.__subclasses__()
        for subclass in subclasses:
            if hasattr(subclass, "miniscript_policy_definitions"):
                required_parameters.extend(list(subclass.miniscript_policy_definitions.keys()))
        return list(set(required_parameters))

class UserScriptTemplate(ScriptTemplate):
    """
    Represents a script that the user picks. This is the input UTXO that gets
    sent into the vault. The user is responsible for specifying this script,
    and then signing the send-to-vault transaction.

    This is spendable by some user-provided signature. The vault is not
    responsible for producing this signature, but it is responsible for
    producing a scriptpubkey for where the coins are going to be sent to.
    """

    miniscript_policy = "pk(user_key)"
    miniscript_policy_definitions = {"user_key_hash160": "hash160 of user public key"}

    #script_template = "<user_key> OP_CHECKSIG"
    #witness_template_map = {"user_key_sig": "user_key"}
    #witness_templates = {
    #    "user": "<user_key_sig>",
    #}

    # Bitcoin Core wallet uses P2WPKH by default.
    script_template = "<user_key_hash160>"
    witness_template_map = {"user_key_sig": "user_key"}
    witness_templates = {
        "user": "<user_key_sig> <user_key>",
    }

class ColdStorageScriptTemplate(ScriptTemplate):
    """
    spendable by: cold wallet keys (after a relative timelock) OR immediately
    burnable (gated by ephemeral multisig)
    """

    miniscript_policy = "or(and(pk(ephemeral_key_1),pk(ephemeral_key_2)),and(pk(cold_key1),and(pk(cold_key2),older(144))))"
    miniscript_policy_definitions = {"ephemeral_key_1": "...", "ephemeral_key_2": "...", "cold_key1": "...", "cold_key2": "..."}

    script_template = """
<ephemeral_key_1> OP_CHECKSIG OP_NOTIF
  <cold_key1> OP_CHECKSIGVERIFY <cold_key2> OP_CHECKSIGVERIFY
  <TIMELOCK1> OP_CHECKSEQUENCEVERIFY
OP_ELSE
  <ephemeral_key_2> OP_CHECKSIG
OP_ENDIF
    """

    witness_template_map = {"ephemeral_sig_1": "ephemeral_key_1", "ephemeral_sig_2": "ephemeral_key_2", "cold_key1_sig": "cold_key1", "cold_key2_sig": "cold_key2"}
    witness_templates = {
        "presigned": "<ephemeral_sig_2> <ephemeral_sig_1>",
        "cold-wallet": "<cold_key2_sig> <cold_key1_sig>",
    }
    # Note that the "cold-wallet" witness template cannot be used to make a
    # valid witness unless the cold keys's private keys are accessed because
    # that's the only way to generate the required signatures. In contrast, the
    # "presigned" witness can be parameterized and correct before secure key
    # deletion occurs, producing a transaction that pushes to cold storage,
    # without requiring access to the cold storage keys.

    relative_timelocks = {
        "replacements": {
            "TIMELOCK1": 144,
        },
        "selections": {
            "cold-storage": "TIMELOCK1",
        },
    }

class BurnUnspendableScriptTemplate(ScriptTemplate):
    """
    unspendable (burned)
    """

    miniscript_policy = "pk(unspendable_key_1)"
    miniscript_policy_definitions = {"unspendable_key_1": "some unknowable key"}

    script_template = "<unspendable_key_1> OP_CHECKSIG"

    witness_template_map = {}
    witness_templates = {} # (intentionally empty)

class BasicPresignedScriptTemplate(ScriptTemplate):
    """
    Represents a script that can only be spent by one child transaction,
    which is pre-signed.

    spendable by: n-of-n ephemeral multisig after relative timelock
    """

    # TODO: pick an appropriate relative timelock (and let it be parameterized
    # somehow)
    miniscript_policy = "and(pk(ephemeral_key_1),and(pk(ephemeral_key_2),older(144)))"
    miniscript_policy_definitions = {"ephemeral_key_1": "...", "ephemeral_key_2": "..."}

    script_template = "<ephemeral_key_1> OP_CHECKSIGVERIFY <ephemeral_key_2> OP_CHECKSIGVERIFY <TIMELOCK1> OP_CHECKSEQUENCEVERIFY"

    witness_template_map = {"ephemeral_sig_1": "ephemeral_key_1", "ephemeral_sig_2": "ephemeral_key_2"}
    witness_templates = {
        "presigned": "<ephemeral_sig_2> <ephemeral_sig_1>",
    }
    relative_timelocks = {
        "replacements": {
            "TIMELOCK1": 144,
        },
        "selections": {
            "presigned": "TIMELOCK1",
        },
    }

class ShardScriptTemplate(ScriptTemplate):
    """
    spendable by: push to cold storage (gated by ephemeral multisig) OR
    spendable by hot wallet after timeout
    """

    ephemeral_multisig_gated = BasicPresignedScriptTemplate.miniscript_policy
    # TODO: pick an appropriate timelock length.
    # (Other code is currently manipulating the timelock to make it
    # monotonically increasing in each sharded UTXO.)
    miniscript_policy = f"or(and(pk(hot_wallet_key),older(144)),{ephemeral_multisig_gated})"
    miniscript_policy_definitions = {"hot_wallet_key": "...", "ephemeral_key_1": "...", "ephemeral_key_2": "..."}
    # or(and(pk(hot_wallet_key),older(144)),and(pk(ephemeral_key_1),and(pk(ephemeral_key_2),older(144))))

    script_template = """
<hot_wallet_key> OP_CHECKSIG OP_NOTIF
  <ephemeral_key_1> OP_CHECKSIGVERIFY <ephemeral_key_2> OP_CHECKSIGVERIFY
OP_ELSE
  <TIMELOCK1> OP_CHECKSEQUENCEVERIFY
OP_ENDIF
    """

    witness_template_map = {"ephemeral_sig_1": "ephemeral_key_1", "ephemeral_sig_2": "ephemeral_key_2", "hot_wallet_key_sig": "hot_wallet_key"}
    witness_templates = {
        "presigned": "<ephemeral_sig_2> <ephemeral_sig_1>",
        "hot-wallet": "<hot_wallet_key_sig>",
    }
    relative_timelocks = {
        "replacements": {
            "TIMELOCK1": 144,
        },
        "selections": {
            #"presigned": None,
            "hot-wallet": "TIMELOCK1",
        },
    }

class CPFPHookScriptTemplate(ScriptTemplate):
    """
    OP_TRUE -- a simple script for anyone-can-spend.
    """

    # TODO: does miniscript policy language support this? andytoshi says no,
    # although miniscript does support this.

    # python-bitcoinlib doesn't know that OP_TRUE==OP_1 so just set to OP_1
    # directly.
    # https://github.com/petertodd/python-bitcoinlib/issues/225
    script_template = "OP_1"

    # For OP_TRUE scriptpubkeys, witness stack can be empty, according to Bob.
    # But we might just upgrade this to use a hot wallet key CHECKSIG anyway.
    witness_template_map = {}
    witness_templates = {} # (intentionally empty)


