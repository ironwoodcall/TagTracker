#!/usr/bin/env python3
"""Leaderboard output for various categories.

CGI parameters:
    category: optional; values include "registrations" (r), "precipitation" (p),
        "temperature" (t), "visits" (v), "fullness" (f), or "all" (a).
    date: optional; defaults to today (YYYY-MM-DD). Any non-empty value is used.
    format: optional; "html" or "plain" (default).
"""

import datetime
import os
import time
import traceback as _tb
import urllib.parse

import common.tt_util as ut
import database.tt_dbutil as db
import web.web_base_config as wcfg
import web.web_common as cc

import cgitb
cgitb.enable()

def _normalize_date(raw_date: str) -> str:
    raw_date = (raw_date or "").strip()
    if not raw_date:
        return ut.date_str("today")
    normalized = ut.date_str(raw_date)
    return normalized or raw_date


def _normalize_category(raw_category: str) -> str | None:
    raw_category = (raw_category or "").strip().lower()
    if not raw_category:
        return "all"
    aliases = {
        "registrations": "registrations",
        "r": "registrations",
        "precipitation": "precipitation",
        "p": "precipitation",
        "temperature": "temperature",
        "t": "temperature",
        "visits": "visits",
        "v": "visits",
        "fullness": "fullness",
        "f": "fullness",
        "all": "all",
        "a": "all",
    }
    return aliases.get(raw_category)


def _render_visits(date_value: str, render_html: bool) -> list[str]:
    parsed_date = _parse_date(date_value)
    if not parsed_date:
        return _render_error(
            f"Bad date '{date_value}'. Expected YYYY-MM-DD or a valid alias.",
            render_html,
        )
    ttdb = _open_db()
    if not ttdb:
        return _render_error("Database not found.", render_html)
    try:
        return _metric_leaderboard(
            ttdb=ttdb,
            date_value=parsed_date,
            title="Most single-day visits as of {date}",
            column="num_parked_combined",
            render_html=render_html,
        )
    finally:
        ttdb.close()


def _render_registrations(date_value: str, render_html: bool) -> list[str]:
    parsed_date = _parse_date(date_value)
    if not parsed_date:
        return _render_error(
            f"Bad date '{date_value}'. Expected YYYY-MM-DD or a valid alias.",
            render_html,
        )
    ttdb = _open_db()
    if not ttdb:
        return _render_error("Database not found.", render_html)
    try:
        return _metric_leaderboard(
            ttdb=ttdb,
            date_value=parsed_date,
            title="Most single-day registrations as of {date}",
            column="bikes_registered",
            render_html=render_html,
        )
    finally:
        ttdb.close()


def _render_error(message: str, render_html: bool) -> list[str]:
    if render_html:
        import html as _html

        return [f"<p>Leaderboard error: {_html.escape(message)}</p>"]
    return [f"Leaderboard error: {message}"]


def _render_category(category: str, date_value: str, render_html: bool) -> list[str]:
    handlers = {
        "registrations": _render_registrations,
        "precipitation": _render_rain,
        "temperature": _render_temperature,
        "visits": _render_visits,
        "fullness": _render_fullest,
    }
    if category in handlers:
        return handlers[category](date_value, render_html)
    if category == "all":
        lines = []
        if render_html:
            renderers = [
                _render_registrations,
                _render_fullest,
                _render_visits,
                _render_rain,
                _render_temperature,
            ]
        else:
            renderers = [
                _render_temperature,
                _render_rain,
                _render_visits,
                _render_fullest,
                _render_registrations,
            ]
        for idx, renderer in enumerate(renderers):
            if idx:
                lines.append("")
            lines.extend(renderer(date_value, render_html))
        return lines
    if render_html:
        cc.error_out(
            "Unknown category. Expected registrations (r), precipitation (p), "
            "temperature (t), visits (v), fullness (f), or all (a)."
        )
    return _render_error(
        "Unknown category. Expected registrations (r), precipitation (p), "
        "temperature (t), visits (v), fullness (f), or all (a).",
        render_html,
    )


def _open_db():
    db_file = wcfg.DB_FILENAME
    if not db_file:
        return None
    return db.db_connect(db_file)


