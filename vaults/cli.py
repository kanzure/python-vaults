"""
Command line interface for the Vault library.
"""

import click

from vaults.exceptions import VaultNotImplementedError
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
def all():
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

