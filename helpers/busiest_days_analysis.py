#!/usr/bin/env python3
"""
busiest_days_analysis.py

Analyze bicycle parking activity in a SQLite database to find, for every
day, the busiest sliding time window (default 30 minutes) of "activity"
events.

Three independent rankings are produced:
    1. Bikes In   -- arrival events only   (time_in)
    2. Bikes Out  -- departure events only (time_out)
    3. Combined   -- all events (arrivals + departures together)

For each rank position (1..top_n, default 4), three rows are shown:
    - the day/window that had the Nth-most Bikes In activity
    - the day/window that had the Nth-most Bikes Out activity
    - the day/window that had the Nth-most Combined activity

Each row reports ALL THREE counts (In, Out, Combined) for that row's
specific date/window -- not just the metric it was ranked on. So a
"Bikes In" row shows its window's arrival count (the metric that earned
it that rank) alongside however many departures happened to occur
during that same window, for context.

Usage:
    python busy3.py <database.sqlite> [window_minutes] [top_n]

Example:
    python busy3.py mydatabase.sqlite 30 4
"""

import sys
import sqlite3
from collections import defaultdict

MINUTES_PER_DAY = 24 * 60  # 1440
DEFAULT_WINDOW = 30
DEFAULT_TOP_N = 4


# --------------------------------------------------------------------------
# Time helpers
# --------------------------------------------------------------------------

def hhmm_to_minutes(time_str):
    """
    Convert a time string like 'HH:MM' or 'HH:MM:SS' into an integer number
    of minutes after midnight.

    Returns None if the string cannot be parsed, is empty/None, or the
    resulting minute value is outside the valid 0..1439 range.
    """
    if not time_str:
        return None
    try:
        parts = time_str.strip().split(':')
        if len(parts) < 2:
            return None
        hours = int(parts[0])
        minutes = int(parts[1])
        total = hours * 60 + minutes
        if total < 0 or total >= MINUTES_PER_DAY:
            # Clamp times that spuriously roll into/after the next day
            # (e.g. a bad time_out) rather than crashing the whole run.
            total = max(0, min(MINUTES_PER_DAY - 1, total))
        return total
    except (ValueError, IndexError):
        return None


def minutes_to_hhmm(total_minutes):
    """Convert an integer minute-of-day value back into 'HH:MM' format."""
    total_minutes = max(0, min(MINUTES_PER_DAY, total_minutes))
    hours, minutes = divmod(total_minutes, 60)
    if hours == 24:
        return "24:00"
    return "%02d:%02d" % (hours, minutes)


# --------------------------------------------------------------------------
# Data loading
# --------------------------------------------------------------------------

def load_days(conn):
    """
    Load all DAY rows and return a dict keyed by day_id:
        day_id -> {
            'date': str,
            'open_min': int,
            'close_min': int,
        }

    Days with missing or unparsable time_open / time_closed values are
    skipped entirely (they cannot contribute a valid in-hours window).
    """
    days = {}
    cur = conn.cursor()
    cur.execute("SELECT id, date, time_open, time_closed FROM DAY")
    for day_id, date, time_open, time_closed in cur.fetchall():
        open_min = hhmm_to_minutes(time_open)
        close_min = hhmm_to_minutes(time_closed)
        if open_min is None or close_min is None:
            continue
        if close_min <= open_min:
            continue
        days[day_id] = {
            'date': date,
            'open_min': open_min,
            'close_min': close_min,
        }
    return days


def load_visits(conn, valid_day_ids):
    """
    Load all VISIT rows belonging to the given set of valid day_ids and
    group them by day_id.

    Returns: dict day_id -> list of (time_in_str, time_out_str)
    """
    visits_by_day = defaultdict(list)
    cur = conn.cursor()
    cur.execute("SELECT day_id, time_in, time_out FROM VISIT")
    for day_id, time_in, time_out in cur.fetchall():
        if day_id not in valid_day_ids:
            continue
        visits_by_day[day_id].append((time_in, time_out))
    return visits_by_day


# --------------------------------------------------------------------------
# Histogram construction
# --------------------------------------------------------------------------

