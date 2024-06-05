"""Create html tables that can act as legends for Dimension and MultiDimensions.

MIT License

Copyright (c) 2023, github.com/tevpg

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the Software
is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS," WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import datacolors as dc


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
            .colortable2d {{
                border-collapse: collapse;
                font-size: 0.8rem;
            }}
            .colortable2d, .colortable2d th, .colortable2d td {{
                border: none;
            }}
            .colortable2d th, .colortable2d td {{
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
            .colortable2d {{ border: 1px solid #000;}}
            .colortable2d tr {{border-top: 1px solid #000;}}
            .colortable2d tr + tr {{border-top: 1px solid white;}}
            .colortable2d td {{border-left: 1px solid #000;}}
            .colortable2d td + td {{border-left: 1px solid white;}}
            </style>"""
        return s


def html_2d_color_table(
    factory: dc.MultiDimension,
    title: str = "",
    x_label: str = "",
    y_label: str = "",
    num_rows: int = 20,
    num_columns: int = 20,
    cell_size: int = 25,
) -> str:
    """Create html color table for cf and return it as a string."""

    def cell(
        factory: dc.MultiDimension,
        x_index,
        y_index,
        x_label: str = "",
        y_label: str = "",
    ) -> str:
        """Return a coloured html table cell."""
        this_color = factory.get_color(x_index, y_index)
        title_text = (
            f"{x_label}: {round(x_index)}\n{y_label}: {round(y_index)}"
        )
        c = factory.get_color(x_index, y_index).html_color
        return f"<td style='{this_color.css_bg()}' title='{title_text}'></td>"

    x: dc.Dimension = factory.dimensions[0]
    y: dc.Dimension = factory.dimensions[1]
    # custom_labels = bool(x_label or y_label)
    x_label = x.get_label()
    y_label = y.get_label()
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
        f"""<table class='colortable2d'>
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
        html.add(cell(factory, x_index, y_index, x_label, y_label))
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
            html.add(cell(factory, x_index, y_index, x_label, y_label))
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
        html.add(cell(factory, x_index, y_index, x_label, y_label))
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

def html_1d_text_color_table(
    dim: dc.Dimension,
    title: str = "",
    subtitle: str = "",
    marker:str = chr(0x25cf),
    num_columns: int = 20,
    cell_size: int = 25,
    bg_color: dc.Color = dc.Color('white'),
) -> str:
    """Create html color table for cf and return it as a string."""

    def cell(
        dim: dc.Dimension,
        index,
        label: str = "",
        bg_color: dc.Color = dc.Color('lightgrey'),
    ) -> str:
        """Return a text-coloured html table cell."""
        this_color = dim.get_color(index).css_fg()
        title_text = (
            f"{label}: {round(index)}"
        )
        bg_color = dc.Color(bg_color).css_bg()
        return f"<td style='text-align:center;{this_color};{bg_color};' title='{title_text}'>{marker}</td>"

    label = dim.get_label()
    title = title if title else label
    html = HtmlHelper()
    html.add(HtmlHelper.style_sheet(cell_size))
    html.add(
        f"""<table class='colortable2d'>
            <tbody>
            <tr>
                <td colspan="{num_columns}" style="text-align: center"><b>{title}</b></td>
            </tr>
    """
    )

    # A row of colors
    html.add("<tr>")
    step = dim.range / (num_columns)
    index = dim.min
    for _ in range(num_columns):
        html.add(cell(dim,index,label=label))
        index += step
    html.add("</tr>")
    # A row to show the values
    html.add("<tr>")
    html.add(f"<td colspan=2 style='text-align:left;{dim.css_bg_fg(dim.min)};'>{round(dim.min)}</td>")
    html.add(f"<td colspan={num_columns-4} style='text-align:center'>{subtitle}</td>")
    html.add(f"<td colspan=2 style='{dim.css_bg_fg(dim.max)};'>{round(dim.max)}</td>")
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
            html_2d_color_table(
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
