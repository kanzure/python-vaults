from bitcoin.wallet import CBitcoinSecret

from vaults.utils import sha256

def make_private_keys():
    """
    Convert a list of passphrases into a list of private keys. For the purposes
    of prototyping, the passphrases are static values. System random should be
    used for the real deal, though.
    """
    # Note that this function uses python-bitcoinlib CBitcoinSecret objects.

    private_keys = []

    passphrases = [
        "password",
        "passphrase",
        "hello world",
        "hello cruel world",
        "correct horse battery staple",
        "correct horse battery staple 1",
        "correct horse battery staple 2",
        "correct horse battery staple 3",
        "correct horse battery staple 4",
    ]
    passphrases = [bytes(each, "utf-8") for each in passphrases]

    for passphrase in passphrases:
        hashed = sha256(passphrase)

        # compressed=True is default
        private_key = CBitcoinSecret.from_secret_bytes(hashed, compressed=True)

        private_keys.append(private_key)

    return private_keys
