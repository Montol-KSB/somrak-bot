import asyncio
import logging

from discord.ext import commands

from app import server_on
from lib.common import load_token, create_default_intents
from lib.guildname_sync import GuildNameSyncCog


TOKEN = load_token()

# configure basic logging so messages appear in stdout/logs
logging.basicConfig(level=logging.INFO)
logging.getLogger("discord").setLevel(logging.INFO)


def create_bot() -> commands.Bot:
    intents = create_default_intents()
    bot = commands.Bot(command_prefix="!", intents=intents)
    return bot


bot = create_bot()


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})", flush=True)

    try:
        # Sync ALL global commands (works for every server that added the bot)
        synced = await bot.tree.sync()
        print(f"🌐 Synced {len(synced)} global command(s).", flush=True)
        print("Commands:", [cmd.qualified_name for cmd in bot.tree.get_commands()], flush=True)
    except Exception as e:
        print(f"⚠️ Failed to sync commands: {e}", flush=True)


async def main():
    server_on()

    # add_cog is synchronous; do not await it
    try:
        bot.add_cog(GuildNameSyncCog(bot))
    except Exception as e:
        print(f"⚠️ Failed to add GuildNameSyncCog: {e}", flush=True)

    try:
        await bot.start(TOKEN)
    except Exception as e:
        print(f"⚠️ Bot stopped with exception: {e}", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Fatal error in main: {e}", flush=True)
