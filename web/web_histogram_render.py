"""
HTML renderers for histogram data.
"""

from html import escape
from common.tt_time import VTime
import common.tt_util as ut

from web_histogram_data import HistogramMatrixResult


def html_histogram(
    data: dict,
    num_data_rows: int = 20,
    bar_color: str = "blue",
    title: str = "",
    subtitle: str = "",
    table_width: int = 40,
    border_color: str = "black",
    mini: bool = False,
    stack_data=None,
    stack_color: str = "",
    link_target: str = "",
    max_value: float | None = None,
    open_marker_label: str | None = None,
    close_marker_label: str | None = None,
    marker_color: str | None = None,
) -> str:
    """Render a single-series (optionally stacked) histogram table as HTML.

    Args:
        data: Mapping of categorical labels to primary values.
        num_data_rows: Number of vertical rows used to draw the bars.
        bar_color: CSS color for the primary portion of each bar.
        title: Optional chart title (suppressed in ``mini`` mode).
        subtitle: Optional chart subtitle placed under the axis labels.
        table_width: Percentage width assigned to the rendered table.
        border_color: CSS color used for table and bar borders.
        mini: When true, suppresses labels and tightens the layout.
        stack_data: Optional mapping of secondary values stacked on top.
        stack_color: CSS color for the stacked portion of each bar.
        link_target: Optional href to wrap the table to make it clickable.
        max_value: Explicit max used for height normalization (auto if ``None``).
        open_marker_label: Label prefix for highlighting a left boundary.
        close_marker_label: Label prefix for highlighting a right boundary.
        marker_color: CSS color for the dotted boundary markers.

    Returns:
        HTML string containing an inline-styled table representation.
    """

    # Nothing to render if both the base and stacked series are empty.
    stack_data = stack_data or {}
    if not data and not stack_data:
        return "<p>No data available.</p>"

    bar_color = bar_color or "blue"
    stack_color = stack_color or "royalblue"

    # Guardrails: invalid arguments usually mean a templating mistake upstream.
    if (
        not all(
            isinstance(arg, expected)
            for arg, expected in zip(
                [data, num_data_rows, title, table_width], [dict, int, str, int]
            )
        )
        or num_data_rows < 1
        or table_width < 1
    ):
        return "Invalid input."

    all_keys = sorted(set(data.keys()) | set(stack_data.keys()))
    num_columns = len(all_keys)
    if num_columns == 0:
        return "<p>No data available.</p>"

    # Randomize CSS prefixes so that multiple tables on a page never collide.
    prefix = ut.random_string(4)

    marker_color = marker_color or "darkblue"
    marker_class_map: dict[str, list[str]] = {}

    if open_marker_label or close_marker_label:

        # Resolve fuzzy marker labels (prefix match) to concrete keys.
        def resolve_marker(label: str | None) -> str | None:
            if not label:
                return None
            for key in all_keys:
                if key.startswith(label):
                    return key
            return None

        open_marker_key = resolve_marker(open_marker_label)
        close_marker_key = resolve_marker(close_marker_label)

        if open_marker_key:
            marker_class_map.setdefault(open_marker_key, []).append(
                f"{prefix}-marker-left"
            )
        if close_marker_key:
            marker_class_map.setdefault(close_marker_key, []).append(
                f"{prefix}-marker-right"
            )

    marker_css = ""
    if marker_class_map:
        marker_css = f"""
        .{prefix}-marker-left {{
            border-left: 1px dotted {marker_color};
        }}
        .{prefix}-marker-right {{
            border-right: 1px dotted {marker_color};
        }}
        """

    totals: dict[str, float] = {}
    base_values: dict[str, float] = {}
    stack_values: dict[str, float] = {}
    for key in all_keys:
        # Track each column's primary + stack contributions for later use.
        base_values[key] = float(data.get(key, 0) or 0)
        stack_values[key] = float(stack_data.get(key, 0) or 0)
        totals[key] = base_values[key] + stack_values[key]

    provided_max = None
    if max_value is not None:
        try:
            provided_max = float(max_value)
        except (TypeError, ValueError):
            provided_max = None
        if provided_max is not None and provided_max <= 0:
            provided_max = None

    reference_max = (
        provided_max if provided_max is not None else max(totals.values(), default=0)
    )

    normalized_primary: dict[str, int] = {}
    normalized_secondary: dict[str, int] = {}
    normalized_totals: dict[str, int] = {}

    for key in all_keys:
        # Convert real-valued totals into integer row counts.
        combined_value = totals[key]
        if reference_max:
            clamped_total = (
                min(combined_value, reference_max) if provided_max else combined_value
            )
            total_height = int(round((clamped_total / reference_max) * num_data_rows))
        else:
            total_height = 0

        if stack_values[key] and combined_value and total_height:
            base_ratio = base_values[key] / combined_value if combined_value else 0
            base_ratio = min(max(base_ratio, 0), 1)
            primary_height = int(round(total_height * base_ratio))
            secondary_height = total_height - primary_height
        else:
            primary_height = total_height
            secondary_height = 0

        normalized_primary[key] = max(primary_height, 0)
        normalized_secondary[key] = max(secondary_height, 0)
        normalized_totals[key] = max(total_height, 0)

    if mini:
        # Mini histograms rely on em-based widths for predictable compactness.
        cell_width = max(0.4, min(1.0, 6.0 / max(num_columns, 1)))
        cell_width_style = f"{cell_width}em"
        empty_width_style = cell_width_style
    else:
        cell_width = 100 / num_columns if num_columns else 0
        cell_width_style = f"{cell_width}%" if num_columns else "auto"
        empty_width_style = cell_width_style
    padding_value = max(0.2, max([len(k) for k in all_keys]) * 0.2)

    has_stack = bool(stack_data)
    top_text_color = "#333333" if has_stack else "white"
    zero_text_color = "#333333" if has_stack else bar_color

    secondary_styles = ""
    if any(normalized_secondary.values()):
        secondary_styles = f"""
        .{prefix}-bar-cell-secondary {{
            background-color: {stack_color}; width: {cell_width}%;
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
        }}
        .{prefix}-bar-top-cell-secondary {{
            text-align: center; font-size: 0.8em;
            color: {top_text_color}; background-color: {stack_color};
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
        }}
        """

    # Inline styles keep the widget self-contained so it can be embedded anywhere.
    html_table = f"""
    <style>
        .{prefix}-table {{ font-family: sans-serif;
                border-collapse: collapse; border: 1px solid {border_color};
                width: {table_width}%;}}
        .{prefix}-empty-cell {{ background-color: white; width: {empty_width_style}; min-width: {empty_width_style}; max-width: {empty_width_style}; }}
        .{prefix}-category-label {{
            transform: rotate(-90deg); padding: {padding_value}em 0;
            border: 1px solid {border_color};border-top: 2px solid {bar_color};
            font-size: 0.85em; text-align: center;
            font-size: 0.85em; text-align: center;
        }}
        .{prefix}-bar-cell {{
            background-color: {bar_color}; width: {cell_width_style};
            min-width: {cell_width_style}; max-width: {cell_width_style};
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
        }}
        .{prefix}-bar-top-cell {{
            text-align: center; font-size: 0.8em;
            color: {top_text_color}; background-color: {bar_color};
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
        }}
        .{prefix}-zero-bar-cell {{
            text-align: center; font-size: 0.8em;
            color: {zero_text_color}; background-color: white; width: {cell_width_style};
            border-left: 1px solid {border_color}; border-right: 1px solid {border_color};
            border-bottom: 2px solid {bar_color}
        }}
        .{prefix}-emptiness-cell {{ background-color: white; width: {empty_width_style}; min-width: {empty_width_style}; max-width: {empty_width_style}; }}
        .{prefix}-titles {{ text-align: center; background-color: white; }}
        {secondary_styles}
        {marker_css}
    </style>
    """

    table_open = f"<table class='{prefix}-table'>"
    table_close = "</table>"
    if link_target:
        table_open = (
            f"<a href='{link_target}' style='text-decoration:none; color:inherit;'>"
            f"{table_open}"
        )
        table_close = f"{table_close}</a>"

    html_table += f"""
        {table_open}

        """
    if title and not mini:
        html_table += f"""<tr><td colspan='{num_columns}' class='{prefix}-titles'
            >{title}</td></tr>"""

    if not mini:
        html_table += "<tr>"
        for key in all_keys:
            cell_classes = [f"{prefix}-empty-cell"]
            cell_classes.extend(marker_class_map.get(key, []))
            html_table += f"<td class='{' '.join(cell_classes)}'>&nbsp;</td>"
        html_table += "</tr>"

    empty_text = "" if mini else "&nbsp;"
    for row_index in range(num_data_rows):
        # Build the histogram top-down so that CSS borders align naturally.
        html_table += "<tr>"
        for key in all_keys:
            total_height = normalized_totals[key]
            primary_height = normalized_primary[key]
            secondary_height = normalized_secondary[key]
            marker_classes = marker_class_map.get(key, [])

            if total_height == 0:
                if row_index == num_data_rows - 1:
                    val = "" if mini else int(round(totals[key]))
                    cell_classes = [f"{prefix}-zero-bar-cell"]
                    cell_classes.extend(marker_classes)
                    html_table += (
                        f"<td class='{' '.join(cell_classes)}'><b>{val}</b></td>"
                    )
                else:
                    cell_classes = [f"{prefix}-emptiness-cell"]
                    cell_classes.extend(marker_classes)
                    html_table += (
                        f"<td class='{' '.join(cell_classes)}'>{empty_text}</td>"
                    )
                continue

            row_from_bottom = num_data_rows - 1 - row_index
            if row_from_bottom >= total_height:
                cell_classes = [f"{prefix}-emptiness-cell"]
                cell_classes.extend(marker_classes)
                html_table += f"<td class='{' '.join(cell_classes)}'>{empty_text}</td>"
                continue

            is_top_cell = row_from_bottom == total_height - 1
            in_primary = row_from_bottom < primary_height

            if in_primary:
                classes = [f"{prefix}-bar-cell"]
                if is_top_cell and secondary_height == 0:
                    classes.append(f"{prefix}-bar-top-cell")
            else:
                classes = [f"{prefix}-bar-cell-secondary"]
                if is_top_cell:
                    classes.append(f"{prefix}-bar-top-cell-secondary")

            if is_top_cell:
                display_val = "" if mini else int(round(totals[key]))
            else:
                display_val = empty_text

            classes.extend(marker_classes)
            html_table += f"<td class='{' '.join(classes)}'>{display_val}</td>"

        html_table += "</tr>\n"

    if not mini:
        html_table += "<tr>"
        for key in all_keys:
            cell_classes = [f"{prefix}-category-label"]
            cell_classes.extend(marker_class_map.get(key, []))
            html_table += f"<td class='{' '.join(cell_classes)}'>{key}</td>"
        html_table += "</tr>\n"

    if subtitle:
        html_table += f"""<tr><td colspan='{num_columns}' class='{prefix}-titles'
            style='font-size:0.85em'>{subtitle}</td></tr>"""

    html_table += table_close
    return html_table