def build_histograms(visits):
    """
    Given the list of (time_in, time_out) tuples for a single day, build
    three minute-resolution activity histograms covering the whole day
    (index 0..1439 = minutes after midnight):

        arrivals[minute]   -> count of bikes arriving (time_in) that minute
        departures[minute] -> count of bikes leaving   (time_out) that minute
        combined[minute]   -> arrivals[minute] + departures[minute]

    Each visit contributes:
        - exactly one arrival event at time_in (always present, NOT NULL)
        - one departure event at time_out, ONLY if time_out is present
    """
    arrivals = [0] * MINUTES_PER_DAY
    departures = [0] * MINUTES_PER_DAY
    combined = [0] * MINUTES_PER_DAY

    for time_in, time_out in visits:
        in_min = hhmm_to_minutes(time_in)
        if in_min is not None:
            arrivals[in_min] += 1
            combined[in_min] += 1

        if time_out:
            out_min = hhmm_to_minutes(time_out)
            if out_min is not None:
                departures[out_min] += 1
                combined[out_min] += 1

    return arrivals, departures, combined


def build_prefix_sums(histogram):
    """
    Build a prefix-sum array of length MINUTES_PER_DAY + 1 such that
        prefix[i] = sum(histogram[0:i])

    Lets us compute the sum of any window [s, s+window) in O(1) time.
    """
    prefix = [0] * (MINUTES_PER_DAY + 1)
    running = 0
    for i in range(MINUTES_PER_DAY):
        running += histogram[i]
        prefix[i + 1] = running
    return prefix


def window_sum(prefix, start, window):
    """Return the sum of a histogram (via its prefix array) over
    [start, start + window)."""
    return prefix[start + window] - prefix[start]


# --------------------------------------------------------------------------
# Sliding-window search
# --------------------------------------------------------------------------

def find_best_window(prefix, open_min, close_min, window):
    """
    Find the busiest `window`-minute sliding window that fits entirely
    within [open_min, close_min), given a precomputed prefix-sum array,
    using O(1) per-window evaluation.

    Tie-breaking: earliest start time wins (only strict improvements
    replace the current best as we scan start times in increasing order).

    Returns (best_count, best_start_minute) or (None, None) if no window
    fits inside the open hours.
    """
    last_start = close_min - window
    if last_start < open_min:
        return None, None

    best_count = -1
    best_start = None
    for start in range(open_min, last_start + 1):
        count = window_sum(prefix, start, window)
        if count > best_count:
            best_count = count
            best_start = start

    return best_count, best_start


# --------------------------------------------------------------------------
# Main analysis driver
# --------------------------------------------------------------------------

def analyze(days, visits_by_day, window, top_n):
    """
    For every day, find each category's busiest window. For that specific
    window, also compute the OTHER two categories' counts (so each result
    row is self-contained: date, window, in-count, out-count, combined-
    count). Then rank each category's list independently and truncate to
    top_n.

    Returns a dict of three lists, each entry a tuple:
        (date, start_min, window, in_count, out_count, combined_count)
    sorted by descending count of that list's own category (ties broken
    by date), truncated to top_n:
        {
            'Bikes In':  [...],
            'Bikes Out': [...],
            'In & Out':  [...],
        }
    """
    results = {'Bikes In': [], 'Bikes Out': [], 'In & Out': []}

    for day_id, day_info in days.items():
        visits = visits_by_day.get(day_id, [])
        arrivals_hist, departures_hist, combined_hist = build_histograms(visits)

        arrivals_prefix = build_prefix_sums(arrivals_hist)
        departures_prefix = build_prefix_sums(departures_hist)
        combined_prefix = build_prefix_sums(combined_hist)

        open_min = day_info['open_min']
        close_min = day_info['close_min']
        date = day_info['date']

        # Find each category's own best window, then look up what the
        # OTHER two categories' counts were during that same window.
        category_prefixes = {
            'Bikes In': arrivals_prefix,
            'Bikes Out': departures_prefix,
            'In & Out': combined_prefix,
        }

        for label, own_prefix in category_prefixes.items():
            count, start = find_best_window(own_prefix, open_min, close_min, window)
            if count is None:
                # Open period shorter than window -- skip this day/category.
                continue

            in_count = window_sum(arrivals_prefix, start, window)
            out_count = window_sum(departures_prefix, start, window)
            combined_count = window_sum(combined_prefix, start, window)

            results[label].append(
                (date, start, window, in_count, out_count, combined_count)
            )

    # Rank each category by ITS OWN metric (index 3=in, 4=out, 5=combined),
    # ties broken by date ascending for deterministic output.
    metric_index = {'Bikes In': 3, 'Bikes Out': 4, 'In & Out': 5}
    for label in results:
        idx = metric_index[label]
        results[label].sort(key=lambda r: (-r[idx], r[0]))
        results[label] = results[label][:top_n]

    return results