def _parse_date(date_value: str) -> datetime.date | None:
    normalized = ut.date_str(date_value, strict=True)
    if not normalized:
        return None
    try:
        return datetime.date.fromisoformat(normalized)
    except ValueError:
        return None


def _shift_months(start: datetime.date, delta_months: int) -> datetime.date:
    month = start.month - 1 + delta_months
    year = start.year + month // 12
    month = month % 12 + 1
    last_day = _days_in_month(year, month)
    day = min(start.day, last_day)
    return datetime.date(year, month, day)


def _shift_years(start: datetime.date, delta_years: int) -> datetime.date:
    year = start.year + delta_years
    try:
        return datetime.date(year, start.month, start.day)
    except ValueError:
        return datetime.date(year, start.month, _days_in_month(year, start.month))


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    return (next_month - datetime.timedelta(days=1)).day


def _top_metric(
    ttdb,
    column: str,
    start_date: datetime.date | None,
    end_date: datetime.date,
    limit: int = 5,
) -> list[tuple[float, str]]:
    orgsite_id = 1  # FIXME: hardcoded orgsite_id
    start_clause = ""
    if start_date:
        start_clause = f"AND date >= '{start_date.isoformat()}'"
    sql = f"""
        SELECT {column} AS metric, date
        FROM day
        WHERE date <= '{end_date.isoformat()}'
            {start_clause}
            AND orgsite_id = {orgsite_id}
            AND {column} IS NOT NULL
        ORDER BY {column} DESC, date DESC
        LIMIT {int(limit)}
    """
    rows = db.db_fetch(ttdb, sql)
    return [(row.metric, row.date) for row in rows if row.metric is not None]


def _format_metric_value(value: float) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.1f}"
    return str(value)


def _format_fixed_one_decimal(value: float) -> str:
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return str(value)


def _format_value_date_rows(
    rows: list[tuple[float, str]],
    total_rows: int = 5,
    formatter=_format_metric_value,
) -> list[str]:
    formatted_values = [(formatter(val), date) for val, date in rows]
    value_width = max([len(val) for val, _ in formatted_values] + [1])
    formatted = [f"{val:>{value_width}} {date}" for val, date in formatted_values]
    while len(formatted) < total_rows:
        formatted.append("")
    return formatted[:total_rows]


def _format_value_date_pairs(
    rows: list[tuple[float, str]],
    total_rows: int = 5,
    formatter=_format_metric_value,
) -> list[tuple[str, str]]:
    formatted = [(formatter(val), date) for val, date in rows]
    while len(formatted) < total_rows:
        formatted.append(("", ""))
    return formatted[:total_rows]


def _format_columns(
    headers: list[str],
    columns: list[list[str]],
    gap: str = "  ",
) -> list[str]:
    widths = []
    for header, col in zip(headers, columns):
        max_len = max([len(header)] + [len(item) for item in col])
        widths.append(max_len)

    lines = []
    header_line = gap.join(
        header.ljust(widths[idx]) for idx, header in enumerate(headers)
    )
    lines.append(header_line)
    for row_idx in range(max(len(col) for col in columns)):
        row_cells = []
        for col_idx, col in enumerate(columns):
            cell = col[row_idx] if row_idx < len(col) else ""
            row_cells.append(cell.ljust(widths[col_idx]))
        lines.append(gap.join(row_cells).rstrip())
    return lines


def _format_columns_html_pairs(
    headers: list[str],
    columns: list[list[tuple[str, str]]],
) -> list[str]:
    import html as _html

    lines = ['<table class="general_table leaderboard_table">', "  <thead>", "    <tr>"]
    for idx, header in enumerate(headers):
        lines.append(f'      <th colspan="2">{_html.escape(header)}</th>')
        if idx < len(headers) - 1:
            lines.append('      <th class="leaderboard-gap">&nbsp;</th>')
    lines.extend(["    </tr>", "  </thead>", "  <tbody>"])
    row_count = max(len(col) for col in columns)
    for row_idx in range(row_count):
        lines.append("    <tr>")
        for col_idx, col in enumerate(columns):
            value, date = col[row_idx] if row_idx < len(col) else ("", "")
            lines.append(
                f'      <td class="leaderboard-value" style="text-align:right;">'
                f"{_html.escape(value)}</td>"
            )
            lines.append(f'      <td class="leaderboard-date">{_html.escape(date)}</td>')
            if col_idx < len(columns) - 1:
                lines.append('      <td class="leaderboard-gap">&nbsp;</td>')
        lines.append("    </tr>")
    lines.extend(["  </tbody>", "</table>"])
    return lines


