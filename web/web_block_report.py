#!/usr/bin/env python3
"""CGI script for TagTracker time-block report(s).

Copyright (C) 2023-2024 Julias Hocking & Todd Glover

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
import sqlite3
import copy
from collections import defaultdict

from web.web_daterange_selector import build_date_dow_filter_widget, find_dow_option
import web.web_common as cc
import web.datacolors as dc
import web.colortable as colortable
import common.tt_dbutil as db
from common.tt_time import VTime
import common.tt_util as ut

# import tt_block


XY_BOTTOM_COLOR = dc.Color((252, 252, 248)).html_color
X_TOP_COLOR = "red"
Y_TOP_COLOR = "royalblue"
NORMAL_MARKER = chr(0x25A0)  # chr(0x25AE)  # chr(0x25a0)#chr(0x25cf)
HIGHLIGHT_MARKER = chr(0x2B24)  # chr(0x25cf) #chr(0x25AE)  # chr(0x25a0)#chr(0x25cf)


# Uses precomputed block summaries stored in the BLOCK table rather than
# rebuilding them from raw visit rows.


class _OneBlock:
    """Data about a single timeblock."""

    def __init__(self):
        self.num_in = 0
        self.num_out = 0
        self.full = 0
        self.so_far = 0

    @property
    def activity(self):
        return self.num_in + self.num_out


class _OneDay:
    _allblocks = {}
    for t in range(6 * 60, 24 * 60, 30):
        _allblocks[VTime(t)] = _OneBlock()

    def __init__(self) -> None:
        self.day_total_bikes = None
        self.day_max_bikes = None
        self.day_max_bikes_time = None
        self.blocks = copy.deepcopy(_OneDay._allblocks)


def _process_iso_dow(
    dow_value,
    orgsite_id: int,
    start_date: str = "",
    end_date: str = "",
) -> tuple[str, str]:
    # Use dow to make report title prefix, and day filter for SQL queries.
    conditions = [f"orgsite_id = {orgsite_id}"]
    title_bit = ""

    if dow_value:
        if isinstance(dow_value, int):
            tokens = [dow_value]
        else:
            tokens = [
                int(piece.strip())
                for piece in str(dow_value).split(",")
                if piece.strip().isdigit()
            ]
        validated: list[int] = []
        for value in tokens:
            if 1 <= value <= 7:
                validated.append(value)
        validated = sorted(set(validated))

        if validated:
            zero_based = ["0" if value == 7 else str(value % 7) for value in validated]
            if len(zero_based) == 1:
                conditions.append(f"strftime('%w',date) = '{zero_based[0]}'")
            else:
                quoted = "','".join(zero_based)
                conditions.append(f"strftime('%w',date) IN ('{quoted}')")

            if len(validated) == 1:
                title_bit = f"{ut.dow_str(validated[0])} "
            else:
                option = find_dow_option(",".join(str(v) for v in validated))
                if option.value:
                    title_bit = f"{option.title_bit} "
                else:
                    title_names = ", ".join(ut.dow_str(v) for v in validated)
                    title_bit = f"{title_names} "

    if start_date:
        conditions.append(f"date >= '{start_date}'")
    if end_date:
        conditions.append(f"date <= '{end_date}'")

    day_where_clause = f" where {' and '.join(conditions)}"

    return title_bit, day_where_clause


def _fetch_block_rows(ttdb: sqlite3.Connection, day_filter: str) -> list[db.DBRow]:
    sel = (
        "select "
        "    day.date,"
        "    block.time_start,"
        "    block.num_incoming_combined,"
        "    block.num_outgoing_combined,"
        "    block.num_on_hand_combined "
        "from day "
        "JOIN block ON block.day_id = day.id"
        f"    {day_filter} "
        "order by day.date, block.time_start"
    )
    return db.db_fetch(ttdb, sel)


def _fetch_day_data(ttdb: sqlite3.Connection, day_filter: str):
    sel = (
        "select "
        "   date, num_parked_combined day_total_bikes, "
        "      num_fullest_combined day_max_bikes, "
        "      time_fullest_combined day_max_bikes_time "
        "from day "
        f"  {day_filter} "
        "   order by date desc"
    )
    return db.db_fetch(ttdb, sel)


def process_day_data(dayrows: list) -> tuple[dict[str:_OneDay], _OneDay]:
    tabledata = {}
    for dayrow in dayrows:
        date = dayrow.date
        day_summary = _OneDay()
        day_summary.day_total_bikes = dayrow.day_total_bikes
        day_summary.day_max_bikes = dayrow.day_max_bikes
        day_summary.day_max_bikes_time = dayrow.day_max_bikes_time
        tabledata[date] = day_summary

    day_maxes = _OneDay()
    day_maxes.day_max_bikes = max([d.day_max_bikes for d in tabledata.values()])
    day_maxes.day_total_bikes = max([d.day_total_bikes for d in tabledata.values()])
    return tabledata, day_maxes


def process_blocks_data(
    tabledata: dict, blockrows: list[db.DBRow]
) -> tuple[dict[VTime:_OneBlock], _OneBlock]:
    """Populate time-block data from BLOCK table rows."""

    rows_by_date = defaultdict(dict)
    for row in blockrows:
        block_time = VTime(row.time_start)
        if not block_time:
            continue
        rows_by_date[row.date][block_time] = row

    for date, day_summary in tabledata.items():
        blocks_for_day = rows_by_date.get(date, {})
        if not blocks_for_day:
            continue
        so_far_today = 0
        for block_key in sorted(day_summary.blocks.keys()):
            block_row = blocks_for_day.get(block_key)
            if not block_row:
                continue
            thisblock: _OneBlock = day_summary.blocks[block_key]
            num_in = block_row.num_incoming_combined or 0
            num_out = block_row.num_outgoing_combined or 0
            so_far_today += num_in
            thisblock.num_in = num_in
            thisblock.num_out = num_out
            thisblock.so_far = so_far_today
            thisblock.full = block_row.num_on_hand_combined or 0

    # Find overall maximum values
    block_maxes = _OneBlock()
    all_blocks = [b for t in tabledata.values() for b in t.blocks.values()]
    if all_blocks:
        block_maxes.num_in = max(b.num_in for b in all_blocks)
        block_maxes.num_out = max(b.num_out for b in all_blocks)
        block_maxes.full = max(b.full for b in all_blocks)
        block_maxes.so_far = max(b.so_far for b in all_blocks)

    return tabledata, block_maxes


def print_the_html(
    tabledata: dict,
    xy_colors: dc.MultiDimension,
    marker_colors: dc.Dimension,
    day_total_bikes_colors: dc.Dimension,
    day_full_colors: dc.Dimension,
    pages_back: int,
    date_filter_html: str = "",
    filter_description: str = "",
):
    def column_gap() -> str:
        """Make a thicker vertical cell border to mark off sets of blocks."""
        return "<td style='width:auto;border: 2px solid rgb(200,200,200);padding: 0px 0px;'></td>"

    title = cc.titleize("Half-hourly activity", filter_description)
    # if filter_description:
    #     title = f"{title} ({html.escape(filter_description)})"
    print(f"{title}")
    print(f"{cc.main_and_back_buttons(pages_back)}<br><br>")
    if date_filter_html:
        print(date_filter_html)
    print("<br><br>")

    # We frequently use xycolors(0,0). Save & store it.
    zero_bg = xy_colors.css_bg((0, 0))

    # Legend for x/y (background colours)
    xy_tab = colortable.html_2d_color_table(
        xy_colors,
        title="<b>Legend for activity (arrivals & departures)</b>",
        num_columns=9,
        num_rows=9,
        cell_size=20,
    )
    # Legend for markers
    marker_tab = colortable.html_1d_text_color_table(
        marker_colors,
        title="<b>Legend for max bikes on-site</b>",
        subtitle=f"{HIGHLIGHT_MARKER} = Time with max bikes onsite",
        marker=NORMAL_MARKER,
        bg_color="grey",  # bg_color=xy_colors.get_color(0,0).html_color
        num_columns=20,
    )
    print(
        "<table style='border-collapse: separate; border-spacing: 16px; width: auto;'>"
    )
    print("<tr>")
    print(
        f"<td style='vertical-align: top; text-align: left; width: auto;'>{xy_tab}</td>"
    )
    print(
        """

        <td style='vertical-align: top; text-align: left; width: auto;'>
            <div style="max-width: 25ch; text-align: left;">
                <p>
                    The half-hourly activity summary shows <i>patterns</i> of activity
                    for each date, in half-hour segments.
                </p>
                <p>
                    The colour grid highlights how inbound and outbound activity
                    shifts through the day, while the marker legend shows the
                    number of bikes onsite.
                </p>
                <p>
                    Click on any square to get more information about that half hour.
                </p>
            </div>
        </td>
        """
    )
    print("</tr>")
    print("<tr>")
    print(f"<td colspan=2 style='padding-top: 8px;'>{marker_tab}</td>")
    print("</tr>")
    print("</table>")
    print("<br>")

    tooltip_prefix = f"blk{ut.random_string(4)}"
    tooltip_style = f"""
    <style>
    .{tooltip_prefix}-data-cell {{
        position: relative;
        cursor: pointer;
    }}
    .{tooltip_prefix}-data-cell:focus {{
        outline: 2px solid #444;
        outline-offset: 1px;
    }}
    .{tooltip_prefix}-tooltip {{
        display: none;
        position: absolute;
        z-index: 30;
        left: 50%;
        top: 100%;
        transform: translate(-50%, 0.5em);
        background: white;
        border: 1px solid #444;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.18);
        padding: 0.6em 0.75em;
        text-align: left;
        color: #222;
        line-height: 1.4;
        min-width: 14em;
        max-width: 20em;
        border-radius: 0.4em;
    }}
    .{tooltip_prefix}-tooltip::before {{
        content: "";
        position: absolute;
        top: -0.5em;
        left: 50%;
        transform: translateX(-50%);
        border-width: 0.5em 0.5em 0;
        border-style: solid;
        border-color: #444 transparent transparent transparent;
    }}
    .{tooltip_prefix}-tooltip::after {{
        content: "";
        position: absolute;
        top: calc(-0.5em + 1px);
        left: 50%;
        transform: translateX(-50%);
        border-width: 0.5em 0.5em 0;
        border-style: solid;
        border-color: white transparent transparent transparent;
    }}
    .{tooltip_prefix}-tooltip-visible .{tooltip_prefix}-tooltip {{
        display: block;
    }}
    </style>
    """

    # Main table. Column headings
    print(tooltip_style)
    print("<table class=general_table>")
    print(
        "<style>td {text-align: right;text-align: center; width: 13px;padding: 4px 4px;}</style>"
    )
    print("<tr>")
    print("<th colspan=3>Date</th>")
    print("<th colspan=7>6:00 - 9:00</th>")
    print("<th colspan=7>9:00 - 12:00</th>")
    print("<th colspan=7>12:00 - 15:00</th>")
    print("<th colspan=7>15:00 - 18:00</th>")
    print("<th colspan=7>18:00 - 21:00</th>")
    print("<th colspan=7>21:00 - 24:00</th>")
    print("<th>Visits</th>")
    print("<th>Max<br/>bikes</th>")
    print("</tr>")

    date_today = ut.date_str("today")
    time_now = VTime("now")
    for date in sorted(tabledata.keys(), reverse=True):
        dayname = ut.date_str(date, dow_str_len=3)
        thisday: _OneDay = tabledata[date]
        tags_report_link = cc.CGIManager.selfref(
            what_report=cc.WHAT_ONE_DAY, start_date=date
        )
        print("<tr style='text-align: center; width: 15px;padding: 0px 3px;'>")
        print(f"<td style=width:auto;><a href='{tags_report_link}'>{date}</a></td>")
        print(f"<td style=width:auto;>{dayname}</td>")

        # Find which time block had the greatest num of bikes this day.
        fullest_block_this_day = ut.block_start(thisday.day_max_bikes_time)

        # Print the blocks for this day.
        row_html = ""
        for num, block_key in enumerate(sorted(thisday.blocks.keys())):
            if num % 6 == 0:
                row_html += column_gap()
            thisblock: _OneBlock = thisday.blocks[block_key]
            if date == date_today and block_key >= time_now:
                # Today, later than now
                cell_color = f"color:{XY_BOTTOM_COLOR};background:{XY_BOTTOM_COLOR};"
                cell_title = "Future unknown"
            elif thisblock.num_in == 0 and thisblock.num_out == 0:
                # No activity this block
                cell_color = f"{zero_bg};" f"{marker_colors.css_fg(thisblock.full)};"
                cell_title = (
                    f"Arrivals: 0\nDepartures: 0\n"
                    f"Visits so far: {thisblock.so_far}\nBikes at end: {thisblock.full} "
                )
            else:
                # Regular block with activity in it
                cell_color = (
                    f"{xy_colors.css_bg((thisblock.num_in, thisblock.num_out))};"
                    f"{marker_colors.css_fg(thisblock.full)};"
                )
                cell_title = (
                    f"Arrivals: {thisblock.num_in}\nDepartures: {thisblock.num_out}\n"
                    f"Visits so far: {thisblock.so_far}\nBikes at end: {thisblock.full} "
                )

            # Special marker & hover text if this is the fullest block of the day
            if block_key == fullest_block_this_day:
                marker = HIGHLIGHT_MARKER
                cell_title = f"{cell_title}\nMax bikes: {thisday.day_max_bikes}"
            else:
                marker = NORMAL_MARKER

            tooltip_lines = [
                line.strip() for line in cell_title.split("\n") if line.strip()
            ]
            tooltip_text = "\n".join(tooltip_lines)
            tooltip_attr = html.escape(tooltip_text, quote=True) if tooltip_text else ""
            tooltip_html = "".join(
                f"<div>{html.escape(line)}</div>" for line in tooltip_lines
            )
            attr_parts = [
                f"class='{tooltip_prefix}-data-cell'",
                f"style='{cell_color}'",
                "tabindex='0'",
            ]
            if tooltip_attr:
                attr_parts.append(f"title='{tooltip_attr}'")
                attr_parts.append(f"aria-label='{tooltip_attr}'")
            attr_str = " ".join(attr_parts)
            row_html += (
                f"<td {attr_str}>"
                f"{marker}"
                f"<div class='{tooltip_prefix}-tooltip' role='tooltip'>{tooltip_html}</div>"
                "</td>"
            )
        row_html += column_gap()

        s = day_total_bikes_colors.css_bg_fg(thisday.day_total_bikes)
        row_html += f"<td style='{s};width:auto;'>{thisday.day_total_bikes}</td>"
        s = day_full_colors.css_bg_fg(thisday.day_max_bikes)
        row_html += f"<td style='{s};width:auto;'>{thisday.day_max_bikes}</td>"
        row_html += "</tr>\n"
        print(row_html)

    print("</table>")
    script_block = f"""
    <script>
    (function() {{
        const scriptEl = document.currentScript;
        if (!scriptEl) {{ return; }}
        const table = scriptEl.previousElementSibling;
        if (!table || table.tagName !== 'TABLE') {{ return; }}
        const cells = Array.from(table.querySelectorAll('.{tooltip_prefix}-data-cell'));
        if (!cells.length) {{ return; }}
        const visibleClass = '{tooltip_prefix}-tooltip-visible';
        let activeCell = null;
        function closeTooltip() {{
            if (activeCell) {{
                activeCell.classList.remove(visibleClass);
                activeCell = null;
            }}
        }}
        cells.forEach((cell) => {{
            const tooltip = cell.querySelector('.{tooltip_prefix}-tooltip');
            if (!tooltip) {{ return; }}
            tooltip.addEventListener('click', function(event) {{
                event.stopPropagation();
            }});
            cell.addEventListener('click', function(event) {{
                event.stopPropagation();
                if (activeCell === cell) {{
                    closeTooltip();
                    return;
                }}
                closeTooltip();
                cell.classList.add(visibleClass);
                activeCell = cell;
            }});
            cell.addEventListener('keydown', function(event) {{
                if (event.key === 'Enter' || event.key === ' ') {{
                    event.preventDefault();
                    cell.click();
                }} else if (event.key === 'Escape') {{
                    closeTooltip();
                }}
            }});
        }});
        document.addEventListener('click', closeTooltip);
        document.addEventListener('keydown', function(event) {{
            if (event.key === 'Escape') {{
                closeTooltip();
            }}
        }});
    }})();
    </script>
    """
    print(script_block)


def blocks_report(
    ttdb: sqlite3.Connection,
    params: cc.ReportParameters,
):
    """Print block-by-block colors report for all days

    If dow is None then do for all days of the week, otherwise do
    for ISO int dow (1=Monday-->7=Sunday)

    """

    orgsite_id = 1  # orgsite_id hardcoded

    start_date, end_date, _default_start, _default_end = cc.resolve_date_range(
        ttdb,
        start_date=params.start_date,
        end_date=params.end_date,
    )

    selected_option = find_dow_option(params.dow)
    normalized_dow = selected_option.value

    self_url = cc.CGIManager.selfref(
        what_report=cc.WHAT_BLOCKS,
        start_date=start_date,
        end_date=end_date,
        pages_back=cc.increment_pages_back(params.pages_back),
    )
    filter_widget = build_date_dow_filter_widget(
        self_url,
        start_date=start_date,
        end_date=end_date,
        selected_dow=normalized_dow,
    )
    normalized_dow = filter_widget.selection.dow_value

    _, day_where_clause = _process_iso_dow(
        normalized_dow,
        orgsite_id=orgsite_id,
        start_date=start_date,
        end_date=end_date,
    )

    filter_description = filter_widget.description()
    date_filter_html = filter_widget.html

    dayrows: list[db.DBRow] = _fetch_day_data(ttdb, day_where_clause)
    blockrows: list[db.DBRow] = _fetch_block_rows(ttdb, day_where_clause)

    # range_label = f"({start_date} to {end_date})" if start_date or end_date else ""

    heading = "Time block summaries"

    # if range_label:
    #     heading = f"{heading} {range_label}"

    if not dayrows:
        print(f"<h1>{heading}</h1>")
        print(f"{cc.main_and_back_buttons(params.pages_back)}<br><br>")
        if date_filter_html:
            print(date_filter_html)
        if filter_description:
            print(
                f"<p class='filter-description'>{html.escape(filter_description)}</p>"
            )
        print("<br><br>")
        print("<p>No data found for the selected date range.</p>")
        return

    if not blockrows:
        print(f"<h1>{heading}</h1>")
        print(f"{cc.main_and_back_buttons(params.pages_back)}<br><br>")
        if date_filter_html:
            print(date_filter_html)
        if filter_description:
            print(
                f"<p class='filter-description'>{html.escape(filter_description)}</p>"
            )
        print("<br><br>")
        print("<p>Block activity data not available for the selected date range.</p>")
        return

    # Create structures for the html tables
    tabledata, day_maxes = process_day_data(dayrows)
    tabledata, block_maxes = process_blocks_data(tabledata, blockrows)

    # Set up color maps
    (
        colors,
        block_parked_colors,
        day_total_bikes_colors,
        day_full_colors,
    ) = create_color_maps(day_maxes, block_maxes)

    # Print the report
    print_the_html(
        tabledata,
        colors,
        block_parked_colors,
        day_total_bikes_colors,
        day_full_colors,
        params.pages_back,
        # page_title_prefix=title_bit,
        date_filter_html=date_filter_html,
        # date_range_label=range_label,
        filter_description=filter_description,
    )


def create_color_maps(day_maxes: _OneDay, block_maxes: _OneBlock) -> tuple:
    """Create color maps for the table.

    Returns
        colors,
        block_parked_colors,
        day_total_bikes_colors,
        day_full_colors,"""
    # Set up color maps
    colors = dc.MultiDimension(blend_method=dc.BLEND_MULTIPLICATIVE)
    d1 = colors.add_dimension(interpolation_exponent=0.82, label="Arrivals")
    d1.add_config(0, XY_BOTTOM_COLOR)
    d1.add_config(block_maxes.num_in, X_TOP_COLOR)
    d2 = colors.add_dimension(interpolation_exponent=0.82, label="Departures")
    d2.add_config(0, XY_BOTTOM_COLOR)
    d2.add_config(block_maxes.num_out, Y_TOP_COLOR)

    block_parked_colors = dc.Dimension(
        interpolation_exponent=0.85, label="Bikes onsite"
    )
    block_colors = [
        colors.get_color(0, 0),
        "thistle",
        "plum",
        "violet",
        "mediumpurple",
        "blueviolet",
        "darkviolet",
        "darkorchid",
        "indigo",
        "black",
    ]
    for n, c in enumerate(block_colors):
        block_parked_colors.add_config(n / (len(block_colors)) * (block_maxes.full), c)

    # These are for the right-most two columns
    day_total_bikes_colors = dc.Dimension(
        interpolation_exponent=1.5, label="Visits this day"
    )
    day_total_bikes_colors.add_config(0, "white")
    day_total_bikes_colors.add_config(day_maxes.day_total_bikes, "green")
    day_full_colors = dc.Dimension(
        interpolation_exponent=1.5, label="Max bikes this day"
    )
    day_full_colors.add_config(0, "white")
    day_full_colors.add_config(day_maxes.day_max_bikes, "teal")

    return colors, block_parked_colors, day_total_bikes_colors, day_full_colors
