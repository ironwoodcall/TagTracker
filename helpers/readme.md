These are fiddly little one-time or
seldom-use scripts to troubleshoot or
to help with change management, or rebuilding the
past, etc

For any that want to import tagtracker modules,
be sure to put the parent dir on the path:
```
import sys
sys.path.append("../")
```

## What's here

### Reconstructing data from transcripts
- `transcript_sim.py` -- shared parser/simulator: replays an ECHO
  transcript's check-in/out, undo/redo, delete/edit, suspend and
  registration confirmation lines into an in-memory picture of the
  day's final state. Not run directly; the two scripts below render it.
  See `docs/recreate-datafile-from-transcript.md` for the design.
- `transcript_to_datafile.py` -- builds a TagTracker JSON datafile
  directly from an ECHO transcript (tags in/out, registrations, hours,
  notes), for a day whose real datafile is missing or lost.
- `transcript_to_playback.py` -- builds a minimal `in`/`out`/`reg`
  command script from an ECHO transcript, meant to be pasted or piped
  into a live `tagtracker.py` session to reproduce the same end state.

### Datafile / database tools
- `csv2tracker.py` -- converts a spreadsheet CSV export (the old
  tracking-sheet format) into a TagTracker datafile.
- `compare_datafiles.py` -- compares same-named datafiles in different
  folders and reports leftover counts as CSV; useful for spotting
  dataflow problems.
- `bike_event_summary.py` -- reads one JSON datafile and prints a
  running on-site total at each arrival/departure event, for
  analysis/debugging.
- `fix-hours.py` -- one-time script to backfill service hours into
  historic datafiles that predate that field (delete once no longer
  needed).
- `db_from_reg_archive.py` -- loads archived day-end registration counts
  (date, registrations, reported-leftovers CSV) into the DAY table of
  the database.
- `convert_db_to_hms.sql` -- one-time SQL migration adding
  minutes-since-midnight columns to the VISIT table, derived from its
  existing HH:MM(:SS) time columns.
- `valet_hours_check.py` -- scans the database for hours that look
  wrong (e.g. closing before opening).

### Analysis / modeling
- `busiest_days_analysis.py` -- finds each day's busiest sliding time
  window (default 30 min) of activity from the database.
- `schedule_model_sweep.py` -- throwaway experiment runner: rolling
  backtests of the schedule-driven predictor under different modeling
  options, to help pick a configuration (needs pandas/scikit-learn).

### Worker registration pipeline
- `worker_reg.py`, `worker_reg_make_summary.py`,
  `worker_reg_process_echo_files.py`, `worker_reg_process_shift_export.py`
  -- turn ECHO transcripts' registration activity plus a Sling schedule
  export into spreadsheet-ready summary tables. `worker_reg.py` is the
  one-step orchestrator; the others are the pipeline stages it calls.
  See `worker_reg_overview.md` for the full writeup.

### Dev smoke-tests
Not a pytest suite (this repo doesn't have one) -- standalone scripts
that drive a synthetic day through the real command parser and assert
the result matches the relevant spec doc. Run directly, e.g.
`python3 helpers/test_undo_redo.py`.
- `test_undo_redo.py` -- walks through UNDO/REDO per
  `docs/undo_redo_spec.md`.
- `test_hold.py` -- walks through HOLD/UNHOLD per
  `docs/hold_tag_spec.md`.
- `test_new_commands.py` -- interactive playground for experimenting
  with command-parsing specs while the real parser is still in flux.

### Misc one-offs
- `file_duplicates_md5.py` -- finds duplicate files under one or more
  directories by MD5 hash (usage: `this_program dir [dir..]`).
- `colorama_colours.py` -- vendored colorama demo script; prints a grid
  of all terminal colours/brightnesses, unrelated to TagTracker itself.
- `internet-check.html` -- standalone page for an operator's laptop to
  watch its internet connection and reachability of the TagTracker
  server, since it re-checks continuously rather than caching a stale
  "OK".


