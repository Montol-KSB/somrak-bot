from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..common import ensure_admin
from .service import GuildNameSyncService


class GuildNameSyncCog(commands.GroupCog, name="guildname"):
    """Sync and summarize members' in-game names from the intro channel."""


    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot
        self.service = GuildNameSyncService(bot)

    # ------------------------------
    # Events
    # ------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Ignore DMs & bot messages
        if message.guild is None or message.author.bot:
            return
        await self.service.on_intro_message(message)

    # ------------------------------
    # /guildname clear  (manual delete of summary messages)
    # ------------------------------
    @app_commands.command(
        name="clear",
        description="Clear the summary messages created by this bot.",
    )
    async def clear_summary(self, interaction: discord.Interaction) -> None:
        if not ensure_admin(interaction):
            await interaction.response.send_message(
                "⛔ You need Administrator permission to use this command.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        assert guild is not None

        await interaction.response.defer(ephemeral=True, thinking=True)
        deleted = await self.service.clear_summary(guild)

        await interaction.followup.send(
            f"✅ Cleared {deleted} summary message(s).",
            ephemeral=True,
        )

    # ------------------------------
    # /guildname enable
    # ------------------------------
    @app_commands.command(
        name="enable",
        description="Enable guild name sync and set channels/keywords.",
    )
    async def enable(
        self,
        interaction: discord.Interaction,
        source_channel: discord.TextChannel,
        summary_channel: discord.TextChannel,
        keywords: Optional[str] = None,
        auto_role: Optional[discord.Role] = None,  # NEW
        newbie_role: Optional[discord.Role] = None,   # NEW
    ) -> None:
        """
        /guildname enable
          source_channel: intro channel
          summary_channel: summary channel
          keywords: optional, e.g. 'ชื่อในเกม, IGN'
        """
        if not ensure_admin(interaction):
            await interaction.response.send_message(
                "⛔ You need Administrator permission to use this command.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        assert guild is not None

        settings = self.service.get_settings(guild)
        settings.enabled = True
        settings.source_channel_id = source_channel.id
        settings.summary_channel_id = summary_channel.id

        if auto_role is not None:
            settings.auto_role_id = auto_role.id
        if newbie_role is not None:
            settings.newbie_role_id = newbie_role.id

        if keywords is not None:
            parts = [k.strip() for k in keywords.split(",") if k.strip()]
            if parts:
                settings.ign_keywords = parts

        keywords_text = ", ".join(settings.ign_keywords) or "None"
        auto_role_text = auto_role.mention if auto_role else "None"
        newbie_role_text = newbie_role.mention if newbie_role else "None"

        await interaction.response.send_message(
            "✅ Guild name sync **enabled**.\n\n"
            f"**Intro channel:** {source_channel.mention}\n"
            f"**Summary channel:** {summary_channel.mention}\n"
            f"**Role grouping:** automatic (Discord role hierarchy)\n"
            f"**IGN keywords:** {keywords_text}\n"
            f"**Auto role:** {auto_role_text}\n"
            f"**Newbie role:** {newbie_role_text}",
            ephemeral=True,
        )

        await self.service.rebuild_summary(guild)

    # ------------------------------
    # /guildname disable
    # ------------------------------
    @app_commands.command(
        name="disable",
        description="Disable guild name sync for this server.",
    )
    async def disable(self, interaction: discord.Interaction) -> None:
        if not ensure_admin(interaction):
            await interaction.response.send_message(
                "⛔ You need Administrator permission to use this command.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        assert guild is not None

        settings = self.service.get_settings(guild)
        settings.enabled = False

        await interaction.response.send_message(
            "⛔ Guild name sync disabled.",
            ephemeral=True,
        )

    # ------------------------------
    # /guildname set  (change channels / keywords later)
    # ------------------------------
    @app_commands.command(
        name="set",
        description="Configure channels and IGN keywords (role grouping is automatic).",
    )
    async def set(
        self,
        interaction: discord.Interaction,
        source_channel: Optional[discord.TextChannel] = None,
        summary_channel: Optional[discord.TextChannel] = None,
        keywords: Optional[str] = None,
        auto_role: Optional[discord.Role] = None,          # NEW
        newbie_role: Optional[discord.Role] = None,     # NEW
    ) -> None:
        """
        /guildname set
          source_channel: optional
          summary_channel: optional
          keywords: optional, comma-separated
        """
        if not ensure_admin(interaction):
            await interaction.response.send_message(
                "⛔ You need Administrator permission to use this command.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        assert guild is not None

        settings = self.service.get_settings(guild)

        if source_channel is not None:
            settings.source_channel_id = source_channel.id
        if summary_channel is not None:
            settings.summary_channel_id = summary_channel.id
        if keywords is not None:
            parts = [k.strip() for k in keywords.split(",") if k.strip()]
            if parts:
                settings.ign_keywords = parts

        if auto_role is not None:
            settings.auto_role_id = auto_role.id
        if newbie_role is not None:
            settings.newbie_role_id = newbie_role.id


        source_text = (
            f"<#{settings.source_channel_id}>"
            if settings.source_channel_id
            else "Not set"
        )
        summary_text = (
            f"<#{settings.summary_channel_id}>"
            if settings.summary_channel_id
            else "Not set"
        )
        keywords_text = ", ".join(settings.ign_keywords) or "None"
        auto_role_text = f"<@&{settings.auto_role_id}>" if settings.auto_role_id else "None"
        newbie_role_text = f"<@&{settings.newbie_role_id}>" if settings.newbie_role_id else "None"

        await interaction.response.send_message(
            "✅ Settings updated.\n\n"
            f"**Intro channel:** {source_text}\n"
            f"**Summary channel:** {summary_text}\n"
            f"**Role grouping:** automatic (Discord role hierarchy)\n"
            f"**IGN keywords:** {keywords_text}\n"
            f"**Auto role:** {auto_role_text}\n"
            f"**Newbie role:** {newbie_role_text}",
            ephemeral=True,
        )

        if settings.enabled:
            await self.service.rebuild_summary(guild)

    # ------------------------------
    # /guildname status
    # ------------------------------
    @app_commands.command(
        name="status",
        description="Show current guild name sync settings.",
    )
    async def status(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None

        settings = self.service.get_settings(guild)

        source_text = (
            f"<#{settings.source_channel_id}>"
            if settings.source_channel_id
            else "Not set"
        )
        summary_text = (
            f"<#{settings.summary_channel_id}>"
            if settings.summary_channel_id
            else "Not set"
        )
        keywords_text = ", ".join(settings.ign_keywords) or "None"
        auto_role_text = f"<@&{settings.auto_role_id}>" if settings.auto_role_id else "None"

        await interaction.response.send_message(
            f"**Guild name sync v0.0.1**\n"
            f"**Enabled:** {settings.enabled}\n"
            f"**Intro channel:** {source_text}\n"
            f"**Summary channel:** {summary_text}\n"
            f"**Role grouping:** automatic (Discord role hierarchy)\n"
            f"**IGN keywords:** {keywords_text}\n"
            f"**Auto role:** {auto_role_text}\n",
            ephemeral=True,
        )

    # ------------------------------
    # /guildname update  (manual rebuild)
    # ------------------------------
    @app_commands.command(
        name="update",
        description="Manually rebuild the guild member summary now.",
    )
    async def update(self, interaction: discord.Interaction) -> None:
        if not ensure_admin(interaction):
            await interaction.response.send_message(
                "⛔ You need Administrator permission to use this command.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        assert guild is not None

        await interaction.response.defer(ephemeral=True, thinking=True)
        posted = await self.service.rebuild_summary(guild)

        if posted:
            await interaction.followup.send(
                "✅ Summary updated manually.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "ℹ Nothing to update (no intro data or channels not set).",
                ephemeral=True,
            )
