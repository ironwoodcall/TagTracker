"""Create an html table showing shades of a 2d MultiDimension."""

import datacolors as dc

##import data_color_extras as extras


class HtmlHelper:
    """Quick and dirty html bits."""

    def __init__(self) -> None:
        """Initialize."""
        self.text = ""

    def print(self):
        """Print self."""
        print(self.text)
        self.text = ""

    def add(self, text_to_add):
        """Add more text to self."""
        self.text += text_to_add

    @staticmethod
    def html_bottom():
        """Return bottom of html document."""
        return "</body></html>"

    @staticmethod
    def html_top(title: str = ""):
        """Return a top-of-html document."""
        return f"""Content-type: text/html\n\n
            <!DOCTYPE html>
            <html>
            <head>
            <title>{title}</title>
            </head>
            <body>
    """

    @staticmethod
    def style_sheet(cell_wid: int = 25) -> str:
        """Return a style sheet for the table."""

        s = f"""<style>
            .colortable {{
                border-collapse: collapse;
                font-size: 0.8rem;
            }}
            .colortable, .colortable th, .colortable td {{
                border: none;
            }}
            .colortable th, .colortable td {{
                width: {cell_wid}px;
                height: {cell_wid}px;
                padding: 0;
            }}
            .rotate {{
                text-align: center;
                white-space: nowrap;
                vertical-align: middle;
                width: 1.5em;
            }}
            .rotate div {{
                -moz-transform: rotate(-90.0deg);  /* FF3.5+ */
                    -o-transform: rotate(-90.0deg);  /* Opera 10.5 */
                -webkit-transform: rotate(-90.0deg);  /* Saf3.1+, Chrome */
                            filter:  progid:DXImageTransform.Microsoft.BasicImage(rotation=0.083);  /* IE6,IE7 */
                        -ms-filter: "progid:DXImageTransform.Microsoft.BasicImage(rotation=0.083)"; /* IE8 */
                        margin-left: -10em;
                        margin-right: -10em;
            }}
            .colortable {{ border: 1px solid #000;}}
            .colortable tr {{border-top: 1px solid #000;}}
            .colortable tr + tr {{border-top: 1px solid white;}}
            .colortable td {{border-left: 1px solid #000;}}
            .colortable td + td {{border-left: 1px solid white;}}
            </style>"""
        return s


