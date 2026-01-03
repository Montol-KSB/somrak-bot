import os

from dotenv import load_dotenv
import discord


def load_token(env_var: str = "DISCORD_BOT_TOKEN") -> str:
    """
    Load Discord bot token from environment (with .env support for local dev).
    """
    load_dotenv()
    token = os.getenv(env_var)
    if not token:
        raise RuntimeError(f"{env_var} not found. Set it in .env or environment variables.")
    return token


def create_default_intents() -> discord.Intents:
    """
    Create default intents with message_content + members enabled.
    """
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    return intents


def ensure_admin(interaction: discord.Interaction) -> bool:
    """
    Simple helper to check if the user is an administrator.
    """
    if interaction.user and isinstance(interaction.user, discord.Member):
        return interaction.user.guild_permissions.administrator
    return False