def _metric_text(
    ttdb,
    date_value: datetime.date,
    title: str,
    column: str,
    formatter=_format_metric_value,
) -> list[str]:
    this_month_start = datetime.date(date_value.year, date_value.month, 1)
    this_year_start = datetime.date(date_value.year, 1, 1)
    since_month_start = _shift_months(date_value, -1)
    since_year_start = _shift_years(date_value, -1)

    month_rows = _top_metric(ttdb, column, this_month_start, date_value)
    year_rows = _top_metric(ttdb, column, this_year_start, date_value)
    since_month_rows = _top_metric(ttdb, column, since_month_start, date_value)
    since_year_rows = _top_metric(ttdb, column, since_year_start, date_value)
    forever_rows = _top_metric(ttdb, column, None, date_value)

    lines = [title.format(date=date_value.isoformat()), ""]

    month_lines = _format_value_date_rows(month_rows, formatter=formatter)
    year_lines = _format_value_date_rows(year_rows, formatter=formatter)
    lines.extend(
        _format_columns(
            ["This month", "This year"],
            [month_lines, year_lines],
            gap="     ",
        )
    )
    lines.append("")

    since_month_lines = _format_value_date_rows(since_month_rows, formatter=formatter)
    since_year_lines = _format_value_date_rows(since_year_rows, formatter=formatter)
    forever_lines = _format_value_date_rows(forever_rows, formatter=formatter)
    lines.extend(
        _format_columns(
            [
                f"Since {since_month_start.isoformat()}",
                f"Since {since_year_start.isoformat()}",
                "Since Forever",
            ],
            [since_month_lines, since_year_lines, forever_lines],
            gap="     ",
        )
    )

    return lines


def _metric_html(
    ttdb,
    date_value: datetime.date,
    title: str,
    column: str,
    formatter=_format_metric_value,
) -> list[str]:
    this_month_start = datetime.date(date_value.year, date_value.month, 1)
    this_year_start = datetime.date(date_value.year, 1, 1)
    since_month_start = _shift_months(date_value, -1)
    since_year_start = _shift_years(date_value, -1)

    month_rows = _top_metric(ttdb, column, this_month_start, date_value)
    year_rows = _top_metric(ttdb, column, this_year_start, date_value)
    since_month_rows = _top_metric(ttdb, column, since_month_start, date_value)
    since_year_rows = _top_metric(ttdb, column, since_year_start, date_value)
    forever_rows = _top_metric(ttdb, column, None, date_value)

    month_lines = _format_value_date_pairs(month_rows, formatter=formatter)
    year_lines = _format_value_date_pairs(year_rows, formatter=formatter)
    since_month_lines = _format_value_date_pairs(since_month_rows, formatter=formatter)
    since_year_lines = _format_value_date_pairs(since_year_rows, formatter=formatter)
    forever_lines = _format_value_date_pairs(forever_rows, formatter=formatter)

    lines = [f"<h2>{title.format(date=date_value.isoformat())}</h2>"]
    lines.extend(
        _format_columns_html_pairs(["This month", "This year"], [month_lines, year_lines])
    )
    lines.append("<br>")
    lines.extend(
        _format_columns_html_pairs(
            [
                f"Since {since_month_start.isoformat()}",
                f"Since {since_year_start.isoformat()}",
                "Since Forever",
            ],
            [since_month_lines, since_year_lines, forever_lines],
        )
    )
    return lines


def _metric_leaderboard(
    ttdb,
    date_value: datetime.date,
    title: str,
    column: str,
    render_html: bool,
    formatter=_format_metric_value,
) -> list[str]:
    if render_html:
        return _metric_html(ttdb, date_value, title, column, formatter=formatter)
    return _metric_text(ttdb, date_value, title, column, formatter=formatter)


def _render_fullest(date_value: str, render_html: bool) -> list[str]:
    parsed_date = _parse_date(date_value)
    if not parsed_date:
        return _render_error(
            f"Bad date '{date_value}'. Expected YYYY-MM-DD or a valid alias.",
            render_html,
        )
    ttdb = _open_db()
    if not ttdb:
        return _render_error("Database not found.", render_html)
    try:
        return _metric_leaderboard(
            ttdb=ttdb,
            date_value=parsed_date,
            title="Most bikes on-site as of {date}",
            column="num_fullest_combined",
            render_html=render_html,
        )
    finally:
        ttdb.close()


