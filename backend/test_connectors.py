"""
Quick smoke test for the connector pipeline.
Run: python test_connectors.py
"""
import asyncio
from datetime import datetime, timedelta
from connectors import ConnectorManager, SourceType


async def main():
    manager = ConnectorManager(configs={
        SourceType.SLACK: {"use_mock": True},
        SourceType.GMAIL: {"use_mock": True},
        SourceType.JIRA:  {"use_mock": True},
    })

    since = datetime.utcnow() - timedelta(days=30)
    results = await manager.sync_all(since=since)

    print("\n=== Sync Summary ===")
    summary = manager.summary(results)
    print(f"Total items: {summary['total_items']}")
    for source, info in summary["by_source"].items():
        status = "OK" if info["success"] else f"ERROR: {info['error']}"
        print(f"  {source:10s} -> {info['items']} items  [{status}]")

    print("\n=== All Items (sorted by date) ===")
    items = ConnectorManager.collect_items(results)
    for item in items:
        print(f"  [{item.source:6s}] {item.timestamp.strftime('%Y-%m-%d %H:%M')}  {item.title[:50]}")
        print(f"           {item.content[:80]}…")
        print()


if __name__ == "__main__":
    asyncio.run(main())