# --------------------------------------------------------------------------
# Output formatting
# --------------------------------------------------------------------------

def ordinal(n):
    """Return an integer's ordinal representation as a string."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def print_report(results, window, top_n):
    """
    Print results interleaved by rank. For each rank position 1..top_n,
    print a header followed by three rows -- Bikes In, Bikes Out, and
    Combined -- each row showing the date/window that earned that rank
    for its category, along with ALL THREE counts (in, out, combined)
    observed during that specific window.

    A category with fewer valid days than top_n shows "N/A" for that rank.
    """
    col_header = "%-12s %-12s %-14s %-6s %-6s %s" % (
        "Category", "Date", "Window", "In", "Out", "In & Out"
    )

    for rank in range(top_n):
        if rank > 0:
            print()  # blank line between rank groups
        ordinal_str = ordinal(rank+1) if rank > 0 else "The"

        print(f"{ordinal_str} busiest days, based on activity in a {window} minute window:")
        print(col_header)
        print("-" * len(col_header))

        for label in ("Bikes In", "Bikes Out", "In & Out"):
            entries = results[label]
            if rank < len(entries):
                date, start, window, in_count, out_count, combined_count = entries[rank]
                window_str = "%s-%s" % (
                    minutes_to_hhmm(start),
                    minutes_to_hhmm(start + window),
                )
                print(
                    "%-12s %-12s %-14s %3d    %3d    %3d"
                    % (label, date, window_str, in_count, out_count, combined_count)
                )
            else:
                print(
                    "%-12s %-12s %-14s %3s    %3s    %3s"
                    % (label, "N/A", "N/A", "N/A", "N/A", "N/A")
                )

# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def parse_args(argv):
    """
    Parse and validate command-line arguments.

    Expected:
        argv[1] -> path to SQLite database file (required)
        argv[2] -> window size in minutes (optional, default 30)
        argv[3] -> top N ranks to display (optional, default 4)

    Exits with a usage message on invalid input.
    """
    if len(argv) < 2 or len(argv) > 4:
        sys.stderr.write(
            "Usage: python busy3.py <database.sqlite> [window_minutes] [top_n]\n"
        )
        sys.exit(1)

    db_path = argv[1]

    window = DEFAULT_WINDOW
    if len(argv) >= 3:
        try:
            window = int(argv[2])
        except ValueError:
            sys.stderr.write(
                "Error: window_minutes must be an integer (got %r)\n" % argv[2]
            )
            sys.exit(1)

    if window <= 0 or window > MINUTES_PER_DAY:
        sys.stderr.write(
            "Error: window_minutes must be between 1 and %d (got %d)\n"
            % (MINUTES_PER_DAY, window)
        )
        sys.exit(1)

    top_n = DEFAULT_TOP_N
    if len(argv) == 4:
        try:
            top_n = int(argv[3])
        except ValueError:
            sys.stderr.write(
                "Error: top_n must be an integer (got %r)\n" % argv[3]
            )
            sys.exit(1)

    if top_n <= 0:
        sys.stderr.write("Error: top_n must be a positive integer (got %d)\n" % top_n)
        sys.exit(1)

    return db_path, window, top_n


def main():
    db_path, window, top_n = parse_args(sys.argv)

    try:
        # conn = sqlite3.connect(db_path)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        sys.stderr.write("Error opening database %r: %s\n" % (db_path, exc))
        sys.exit(1)

    try:
        days = load_days(conn)
        if not days:
            print("No days with valid open/close times found; nothing to analyze.")
            return

        visits_by_day = load_visits(conn, set(days.keys()))

        results = analyze(days, visits_by_day, window, top_n)
        print_report(results, window, top_n)
    finally:
        conn.close()


if __name__ == "__main__":
    main()