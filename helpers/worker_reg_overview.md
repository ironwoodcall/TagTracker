# Worker Registration Helpers Overview

This folder includes three scripts that turn TagTracker registration activity and a Sling schedule export into tabular summaries suitable for spreadsheet analysis.

## Scripts

- `worker_reg.py`
  - One-step orchestrator for the full flow.  Using this will orchestrate everything else.
  - Takes `--echo` file(s) and `--shifts` export CSV file(s), creates intermediate CSVs in a temp folder, and invokes `worker_reg_make_summary.py`.
  - Forwards summary flags (for example: `--by-month`, `--report-unassigned`, `-o/--output`).

- `worker_reg_process_echo_files.py`
  - Reads TagTracker ECHO transcript files.
  - Extracts successful `reg/register` commands and converts them into a CSV with `DATE,TIME,REGISTRATIONS` (delta) rows.

- `worker_reg_process_shift_export.py`
  - Reads one or more Sling schedule CSV exports (one column per date, one row per person).
  - Emits a normalized shift CSV with `PERSON,DATE,START_TIME,END_TIME` rows.
  - Filters to shifts labeled `CoV Bike Valet Attendant` and ignores availability/callout blocks.

- `worker_reg_make_summary.py`
  - Combines the normalized shift CSV with the registration activity CSV.
  - Produces four tables:
    - Person metrics (points, shifts, hours, registrations per hour).
    - Team metrics (pairwise registrations per hour for exact two-person overlaps).
    - Registration log with worker assignments.
    - Coverage warnings for any shift period with worker counts other than two
      when those segments contain at least one registration event.
  - Also prints coverage warnings to stderr (with registration deltas and worker initials).

## Typical Data Flow

1. Start with TagTracker ECHO transcript files and one or more Sling schedule export CSVs.
2. - Run `worker_reg.py --echo <echo1> [<echo2> ...] --shifts <shift_export1.csv> [<shift_export2.csv> ...] [summary flags]`.
- Example:
  - `python3 helpers/worker_reg.py --echo ~/echo/*.txt --shifts shifts_jan.csv shifts_feb.csv --by-month -o summary.csv`

Output tables can be written to stdout or to files. Use the `--by-month` option to emit separate tables per month if desired.

## Alternative piece-by-pice flow (or for debugging)

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

