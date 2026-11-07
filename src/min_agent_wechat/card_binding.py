"""Expose only the connection-state directory to the existing native card."""
from .files import save_json


def register_connection(card_directory, state_directory):
    if card_directory:
        save_json(card_directory / "wechat-source.json", {
            "version": 1, "directory": str(state_directory.resolve(strict=True))})
