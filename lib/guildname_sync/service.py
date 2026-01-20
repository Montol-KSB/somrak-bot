from __future__ import annotations

import asyncio
import re
from typing import Dict, List, Tuple

import discord

from .settings import GuildSettings

MAX_DISCORD_LEN = 2000
DEFAULT_MAX_IGN_LENGTH = 100  # กัน ign ยาวเว่อร์

def split_text_lines(text: str, limit: int = MAX_DISCORD_LEN) -> List[str]:
    lines = text.splitlines()
    chunks: List[str] = []
    buf = ""

    for line in lines:
        add = line + "\n"
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
    def __init__(self, bot: discord.Client) -> None:
        self.bot = bot
        self._settings: Dict[int, GuildSettings] = {}

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
        text = content.strip()

        for kw in settings.ign_keywords:
            max_len = getattr(settings, "ign_max_length", DEFAULT_MAX_IGN_LENGTH)
            if not (isinstance(max_len, int) and max_len > 0):
                max_len = DEFAULT_MAX_IGN_LENGTH

            pattern = re.compile(
                re.escape(kw) + r'[：:=\-\s]*([^\n]{1,' + str(max_len) + r'})',
                flags=re.IGNORECASE,
            )
            m = pattern.search(text)
            if m:
                part = m.group(1)
                # ตัดที่ ID/UID/ไอดี
                part = re.split(r'\b(?:ID|UID)\b|ไอดี', part, flags=re.IGNORECASE)[0]
                part = re.sub(r'[()\[\]{}]+', '', part)
                ign = part.strip()
                if ign:
                    return ign

            # fallback
            if kw in text:
                part = text.split(kw, 1)[1]
                part = re.sub(r'^[:：=\-\s]+', '', part)
                part = part[:max_len]
                part = part.split('\n')[0]
                part = re.split(r'\b(?:ID|UID)\b|ไอดี', part, flags=re.IGNORECASE)[0]
                part = re.sub(r'[()\[\]{}]+', '', part)
                ign = part.strip()
                if ign:
                    return ign

        return None

    # ------------------------------
    # Collect intro data (user_map)
    # ------------------------------
    async def collect_intro_user_map(
        self, guild: discord.Guild, limit: int = 3000
    ) -> Dict[int, Tuple[discord.Member, str]]:
        settings = self.get_settings(guild)

        if not settings.enabled:
            return {}
        if not settings.source_channel_id:
            return {}

        source = guild.get_channel(settings.source_channel_id)
        if not isinstance(source, discord.TextChannel):
            return {}

        print(f"[{guild.name}] Collecting intro data...")

        user_map: Dict[int, Tuple[discord.Member, str]] = {}

        async for msg in source.history(limit=limit, oldest_first=True):
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

            # newest wins
            user_map[member.id] = (member, ign)

        return user_map

    # ------------------------------
    # Auto role apply (safe)
    # ------------------------------
    async def _apply_auto_role(self, guild: discord.Guild, member: discord.Member, settings: GuildSettings) -> bool:
        """Return True if role added."""
        if not settings.auto_role_id:
            return False

        role = guild.get_role(settings.auto_role_id)
        if role is None:
            return False

        if role in member.roles:
            return False

        me = guild.me  # type: ignore[attr-defined]
        if me is None:
            return False
        if not me.guild_permissions.manage_roles:
            return False

        # bot must be higher than target role
        if role.position >= me.top_role.position:
            return False

        try:
            await member.add_roles(role, reason="Intro completed (auto role)")
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    def build_summary_from_guild(
        self,
        guild: discord.Guild,
        user_map: Dict[int, Tuple[discord.Member, str]],
        settings: GuildSettings,
    ) -> str | None:
        # member_id -> (member, ign_or_note)
        combined: Dict[int, Tuple[discord.Member, str]] = dict(user_map)
        note = "ยังไม่แนะนำตัว"

        # -------------------------
        # เติมคนที่ "ยังไม่แนะนำตัว"
        # เงื่อนไข:
        # - ต้องมี role จริงอย่างน้อย 1 (ไม่ใช่แค่ @everyone)
        # - ถ้าไม่มี role จริง (มีแค่ @everyone) -> ไม่โชว์
        # -------------------------
        for member in guild.members:
            if member.bot:
                continue
            if any(r.id in settings.excluded_role_ids for r in member.roles):
                continue
            if member.id in combined:
                continue

            # real roles = roles ที่ไม่ใช่ @everyone
            real_roles = [r for r in member.roles if not r.is_default()]
            if not real_roles:
                # มีแค่ @everyone -> ไม่โชว์
                continue

            combined[member.id] = (member, f"({note})")

        if not combined:
            return None

        # -------------------------
        # group by "top real role" (exclude @everyone)
        # -------------------------
        groups: Dict[str, Dict[str, object]] = {}

        for member, ign in combined.values():
            real_roles = [r for r in member.roles if not r.is_default()]
            if real_roles:
                top_role = max(real_roles, key=lambda r: r.position)
                group_name = top_role.name
                sort_key = -top_role.position
            else:
                # กรณีนี้จะเกิดได้แค่ถ้า member อยู่ใน user_map แต่มีแค่ @everyone
                # คุณบอกให้ "ลืมยศนี้ไปเลย" -> งั้นไม่โชว์คนนี้
                continue

            g = groups.setdefault(group_name, {"sort_key": sort_key, "members": []})
            g["members"].append((member, ign))

        if not groups:
            return None

        # -------------------------
        # Build text
        # -------------------------
        lines: List[str] = []
        lines.append("📜 **รายชื่อสมาชิกกิลด์**\n")

        for group_name, data in sorted(groups.items(), key=lambda kv: kv[1]["sort_key"]):  # type: ignore[index]
            members: List[Tuple[discord.Member, str]] = data["members"]  # type: ignore[assignment]
            lines.append(f"**{group_name}**")

            # sort: คนมี IGN จริงขึ้นก่อน, คนยังไม่แนะนำตัวไว้ท้าย
            def sort_key_fn(x: Tuple[discord.Member, str]) -> tuple:
                ign = x[1]
                is_note = "ยังไม่แนะนำตัว" in ign
                return (is_note, ign.lower())

            for member, ign in sorted(members, key=sort_key_fn):
                if "ยังไม่แนะนำตัว" in ign:
                    lines.append(f"- {member.mention} — {ign}")
                else:
                    lines.append(f"- {member.mention} — ชื่อในเกม: {ign}")
            lines.append("")

        return "\n".join(lines).strip()


    # ------------------------------
    # Rebuild summary (NOW includes backfill role on update)
    # ------------------------------
    async def rebuild_summary(self, guild: discord.Guild) -> int:
        settings = self.get_settings(guild)

        if not settings.enabled or not settings.summary_channel_id:
            return 0

        summary_ch = guild.get_channel(settings.summary_channel_id)
        if not isinstance(summary_ch, discord.TextChannel):
            return 0

        # 1) collect all intro data (this is the "truth" source)
        user_map = await self.collect_intro_user_map(guild, limit=3000)
        if not user_map:
            print(f"[{guild.name}] No intro data found.")
            return 0

        # 2) BACKFILL: apply auto role for everyone who has intro
        #    (throttle a bit to be nice to Discord API)
        added = 0
        for member, _ign in user_map.values():
            ok = await self._apply_auto_role(guild, member, settings)
            if ok:
                added += 1
                await asyncio.sleep(0.2)  # กัน burst; ปรับได้

        if added:
            # roles changed → top_role may change → rebuild user_map members are same, but their roles updated already
            print(f"[{guild.name}] Auto role applied to {added} member(s).")

        # 3) build summary text
        summary_text = self.build_summary_from_guild(guild, user_map, settings)
        if summary_text is None:
            return 0

        chunks = split_text_lines(summary_text)

        # 4) edit existing summary messages if possible (otherwise send new)
        old_msgs: List[discord.Message] = []
        for mid in list(settings.summary_message_ids):
            try:
                m = await summary_ch.fetch_message(mid)
                old_msgs.append(m)
            except discord.NotFound:
                continue
            except discord.Forbidden:
                old_msgs = []
                break

        used_ids: List[int] = []
        for i, chunk in enumerate(chunks):
            if i < len(old_msgs):
                await old_msgs[i].edit(content=chunk)
                used_ids.append(old_msgs[i].id)
            else:
                m = await summary_ch.send(chunk)
                used_ids.append(m.id)

        for j in range(len(chunks), len(old_msgs)):
            try:
                await old_msgs[j].delete()
            except Exception:
                pass

        settings.summary_message_ids = used_ids
        print(f"[{guild.name}] Summary updated. chunks={len(chunks)}")
        return 1

    async def clear_summary(self, guild: discord.Guild) -> int:
        settings = self.get_settings(guild)

        if not settings.summary_channel_id:
            return 0

        summary = guild.get_channel(settings.summary_channel_id)
        if not isinstance(summary, discord.TextChannel):
            return 0

        deleted = 0
        # ลบตามที่เรา track ไว้ก่อน (เร็ว/ชัวร์)
        for mid in list(settings.summary_message_ids):
            try:
                m = await summary.fetch_message(mid)
                await m.delete()
                deleted += 1
            except Exception:
                pass
        settings.summary_message_ids = []

        return deleted

    # ------------------------------
    # Hook for on_message (ยังทำงานเหมือนเดิม)
    # ------------------------------
    async def on_intro_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        guild = message.guild
        settings = self.get_settings(guild)

        if not settings.enabled:
            return
        if message.channel.id != settings.source_channel_id:
            return

        ign = self.extract_ign(message.content, settings)
        if not ign:
            return

        if isinstance(message.author, discord.Member):
            await self._apply_auto_role(guild, message.author, settings)

        await self.rebuild_summary(guild)
