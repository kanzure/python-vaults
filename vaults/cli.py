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
def create():
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
def stipend():
    """
    Commands dealing with regular, pre-scheduled withdrawals from the vault.
    """
    pass

@stipend.command()
def start():
    """
    Begin the process of withdrawing sharded UTXOs from the vault.
    """
    pass

@stipend.command()
def push_to_cold():
    """
    Push all remaining UTXOs in the vault to the cold storage layer.
    """
    pass

@stipend.command()
def re_vault_pending():
    """
    Push all pending UTXOs (about to be unlocked on-chain) to a new vault made
    with the keys used to create the original vault.
    """
    pass

cli.add_command(stipend)

