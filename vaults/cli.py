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
@click.option("--private-key", default="cUB8G5cFtxc4usfgfovqRgCo8qTQUJtctLV8t6YYNfULg3GtehdX", help="Override insecure default bitcoin private key.")
def init(private_key):
    """
    Create a new vault in the current working directory.

    **Note**: The default --private-key value is insecure, it's the famous
    "correct horse battery staple" key.
    """
    initialize(private_key=private_key)

@cli.command()
def info():
    """
    Display vault state information, including last sync time.
    """
    output = get_info()
    print(output) # TODO: switch to logger?

@cli.command()
def status():
    """
    same as info
    """
    output = get_info()
    print(output) # TODO: switch to logger?

@cli.command()
@click.argument("internal_id")
def broadcast(internal_id):
    """
    Broadcast a specific transaction. Only if the transaction is one of the
    next possible transactions.
    """
    broadcast_next_transaction(internal_id)

