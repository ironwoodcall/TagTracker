#!/usr/bin/python3

import sqlite3

import tt_util as ut
import tt_dbutil as db
import cgi_common as cc

def html_histogram(
    data: dict,
    num_data_rows: int = 20,
    bar_color: str = "blue",
    title: str = "",
    subtitle: str = "",
    table_width: int = 40,
    border_color: str = "black",
    mini:bool=False
) -> str:
    """Create an html histogram from a dictionary.

    Note about css style names.  The css stylesheet is inline and
    its names could conflict with other styles -- including other
    calls to this function on the same html page.  Workaround is
    to dynamically name the styles with random prefixes."""
    ##border_color = "black"

    # Input validation
    if (
        not all(
            isinstance(arg, type)
            for arg, type in zip(
                [data, num_data_rows, title, table_width], [dict, int, str, int]
            )
        )
        or num_data_rows < 1
        or table_width < 1
    ):
        return "Invalid input."

    # Each style sheet must be unique wrt its classes in case mult on one page
    prefix = ut.random_string(4)

    # Normalize data values to fit within the num of rows
    max_value = max(data.values(), default=0)

    normalized_data = {
        key: 0 if not max_value else int(value / max_value * num_data_rows)
        for key, value in data.items()
    }

    # Sort data keys for consistent order
    sorted_keys = sorted(data.keys())

    # Calculate cell width
    cell_width = 100 / len(data)
    padding_value = max(
        0.2, max([len(k) for k in sorted_keys]) * 0.2
    )  # FIXME: may require adjustment

    # Build the HTML table with inline CSS styles
    html_table = f"""
    <style>
        .{prefix}-table {{ font-family: sans-serif;
                border-collapse: collapse; border: 1px solid {border_color};
                width: {table_width}%;}}
        .{prefix}-empty-cell {{ background-color: white; width: {cell_width}%; }}
        .{prefix}-category-label {{
            transform: rotate(-90deg); padding: {padding_value}em 0;
            border: 1px solid {border_color};border-top: 2px solid {bar_color};
            font-size: 0.85em; text-align: center;
        }}
        .{prefix}-bar-cell {{
            background-color: {bar_color}; width: {cell_width}%;
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
        }}
        .{prefix}-bar-top-cell {{
            text-align: center; font-size: 0.8em;
            color: white; background-color: {bar_color};
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
        }}
        .{prefix}-zero-bar-cell {{
            text-align: center; font-size: 0.8em;
            color: {bar_color}; background-color: white; width: {cell_width}%;
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
            border-bottom: 2px solid {bar_color}
        }}
        .{prefix}-emptiness-cell {{ background-color: white; width: {cell_width}%; }}
        .{prefix}-titles {{ text-align: center; background-color: white; }}
    </style>
    """

    html_table += f"""
        <table class="{prefix}-table">

        """
    # Add the title in otherwise blank row at top
    html_table += f"""<tr><td colspan='{len(data)}' class='{prefix}-titles'
        >{title}</td></tr>"""

    # Add an empty row at the top
    html_table += "<tr>"
    for key in sorted_keys:
        html_table += "<td class='{prefix}-empty-cell'>&nbsp;</td>"
    html_table += "</tr>"

    empty_text = "" if mini else "&nbsp;"
    for i in range(num_data_rows + 1):
        html_table += "<tr>"

        for key in sorted_keys:
            if i == num_data_rows:
                if not mini:
                    # Category label at the bottom (rotated 90 degrees)
                    html_table += f"<td class='{prefix}-category-label'>{key}</td>"
            elif i >= num_data_rows - normalized_data[key]:
                # Blue-colored cells for data
                if i == num_data_rows - normalized_data[key]:
                    # Print the value in the highest cell with a {bar_color} background
                    val = "" if mini else data[key]
                    html_table += f"""<td class='{prefix}-bar-cell
                        {prefix}-bar-top-cell'>{val}</td>"""
                else:
                    # Other {bar_color} cells
                    html_table += f"<td class='{prefix}-bar-cell'>{empty_text}</td>"
            else:
                if i == num_data_rows - 1:
                    # Bottom-most cell for a column with no colored blocks
                    val = "" if mini else data[key]
                    html_table += (
                        f"<td class='{prefix}-zero-bar-cell'><b>{val}</b></td>"
                    )
                else:
                    # White background cells above the data
                    html_table += f"<td class='{prefix}-emptiness-cell'>{empty_text}</td>"

        html_table += "</tr>\n"

    # Add a caption below category labels
    if subtitle:
        html_table += f"""<tr><td colspan='{len(data)}' class='{prefix}-titles'
            style='font-size:0.85em'>{subtitle}</td></tr>"""

    html_table += "</table>"
    return html_table


