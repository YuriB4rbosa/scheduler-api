"""Comandos da CLI (``flask <comando>``)."""

import os

import click
from flask import Flask, current_app
from flask.cli import with_appcontext

from app.services import seed_service


@click.command("seed")
@click.option("--reset", is_flag=True, help="Apaga e recria os dados do usuário de demonstração.")
@with_appcontext
def seed_command(reset: bool) -> None:
    """Popula o banco com dados de demonstração (nunca em produção)."""
    env_name = current_app.config["ENV_NAME"]
    if env_name == "production":
        raise click.ClickException("O seed é bloqueado em produção (APP_ENV=production).")

    try:
        password = seed_service.resolve_password(env_name, os.environ.get("SEED_DEMO_PASSWORD"))
        counts = seed_service.seed_demo(password, reset=reset)
    except seed_service.SeedError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(
        f"Seed concluído: {counts['customers']} clientes, {counts['services']} serviços, "
        f"{counts['appointments']} agendamentos."
    )
    click.echo(f"Login de demonstração: {seed_service.DEMO_EMAIL}")


def register_cli(app: Flask) -> None:
    app.cli.add_command(seed_command)
