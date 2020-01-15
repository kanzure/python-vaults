"""
Command line interface for the Vault library.
"""

import click

from vaults.exceptions import VaultNotImplementedError

@click.group()
def cli():
    pass

@cli.command()
def init():
    """
    Create a new vault in the current working directory.
    """
    raise VaultNotImplementedError

@cli.command()
def info():
    """
    Display vault state information, including last sync time.
    """
    raise VaultNotImplementedError

@cli.command()
def clone():
    """
    Copy another vault's parameters (hot wallet keys etc).
    """
    raise VaultNotImplementedError

@cli.command()
def lock():
    """
    Initialize the vault and fund it with on-chain UTXOs.
    """
    raise VaultNotImplementedError

@cli.command()
def sync():
    """
    Synchronize against the blockchain and update local vault state data.
    """
    raise VaultNotImplementedError

@click.group()
def unlock():
    """
    Commands dealing with regular, pre-scheduled withdrawals from the vault.
    """
    pass

@unlock.command()
def single():
    """
    Withdraw a single sharded UTXO from the vault.
    """
    raise VaultNotImplementedError

@unlock.command()
def many():
    """
    Withdraw multiple sharded UTXOs from the vault.
    """
    raise VaultNotImplementedError

@cli.command()
def rotate():
    """
    Push all remaining UTXOs in the vault to the cold storage layer.
    """
    raise VaultNotImplementedError

@cli.command()
def burn():
    """
    Burn (or donate) the UTXOs.
    """
    # Note: can't burn the coins until they are in the cold storage layer.
    raise VaultNotImplementedError

cli.add_command(unlock)

