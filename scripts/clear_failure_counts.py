#!/usr/bin/env python3
"""Utility script to clear failure counts from the database.

This script allows you to clear failure counts for:
- All records
- Specific states
- Specific schools (optionally filtered by state)
- Year ranges

Examples:
    # Clear all failure counts
    python scripts/clear_failure_counts.py --all

    # Clear failure counts for a specific state
    python scripts/clear_failure_counts.py --states California

    # Clear failure counts for multiple states
    python scripts/clear_failure_counts.py --states California Texas

    # Clear failure counts for specific schools in a state
    python scripts/clear_failure_counts.py --states California --schools LincolnHigh RooseveltHigh

    # Clear failure counts for a year range
    python scripts/clear_failure_counts.py --states California --year-start 2020 --year-end 2023

    # Clear failure counts for specific schools in a year range
    python scripts/clear_failure_counts.py --states California --schools LincolnHigh --year-start 2020 --year-end 2023
"""

from __future__ import annotations

import argparse
from sqlalchemy import text

from src.database import get_session
from src.models import PageId


def clear_failure_counts(
    *,
    all_records: bool = False,
    states: list[str] | None = None,
    schools: list[str] | None = None,
    year_start: int | None = None,
    year_end: int | None = None,
    dry_run: bool = False,
) -> int:
    """Clear failure counts matching the given criteria.

    Args:
        all_records: If True, clear all failure counts (ignores other filters)
        states: List of states to filter by
        schools: List of schools to filter by (requires states to be specified)
        year_start: Minimum year to include
        year_end: Maximum year to include
        dry_run: If True, only show what would be deleted without actually deleting

    Returns:
        Number of records cleared
    """
    with get_session() as session:
        if all_records:
            # Clear all failure counts
            if dry_run:
                result = session.execute(text("SELECT COUNT(*) FROM failure_counts"))
                count = result.scalar()
                print(f"[DRY RUN] Would clear {count} failure count records")
                return count
            else:
                result = session.execute(text("SELECT COUNT(*) FROM failure_counts"))
                count = result.scalar()
                session.execute(text("DELETE FROM failure_counts"))
                session.commit()
                print(f"Cleared {count} failure count records")
                return count

        if states:
            # Parse record keys to filter by state
            all_keys_result = session.execute(
                text("SELECT record_key FROM failure_counts")
            )
            matching_keys = []
            for row in all_keys_result:
                try:
                    page_id = PageId.from_key(row[0])
                    if page_id.state in states:
                        # Apply additional filters
                        if schools and page_id.school not in schools:
                            continue
                        if year_start is not None and page_id.year < year_start:
                            continue
                        if year_end is not None and page_id.year > year_end:
                            continue
                        matching_keys.append(row[0])
                except ValueError:
                    # Skip invalid keys
                    continue

            if not matching_keys:
                print("No matching records found")
                return 0

            if dry_run:
                print(
                    f"[DRY RUN] Would clear {len(matching_keys)} failure count records:"
                )
                for key in matching_keys[:10]:  # Show first 10
                    print(f"  - {key}")
                if len(matching_keys) > 10:
                    print(f"  ... and {len(matching_keys) - 10} more")
                return len(matching_keys)

            # Delete matching keys
            placeholders = ",".join([f":key{i}" for i in range(len(matching_keys))])
            delete_params = {f"key{i}": key for i, key in enumerate(matching_keys)}
            session.execute(
                text(
                    f"DELETE FROM failure_counts WHERE record_key IN ({placeholders})"
                ),
                delete_params,
            )
            session.commit()
            print(f"Cleared {len(matching_keys)} failure count records")
            return len(matching_keys)
        else:
            # No filters specified
            if schools or year_start is not None or year_end is not None:
                print(
                    "Error: --schools, --year-start, and --year-end require --states to be specified"
                )
                return 0

            print("Error: Must specify --all or --states")
            return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clear failure counts from the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Clear all failure counts (ignores other filters)",
    )
    parser.add_argument(
        "--states",
        nargs="+",
        help="List of states to filter by (e.g., California Texas)",
    )
    parser.add_argument(
        "--schools",
        nargs="+",
        help="List of schools to filter by (requires --states)",
    )
    parser.add_argument(
        "--year-start",
        type=int,
        help="Minimum year to include",
    )
    parser.add_argument(
        "--year-end",
        type=int,
        help="Maximum year to include",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )

    args = parser.parse_args()

    count = clear_failure_counts(
        all_records=args.all,
        states=args.states,
        schools=args.schools,
        year_start=args.year_start,
        year_end=args.year_end,
        dry_run=args.dry_run,
    )

    if count > 0:
        print(f"\n✓ Successfully processed {count} record(s)")
    else:
        print("\n✗ No records were cleared")


if __name__ == "__main__":
    # Example usage patterns
    import sys

    if len(sys.argv) == 1:
        print("Usage examples:")
        print("  # Clear all failure counts")
        print("  python scripts/clear_failure_counts.py --all")
        print()
        print("  # Clear failure counts for a specific state")
        print("  python scripts/clear_failure_counts.py --states California")
        print()
        print("  # Clear failure counts for multiple states")
        print("  python scripts/clear_failure_counts.py --states California Texas")
        print()
        print("  # Clear failure counts for specific schools in a state")
        print(
            "  python scripts/clear_failure_counts.py --states California --schools LincolnHigh RooseveltHigh"
        )
        print()
        print("  # Clear failure counts for a year range")
        print(
            "  python scripts/clear_failure_counts.py --states California --year-start 2020 --year-end 2023"
        )
        print()
        print("  # Clear failure counts for specific schools in a year range")
        print(
            "  python scripts/clear_failure_counts.py --states California --schools LincolnHigh --year-start 2020 --year-end 2023"
        )
        print()
        print("  # Dry run to see what would be cleared")
        print("  python scripts/clear_failure_counts.py --states California --dry-run")
        sys.exit(0)

    main()
