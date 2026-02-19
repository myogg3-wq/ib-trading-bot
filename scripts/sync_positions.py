"""
Manual position sync script.
Run this to check for mismatches between IB and DB.

Usage:
    python -m scripts.sync_positions
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.broker.position_sync import sync_positions, format_sync_report
from app.database.connection import init_db


async def main():
    await init_db()
    print("Starting position sync...\n")

    result = await sync_positions()
    report = format_sync_report(result)

    # Strip emojis for terminal display
    print(report)
    print(f"\nFull result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
