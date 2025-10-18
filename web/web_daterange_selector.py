#!/usr/bin/env python3
"""
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

from dataclasses import dataclass
import html
from typing import Iterable, Sequence
import urllib.parse

import common.tt_util as ut

DATE_PATTERN = "[0-9]{4}-[0-9]{2}-[0-9]{2}"


@dataclass(frozen=True)
class DowOption:
    """One selectable option for the filter's day-of-week dropdown."""

    value: str
    label: str
    description_suffix: str
    title_suffix: str


def _build_day_name(iso_dow: int) -> str:
    """Return a tidy name for the ISO day-of-week value."""
    return ut.dow_str(iso_dow, 10).strip()


DEFAULT_DOW_OPTIONS: tuple[DowOption, ...] = tuple(
    [DowOption("", "All days", "", "all days of the week")]
    + [
        DowOption(
            str(iso_dow),
            _build_day_name(iso_dow),
            f"for {_build_day_name(iso_dow)}",
            f"{_build_day_name(iso_dow)}s",
        )
        for iso_dow in range(1, 8)
    ]
    + [
        DowOption("1,2,3,4,5", "Weekdays", "for weekdays", "weekdays"),
        DowOption("6,7", "Weekends", "for weekends", "weekends"),
    ]
)

def _cap_first(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def _normalize_dow_value(
    dow_value: str | int | Sequence[int] | None,
    options: Sequence[DowOption] = DEFAULT_DOW_OPTIONS,
) -> str:
    """Return a canonical string for the requested day-of-week selection."""

    if dow_value is None:
        return ""
    if isinstance(dow_value, int):
        dow_value = str(dow_value)
    elif isinstance(dow_value, (list, tuple)):
        dow_value = ",".join(str(v) for v in dow_value)

    as_text = str(dow_value).strip()
    if not as_text:
        return ""

    tokens = [token.strip() for token in as_text.split(",") if token.strip()]
    ints: list[int] = []
    for token in tokens:
        if not token.isdigit():
            return ""
        candidate = int(token)
        if candidate < 1 or candidate > 7:
            return ""
        ints.append(candidate)

    normalized = ",".join(str(v) for v in sorted(set(ints)))
    for option in options:
        if option.value == normalized:
            return option.value
    return ""


def find_dow_option(
    dow_value: str | int | Sequence[int] | None,
    options: Sequence[DowOption] = DEFAULT_DOW_OPTIONS,
) -> DowOption:
    """Return the option that matches dow_value, defaulting to 'All days'."""

    normalized = _normalize_dow_value(dow_value, options)
    for option in options:
        if option.value == normalized:
            return option
    return options[0]


@dataclass(frozen=True)
class DateDowSelection:
    """The concrete selections chosen in the filter widget."""

    start_date: str
    end_date: str
    dow_value: str = ""

    def option(self, options: Sequence[DowOption] = DEFAULT_DOW_OPTIONS) -> DowOption:
        return find_dow_option(self.dow_value, options)

    def description(
        self, options: Sequence[DowOption] = DEFAULT_DOW_OPTIONS
    ) -> str:
        """Return a human-friendly '(Dow from ...)' description."""

        if not self.start_date and not self.end_date:
            return ""

        option = self.option(options)
        single_day = (
            self.start_date
            and self.end_date
            and self.start_date == self.end_date
        )

        if single_day:
            date_part = self.start_date
            dow_part = ut.dow_str(self.start_date, 10) or option.label
            content = " ".join(part for part in (dow_part, date_part) if part)
            return f"({content})" if content else ""

        if self.start_date and self.end_date:
            date_part = f"from {self.start_date} to {self.end_date}"
        elif self.start_date:
            date_part = f"from {self.start_date}"
        elif self.end_date:
            date_part = f"through {self.end_date}"
        else:
            date_part = ""

        dow_plural = _cap_first(option.title_suffix or option.label)
        content = " ".join(part for part in (dow_plural, date_part) if part).strip()

        return f"({content})" if content else ""

    def title_fragment(
        self, options: Sequence[DowOption] = DEFAULT_DOW_OPTIONS
    ) -> str:
        """Return a text fragment such as 'weekdays' or 'Mondays'."""

        option = self.option(options)
        return option.title_suffix


@dataclass(frozen=True)
class DateDowFilterWidget:
    """Rendered HTML plus the associated selection metadata."""

    html: str
    selection: DateDowSelection
    options: tuple[DowOption, ...] = DEFAULT_DOW_OPTIONS

    def description(self) -> str:
        return self.selection.description(self.options)

    def title_fragment(self) -> str:
        return self.selection.title_fragment(self.options)

    def selected_option(self) -> DowOption:
        return self.selection.option(self.options)


def _render_hidden_fields(query_params: dict[str, list[str]]) -> str:
    tokens: list[str] = []
    for name, values in query_params.items():
        if not values:
            continue
        tokens.append(
            f'<input type="hidden" name="{html.escape(name)}" '
            f'value="{html.escape(values[0])}">'
        )
    return "\n        ".join(tokens)


def _render_day_dropdown(
    selection: DateDowSelection,
    options: Iterable[DowOption],
) -> str:
    rows = ['<label for="dow" style="margin-right:0.5rem;">Day of week:</label>']
    rows.append('<select id="dow" name="dow">')
    for option in options:
        value = html.escape(option.value)
        label = html.escape(option.label)
        selected_attr = " selected" if option.value == selection.dow_value else ""
        rows.append(f'  <option value="{value}"{selected_attr}>{label}</option>')
    rows.append("</select>")
    return "\n        ".join(rows)


def build_date_dow_filter_widget(
    base_url: str,
    start_date: str = "",
    end_date: str = "",
    selected_dow: str | int | Sequence[int] | None = "",
    *,
    include_day_filter: bool = True,
    submit_label: str = "Apply filters",
    options: Sequence[DowOption] = DEFAULT_DOW_OPTIONS,
) -> DateDowFilterWidget:
    """Return a widget that renders the combined date/dow filter."""

    options_tuple = tuple(options)
    normalized_dow = (
        _normalize_dow_value(selected_dow, options_tuple) if include_day_filter else ""
    )
    selection = DateDowSelection(
        start_date=start_date or "",
        end_date=end_date or "",
        dow_value=normalized_dow,
    )

    parsed_url = urllib.parse.urlparse(base_url)
    base_portion = base_url.split("?", 1)[0]
    query_params = urllib.parse.parse_qs(parsed_url.query)
    filtered_params = {
        k: v
        for k, v in query_params.items()
        if k.lower() not in {"start_date", "end_date", "dow"}
    }
    hidden_fields = _render_hidden_fields(filtered_params)

    if include_day_filter:
        form_style = (
            "border: 1px solid black; display: inline-grid; "
            "grid-template-columns: auto auto; grid-auto-rows: auto; "
            "gap: 0.5rem 1rem; align-items: end; padding: 10px;"
        )
        html_bits = [
            f"<form action=\"{html.escape(base_portion)}\" method=\"get\" style=\"{form_style}\">",
            "<div style='grid-column:1; grid-row:1; display:flex; align-items:center; gap:0.5rem;'>"
            "<label for=\"start_date\">Start date:</label>"
            f"<input type=\"date\" id=\"start_date\" name=\"start_date\" "
            f"value=\"{html.escape(selection.start_date)}\" "
            f"required pattern=\"{DATE_PATTERN}\"></div>",
            "<div style='grid-column:1; grid-row:2; display:flex; align-items:center; gap:0.5rem;'>"
            "<label for=\"end_date\">End date:</label>"
            f"<input type=\"date\" id=\"end_date\" name=\"end_date\" "
            f"value=\"{html.escape(selection.end_date)}\" "
            f"required pattern=\"{DATE_PATTERN}\"></div>",
            "<div style='grid-column:2; grid-row:1; display:flex; align-items:center; gap:0.5rem;'>"
            f"{_render_day_dropdown(selection, options_tuple)}</div>",
            "<div style='grid-column:2; grid-row:2; justify-self:end; align-self:end;'>"
            f"<input type=\"submit\" value=\"{html.escape(submit_label)}\"></div>",
        ]
    else:
        form_style = (
            "border: 1px solid black; display: inline-flex; "
            "flex-wrap: wrap; gap: 0.5rem; align-items: center; padding: 10px;"
        )
        html_bits = [
            f"<form action=\"{html.escape(base_portion)}\" method=\"get\" style=\"{form_style}\">",
            '<label for="start_date">Start Date:</label>',
            '<input type="date" id="start_date" name="start_date" '
            f'value="{html.escape(selection.start_date)}" '
            f'required pattern="{DATE_PATTERN}">',
            '<label for="end_date">End Date:</label>',
            '<input type="date" id="end_date" name="end_date" '
            f'value="{html.escape(selection.end_date)}" '
            f'required pattern="{DATE_PATTERN}">',
            f'<input type="submit" value="{html.escape(submit_label)}">',
        ]

    if hidden_fields:
        html_bits.append(hidden_fields)

    html_bits.append("</form>")

    widget_html = "\n        ".join(html_bits)
    return DateDowFilterWidget(widget_html, selection, options_tuple)


def generate_date_filter_form(base_url, default_start_date="", default_end_date=""):
    """Compatibility helper to render the legacy date-only filter."""

    widget = build_date_dow_filter_widget(
        base_url,
        start_date=default_start_date,
        end_date=default_end_date,
        include_day_filter=False,
        submit_label="Filter by this date range",
    )
    return widget.html


def main():
    # Example usage when testing this module in isolation.
    base_url = "http://example.com/report?user=admin&role=user"
    widget = build_date_dow_filter_widget(
        base_url,
        start_date="2024-01-01",
        end_date="2024-12-31",
        selected_dow="1,2,3,4,5",
    )

    print("Content-Type: text/html\n")
    print(
        f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <title>Date Range Filter</title>
    </head>
    <body>
    {widget.html}
    <p>{html.escape(widget.description())}</p>
    </body>
    </html>
    """
    )


if __name__ == "__main__":
    main()
