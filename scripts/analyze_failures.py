#!/usr/bin/env python3
"""Utility script to analyze failure reasons from the database.

This script provides insights into:
- Failure counts by error type
- Most common error messages
- Failure distribution by state/school/year
- Detailed failure logs for specific records

Examples:
    # Show summary statistics
    python scripts/analyze_failures.py --summary

    # Show failures by error type
    python scripts/analyze_failures.py --by-error-type

    # Show failures by state
    python scripts/analyze_failures.py --by-state

    # Show detailed logs for a specific record
    python scripts/analyze_failures.py --record-key "California:LincolnHigh:2023:4"

    # Show failures for a specific state
    python scripts/analyze_failures.py --states California

    # Export failures to CSV
    python scripts/analyze_failures.py --export-csv failures.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from sqlalchemy import text

from src.database import get_session
from src.models import PageId


def get_failure_summary() -> dict:
    """Get summary statistics about failures."""
    with get_session() as session:
        # Total failure counts
        total_failures_result = session.execute(
            text("SELECT COUNT(*) FROM failure_counts")
        )
        total_failures = total_failures_result.scalar()

        # Total failure logs
        total_logs_result = session.execute(text("SELECT COUNT(*) FROM failure_logs"))
        total_logs = total_logs_result.scalar()

        # Records with failures
        records_with_failures_result = session.execute(
            text("SELECT COUNT(DISTINCT record_key) FROM failure_logs")
        )
        records_with_failures = records_with_failures_result.scalar()

        # Max retry count
        max_retry_result = session.execute(
            text("SELECT MAX(count) FROM failure_counts")
        )
        max_retry = max_retry_result.scalar() or 0

        return {
            "total_failure_counts": total_failures,
            "total_failure_logs": total_logs,
            "records_with_failures": records_with_failures,
            "max_retry_count": max_retry,
        }


def get_failures_by_error_type() -> dict[str, int]:
    """Get failure counts grouped by error type."""
    with get_session() as session:
        result = session.execute(
            text(
                "SELECT error_type, COUNT(*) as count FROM failure_logs GROUP BY error_type ORDER BY count DESC"
            )
        )
        return {row[0] or "Unknown": row[1] for row in result}


def get_failures_by_state() -> dict[str, int]:
    """Get failure counts grouped by state."""
    with get_session() as session:
        result = session.execute(text("SELECT record_key FROM failure_counts"))
        state_counts = Counter()
        for row in result:
            try:
                page_id = PageId.from_key(row[0])
                state_counts[page_id.state] += 1
            except ValueError:
                continue
        return dict(state_counts.most_common())


def get_failures_by_school(state: str | None = None) -> dict[str, int]:
    """Get failure counts grouped by school."""
    with get_session() as session:
        result = session.execute(text("SELECT record_key FROM failure_counts"))
        school_counts = Counter()
        for row in result:
            try:
                page_id = PageId.from_key(row[0])
                if state and page_id.state != state:
                    continue
                school_key = f"{page_id.state}:{page_id.school}"
                school_counts[school_key] += 1
            except ValueError:
                continue
        return dict(school_counts.most_common())


def get_failure_logs(
    record_key: str | None = None,
    states: list[str] | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Get detailed failure logs."""
    with get_session() as session:
        query = """
            SELECT 
                record_key,
                batch_id,
                attempt_number,
                error_type,
                error_message,
                model_name,
                prompt_name,
                created_at
            FROM failure_logs
        """
        conditions = []
        params = {}

        if record_key:
            conditions.append("record_key = :record_key")
            params["record_key"] = record_key

        if states:
            # Filter by parsing record keys
            all_logs_result = session.execute(
                text("SELECT record_key FROM failure_logs")
            )
            matching_keys = set()
            for row in all_logs_result:
                try:
                    page_id = PageId.from_key(row[0])
                    if page_id.state in states:
                        matching_keys.add(row[0])
                except ValueError:
                    continue

            if matching_keys:
                placeholders = ",".join([f":key{i}" for i in range(len(matching_keys))])
                key_params = {f"key{i}": key for i, key in enumerate(matching_keys)}
                conditions.append(f"record_key IN ({placeholders})")
                params.update(key_params)
            else:
                # No matching keys, return empty
                return []

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY created_at DESC"

        if limit:
            query += f" LIMIT {limit}"

        result = session.execute(text(query), params)
        return [
            {
                "record_key": row[0],
                "batch_id": row[1],
                "attempt_number": row[2],
                "error_type": row[3] or "Unknown",
                "error_message": row[4] or "",
                "model_name": row[5] or "",
                "prompt_name": row[6] or "",
                "created_at": row[7].isoformat() if row[7] else "",
            }
            for row in result
        ]


