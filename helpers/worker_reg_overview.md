# Worker Registration Helpers Overview

This folder includes three scripts that turn TagTracker registration activity and a Sling schedule export into tabular summaries suitable for spreadsheet analysis.

## Scripts

- `worker_reg_process_echo_files.py`
  - Reads TagTracker ECHO transcript files.
  - Extracts successful `reg/register` commands and converts them into a CSV with `DATE,TIME,REGISTRATIONS` (delta) rows.

- `worker_reg_process_shift_export.py`
  - Reads a Sling schedule CSV export (one column per date, one row per person).
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

1. Start with TagTracker ECHO transcript files and a Sling schedule export CSV.
2. Convert ECHO transcripts into a registration activity CSV:
   - Run `worker_reg_process_echo_files.py` on the ECHO files.
   - Save the output as `registrations.csv`.
3. Convert the Sling schedule export into a normalized shift CSV:
   - Run `worker_reg_process_shift_export.py` on the Sling export.
   - Save the output as `shifts.csv`.
4. Merge shifts and registration activity:
   - Run `worker_reg_make_summary.py` with the shift CSV and the registrations CSV.
   - Load the resulting tables into a spreadsheet for analysis.

Output tables can be written to stdout or to files. Use the `--by-month` option to emit separate tables per month if desired.
