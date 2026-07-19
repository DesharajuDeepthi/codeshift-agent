import click
import requests


@click.command()
@click.option("--url")
def fetch(url: str) -> None:
    resp = requests.get(url, timeout=10)
    print(resp.text)