def times_hist_table(
    ttdb: sqlite3.Connection,
    query_column: str,
    start_date: str = None,
    end_date: str = None,
    days_of_week: str = None,
    title: str = "",
    subtitle:str = "",
    color: str = None,
    mini:bool=False
) -> str:
    """Create one html histogram table on lengths of stay.

    Parameters:
        query_column: time_in, time_out or duration (VISIT table)
        start_date, end_date: the date range as date_str() compatible strings.
            If missing, uses earliest & latest date in database.
        days_of_week: "" or "6" or "4,5,6" etc. ISO8601 integer days of week. If multiple
            days of week are given, will include only those days of the week.
    """
    if query_column.lower() not in ["time_in", "time_out", "duration"]:
        raise ValueError(f"Bad value for query column, '{query_column}' ")

    def make_sql(
        time_column: str,
        start_date: str = None,
        end_date: str = None,
        days_of_week: list = None,
    ) -> str:
        """Make sql query to fetch the time values from one column."""
        # convert days of week from ISO8601 to as-used by sqlite3

        filter_items = [f"{time_column} != ''"]
        if start_date:
            filter_items.append(f"DATE >= '{start_date}'")
        if end_date:
            filter_items.append(f"DATE <= '{end_date}'")
        if days_of_week:
            cc.test_dow_parameter(days_of_week,list_ok=True)
            dow_bits = [int(s) for s in days_of_week.split(",")]
            zero_based_days_of_week = ["0" if i == 7 else str(i) for i in dow_bits]
            filter_items.append(
                f"""strftime('%w',DATE) IN ('{"','".join(zero_based_days_of_week)}')"""
                #f"""strftime('%w',DATE) IN ('{days_of_week}')"""
            )
        sql = f"SELECT {time_column} FROM VISIT WHERE {' AND '.join(filter_items)};"
        return sql

    sql_query = make_sql(query_column, start_date, end_date, days_of_week)
    rows = db.db_fetch(
        ttdb, sql_query, ["time_column"]
    )
    #print(f"{sql_query=};{len(rows)=}; {query_column=}")
    times_list = [r.time_column for r in rows]
    if query_column == "duration":
        start_time, end_time = ("00:00", "12:00")
    else:
        start_time, end_time = ("07:00", "22:00")

    times_freq = ut.time_distribution(times_list, start_time, end_time, 30)
    if mini:
        top_text = ""
        bottom_text = title
        rows = 20
    else:
        top_text = title
        bottom_text = subtitle
        rows = 20
    return html_histogram(times_freq, rows, color, mini=mini, title=top_text,subtitle=bottom_text)
    #return chartjs_histogram(times_freq,400,400,bar_color=color,title=top_text,subtitle=bottom_text,)


if __name__ == "__main__":
    # Example usage
    data_example = {
        "00:00": 2003,
        "00:30": 3482,
        "01:00": 3996,
        "01:30": 3791,
        "02:00": 2910,
        "02:30": 2246,
        "03:00": 1707,
        "03:30": 1365,
        "04:00": 1027,
        "04:30": 846,
        "05:00": 738,
        "05:30": 730,
        "06:00": 584,
        "06:30": 654,
        "07:00": 771,
        "07:30": 1093,
        "08:00": 2042,
        "08:30": 2135,
        "09:00": 777,
        "09:30": 334,
        "10:00": 177,
        "10:30": 101,
        "11:00": 62,
        "11:30": 41,
        "12:00+": 55,
    }
    print("Content-type: text/html\n\n")
    result = html_histogram(
        data_example,
        num_data_rows=6,
        subtitle="Frequency distribution of stay lengths",
        table_width=20,
        mini=True,
        bar_color="royalblue",
        border_color="white",
    )

    print(
        """<div style="display: flex;">
        <!-- Left Column -->
        <div XXstyle="flex: 0; margin-right: 20px;">"""
    )
    print(result)

    print(
        """ </div>
        <!-- Right Column -->
        <div XXstyle="flex: 0;">"""
    )
    print("<br><br>")
    result = html_histogram(
        data_example,
        20,
        "orange",
        "<b>Lengths of stay 2023</b>",
        "Category start (30 minute categories)",
        10,
        mini=False,
    )
    print(result)
    print("</div></div>")