def _render_rain(date_value: str, render_html: bool) -> list[str]:
    parsed_date = _parse_date(date_value)
    if not parsed_date:
        return _render_error(
            f"Bad date '{date_value}'. Expected YYYY-MM-DD or a valid alias.",
            render_html,
        )
    ttdb = _open_db()
    if not ttdb:
        return _render_error("Database not found.", render_html)
    try:
        return _metric_leaderboard(
            ttdb=ttdb,
            date_value=parsed_date,
            title="Greatest single-day precipitation as of {date}",
            column="precipitation",
            render_html=render_html,
            formatter=_format_fixed_one_decimal,
        )
    finally:
        ttdb.close()


def _render_temperature(date_value: str, render_html: bool) -> list[str]:
    parsed_date = _parse_date(date_value)
    if not parsed_date:
        return _render_error(
            f"Bad date '{date_value}'. Expected YYYY-MM-DD or a valid alias.",
            render_html,
        )
    ttdb = _open_db()
    if not ttdb:
        return _render_error("Database not found.", render_html)
    try:
        return _metric_leaderboard(
            ttdb=ttdb,
            date_value=parsed_date,
            title="Highest temperature as of {date}",
            column="max_temperature",
            render_html=render_html,
            formatter=_format_fixed_one_decimal,
        )
    finally:
        ttdb.close()


if __name__ == "__main__":
    try:
        def _init_from_cgi() -> tuple[str, str, bool]:
            query_str = ut.untaint(os.environ.get("QUERY_STRING", ""))
            query_parms = urllib.parse.parse_qs(query_str)
            raw_category = query_parms.get("category", [""])[0]
            param_category = _normalize_category(raw_category)
            if param_category is None and raw_category.strip():
                param_category = "__invalid__"
            param_date = _normalize_date(query_parms.get("date", [""])[0])
            render_format = (
                (query_parms.get("format", ["plain"])[0] or "plain").strip().lower()
            )
            param_render_html = render_format == "html"
            return param_category, param_date, param_render_html

        start_time = time.perf_counter()
        is_cgi = bool(os.environ.get("REQUEST_METHOD"))
        if not is_cgi:
            print("Must use CGI interface")
            raise SystemExit(0)

        category, date_value, render_html = _init_from_cgi()
        mime = "text/html" if render_html else "text/plain"
        print(f"Content-type: {mime}\n")
        if render_html:
            print(cc.style())
            if os.getenv("TAGTRACKER_DEBUG"):
                print("<pre style='color:red'>\nDEBUG -- TAGTRACKER_DEBUG flag is set\n\n" "</pre>")



        output_lines = _render_category(category, date_value, render_html)
        for line in output_lines:
            print(line)

        elapsed_time = time.perf_counter() - start_time
        if render_html:
            print(
                f'<p class="estimator-query-time">Query took {elapsed_time:.1f} seconds.</p>'
            )
        else:
            print(f"\n\nQuery took {elapsed_time:.1f} seconds.")
    except Exception as e:  # pylint:disable=broad-except
        is_cgi = bool(os.environ.get("REQUEST_METHOD"))
        try:
            render_html
        except NameError:
            render_html = False
        if is_cgi:
            try:
                mime = "text/html" if render_html else "text/plain"
                print(f"Content-type: {mime}\n")
            except Exception:  # pylint:disable=broad-except
                pass
        if render_html:
            import html as _html

            print(f"<p>Leaderboard error: {_html.escape(str(e))}</p>")
            try:
                tb_html = "<br>".join(
                    _html.escape(line.rstrip("\n"))
                    for line in _tb.format_exception(type(e), e, e.__traceback__)
                )
                print(f"<pre>{tb_html}</pre>")
            except Exception:  # pylint:disable=broad-except
                pass
            raise SystemExit(1)

        print(f"Leaderboard error: {e}")
        try:
            print("\n".join(_tb.format_exception(type(e), e, e.__traceback__)))
        except Exception:  # pylint:disable=broad-except
            pass