def make_html_color_table(
    factory: dc.MultiDimension,
    title: str = "",
    x_label: str = "",
    y_label: str = "",
    num_rows: int = 20,
    num_columns: int = 20,
    cell_size: int = 25,
) -> str:
    """Create html color table for cf and return it as a string."""

    def axis_label(dim: dc.Dimension) -> str:
        """Make a default label for this dimension."""
        lab = " => ".join([p.color.similar_to() for p in dim.configs])
        if dim.interpolation_exponent != 1:
            lab = f"{lab}  exp={dim.interpolation_exponent}"
        return lab

    def cell(
        factory: dc.MultiDimension,
        x_index,
        y_index,
        x_label: str = "",
        y_label: str = "",
        custom_labelling: bool = True,
    ) -> str:
        """Return a coloured html table cell."""
        this_color = factory.get_color(x_index, y_index)
        if custom_labelling:
            title_text = (
                f"{x_label}: {round(x_index)}\n{y_label}: {round(y_index)}"
            )
        else:
            title_text = this_color.html_color
        c = factory.get_color(x_index, y_index).html_color
        return f"<td style='{this_color.css_bg()}' title='{title_text}'></td>"

    x: dc.Dimension = factory.dimensions[0]
    y: dc.Dimension = factory.dimensions[1]
    custom_labels = bool(x_label or y_label)
    if not x_label:
        x_label = axis_label(x)
    if not y_label:
        y_label = axis_label(y)
    if not title:
        title = f"Blend method: {factory.blend_method}"

    x_min = x.min
    x_max = x.max
    y_min = y.min
    y_max = y.max

    x_step = x.range / (num_columns - 1)
    y_step = y.range / (num_rows - 1)

    html = HtmlHelper()

    # Generate the HTML code
    html.add(HtmlHelper.style_sheet(cell_size))
    html.add(
        f"""<table class='colortable'>
            <tbody>
            <tr>
                <td colspan="{num_columns+1}" style="text-align: center">{title}</td>
            </tr>
    """
    )

    # Generate the data rows
    # top row (includes y_max)

    y_index = y.max
    rownum = 1
    html.add("            <tr>")
    html.add(
        f"               <td style='{y.css_bg_fg(y_max)}'>{round(y_max)}</td>"
    )
    x_index = x_min
    for _ in range(num_columns):
        html.add(
            cell(factory, x_index, y_index, x_label, y_label, custom_labels)
        )
        x_index += x_step
    html.add("</tr>\n")
    rownum += 1
    y_index -= y_step

    html.add(
        "<tr>"
        f"<td rowspan='{num_rows-1}' class='rotate' style='text-align: center'>"
        f"<div>{y_label}</div>"
        "</td></tr>"
    )

    while rownum < num_rows:
        html.add("            <tr>")
        x_index = x_min
        for _ in range(num_columns):
            html.add(
                cell(
                    factory, x_index, y_index, x_label, y_label, custom_labels
                )
            )
            x_index += x_step
        html.add("</tr>\n")
        rownum += 1
        y_index -= y_step

    # bottom row (includes y_min)
    html.add("            <tr>")
    html.add(
        f"               <td style='text-align: center;{y.css_bg_fg(y_min)}'>{round(y_min)}</td>"
    )
    x_index = x_min
    for _ in range(num_columns):
        html.add(
            cell(factory, x_index, y_index, x_label, y_label, custom_labels)
        )
        x_index += x_step
    html.add("</tr>\n")

    # label row at the bottom
    bottom_row_merge = 2
    html.add("<tr>")
    html.add("<td></td>")
    html.add(
        f"<td colspan={bottom_row_merge} "
        f'style="text-align: center;{x.css_bg_fg(x_min)};">'
        f"{round(x_min)}</td>"
    )
    html.add(
        f"<td colspan={num_columns - 2 * bottom_row_merge} "
        f'style="text-align: center">{x_label}</td>'
    )
    html.add(
        f"<td colspan={bottom_row_merge} "
        f'style="text-align: right; {x.css_bg_fg(x_max)};">'
        f"{round(x_max)}</td>"
    )
    html.add("</tr>")

    # Close the HTML
    html.add(
        """        </tbody>
        </table>
    """
    )
    return html.text


if __name__ == "__main__":
    ROWS = 30
    COLUMNS = 30
    CELL_WIDTH = 20

    cf = dc.MultiDimension()  # dc.BLEND_MULTIPLICATIVE)
    d = cf.add_dimension(0.8)
    d.add_config(0, "white")
    d.add_config(50, "blue")  # (100,255,255))
    d = cf.add_dimension(0.8)
    d.add_config(0, "white")
    d.add_config(100, "red")  # "#4343d3")#"royalblue")

    print(HtmlHelper.html_top())
    for blend in [
        dc.BLEND_MULTIPLICATIVE,
        dc.BLEND_MIN,
        dc.BLEND_MAX,
        dc.BLEND_ALPHA,
        dc.BLEND_SUBTRACTIVE,
        dc.BLEND_DIFFERENCE,
        dc.BLEND_OVERLAY,
        dc.BLEND_ADDITIVE,
    ]:
        cf.blend_method = blend
        print(
            make_html_color_table(
                cf,
                # title="Legend for activity chart",
                # x_label="Busy (in+out)",
                # y_label="Full (bikes present)",
                num_columns=COLUMNS,
                num_rows=ROWS,
                cell_size=CELL_WIDTH,
            )
        )

    print(HtmlHelper.html_bottom)

    dump = cf.dump(quiet=True)
    print("\n\n<pre>")
    for l in dump:
        print(l)
    print("</pre>")
