"""
Command line interface for the Vault library.
"""

import click

@click.group()
def cli():
    pass

@cli.command()
def init():
    """
    Create a new vault in the current working directory.
    """
    pass

@cli.command()
def info():
    """
    Display vault state information, including last sync time.
    """
    pass

@cli.command()
def clone():
    """
    Copy another vault's parameters (hot wallet keys etc).
    """
    pass

@cli.command()
def lock():
    """
    Initialize the vault and fund it with on-chain UTXOs.
    """
    pass

@cli.command()
def sync():
    """
    Synchronize against the blockchain and update local vault state data.
    """
    pass

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
    pass

@unlock.command()
def many():
    """
    Withdraw multiple sharded UTXOs from the vault.
    """
    pass

@cli.command()
def rotate():
    """
    Push all remaining UTXOs in the vault to the cold storage layer.
    """
    pass

cli.add_command(unlock)

