from __future__ import annotations
# settings.py
# settings.py
from dataclasses import dataclass, field
from typing import List

@dataclass
class GuildSettings:
    enabled: bool = False
    source_channel_id: int | None = None
    summary_channel_id: int | None = None

    excluded_role_ids: List[int] = field(default_factory=list)
    ign_keywords: List[str] = field(default_factory=lambda: ["ชื่อในเกม"])

    auto_role_id: int | None = None
    newbie_role_id: int | None = None          # NEW: role สมาชิกใหม่
    summary_message_ids: List[int] = field(default_factory=list)


