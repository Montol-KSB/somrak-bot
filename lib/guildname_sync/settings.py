from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class GuildSettings:
    """
    Per-guild configuration for the intro → summary sync feature.
    """

    enabled: bool = False

    # Channel IDs
    source_channel_id: int | None = None    # intro / register channel
    summary_channel_id: int | None = None   # summary channel

    # Roles to exclude from list (future use – keep if you want)
    excluded_role_ids: List[int] = field(default_factory=list)

    # Keywords used to detect IGN / in-game name
    ign_keywords: List[str] = field(default_factory=lambda: ["ชื่อในเกม"])
