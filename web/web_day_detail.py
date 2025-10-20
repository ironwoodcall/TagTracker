#!/usr/bin/env python3
"""HTML report on tags in/out for one day.

Copyright (C) 2023-2025 Julias Hocking & Todd Glover

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""

import html
import math
import sqlite3
from dataclasses import dataclass

import common.tt_dbutil as db
from common.tt_tag import TagID
from common.tt_time import VTime
import common.tt_util as ut
from common.tt_daysummary import DayTotals, PeriodDetail
from common.tt_statistics import VisitStats
import common.tt_constants as k
import web_common as cc
import datacolors as dc
import web.web_estimator as web_estimator
import web_histogram
from web.web_base_config import EST_TYPE_FOR_ONEDAY_SUMMARY, HIST_FIXED_Y_AXIS_FULLNESS
try:
    from common.commuter_hump import CommuterHumpAnalyzer
except ImportError:  # pragma: no cover - optional dependency
    CommuterHumpAnalyzer = None


HIGHLIGHT_NONE = 0
HIGHLIGHT_WARN = 1
HIGHLIGHT_ERROR = 2
HIGHLIGHT_MAYBE_ERROR = 3
BAR_MARKERS = {"R": chr(0x25CF), "O": chr(0x25A0)}
BAR_MARKER_FUTURE = chr(0x2011)
BAR_COL_WIDTH = 80


def _nav_buttons(ttdb, orgsite_id: int, thisday: str, pages_back) -> str:
    """Make nav buttons for the one-day report."""

    def find_prev_next_date(current_date, direction):
        """Return member after (or before) current_date in sorted all_dates."""
        # Check if the list of dates is empty
        if not all_dates:
            return None  # Return None if the list is empty

        # Check if the current date is within the range of dates
        if current_date < all_dates[0]:
            return all_dates[0] if direction == 1 else None
        elif current_date > all_dates[-1]:
            return all_dates[-1] if direction == -1 else None

        # Binary search for the closest date
        low, high = 0, len(all_dates) - 1
        while low <= high:
            mid = (low + high) // 2
            if all_dates[mid] == current_date:
                return (
                    all_dates[mid + direction]
                    if mid + direction >= 0 and mid + direction < len(all_dates)
                    else None
                )
            elif all_dates[mid] < current_date:
                low = mid + 1
            else:
                high = mid - 1

        # If the current date is not found, return the closest date based on direction
        if direction == 1:
            return all_dates[low] if low < len(all_dates) else None
        else:
            return all_dates[high] if high >= 0 else None

    def prev_next_button(label, offset) -> str:
        # target = adjacent_date(thisday,offset)
        target = find_prev_next_date(thisday, offset)
        if target is None:
            return f"""
                <button type="button" disabled
                    style="opacity: 0.5; cursor: not-allowed;">
                {label}</button>
                """
        link = cc.selfref(
            what=cc.WHAT_ONE_DAY,
            qdate=target,
            pages_back=cc.increment_pages_back(pages_back),
        )
        return f"""
            <button type="button"
            onclick="window.location.href='{link}';">{label}</button>
            """

    def today_button(label) -> str:
        # target = ut.date_str("today")
        if ut.date_str("today") == thisday:
            return f"""
                <button type="button" disabled
                    style="opacity: 0.5; cursor: not-allowed;">
                {label}</button>
                """
        link = cc.selfref(
            what=cc.WHAT_ONE_DAY,
            qdate='today',
            pages_back=cc.increment_pages_back(pages_back),
        )
        return f"""
            <button type="button"
            onclick="window.location.href='{link}';">{label}</button>
            """

    dbrows = db.db_fetch(
        ttdb, f"SELECT DATE FROM DAY WHERE ORGSITE_ID = '{orgsite_id}' ORDER BY DATE "
    )
    all_dates = sorted([r.date for r in dbrows])

    buttons = f"{cc.main_and_back_buttons(pages_back)}&nbsp;&nbsp;&nbsp;&nbsp;"
    buttons += prev_next_button("Previous day", -1)
    buttons += prev_next_button("Next day", 1)
    buttons += today_button("Today")
    return buttons


def one_day_tags_report(
    ttdb: sqlite3.Connection,
    orgsite_id: int,
    whatday: str = "",
    sort_by: str = "",
    pages_back: int = 1,
):
    @dataclass
    class _VisitRow:
        tag: str = ""
        next_tag: str = ""
        bike_type: str = "?"
        time_in: str = ""
        next_time_in: str = ""
        time_out: str = ""
        duration: int = None

    thisday = ut.date_str(whatday)
    if not thisday:
        cc.bad_date(whatday)
    is_today = bool(thisday == ut.date_str("today"))
    if is_today:
        day_str = "Today"
    elif thisday == ut.date_str("yesterday"):
        day_str = "Yesterday"
    else:
        day_str = ut.date_str(thisday, dow_str_len=10)

    print(cc.titleize(f"{day_str}, {thisday} (detail)"))

    if not cc.called_by_self():
        pages_back = cc.NAV_MAIN_BUTTON

    print(_nav_buttons(ttdb, orgsite_id, thisday, pages_back))
    print("<br><br>")

    cursor = ttdb.cursor()
    day_id = db.fetch_day_id(cursor=cursor, date=thisday, maybe_orgsite_id=orgsite_id)
    if not day_id:
        print(f"<br>No information in database for {thisday}<br><br>")
        cursor.close()
        return

    day_data: DayTotals = db.fetch_day_totals(cursor=cursor, day_id=day_id)

    # In the code below, 'next_*' are empty placeholders
    sql = f"""
        select
           bike_id, bike_type,
           time_in, time_out, duration
        from visit
        where day_id = {day_id}
        order by bike_id asc
    """
    rows = cursor.execute(sql).fetchall()

    try:
        blocks = db.fetch_day_blocks(cursor=cursor, day_id=day_id)
    except k.TagTrackerError:
        blocks = None

    if not rows:
        cursor.close()
        return
    cursor.close()  # day_data.min_stay = VTime(min(durations)).tidy
    # if not rows:
    #     print(f"<pre>No activity recorded for {thisday}")
    #     sys.exit()

    visits = []
    for row in rows:
        visit = _VisitRow(
            tag=TagID(row[0]),
            bike_type=row[1],
            time_in=VTime(row[2]),
            time_out=VTime(row[3]),
            duration=row[4],
        )
        visits.append(visit)

    tags_used_count = len(set(v.tag for v in visits))

    # Process the rows
    stats = VisitStats([v.duration for v in visits])
    visits = sorted(visits, key=lambda x: x.tag)
    # rows = sorted(rows, key=lambda x: x.tag)
    # Calculate next_tag and next_time_in values
    for i, v in enumerate(visits):
        if i >= 1:
            visits[i - 1].next_time_in = v.time_in
            visits[i - 1].next_tag = v.tag

    # # leftovers = len([t.time_out for t in rows if t.time_out <= ""])
    # suspicious = len(
    #     [
    #         t.next_time_in
    #         for t in visits
    #         if t.next_time_in < t.time_in and t.time_out <= ""
    #     ]
    # )

    daylight = dc.Dimension()
    daylight.add_config(VTime("07:30").num, "LightSkyBlue")
    daylight.add_config(VTime("12:00").num, "LightCyan")
    daylight.add_config(VTime("16:00").num, "YellowGreen")
    daylight.add_config(VTime("22:00").num, "DarkOrange")

    highlights = dc.Dimension(interpolation_exponent=1)
    highlights.add_config(HIGHLIGHT_NONE, "white")
    highlights.add_config(HIGHLIGHT_WARN, "khaki")
    highlights.add_config(HIGHLIGHT_ERROR, "magenta")
    highlights.add_config(HIGHLIGHT_MAYBE_ERROR, "cyan")

    duration_colors = dc.Dimension()
    duration_colors.add_config(0, "white")
    duration_colors.add_config(VTime("1200").num, "teal")

    if not visits:
        print(f"No information in database for {thisday}")
        return

    print(
        "<div style='display:flex; flex-wrap:wrap; align-items:flex-start;'>"
    )
    print("<div style='flex:0 1 auto; min-width:260px; margin-right:1.5em;'>")

    commuter_mean = None
    commuter_confidence = None
    if not is_today and CommuterHumpAnalyzer is not None:
        try:
            analyzer = CommuterHumpAnalyzer(
                db_path=ttdb,
                start_date=thisday,
                end_date=thisday,
                days_of_week=(1, 2, 3, 4, 5, 6, 7),
            ).run()
        except Exception:
            analyzer = None
        if analyzer and not getattr(analyzer, "error", None):
            mean_value = getattr(analyzer, "mean_commuter_per_day", None)
            if mean_value is not None:
                try:
                    mean_value = float(mean_value)
                except (TypeError, ValueError):
                    mean_value = None
            if mean_value is not None and not math.isnan(mean_value):
                commuter_mean = mean_value
                commuter_confidence = analyzer.confidence_text(long_text=False)

    summary_html, prediction_html = summary_table(
        day_data,
        stats,
        tags_used_count,
        highlights,
        is_today,
        commuter_mean,
        commuter_confidence,
    )
    print(summary_html)
    print("</div>")

    print("<div style='flex:0 0 auto; min-width:260px; text-align:center;'>")
    print(day_activity_histogram(ttdb, thisday))
    fullness_hist = day_fullness_histogram(day_data, blocks)
    if fullness_hist:
        print("<div style='margin-top:0.75em;'>")
        print(fullness_hist)
        print("</div>")
    print("</div>")
    print("</div>")
    if prediction_html:
        print(prediction_html)
    # print("<br>")
    ##print("</div></div>")

    block_activity_table(thisday, day_data, blocks, is_today)
    # print("<br>")
    # legend_table(daylight, duration_colors)
    visits_table(
        thisday,
        is_today,
        visits,
        highlights,
        daylight,
        duration_colors,
        sort_by,
        pages_back,
    )


def day_activity_histogram(ttdb: sqlite3.Connection, today: str) -> str:
    """Return a mini activity histogram for the one day view."""

    orgsite_id = 1  # FIXME hardcoded orgsite_id
    graph_link = cc.selfref(
        what=cc.WHAT_ONE_DAY_FREQUENCIES,
        start_date=today,
        end_date=today,
        pages_back=1,
        text_note="one day",
    )
    return web_histogram.activity_hist_table(
        ttdb,
        orgsite_id=orgsite_id,
        start_date=today,
        end_date=today,
        mini=True,
        title=(
            f"<a href='{graph_link}' style='text-decoration:none; font-weight:bold;'>Activity graph</a>"
        ),
        link_target=graph_link,
    )


def day_fullness_histogram(day_data: DayTotals, blocks) -> str:
    """Render a mini histogram of bikes on hand during the day."""

    if not blocks:
        return ""

    def _as_vtime(value):
        return value if isinstance(value, VTime) else VTime(value)

    occupancy_points: list[tuple[VTime, int]] = []
    for block_start, block_detail in blocks.items():
        if not block_detail:
            continue
        v_start = _as_vtime(block_start)
        on_hand = getattr(block_detail, "num_on_hand", {})
        combined_on_hand = int(on_hand.get(k.COMBINED, 0) or 0) if on_hand else 0
        occupancy_points.append((v_start, max(combined_on_hand, 0)))

    occupancy_points.sort(
        key=lambda item: item[0].num if getattr(item[0], "num", None) is not None else 0
    )

    if not occupancy_points:
        return ""

    category_minutes = 30
    start_minutes = VTime("07:00").num
    end_minutes = VTime("22:00").num
    if start_minutes is None or end_minutes is None:
        return ""

    start_bucket = (start_minutes // category_minutes) * category_minutes
    end_bucket = (end_minutes // category_minutes) * category_minutes
    bucket_range = range(start_bucket, end_bucket + category_minutes, category_minutes)

    buckets_to_totals: dict[int, float] = {minute: 0.0 for minute in bucket_range}
    buckets_to_counts: dict[int, int] = {minute: 0 for minute in bucket_range}
    have_unders = have_overs = False

    for v_start, combined_on_hand in occupancy_points:
        minute_value = getattr(v_start, "num", None)
        if minute_value is None:
            continue
        bucket_minute = (minute_value // category_minutes) * category_minutes
        if bucket_minute < start_bucket:
            buckets_to_totals[start_bucket] += combined_on_hand
            buckets_to_counts[start_bucket] += 1
            have_unders = True
        elif bucket_minute > end_bucket:
            buckets_to_totals[end_bucket] += combined_on_hand
            buckets_to_counts[end_bucket] += 1
            have_overs = True
        else:
            buckets_to_totals.setdefault(bucket_minute, 0.0)
            buckets_to_counts.setdefault(bucket_minute, 0)
            buckets_to_totals[bucket_minute] += combined_on_hand
            buckets_to_counts[bucket_minute] += 1

    ordered_pairs: list[tuple[str, float]] = []
    for minute in bucket_range:
        vt = VTime(minute)
        if not vt:
            continue
        label = vt.tidy if hasattr(vt, "tidy") else str(vt)
        total = buckets_to_totals.get(minute, 0.0)
        count = buckets_to_counts.get(minute, 0)
        avg_value = total / count if count else 0.0
        ordered_pairs.append((label, avg_value))

    if not ordered_pairs:
        return ""

    if have_unders:
        start_label, start_value = ordered_pairs[0]
        ordered_pairs[0] = (f"{start_label}-", start_value)

    if have_overs:
        end_idx = len(ordered_pairs) - 1
        end_label, end_value = ordered_pairs[end_idx]
        ordered_pairs[end_idx] = (f"{end_label}+", end_value)

    histogram_data = dict(ordered_pairs)

    graph_link = cc.selfref(
        what=cc.WHAT_ONE_DAY_FREQUENCIES,
        start_date=day_data.date if day_data else "",
        end_date=day_data.date if day_data else "",
        pages_back=1,
        text_note="one day",
    )

    footer_label = "Graph of Bikes on Hand"
    if graph_link:
        footer_label = (
            f"<a href='{graph_link}' style='text-decoration:none; font-weight:bold;'>"
            f"Max bikes graph"
            "</a>"
        )

    open_marker_label = None
    close_marker_label = None
    if day_data:
        open_time = getattr(day_data, "time_open", None)
        close_time = getattr(day_data, "time_closed", None)
        if open_time:
            open_block = ut.block_start(open_time)
            if getattr(open_block, "tidy", None):
                open_marker_label = open_block.tidy
        if close_time and getattr(close_time, "num", None) is not None:
            close_block = ut.block_start(max(close_time.num - 1, 0))
            if getattr(close_block, "tidy", None):
                close_marker_label = close_block.tidy

    return web_histogram.html_histogram(
        histogram_data,
        mini=True,
        bar_color="darkcyan",
        title="",
        subtitle=footer_label,
        link_target=graph_link,
        max_value=HIST_FIXED_Y_AXIS_FULLNESS,
        open_marker_label=open_marker_label,
        close_marker_label=close_marker_label,
    )


def block_activity_table(
    thisday: str, day_data: DayTotals, blocks, is_today: bool
) -> None:
    """Render a half-hour activity summary using stored block data."""

    if not blocks:
        print("<p>Block activity summary not available for this day.</p>")
        return

    def _as_vtime(value):
        return value if isinstance(value, VTime) else VTime(value)

    block_items = sorted(
        ((_as_vtime(start), block) for start, block in blocks.items()),
        key=lambda item: (
            item[0].num if getattr(item[0], "num", None) is not None else 0
        ),
    )
    if not block_items:
        print("<p>Block activity summary not available for this day.</p>")
        return

    open_block = (
        ut.block_start(day_data.time_open) if day_data and day_data.time_open else None
    )
    close_block = (
        ut.block_start(day_data.time_closed)
        if day_data and day_data.time_closed
        else None
    )

    if block_items and close_block and not is_today:
        close_num = getattr(close_block, "num", None)
        if close_num is not None:
            blocks_by_start = {start: block for start, block in block_items}
            last_start = block_items[-1][0]
            last_num = getattr(last_start, "num", None)
            if last_num is not None and last_num < close_num:
                previous_block = block_items[-1][1]
                current_num = last_num
                while current_num < close_num:
                    current_num += k.BLOCK_DURATION
                    current_start = VTime(current_num)
                    if current_start in blocks_by_start:
                        previous_block = blocks_by_start[current_start]
                        continue
                    filler = PeriodDetail(time_start=current_start)
                    for bike_type in (k.REGULAR, k.OVERSIZE, k.COMBINED):
                        last_on_hand = previous_block.num_on_hand[bike_type]
                        filler.num_on_hand[bike_type] = last_on_hand
                        filler.num_fullest[bike_type] = last_on_hand
                        filler.time_fullest[bike_type] = current_start
                    blocks_by_start[current_start] = filler
                    previous_block = filler

                block_items = sorted(
                    blocks_by_start.items(),
                    key=lambda item: (
                        item[0].num if getattr(item[0], "num", None) is not None else 0
                    ),
                )

    rows_to_render = []
    cumulative_total_in = 0
    open_boundary_marked = False
    closed_boundary_marked = False

    print("<table class=general_table style='text-align:right'>")
    print(
        "<tr><th colspan=9 style='text-align:center'>Half-hourly activity"
        f" for {thisday}</th></tr>"
    )
    print(
        "<tr>"
        "<th rowspan=2>Time</th>"
        "<th colspan=3>Arrivals</th>"
        "<th colspan=3>Departures</th>"
        "<th rowspan=2>Visits<br>this day</th>"
        "<th rowspan=2>Max<br>bikes</th>"
        "</tr>"
    )
    print(
        "<tr>"
        "<th>Reglr</th>"
        "<th>Ovrsz</th>"
        "<th>Total</th>"
        "<th>Reglr</th>"
        "<th>Ovrsz</th>"
        "<th>Total</th>"
        "</tr>"
    )

    for block_start_vtime, block in block_items:
        block_start_num = block_start_vtime.num

        rg_in = block.num_incoming[k.REGULAR]
        ov_in = block.num_incoming[k.OVERSIZE]
        all_in = block.num_incoming[k.COMBINED]
        cumulative_total_in += all_in

        rg_out = block.num_outgoing[k.REGULAR]
        ov_out = block.num_outgoing[k.OVERSIZE]
        all_out = block.num_outgoing[k.COMBINED]

        block_max = block.num_fullest[k.COMBINED]
        end_on_hand = block.num_on_hand[k.COMBINED]
        start_on_hand = max(end_on_hand - all_in + all_out, 0)
        time_label = block_start_vtime.tidy

        add_boundary = False
        if (
            open_block
            and not open_boundary_marked
            and block_start_num >= open_block.num
        ):
            add_boundary = True
            open_boundary_marked = True

        if (
            close_block
            and not closed_boundary_marked
            and rows_to_render
            and block_start_num >= close_block.num
        ):
            add_boundary = True
            closed_boundary_marked = True

        rows_to_render.append(
            {
                "time_label": time_label,
                "rg_in": rg_in,
                "ov_in": ov_in,
                "all_in": all_in,
                "rg_out": rg_out,
                "ov_out": ov_out,
                "all_out": all_out,
                "total_in": cumulative_total_in,
                "block_max": block_max,
                "start_on_hand": start_on_hand,
                "end_on_hand": end_on_hand,
                "border_top": add_boundary,
            }
        )

    max_block_peak = max([row["block_max"] for row in rows_to_render] or [0])
    max_total_parked = max([row["total_in"] for row in rows_to_render] or [0])
    max_in_value = max(
        [max(row["rg_in"], row["ov_in"], row["all_in"]) for row in rows_to_render]
        or [0]
    )
    max_out_value = max(
        [max(row["rg_out"], row["ov_out"], row["all_out"]) for row in rows_to_render]
        or [0]
    )

    day_total_bikes_colors = dc.Dimension(
        interpolation_exponent=1.5, label="Bikes parked this day"
    )
    day_total_bikes_colors.add_config(0, "white")
    total_color_max = max(
        max_total_parked * 1.5,
        getattr(day_data, "num_parked_combined", 0) if day_data else 0,
    )
    if total_color_max > 0:
        day_total_bikes_colors.add_config(total_color_max, "green")

    day_full_colors = dc.Dimension(
        interpolation_exponent=1.5, label="Most bikes this day"
    )
    day_full_colors.add_config(0, "white")
    full_color_max = max(
        max_block_peak,
        getattr(day_data, "num_fullest_combined", 0) if day_data else 0,
    )
    if full_color_max > 0:
        day_full_colors.add_config(full_color_max, "teal")

    XY_BOTTOM_COLOR = dc.Color((252, 252, 248)).html_color
    X_TOP_COLOR = "red"
    Y_TOP_COLOR = "royalblue"

    max_activity_value = max(max_in_value, max_out_value)
    bikes_in_colors = dc.Dimension(interpolation_exponent=0.82, label="Bikes in")
    bikes_in_colors.add_config(0, XY_BOTTOM_COLOR)
    if max_activity_value > 0:
        bikes_in_colors.add_config(max_activity_value, X_TOP_COLOR)

    bikes_out_colors = dc.Dimension(interpolation_exponent=0.82, label="Bikes out")
    bikes_out_colors.add_config(0, XY_BOTTOM_COLOR)
    if max_activity_value > 0:
        bikes_out_colors.add_config(max_activity_value, Y_TOP_COLOR)

    def mix_styles(*parts) -> str:
        pieces = [p.strip().rstrip(";") for p in parts if p]
        return (";".join(pieces) + ";") if pieces else ""

    for row in rows_to_render:
        row_border = "border-top:3px solid black;" if row["border_top"] else ""
        base_style = mix_styles("text-align:right", row_border)
        in_style = lambda val: mix_styles(
            "text-align:right",
            row_border,
            bikes_in_colors.css_bg_fg(val),
        )
        out_style = lambda val: mix_styles(
            "text-align:right",
            row_border,
            bikes_out_colors.css_bg_fg(val),
        )
        total_style = mix_styles(
            "text-align:right",
            row_border,
            day_total_bikes_colors.css_bg_fg(row["total_in"]),
        )
        most_parts = [
            "text-align:right",
            row_border,
            day_full_colors.css_bg_fg(row["block_max"]),
        ]
        if row["block_max"] == max_block_peak and max_block_peak:
            most_parts.extend(["border:3px solid black", "font-weight:bold"])
        most_style = mix_styles(*most_parts)
        hover_detail = (
            f"Bikes at start: {row['start_on_hand']}\n"
            f"Bikes at end: {row['end_on_hand']}"
        )
        hover_attr = html.escape(hover_detail)

        print(
            "<tr>"
            f"<td style='{base_style}' title=\"{hover_attr}\">{row['time_label']}</td>"
            f"<td style='{in_style(row['rg_in'])}'>{row['rg_in']}</td>"
            f"<td style='{in_style(row['ov_in'])}'>{row['ov_in']}</td>"
            f"<td style='{in_style(row['all_in'])}'>{row['all_in']}</td>"
            f"<td style='{out_style(row['rg_out'])}'>{row['rg_out']}</td>"
            f"<td style='{out_style(row['ov_out'])}'>{row['ov_out']}</td>"
            f"<td style='{out_style(row['all_out'])}'>{row['all_out']}</td>"
            f"<td style='{total_style}' title=\"{hover_attr}\">{row['total_in']}</td>"
            f"<td style='{most_style}' title=\"{hover_attr}\">{row['block_max']}</td>"
            "</tr>"
        )

    print("</table><br>")


def visits_table(
    thisday,
    is_today,
    rows,
    highlights,
    daylight,
    duration_colors,
    sort_by,
    pages_back,
):
    # Sort the rows list according to the sort parameter
    sort_by = sort_by if sort_by else cc.SORT_TIME_IN
    if sort_by == cc.SORT_TAG:
        rows = sorted(rows, key=lambda x: x.tag)
        sort_msg = "bike tag"
    elif sort_by == cc.SORT_TIME_IN:
        rows = sorted(rows, key=lambda x: x.time_in)
        sort_msg = "arrival time"
    elif sort_by == cc.SORT_TIME_OUT:
        rows = sorted(rows, key=lambda x: x.time_in)
        rows = sorted(rows, key=lambda x: (not x.time_out, x.time_out))
        sort_msg = "departure time"
    elif sort_by == cc.SORT_DURATION:
        rows = sorted(rows, key=lambda x: x.time_in)
        rows = sorted(
            rows,
            reverse=True,
            key=lambda x: (
                x.time_out != "",
                1000000 if x.time_out == "" else x.duration,
            ),
        )
        sort_msg = "visit duration"
    else:
        rows = sorted(rows, key=lambda x: x.tag)
        sort_msg = f"bike tag (sort parameter '{sort_by}' unrecognized)"
    sort_msg = f"(Sorted by {sort_msg}) "

    link_sort_time = cc.selfref(
        what=cc.WHAT_ONE_DAY,
        qdate=thisday,
        qsort=cc.SORT_TIME_IN,
        pages_back=cc.increment_pages_back(pages_back),
    )
    link_sort_time_out = cc.selfref(
        what=cc.WHAT_ONE_DAY,
        qdate=thisday,
        qsort=cc.SORT_TIME_OUT,
        pages_back=cc.increment_pages_back(pages_back),
    )
    link_sort_tag = cc.selfref(
        what=cc.WHAT_ONE_DAY,
        qdate=thisday,
        qsort=cc.SORT_TAG,
        pages_back=cc.increment_pages_back(pages_back),
    )
    link_sort_duration = cc.selfref(
        what=cc.WHAT_ONE_DAY,
        qdate=thisday,
        qsort=cc.SORT_DURATION,
        pages_back=cc.increment_pages_back(pages_back),
    )

    # Earliest and latest event are for the bar graph
    earliest_event = VTime(min([r.time_in for r in rows if r.time_in > ""])).num
    max_visit = VTime(
        max([VTime(r.time_in).num + VTime(r.duration).num for r in rows])
        - earliest_event
    ).num
    bar_scaling_factor = BAR_COL_WIDTH / (max_visit)
    bar_offset = round(earliest_event * bar_scaling_factor)

    now_minutes = VTime("now").num if is_today else None

    html = "<table style=text-align:right class=general_table>"
    html += (
        "<tr><th colspan=5 style='text-align:center'>"
        f"Visits on {thisday}<br>{sort_msg}</th></tr>"
    )
    html += f"<tr><th><a href='{link_sort_tag}'>Tag</a></th>"
    html += f"<th><a href='{link_sort_time}'>Arrival</a></th>"
    html += f"<th><a href='{link_sort_time_out}'>Departure</a></th>"
    html += f"<th><a href='{link_sort_duration}'>Duration</a></th>"
    html += (
        "<th>Bar graph showing each visit<br>"
        f"{BAR_MARKERS['R']} = Regular bike visit; "
        f"{BAR_MARKERS['O']} = Oversize bike visit; "
        "'-' = visit in progress</th></tr>"
    )
    print(html)

    for v in rows:
        time_in = VTime(v.time_in)
        time_out = VTime(v.time_out)
        duration = VTime(v.duration)
        print("<tr>")
        # Tag
        tag_link = cc.selfref(what=cc.WHAT_TAG_HISTORY, qtag=v.tag)
        c = "color:auto;"
        # if v.next_time_in < time_in and time_out <= "" and not is_today:
        #     if v.tag[:1] == v.next_tag[:1]:
        #         c = highlights.css_bg_fg(HIGHLIGHT_ERROR)
        #     elif v.next_tag:
        #         c = highlights.css_bg_fg(HIGHLIGHT_MAYBE_ERROR)
        print(
            f"<td style='text-align:center;{c}'><a href='{tag_link}'>{v.tag}</a></td>"
        )
        # Time in
        c = daylight.css_bg_fg(time_in.num)
        print(f"<td style='{c}'>{time_in.tidy}</td>")
        # Time out
        if v.time_out <= "":
            c = highlights.css_bg_fg(HIGHLIGHT_WARN)
        else:
            c = daylight.css_bg_fg(time_out.num)
        print(f"<td style='{c}'>{time_out.tidy}</td>")
        # Duration
        c = duration_colors.css_bg_fg(duration.num)
        print(f"<td style='{c}'>{duration.tidy}</td>")
        # picture of the bike's visit.
        #   Bar start is based on time_in
        #   Bar length is based on duration
        #   Bar scaling factor is based on latest - earliest
        bar_marker = BAR_MARKERS[v.bike_type.upper()]
        bar_before_len = round(((time_in.num) * bar_scaling_factor)) - bar_offset
        bar_before = bar_before_len * "&nbsp;" if bar_before_len else ""
        duration_minutes = duration.num or 0
        bar_itself_len = round((duration_minutes * bar_scaling_factor))
        bar_itself_len = bar_itself_len if bar_itself_len else 1

        if (
            is_today
            and (v.time_out <= "" or not v.time_out)
            and now_minutes is not None
            and duration_minutes > 0
        ):
            elapsed_minutes = max(0, min(now_minutes - time_in.num, duration_minutes))
            if duration_minutes:
                elapsed_len = round(
                    bar_itself_len * (elapsed_minutes / duration_minutes)
                )
            else:
                elapsed_len = bar_itself_len
            elapsed_len = max(0, min(bar_itself_len, elapsed_len))
            remaining_len = max(0, bar_itself_len - elapsed_len)
            bar_itself = (bar_marker * elapsed_len) + (BAR_MARKER_FUTURE * remaining_len)
        else:
            bar_itself = bar_marker * bar_itself_len
        c = "background:auto" if time_out else "background:khaki"  # "rgb(255, 230, 0)"
        print(
            f"<td style='text-align:left;font-family: monospace;color:purple;{c}'>"
            f"{bar_before}{bar_itself}</td>"
        )
        print("</tr>")
    html = ""
    html += (
        "<tr><td colspan=5 style='text-align:center'><i>"
        "Where no departure time exists, duration is "
        "estimated assuming bike is present until "
        "the end of the day</i></td></tr>"
    )
    html += "</table></body></html>"
    print(html)


def summary_table(
    day_data: DayTotals,
    stats: VisitStats,
    tags_used_count: int,
    highlights: dc.Dimension,
    is_today: bool,
    commuter_mean=None,
    commuter_confidence=None,
    # suspicious: int,
):
    def fmt_none(obj) -> object:
        if obj is None:
            return ""
        return obj

    the_estimate = None
    if is_today:
        est = web_estimator.Estimator(estimation_type=EST_TYPE_FOR_ONEDAY_SUMMARY)
        est.guess()
        if est.state != web_estimator.ERROR and est.time_closed > VTime("now"):
            est_min = est.bikes_so_far + est.min
            est_max = est.bikes_so_far + est.max
            the_estimate = (
                str(est_min) if est_min == est_max else f"{est_min}-{est_max}"
            )

    table_bits: list[str] = []
    table_bits.append(
        "<table class=general_table summary_table><style>"
        ".summary_table td {text-align:right;}"
        "</style>"
    )
    table_bits.append(
        f"""
        <tr class='heavy-bottom'><td colspan=3>Hours of operation:
            {day_data.time_open.tidy} - {day_data.time_closed.tidy}</td></tr>
        <tr><td colspan=2>Visits (all bike types):</td>
            <td>{day_data.num_parked_combined}</td></tr>
        <tr><td colspan=2>&nbsp;&nbsp;&nbsp;Regular bike visits:</td>
            <td>{day_data.num_parked_regular}</td></tr>
        <tr><td colspan=2>&nbsp;&nbsp;&nbsp;Oversize bike visits:</td>
            <td>{day_data.num_parked_oversize}</td></tr>
            """
    )
    if (
        not is_today
        and commuter_mean is not None
        and commuter_confidence is not None
    ):
        table_bits.append(
            "<tr class='heavy-bottom'><td colspan=2>&nbsp;&nbsp;&nbsp;Commuter portion "
            f"(confidence={html.escape(commuter_confidence)}):</td>"
            f"<td>{int(round(commuter_mean))}</td></tr>"
        )
    if is_today and the_estimate is not None:
        table_bits.append(
            f"""
        <tr class='heavy-bottom'><td colspan=2>&nbsp;&nbsp;&nbsp;Predicted total visits:</td>
            <td>{the_estimate}</td></tr>
        """
        )
    table_bits.append(
        f"""
        <tr class='heavy-top'><td colspan=2>Max bikes (at {day_data.time_fullest_combined.tidy}):</td>
            <td>{day_data.num_fullest_combined}</td></tr>
        <tr class='heavy-bottom'><td colspan=2>Bikes left:</td>
            <td  width=40 style='{highlights.css_bg_fg(int(day_data.num_remaining_combined>0)*HIGHLIGHT_WARN)}'>
                {day_data.num_remaining_combined}</td></tr>
        <tr><td colspan=2>Registrations:</td>
            <td>{day_data.bikes_registered}</td></tr>
        <tr class='heavy-bottom'><td colspan=2>Tags used this day:</td>
            <td>{tags_used_count}</td></tr>
        """
    )
    if not is_today:
        table_bits.append(
            f"""
            <tr><td colspan=2>Visit duration (max):</td>
                <td>{stats.longest}</td></tr>
            <tr><td colspan=2>Visit duration (mean):</td>
                <td>{stats.mean}</td></tr>
            <tr><td colspan=2>Visit duration (median):</td>
                <td>{stats.median}</td></tr>
            <tr class='heavy-bottom'><td colspan=2>{ut.plural(len(stats.modes),'Visit duration (mode, ')}
                    {stats.mode_occurences} occurences):</td>
                <td>{'<br>'.join(stats.modes)}</td></tr>
            <tr><td colspan=2>Precipitation (mm):</td>
                <td>{fmt_none(day_data.precipitation)}</td></tr>
            <tr><td colspan=2>Max temperature:</td>
                <td>{fmt_none(day_data.max_temperature)}</td></tr>
    """
        )
    table_bits.append("</table><p></p>")
    prediction_bits = ""
    if is_today and est is not None and est.state != web_estimator.ERROR:
        detail_link = cc.selfref(what=cc.WHAT_ESTIMATE_VERBOSE)
        audit_link = cc.selfref(what=cc.WHAT_AUDIT)
        result_html = "".join(est.result_msg(as_html=True))
        prediction_bits = (
            "<div style='margin-top:0.5em'>"
            f"{result_html}"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
            f"<button type=\"button\" style=\"padding: 10px; display: inline-block;\" "
            f"onclick=\"window.location.href='{detail_link}';\"><b>Detailed<br>Prediction</b></button>"
            "&nbsp;&nbsp;&nbsp;&nbsp;"
            f"<button type=\"button\" style=\"padding: 10px; display: inline-block;\" "
            f"onclick=\"window.location.href='{audit_link}';\"><b>Audit<br>Report</b></button>"
            "<br><br></div>"
        )

    return "".join(table_bits), prediction_bits


def legend_table(daylight: dc.Dimension, duration_colors: dc.Dimension):
    print("<table class=general_table>")
    print("<tr><td>Colours for time of day:</td>")
    print(f"<td style={daylight.css_bg_fg(daylight.min)}>Early</td>")
    print(f"<td style={daylight.css_bg_fg((daylight.min+daylight.max)/2)}>Mid-day</td>")
    print(f"<td style={daylight.css_bg_fg(daylight.max)}>Later</td>")
    print("<tr><td>Colours for length of visit:</td>")
    print(f"<td style={duration_colors.css_bg_fg(duration_colors.min)}>Short</td>")
    print(
        f"<td style={duration_colors.css_bg_fg((duration_colors.min+duration_colors.max)/2)}>"
        "Medium</td>"
    )
    print(f"<td style={duration_colors.css_bg_fg(duration_colors.max)}>Long</td>")
    print("</table><p></p>")
