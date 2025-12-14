#!/usr/bin/env python3
"""Utility script to completely clear/reset the database.

⚠️  WARNING: This will delete ALL data from the database including:
- All active batches
- All batch record keys
- All inflight records
- All failure counts
- All failure logs

This is useful when you want to start fresh or reset the entire system state.

Examples:
    # Dry run to see what would be deleted
    python scripts/nuke_database.py --dry-run

    # Actually delete everything
    python scripts/nuke_database.py --confirm

    # Delete everything and recreate tables
    python scripts/nuke_database.py --confirm --recreate-tables
"""

from __future__ import annotations

import argparse
from sqlalchemy import text

from src.database import get_session, init_database


def get_table_counts() -> dict[str, int]:
    """Get record counts for all tables."""
    with get_session() as session:
        tables = [
            "active_batches",
            "batch_record_keys",
            "inflight_records",
            "failure_counts",
            "failure_logs",
        ]
        counts = {}
        for table in tables:
            result = session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = result.scalar()
        return counts


def nuke_database(*, recreate_tables: bool = False, dry_run: bool = False) -> None:
    """Delete all data from the database.

    Args:
        recreate_tables: If True, drop and recreate all tables
        dry_run: If True, only show what would be deleted
    """
    counts = get_table_counts()

    print("\n=== Current Database State ===")
    total_records = 0
    for table, count in counts.items():
        print(f"  {table}: {count} records")
        total_records += count

    print(f"\nTotal records: {total_records}")

    if dry_run:
        print("\n[DRY RUN] Would delete all records from:")
        for table in counts.keys():
            print(f"  - {table}")
        if recreate_tables:
            print("\n[DRY RUN] Would also drop and recreate all tables")
        return

    # Confirm deletion
    print("\n⚠️  WARNING: This will delete ALL data from the database!")
    print("This includes:")
    print("  - All active batches")
    print("  - All batch record keys")
    print("  - All inflight records")
    print("  - All failure counts")
    print("  - All failure logs")
    print()

    response = input("Type 'DELETE' to confirm: ")
    if response != "DELETE":
        print("Aborted. Database unchanged.")
        return

    with get_session() as session:
        # Delete all records from each table
        tables = [
            "active_batches",
            "batch_record_keys",
            "inflight_records",
            "failure_counts",
            "failure_logs",
        ]

        deleted_counts = {}
        for table in tables:
            result = session.execute(text(f"DELETE FROM {table}"))
            deleted_counts[table] = result.rowcount

        session.commit()

        print("\n✓ Deleted records:")
        for table, count in deleted_counts.items():
            print(f"  {table}: {count} records")

    if recreate_tables:
        print("\nRecreating tables...")
        # Drop all tables
        with get_session() as session:
            session.execute(text("DROP TABLE IF EXISTS failure_logs"))
            session.execute(text("DROP TABLE IF EXISTS inflight_records"))
            session.execute(text("DROP TABLE IF EXISTS batch_record_keys"))
            session.execute(text("DROP TABLE IF EXISTS failure_counts"))
            session.execute(text("DROP TABLE IF EXISTS active_batches"))
            session.commit()

        # Recreate tables
        init_database()
        print("✓ Tables recreated")

    print("\n✓ Database cleared successfully!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Completely clear/reset the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Skip confirmation prompt (use with caution!)",
    )
    parser.add_argument(
        "--recreate-tables",
        action="store_true",
        help="Drop and recreate all tables after clearing",
    )

    args = parser.parse_args()

    if args.dry_run:
        nuke_database(recreate_tables=args.recreate_tables, dry_run=True)
    elif args.confirm:
        # For scripted use, skip the confirmation prompt
        nuke_database(recreate_tables=args.recreate_tables, dry_run=False)
    else:
        # Interactive mode with confirmation
        nuke_database(recreate_tables=args.recreate_tables, dry_run=False)


if __name__ == "__main__":
    # Example usage patterns
    import sys

    if len(sys.argv) == 1:
        print("Usage examples:")
        print("  # Dry run to see what would be deleted")
        print("  python scripts/nuke_database.py --dry-run")
        print()
        print("  # Actually delete everything (interactive confirmation)")
        print("  python scripts/nuke_database.py")
        print()
        print("  # Delete everything without confirmation prompt")
        print("  python scripts/nuke_database.py --confirm")
        print()
        print("  # Delete everything and recreate tables")
        print("  python scripts/nuke_database.py --confirm --recreate-tables")
        sys.exit(0)

    main()