def export_to_csv(output_path: str, states: list[str] | None = None) -> None:
    """Export failure logs to CSV."""
    logs = get_failure_logs(states=states)
    if not logs:
        print("No failure logs to export")
        return

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "record_key",
                "batch_id",
                "attempt_number",
                "error_type",
                "error_message",
                "model_name",
                "prompt_name",
                "created_at",
            ],
        )
        writer.writeheader()
        writer.writerows(logs)

    print(f"Exported {len(logs)} failure logs to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze failure reasons from the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show summary statistics",
    )
    parser.add_argument(
        "--by-error-type",
        action="store_true",
        help="Show failures grouped by error type",
    )
    parser.add_argument(
        "--by-state",
        action="store_true",
        help="Show failures grouped by state",
    )
    parser.add_argument(
        "--by-school",
        action="store_true",
        help="Show failures grouped by school",
    )
    parser.add_argument(
        "--record-key",
        help="Show detailed logs for a specific record key",
    )
    parser.add_argument(
        "--states",
        nargs="+",
        help="Filter by states",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of results",
    )
    parser.add_argument(
        "--export-csv",
        help="Export failure logs to CSV file",
    )

    args = parser.parse_args()

    # If no specific action is requested, show summary
    if not any(
        [
            args.summary,
            args.by_error_type,
            args.by_state,
            args.by_school,
            args.record_key,
            args.export_csv,
        ]
    ):
        args.summary = True

    if args.summary:
        summary = get_failure_summary()
        print("\n=== Failure Summary ===")
        print(f"Total failure counts: {summary['total_failure_counts']}")
        print(f"Total failure logs: {summary['total_failure_logs']}")
        print(f"Records with failures: {summary['records_with_failures']}")
        print(f"Max retry count: {summary['max_retry_count']}")

    if args.by_error_type:
        error_types = get_failures_by_error_type()
        print("\n=== Failures by Error Type ===")
        for error_type, count in error_types.items():
            print(f"  {error_type}: {count}")

    if args.by_state:
        state_counts = get_failures_by_state()
        print("\n=== Failures by State ===")
        for state, count in state_counts.items():
            print(f"  {state}: {count}")

    if args.by_school:
        school_counts = get_failures_by_school(
            state=args.states[0] if args.states else None
        )
        print("\n=== Failures by School ===")
        for school, count in list(school_counts.items())[:20]:  # Show top 20
            print(f"  {school}: {count}")
        if len(school_counts) > 20:
            print(f"  ... and {len(school_counts) - 20} more schools")

    if args.record_key:
        logs = get_failure_logs(record_key=args.record_key)
        print(f"\n=== Failure Logs for {args.record_key} ===")
        if not logs:
            print("  No failure logs found")
        else:
            for log in logs:
                print(f"\n  Attempt {log['attempt_number']}:")
                print(f"    Batch ID: {log['batch_id']}")
                print(f"    Error Type: {log['error_type']}")
                print(f"    Error Message: {log['error_message'][:200]}...")
                print(f"    Model: {log['model_name']}")
                print(f"    Prompt: {log['prompt_name']}")
                print(f"    Created At: {log['created_at']}")

    if args.export_csv:
        export_to_csv(args.export_csv, states=args.states)


if __name__ == "__main__":
    # Example usage patterns
    import sys

    if len(sys.argv) == 1:
        print("Usage examples:")
        print("  # Show summary statistics")
        print("  python scripts/analyze_failures.py --summary")
        print()
        print("  # Show failures by error type")
        print("  python scripts/analyze_failures.py --by-error-type")
        print()
        print("  # Show failures by state")
        print("  python scripts/analyze_failures.py --by-state")
        print()
        print("  # Show detailed logs for a specific record")
        print(
            '  python scripts/analyze_failures.py --record-key "California:LincolnHigh:2023:4"'
        )
        print()
        print("  # Show failures for a specific state")
        print("  python scripts/analyze_failures.py --states California")
        print()
        print("  # Export failures to CSV")
        print("  python scripts/analyze_failures.py --export-csv failures.csv")
        sys.exit(0)

    main()
