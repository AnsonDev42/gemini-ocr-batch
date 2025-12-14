# Utility Scripts

This directory contains utility scripts for managing the Gemini OCR batch system.

## Scripts

### 1. `clear_failure_counts.py`

Clear failure counts from the database with flexible filtering options.

**Usage:**
```bash
# Clear all failure counts
python clear_failure_counts.py --all

# Clear failure counts for specific states
python clear_failure_counts.py --states California Texas

# Clear failure counts for specific schools
python clear_failure_counts.py --states California --schools LincolnHigh RooseveltHigh

# Clear failure counts for a year range
python clear_failure_counts.py --states California --year-start 2020 --year-end 2023

# Dry run to see what would be cleared
python clear_failure_counts.py --states California --dry-run
```

**Options:**
- `--all`: Clear all failure counts (ignores other filters)
- `--states`: List of states to filter by
- `--schools`: List of schools to filter by (requires --states)
- `--year-start`: Minimum year to include
- `--year-end`: Maximum year to include
- `--dry-run`: Show what would be deleted without actually deleting

### 2. `analyze_failures.py`

Analyze failure reasons and patterns from the database.

**Usage:**
```bash
# Show summary statistics
python analyze_failures.py --summary

# Show failures grouped by error type
python analyze_failures.py --by-error-type

# Show failures grouped by state
python analyze_failures.py --by-state

# Show failures grouped by school
python analyze_failures.py --by-school

# Show detailed logs for a specific record
python analyze_failures.py --record-key "California:LincolnHigh:2023:4"

# Show failures for specific states
python analyze_failures.py --states California Texas

# Export failures to CSV
python analyze_failures.py --export-csv failures.csv
```

**Options:**
- `--summary`: Show summary statistics
- `--by-error-type`: Group failures by error type
- `--by-state`: Group failures by state
- `--by-school`: Group failures by school
- `--record-key`: Show detailed logs for a specific record key
- `--states`: Filter by states
- `--limit`: Limit number of results
- `--export-csv`: Export failure logs to CSV file

### 3. `nuke_database.py`

Completely clear/reset the database. ⚠️ **Use with caution!**

**Usage:**
```bash
# Dry run to see what would be deleted
python nuke_database.py --dry-run

# Actually delete everything (interactive confirmation)
python nuke_database.py

# Delete everything without confirmation prompt
python nuke_database.py --confirm

# Delete everything and recreate tables
python nuke_database.py --confirm --recreate-tables
```

**Options:**
- `--dry-run`: Show what would be deleted without actually deleting
- `--confirm`: Skip confirmation prompt (use with caution!)
- `--recreate-tables`: Drop and recreate all tables after clearing

**What gets deleted:**
- All active batches
- All batch record keys
- All inflight records
- All failure counts
- All failure logs

## Common Use Cases

### Re-running a book after deleting output files

1. Delete the output folder for the book
2. Clear failure counts for that book:
   ```bash
   python clear_failure_counts.py --states <state> --schools <school> --year-start <year> --year-end <year>
   ```
3. Run the flow: `uv run python -m src run-once`

### Unblocking pages that exceeded max retries

```bash
# Clear failure counts for a specific state
python clear_failure_counts.py --states California

# Or clear all failure counts
python clear_failure_counts.py --all
```

### Analyzing why pages are failing

```bash
# Get an overview
python analyze_failures.py --summary

# See what error types are most common
python analyze_failures.py --by-error-type

# See which states have the most failures
python analyze_failures.py --by-state

# Export to CSV for deeper analysis
python analyze_failures.py --export-csv failures.csv
```

### Starting fresh

```bash
# Clear everything and start over
python nuke_database.py --confirm --recreate-tables
```
