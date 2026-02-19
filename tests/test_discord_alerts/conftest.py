"""Test configuration for Discord alerts tests."""

from __future__ import annotations

import os
import sys

# Add src to path for imports
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
src_path = os.path.join(project_root, "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Set test environment variables
os.environ.setdefault("DISCORD_GUILD_ID", "1413522994810327134")
os.environ.setdefault("DISCORD_SUMMARIES_CHANNEL_ID", "1445752426563899492")
os.environ.setdefault("DISCORD_TRADING_CHANNEL_ID", "1444447985378398459")
