from __future__ import annotations
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

    # NEW: auto role after intro (optional)
    summary_message_ids: List[int] = field(default_factory=list)
    auto_role_id: int | None = None



