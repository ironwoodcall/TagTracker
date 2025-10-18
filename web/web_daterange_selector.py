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
    """
    Immutable configuration for a single day-of-week dropdown choice.

    Attributes:
        value: Underlying value submitted with the form; may be a comma-delimited list.
        label: User-facing text displayed within the dropdown.
        title_bit: Lowercase fragment suitable for titles (e.g., "Mondays" or "weekdays").
    """

    value: str
    label: str
    title_bit: str


def _build_day_name(iso_dow: int) -> str:
    """Return the display name for the provided ISO day-of-week (1=Monday)."""
    return ut.dow_str(iso_dow, 10).strip()


DEFAULT_DOW_OPTIONS: tuple[DowOption, ...] = tuple(
    [DowOption("", "All days ", "")]
    + [
        DowOption(
            str(iso_dow),
            f"{_build_day_name(iso_dow)}s",
            f"{_build_day_name(iso_dow)}s",
        )
        for iso_dow in range(1, 8)
    ]
    + [
        DowOption("1,2,3,4,5", "Weekdays", "weekdays"),
        DowOption("6,7", "Weekends", "weekends"),
    ]
)

# def _cap_first(text: str) -> str:
#     """Return text with only the first character capitalized if present."""
#     return text[:1].upper() + text[1:] if text else text


def _normalize_dow_value(
    dow_value: str | int | Sequence[int] | None,
    options: Sequence[DowOption] = DEFAULT_DOW_OPTIONS,
) -> str:
    """
    Return a normalized comma-separated list of ISO day numbers representing a selection.

    The input may be a string, a single integer, a sequence of integers, or ``None``.
    Non-numeric values or numbers outside the inclusive range of 1–7 yield an empty string.
    A recognized value must also correspond to one of the supplied ``options``.
    """

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
    """
    Return the option matching ``dow_value``, or fall back to the "All days" choice.

    The candidate value is normalized in the same manner as the day-of-week selector.
    """

    normalized = _normalize_dow_value(dow_value, options)
    for option in options:
        if option.value == normalized:
            return option
    return options[0]


@dataclass(frozen=True)
class DateDowSelection:
    """User-specified date range and optional day-of-week filter selection."""

    start_date: str
    end_date: str
    dow_value: str = ""

    def option(self, options: Sequence[DowOption] = DEFAULT_DOW_OPTIONS) -> DowOption:
        """Return the dropdown option that matches the stored day-of-week value."""
        return find_dow_option(self.dow_value, options)

    def description(self, options: Sequence[DowOption] = DEFAULT_DOW_OPTIONS) -> str:
        """
        Return a human-friendly summary such as ``"Mondays from 2024-01-01 to 2024-01-31"``.

        A blank string is returned when neither start nor end date are present.
        """

        if not self.start_date and not self.end_date:
            return ""

        option = self.option(options)

        # Single day, say dow name and the date.
        if self.start_date and self.end_date and self.start_date == self.end_date:
            date_part = self.start_date
            dow_part = ut.dow_str(self.start_date, 10) or option.label
            content = ", ".join(part for part in (dow_part, date_part) if part)
            return f"{content}" if content else ""

        if self.start_date and self.end_date:
            date_part = f"{self.start_date} to {self.end_date}"
        elif self.start_date:
            date_part = f"{self.start_date}"
        elif self.end_date:
            date_part = f"through {self.end_date}"
        else:
            date_part = ""

        content = " from ".join(
            part for part in (option.title_bit, date_part) if part
        ).strip()

        return f"{content}" if content else ""

    def title_fragment(self, options: Sequence[DowOption] = DEFAULT_DOW_OPTIONS) -> str:
        """Return a concise label such as ``"weekdays"`` or ``"Mondays"``."""

        option = self.option(options)
        return option.title_bit


@dataclass(frozen=True)
class DateDowFilterWidget:
    """Pair the rendered HTML form with the user selection it represents."""

    html: str
    selection: DateDowSelection
    options: tuple[DowOption, ...] = DEFAULT_DOW_OPTIONS

    def description(self) -> str:
        """Delegate to the selection object for a human-readable description."""
        return self.selection.description(self.options)

    def title_fragment(self) -> str:
        """Return the selection's brief label suitable for headings."""
        return self.selection.title_fragment(self.options)

    def selected_option(self) -> DowOption:
        """Return the resolved dropdown option for the stored day-of-week value."""
        return self.selection.option(self.options)


