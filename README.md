# Sharding Vaults

This project provides some tools and a prototype for bitcoin vaults based
around the concept of sharding and pre-signed transactions.

# Background (summary)

A **vault** is an on-chain construct that keeps coins locked up until someone opens the vault. Upon opening the vault, the user has the option of sending coins back into a new vault configured with identical keys, sweeping the coins to a cold storage wallet or more-deep cold storage vault, or allowing the coins to exit the vault and be used by some hot wallet.

**Sharding** refers to a policy recommendation of splitting a bitcoin UTXO into multiple new UTXOs that can each become un-vaulted only on a specific schedule. The purpose of sharding is to minimize the total amount lost due to theft. By sampling the hot wallet with only one sharded UTXO at a time, the user can immediately push the remaining UTXOs to cold storage the moment a theft on the hot wallet is detected. Without this feature, a user might keep 100% of their funds in a single UTXO which can be stolen by that same kind of thief.

Additional background:

<https://www.coindesk.com/the-vault-is-back-bitcoin-coder-to-revive-plan-to-shield-wallets-from-theft>

<https://bitcoinmagazine.com/articles/revamped-idea-bitcoin-vaults-may-end-exchange-hacks-good>

<https://lists.linuxfoundation.org/pipermail/bitcoin-dev/2019-August/017229.html>

<https://lists.linuxfoundation.org/pipermail/bitcoin-dev/2019-August/017231.html>

