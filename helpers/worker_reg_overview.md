# Worker Registration Helpers Overview

This folder includes scripts that turn TagTracker registration activity and a Sling schedule export into tabular summaries suitable for spreadsheet analysis.

## Scripts

### Main Script
- `worker_reg.py`
  - One-step orchestrator for the full flow.
  - Takes `--echo` file(s) and `--shifts` export CSV file(s), creates intermediate CSVs in a temp folder, and invokes `worker_reg_make_summary.py`.
  - Forwards summary flags (`--by-month`, `--report-unassigned`, `-o/--output`).
  - Captures upstream stderr warnings/notes from preprocessing and passes them into the final workbook notes tab.

### Supporting Scripts

- `worker_reg_process_echo_files.py`
  - Reads TagTracker ECHO transcript files.
  - Extracts successful `reg/register` commands and converts them into a CSV with `DATE,TIME,REGISTRATIONS` (delta) rows.

- `worker_reg_process_shift_export.py`
  - Reads one or more Sling schedule CSV exports (one column per date, one row per person).
  - Emits a normalized shift CSV with `PERSON,DATE,START_TIME,END_TIME` rows.
  - Filters to shifts labeled `CoV Bike Valet Attendant` and ignores availability/callout blocks.

- `worker_reg_make_summary.py`
  - Combines the normalized shift CSV with the registration activity CSV.
  - Constrains analysis to the shared date window where both shift coverage and registration events exist.
  - Produces worker/team/register summary tables.
  - When `-o/--output` is used, writes one `.xlsx` workbook:
    - `Workers` tab (points, shifts, hours, registrations per hour).
    - `Teams` tab (pairwise registrations per hour for exact two-person overlaps).
    - `Reg Log` tab (registration events with worker assignments).
    - `Warnings∕Notes` tab containing:
      - run timestamp
      - upstream warnings/notes (stderr)
      - suppressed months
      - dates with no matching shifts
      - worker-count mismatch lines
      - input files list (at the bottom)
  - In `--by-month` mode, month tabs are omitted when that month has zero registration events.
  - Numeric columns are written as numeric cells (not text) for spreadsheet compatibility.
  - Also prints coverage warnings to stderr (with registration deltas and worker initials).

## Typical Data Flow

1. Start with TagTracker ECHO transcript files and one or more Sling schedule export CSVs.
2. Run `worker_reg.py --echo <echo1> [<echo2> ...] --shifts <shift_export1.csv> [<shift_export2.csv> ...] [summary flags]`.
3. Example:
   - `python3 helpers/worker_reg.py --echo ~/echo/*.txt --shifts shifts_jan.csv shifts_feb.csv --by-month -o summary.xlsx`

Output tables can be written to stdout (CSV-style) or to a single `.xlsx` workbook when `-o/--output` is provided. Use the `--by-month` option to emit separate month-specific tabs.

## Alternative piece-by-piece flow (or for debugging)

1. Start with TagTracker ECHO transcript files and one or more Sling schedule export CSVs.
2. Convert ECHO transcripts into a registration activity CSV:
   - Run `worker_reg_process_echo_files.py` on the ECHO files.
   - Save the output as `registrations.csv`.
3. Convert the Sling schedule export(s) into a normalized shift CSV:
   - Run `worker_reg_process_shift_export.py` on one or more Sling exports.
   - Save the output as `shifts.csv`.
4. Merge shifts and registration activity:
   - Run `worker_reg_make_summary.py` with the shift CSV and the registrations CSV.
   - Load the resulting tables into a spreadsheet for analysis.