def _render_hidden_fields(query_params: dict[str, list[str]]) -> str:
    """Render hidden ``<input>`` elements for existing query parameters."""
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
    field_name: str,
) -> str:
    """Render the day-of-week ``<select>`` element for the filter form."""
    field_id = field_name
    escaped_id = html.escape(field_id)
    escaped_name = html.escape(field_name)
    rows = [
        f'<label for="{escaped_id}" style="margin-right:0.5rem;">Day of week:</label>'
    ]
    rows.append(f'<select id="{escaped_id}" name="{escaped_name}">')
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
    field_suffix: str = "",
) -> DateDowFilterWidget:
    """
    Build a date and optional day-of-week filter widget and associated selection.

    The resulting :class:`DateDowFilterWidget` contains the HTML form markup alongside
    the normalized selection metadata, allowing callers to render or inspect the state.

    Args:
        base_url: Target URL for the generated ``<form>`` element.
        start_date: Pre-selected start date in ISO format.
        end_date: Pre-selected end date in ISO format.
        selected_dow: Pre-selected day-of-week specifier.
        include_day_filter: Whether to include the day-of-week dropdown.
        submit_label: Text for the submit button.
        options: Available day-of-week choices.
        field_suffix: Optional suffix appended to each input name/id so multiple widgets
            can coexist on the same page without collisions (e.g. ``"2"``).
    """

    options_tuple = tuple(options)
    start_field = f"start_date{field_suffix}"
    end_field = f"end_date{field_suffix}"
    dow_field = f"dow{field_suffix}"
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
    excluded_fields = {start_field.lower(), end_field.lower()}
    if include_day_filter:
        excluded_fields.add(dow_field.lower())
    filtered_params = {
        k: v
        for k, v in query_params.items()
        if k.lower() not in excluded_fields
    }
    hidden_fields = _render_hidden_fields(filtered_params)

    if include_day_filter:
        form_style = (
            "border: 1px solid black; display: inline-grid; "
            "grid-template-columns: auto auto; grid-auto-rows: auto; "
            "gap: 0.5rem 1rem; align-items: end; padding: 10px;"
        )
        escaped_start_field = html.escape(start_field)
        escaped_end_field = html.escape(end_field)
        html_bits = [
            f'<form action="{html.escape(base_portion)}" method="get" style="{form_style}">',
            "<div style='grid-column:1; grid-row:1; display:flex; align-items:center; gap:0.5rem;'>"
            f'<label for="{escaped_start_field}">Start date:</label>'
            f'<input type="date" id="{escaped_start_field}" name="{escaped_start_field}" '
            f'value="{html.escape(selection.start_date)}" '
            f'required pattern="{DATE_PATTERN}"></div>',
            "<div style='grid-column:1; grid-row:2; display:flex; align-items:center; gap:0.5rem;'>"
            f'<label for="{escaped_end_field}">End date:&nbsp;</label>'
            f'<input type="date" id="{escaped_end_field}" name="{escaped_end_field}" '
            f'value="{html.escape(selection.end_date)}" '
            f'required pattern="{DATE_PATTERN}"></div>',
            "<div style='grid-column:2; grid-row:1; display:flex; align-items:center; gap:0.5rem;'>"
            f"{_render_day_dropdown(selection, options_tuple, dow_field)}</div>",
            "<div style='grid-column:2; grid-row:2; justify-self:end; align-self:end;'>"
            f'<input type="submit" value="{html.escape(submit_label)}"></div>',
        ]
    else:
        form_style = (
            "border: 1px solid black; display: inline-flex; "
            "flex-wrap: wrap; gap: 0.5rem; align-items: center; padding: 10px;"
        )
        escaped_start_field = html.escape(start_field)
        escaped_end_field = html.escape(end_field)
        html_bits = [
            f'<form action="{html.escape(base_portion)}" method="get" style="{form_style}">',
            f'<label for="{escaped_start_field}">Start Date:</label>',
            f'<input type="date" id="{escaped_start_field}" name="{escaped_start_field}" '
            f'value="{html.escape(selection.start_date)}" '
            f'required pattern="{DATE_PATTERN}">',
            f'<label for="{escaped_end_field}">End Date:</label>',
            f'<input type="date" id="{escaped_end_field}" name="{escaped_end_field}" '
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
    """
    Return HTML markup that mimics the legacy date-only filtering widget.

    This helper wraps :func:`build_date_dow_filter_widget` while omitting the
    day-of-week dropdown and using a historical submit button label.
    """

    widget = build_date_dow_filter_widget(
        base_url,
        start_date=default_start_date,
        end_date=default_end_date,
        include_day_filter=False,
        submit_label="Filter by this date range",
    )
    return widget.html


def main():
    """Render an example widget when the module is executed directly."""
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
