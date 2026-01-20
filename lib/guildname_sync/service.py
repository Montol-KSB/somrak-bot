from __future__ import annotations

import re
from typing import Dict, List, Tuple

import discord

from .settings import GuildSettings

MAX_DISCORD_LEN = 2000

def split_text_lines(text: str, limit: int = MAX_DISCORD_LEN) -> List[str]:
    lines = text.splitlines()
    chunks: List[str] = []
    buf = ""

    for line in lines:
        add = line + "\n"

        # ถ้า line เดียวเกิน limit ให้ตัดทิ้ง (กัน crash)
        if len(add) > limit:
            add = add[: limit - 1] + "\n"

        if len(buf) + len(add) > limit:
            if buf.strip():
                chunks.append(buf.rstrip())
            buf = add
        else:
            buf += add

    if buf.strip():
        chunks.append(buf.rstrip())

    return chunks


class GuildNameSyncService:
    """
    Logic layer for guild name sync:
    - manage per-guild settings
    - parse IGN from messages
    - build & update summary messages
    - clear summary messages
    """

    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        # guild_id -> GuildSettings
        self._settings: Dict[int, GuildSettings] = {}

    # ------------------------------
    # Settings API
    # ------------------------------
    def get_settings(self, guild: discord.Guild) -> GuildSettings:
        gs = self._settings.get(guild.id)
        if gs is None:
            gs = GuildSettings()
            self._settings[guild.id] = gs
        return gs

    # ------------------------------
    # IGN extraction
    # ------------------------------
    def extract_ign(self, content: str, settings: GuildSettings) -> str | None:
        """
        Extract in-game name from a message.

        Rules:
        - look for configured keywords
        - take text AFTER keyword
        - stop at newline
        - stop at "ID"
        - strip brackets / spaces
        """

        text = content.strip()

        for kw in settings.ign_keywords:
            if kw in text:
                # take text after keyword
                part = text.split(kw, 1)[1]

                # remove leading separators
                # : ： = - whitespace
                part = re.sub(r'^[:：=\-\s]+', '', part)

                # stop at newline
                part = part.split('\n')[0]

                # stop at ID (Thai / English)
                part = re.split(r'\bID\b|ไอดี', part, flags=re.IGNORECASE)[0]

                # remove surrounding brackets/comments
                part = re.sub(r'[()\[\]{}]+', '', part)

                ign = part.strip()

                if ign:
                    return ign

        return None


    # ------------------------------
    # Role priority
    # ------------------------------
    def get_role_priority(self, member: discord.Member, settings: GuildSettings) -> int:
        """
        Lower number = higher rank.

        - If settings.role_order is set:
            use that as custom priority.
        - If it's empty:
            use Discord's role hierarchy (highest role.position).
        """

        # 1) If you set a custom role order via /guildname set
        if settings.role_order:
            indices = [
                idx
                for idx, role_id in enumerate(settings.role_order)
                if any(r.id == role_id for r in member.roles)
            ]
            return min(indices) if indices else len(settings.role_order) + 1

        # 2) Default: use server's role hierarchy (Discord order)
        #    member.top_role is the highest role by position
        if member.roles:
            top_role = member.top_role
            # Discord: higher position = higher rank
            # We want "lower number = higher priority" → invert position
            return -top_role.position

        # no roles (rare): push to bottom
        return 9999


    # ------------------------------
    # Core: build summary text
    # ------------------------------
    async def build_summary_text(self, guild: discord.Guild) -> str | None:
        """
        Read intro channel history and return summary text.

        Always groups by member.top_role (Discord role hierarchy).
        """

        settings = self.get_settings(guild)

        if not settings.enabled:
            return None
        if not settings.source_channel_id or not settings.summary_channel_id:
            return None

        source = guild.get_channel(settings.source_channel_id)
        if not isinstance(source, discord.TextChannel):
            return None

        print(f"[{guild.name}] Building summary text...")

        # user_id -> (member, ign)
        user_map: Dict[int, Tuple[discord.Member, str]] = {}

        async for msg in source.history(limit=3000, oldest_first=True):
            if msg.author.bot:
                continue
            if not isinstance(msg.author, discord.Member):
                continue

            ign = self.extract_ign(msg.content, settings)
            if not ign:
                continue

            member = msg.author

            if any(r.id in settings.excluded_role_ids for r in member.roles):
                continue

            # newest intro wins
            user_map[member.id] = (member, ign)

        if not user_map:
            print(f"[{guild.name}] No IGN data found.")
            return None

        # ---------------------------
        # Group by top_role
        # ---------------------------
        # group_name -> { "sort_key": int, "members": [(member, ign), ...] }
        groups: Dict[str, Dict[str, object]] = {}

        for member, ign in user_map.values():
            if member.roles:
                top_role = member.top_role
                group_name = top_role.name
                # higher position = higher rank, so use negative for ascending sort
                sort_key = -top_role.position
            else:
                group_name = "Other"
                sort_key = 9999

            g = groups.setdefault(group_name, {"sort_key": sort_key, "members": []})
            g["members"].append((member, ign))

        # ---------------------------
        # Build text
        # ---------------------------
        lines: List[str] = []
        lines.append("📜 **รายชื่อสมาชิกกิลด์ (Auto-Update)**\n")

        for group_name, data in sorted(
            groups.items(), key=lambda kv: kv[1]["sort_key"]  # type: ignore[index]
        ):
            members: List[Tuple[discord.Member, str]] = data["members"]  # type: ignore[assignment]

            lines.append(f"**{group_name}**")
            for member, ign in sorted(members, key=lambda x: x[1].lower()):
                lines.append(f"- {member.mention} — ชื่อในเกม: {ign}")
            lines.append("")

        return "\n".join(lines).strip()

    # ------------------------------
    # Apply summary to summary channel
    # ------------------------------
    async def rebuild_summary(self, guild: discord.Guild) -> int:
        settings = self.get_settings(guild)

        summary_text = await self.build_summary_text(guild)
        if summary_text is None:
            return 0

        if not settings.summary_channel_id:
            return 0

        summary = guild.get_channel(settings.summary_channel_id)
        if not isinstance(summary, discord.TextChannel):
            return 0

        chunks = split_text_lines(summary_text)  # <= 2000 guaranteed

        # fetch old messages (if any)
        old_msgs: List[discord.Message] = []
        for mid in list(settings.summary_message_ids):
            try:
                m = await summary.fetch_message(mid)
                old_msgs.append(m)
            except discord.NotFound:
                # message deleted manually
                continue
            except discord.Forbidden:
                # no permission to fetch
                old_msgs = []
                break

        # edit existing messages
        used_ids: List[int] = []
        for i, chunk in enumerate(chunks):
            if i < len(old_msgs):
                await old_msgs[i].edit(content=chunk)
                used_ids.append(old_msgs[i].id)
            else:
                m = await summary.send(chunk)
                used_ids.append(m.id)

        # delete extra old messages if new chunks fewer
        for j in range(len(chunks), len(old_msgs)):
            try:
                await old_msgs[j].delete()
            except Exception:
                pass

        settings.summary_message_ids = used_ids
        print(f"[{guild.name}] Summary updated. chunks={len(chunks)}")
        return 1


    async def clear_summary(self, guild: discord.Guild) -> int:
        """
        Delete summary messages (by this bot) from summary channel.
        Return count of deleted messages.
        """
        settings = self.get_settings(guild)

        if not settings.summary_channel_id:
            return 0

        summary = guild.get_channel(settings.summary_channel_id)
        if not isinstance(summary, discord.TextChannel):
            return 0

        deleted = 0
        async for m in summary.history(limit=100):
            if m.author == self.bot.user:
                await m.delete()
                deleted += 1

        print(f"[{guild.name}] Cleared {deleted} summary messages.")
        return deleted

    # ------------------------------
    # Hook for on_message
    # ------------------------------
    async def on_intro_message(self, message: discord.Message) -> None:
        """
        Called from Cog.on_message. If message looks like IGN update,
        rebuild summary.
        """
        if message.guild is None:
            return

        guild = message.guild
        settings = self.get_settings(guild)

        if not settings.enabled:
            return
        if message.channel.id != settings.source_channel_id:
            return

        ign = self.extract_ign(message.content, settings)
        if ign:
            await self.rebuild_summary(guild)
