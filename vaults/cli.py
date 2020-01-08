"""
Command line interface for the Vault library.
"""

import click

@click.group()
def cli():
    pass

@cli.command()
def init():
    pass

@cli.command()
def info():
    pass

@cli.command()
def create():
    pass

@cli.command()
def sync():
    pass

@click.group()
def stipend():
    pass

@stipend.command()
def start():
    pass

@stipend.command()
def push_to_cold():
    pass

@stipend.command()
def re_vault_pending():
    pass

cli.add_command(stipend)

