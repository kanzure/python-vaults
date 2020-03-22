"""
Command line interface for the Vault library.
"""

import click

from vaults.commands.initialize import initialize
from vaults.commands.broadcast import broadcast_next_transaction
from vaults.commands.info import get_info

@click.group()
def cli():
    pass

@cli.command()
def init():
    """
    Create a new vault in the current working directory.
    """
    initialize()

@cli.command()
def info():
    """
    Display vault state information, including last sync time.
    """
    output = get_info()
    print(output)

@cli.command()
@click.argument("internal_id")
def broadcast(internal_id):
    """
    Broadcast a specific transaction. Only if the transaction is one of the
    next possible transactions.
    """
    broadcast_next_transaction(internal_id)

cli.add_command(unlock)