def html_histogram_matrix(
    matrix: HistogramMatrixResult,
    dimension,
    *,
    title: str = "",
    subtitle: str = "",
    table_width: int = 60,
    border_color: str = "black",
    visit_threshold: float = 0.05,
    show_counts: bool = True,
    use_contrasting_text: bool = False,
    normalization_mode: str = HistogramMatrixResult.NORMALIZATION_BLEND,
) -> str:
    """Render a 2D histogram matrix (arrival x duration) as HTML.

    Args:
        matrix: ``HistogramMatrixResult`` carrying raw and normalized values.
        dimension: ``datacolors.Dimension`` instance to translate magnitudes to CSS.
        title: Optional heading shown above the matrix.
        subtitle: Optional text rendered below the axis labels.
        table_width: Percentage width to allocate to the table.
        border_color: CSS color applied to table borders.
        visit_threshold: Minimum mean visits required before numbers are shown.
        show_counts: When false suppresses numeric labels entirely.
        use_contrasting_text: Prefer ``css_bg_fg`` if the dimension exposes it.
        normalization_mode: Controls how intensities are scaled:
            - ``"column"`` (default): scale per arrival column.
            - ``"global"``: scale against the single global max.
            - ``"blend"``: average of the column and global scales.

    Returns:
        Fully composed HTML snippet ready for embedding.
    """

    if not matrix.arrival_labels or not matrix.duration_labels:
        return "<p>No data available.</p>"

    try:
        visit_threshold = float(visit_threshold)
    except (TypeError, ValueError):
        visit_threshold = 0.0
    # Negative thresholds make no sense for visit counts, so clamp up.
    visit_threshold = max(0.0, visit_threshold)

    if dimension is None:
        try:
            import datacolors as dc  # type: ignore
        except ModuleNotFoundError:
            from web import datacolors as dc  # type: ignore

        # Fall back to a simple pastel-to-purple ramp if no palette is provided.
        dimension = dc.Dimension()
        dimension.add_config(0.0, "lemonchiffon")
        dimension.add_config(0.35, "khaki")
        dimension.add_config(0.7, "orchid")
        dimension.add_config(1.0, "purple")

    table_width = table_width or 0
    table_width = max(table_width, 10)
    width_style = f"{table_width}%" if table_width else "auto"
    # Prefix randomization ensures multiple tables can co-exist without CSS bleed.
    prefix = ut.random_string(4)

    data_columns = len(matrix.arrival_labels)
    colspan = data_columns + 2
    duration_labels = list(matrix.duration_labels)[::-1]

    color_func_name = (
        "css_bg_fg"
        if use_contrasting_text and hasattr(dimension, "css_bg_fg")
        else "css_bg"
    )
    # Dimension instances expose helpers that return inline CSS declarations;
    # pick whichever variant delivers readable text for the current settings.
    color_func = getattr(dimension, color_func_name)

    data_cell_width_em = 1.2
    row_unit_em = 0.18
    cell_height_em = row_unit_em * 2

    style_block = f"""
    <style>
        .{prefix}-table {{font-family: sans-serif;
                border-collapse: collapse;
                border: 1px solid {border_color};
                #width: {width_style};
        }}
        .{prefix}-title-row {{
            background: white;
        }}
        .{prefix}-title-cell {{
            text-align: center;
            font-weight: bold;
            padding: 0.4em 0.6em;
            background: white;
            border-bottom: 1px solid {border_color};
        }}
        .{prefix}-subtitle-cell {{
            text-align: center;
            font-size: 0.85em;
            padding: 0.35em 0.6em;
            background: white;
            border-top: 1px solid {border_color};
        }}
        .{prefix}-duration-axis-label {{
            text-align: center;
            vertical-align: middle;
            white-space: nowrap;
            font-weight: normal;
            font-size: 0.85em;
            width: 1.5em;
        }}
        .{prefix}-duration-axis-label div {{
            width: 0;
            display: inline-block;
            transform: rotate(-90deg);
            transform-origin: center center;
        }}
        .{prefix}-duration-label-cell {{
            text-align: right;
            font-weight: normal;
            font-size: 0.8em;
            ZZZpadding: 0.3em 0.4em;
            white-space: nowrap;
            border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
            border-bottom: 1px solid {border_color};
        }}
        .{prefix}-arrival-label-cell {{
            position: relative;
            #text-align: right;
            font-weight: normal;
            #padding: 0;
            background: white;
            white-space: nowrap;
            height: 6ch;
            border-left: 1px solid {border_color};
            border-right: 1px solid {border_color};
            border-top: 1px solid {border_color};
            border-bottom: 0px solid {border_color};
        }}
        .{prefix}-arrival-label-text {{
            position: absolute;
            left: 2.5ch;
            bottom: 4ch;
            #bottom: 0.3em;
            transform: translateX(-50%) rotate(-90deg);
            transform-origin: bottom center;
            white-space: nowrap;
            font-weight: normal;
            font-size: 0.8em;
        }}
        .{prefix}-axis-corner {{
            border: 1px solid {border_color};
            background: white;
        }}
        .{prefix}-arrival-axis-label {{
            text-align: center;
            padding: 0.4em 0.6em;
            font-weight: normal;
            font-size: 0.8em;
            background: white;
            border-left: 1px solid {border_color};
            border-right: 1px solid {border_color};
            border-bottom: 1px solid {border_color};
        }}
        .{prefix}-data-cell {{
            text-align: center;
            font-size: 0.75em;
            padding: 0;
            min-width: {data_cell_width_em:.2f}em;
            ZZZborder-bottom: 1px solid {border_color};
        }}
        .{prefix}-empty-cell {{
            background: white;
            border-bottom: 0px solid {border_color};
            min-width: {data_cell_width_em:.2f}em;
        }}
    </style>
    """

    # Build HTML in chunks; it keeps string reallocations under control.
    parts: list[str] = [style_block]
    parts.append(f"<table class='{prefix}-table'>")

    if title:
        parts.append(
            f"<tr class='{prefix}-title-row'><th class='{prefix}-title-cell' "
            f"colspan='{colspan}'>{title}</th></tr>"
        )

    matrix.normalize(normalization_mode=normalization_mode)

    normalized_mode = (normalization_mode or "column").lower()
    if normalized_mode not in {"column", "global", "blend"}:
        normalized_mode = "column"

    per_column_lookup = matrix.normalized_values

    global_max = 0.0
    for raw_row in matrix.raw_values.values():
        for value in raw_row.values():
            if value > global_max:
                global_max = value
    # Figure out whether we need normalized (0..1) values based on a global max.
    if global_max > 0.0:
        global_lookup = {
            arrival_label: {
                duration_label: (
                    matrix.raw_values.get(arrival_label, {}).get(duration_label, 0.0)
                    / global_max
                )
                for duration_label in duration_labels
            }
            for arrival_label in matrix.arrival_labels
        }
    else:
        global_lookup = {
            arrival_label: {duration_label: 0.0 for duration_label in duration_labels}
            for arrival_label in matrix.arrival_labels
        }

    # Choose the normalization table based on the requested mode.
    if normalized_mode == "column":
        normalized_lookup = per_column_lookup
    elif normalized_mode == "global":
        normalized_lookup = global_lookup
    else:
        normalized_lookup = {}
        for arrival_label in matrix.arrival_labels:
            column_row = per_column_lookup.get(arrival_label, {})
            matrix_row = global_lookup.get(arrival_label, {})
            blended_row: dict[str, float] = {}
            for duration_label in duration_labels:
                column_val = column_row.get(duration_label, 0.0)
                matrix_val = matrix_row.get(duration_label, 0.0)
                blended_row[duration_label] = (column_val + matrix_val) / 2.0
            normalized_lookup[arrival_label] = blended_row

    # Track where each column's data stack begins so empty padding stays put.
    column_top_indices: dict[str, int] = {}
    for arrival_label in matrix.arrival_labels:
        column_top_indices[arrival_label] = next(
            (
                idx
                for idx, duration_label in enumerate(duration_labels)
                if matrix.raw_values.get(arrival_label, {}).get(duration_label, 0.0)
                > 0.0
            ),
            None,
        )

    _first_data_row = True
    for row_index, duration_label in enumerate(duration_labels):
        parts.append("<tr>")
        # For first row, create a rowspan column for the y axis label
        if _first_data_row:
            _first_data_row = False
            parts.append(
                f"<td rowspan='{len(duration_labels)}' class='{prefix}-duration-axis-label' style='text-align: center'>"
                "<div>Duration of visit</div>"
                "</td>"
            )

        display_duration = VTime(duration_label).short or "&nbsp;"
        parts.append(
            f"<th class='{prefix}-duration-label-cell'>{display_duration}</th>"
        )
        for arrival_label in matrix.arrival_labels:
            raw_row = matrix.raw_values.get(arrival_label, {})
            normalized_row = normalized_lookup.get(arrival_label, {})
            normalized_value = normalized_row.get(duration_label, 0.0)
            raw_value = raw_row.get(duration_label, 0.0)
            is_above_threshold = raw_value >= visit_threshold
            effective_value = normalized_value if is_above_threshold else 0.0
            cell_text = "&nbsp;"
            mean_visits = float(raw_value)
            # Provide human-friendly hover text for analysts poking at cells.
            tooltip = (
                "There were\n"
                f"  {mean_visits:.2f} visits {'' if matrix.day_count == 1 else 'per day'}\n"
                f"  that started at {arrival_label}\n"
                f"  and lasted {VTime(duration_label).short} hours\n"
            )
            title_text = escape(tooltip, quote=True).replace("\n", "&#10;")

            top_index = column_top_indices.get(arrival_label)
            is_empty_above_stack = top_index is None or row_index < top_index

            if is_empty_above_stack:
                style_attr = f"height: {cell_height_em:.3f}em; min-height: {cell_height_em:.3f}em;"
                parts.append(
                    f"<td class='{prefix}-empty-cell' style='{style_attr}'>&nbsp;</td>"
                )
                continue
            if show_counts:
                # Only show values when the associated raw metric clears the threshold.
                if is_above_threshold:
                    if raw_value.is_integer():
                        cell_text = str(int(raw_value))
                    else:
                        cell_text = f"{raw_value:.2f}"
                else:
                    cell_text = "0"
            classes = [f"{prefix}-data-cell"]
            style_value = color_func(effective_value)
            style_components = [
                style_value,
                f"height: {cell_height_em:.3f}em;",
                f"min-height: {cell_height_em:.3f}em;",
            ]
            if top_index is not None and row_index >= top_index:
                style_components.append(f"border-left: 1px solid {border_color};")
                style_components.append(f"border-right: 1px solid {border_color};")
                if row_index == top_index:
                    style_components.append(f"border-top: 1px solid {border_color};")
            style_attr = " ".join(style_components)
            parts.append(
                f"<td class='{' '.join(classes)}' style='{style_attr}' "
                f"title='{title_text}'>{cell_text}</td>"
            )
        parts.append("</tr>")

    parts.append("<tr>")
    parts.append(f"<th colspan=2 rowspan=2 class='{prefix}-axis-corner'>&nbsp;</th>")
    for arrival_label in matrix.arrival_labels:
        display_arrival = arrival_label if arrival_label else "&nbsp;"
        parts.append(
            f"<th class='{prefix}-arrival-label-cell'><span class='{prefix}-arrival-label-text'>{display_arrival}</span></th>"
        )
    parts.append("</tr>")

    parts.append("<tr>")
    # parts.append(f"<th colspan=2 class='{prefix}-axis-corner'>&nbsp;</th>")
    parts.append(
        f"<td class='{prefix}-arrival-axis-label' colspan='{data_columns}'>Time of arrival</td>"
    )
    parts.append("</tr>")

    if subtitle:
        parts.append(
            f"<tr><td colspan='{colspan-1}' class='{prefix}-subtitle-cell'>{subtitle}</td></tr>"
        )

    parts.append("</table>")
    return "\n".join(parts)


__all__ = [
    "html_histogram",
    "html_histogram_matrix",
]
