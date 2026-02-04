import asyncio
import logging
from discord.ext import commands

from lib.common import load_token, create_default_intents
from lib.guildname_sync import GuildNameSyncCog


TOKEN = load_token()



logging.basicConfig(
    level=logging.INFO,  # อยากละเอียดใช้ DEBUG
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# เพิ่มถ้าอยากเห็น HTTP / rate limit ชัดขึ้น
logging.getLogger("discord").setLevel(logging.INFO)
logging.getLogger("discord.http").setLevel(logging.INFO)  # เปลี่ยนเป็น DEBUG ได้


def create_bot() -> commands.Bot:
    intents = create_default_intents()
    bot = commands.Bot(command_prefix="!", intents=intents)
    return bot


bot = create_bot()


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    try:
        # Sync ALL global commands (works for every server that added the bot)
        synced = await bot.tree.sync()
        print(f"🌐 Synced {len(synced)} global command(s).")
        print("Commands:", [cmd.qualified_name for cmd in bot.tree.get_commands()])
    except Exception as e:
        print(f"⚠️ Failed to sync commands: {e}")


async def main():
    #server_on()
    await bot.add_cog(GuildNameSyncCog(bot))
    await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
