#!/usr/bin/python3

"""This works to print a vertical bar chart.

It is not yet in use in tagtracker.

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

import random
import string


def chartjs_histogram(
    category_labels: list,
    datasets: list[list],
    width: str = "",
    height: str = "",
    bar_colors_list: list[str] = None,
    data_labels_list: list[str] = None,
    mini: bool = False,
    title: str = "",
    subtitle: str = "",
):
    """Make a vertical bar chart.

    width, height need units -- %, em, px, in, etc. Can be empty.
    mini: if True, makes a histogram that has no labels or other decorations
    """

    my_datasets = datasets

    uniq = f"Z{random_string(4)}"
    canvas_id = f"Z{uniq}_chart"

    # A "mini" has no border, puts title underneat, has no tooltips and no legends
    # In a mini, the title goes at the bottom, and the subtitle (if present) is a hyperlink
    if mini:
        tooltips_bit = "events: [],"
        border_bit = ""
        border_bit = "border: 1px solid grey;"
        title_bit = ""
        axis_label_bit = (
            f"title: {{ display: true, text: '{title}' }}," if title else ""
        )
        if subtitle:
            hyperlink_bit = (
                f"<a href='{subtitle}' style='display: block; "
                "width: 100%; height: 100%; text-decoration: none; color: inherit;'>"
            )
        else:
            hyperlink_bit = ""
    else:
        tooltips_bit = ""
        border_bit = "border: 1px solid grey;"
        title_bit = f"title: {{display: true,text: '{title}',font: {{ size: 14 }} }}," if title else ""
        hyperlink_bit = ""
        axis_label_bit = (
            f"title: {{ display: true, text: '{subtitle}' }}," if subtitle else ""
        )

    print(
        f"""
        <div style="height:{height}; width: {width}; {border_bit}">
        {hyperlink_bit}
        <canvas id="{canvas_id}"></canvas>
        {"</a>" if hyperlink_bit else ""}
        </div>

        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

        <script>
        const {uniq}_ctx = document.getElementById('{canvas_id}').getContext('2d');
        const {uniq}_chart = new Chart({uniq}_ctx, {{
        type: 'bar',
        //plugins: [chartAreaBorder],
        data: {{
            labels: {category_labels},
            datasets: [
        """
    )

    for set_num, points in enumerate(my_datasets):
        if bar_colors_list and set_num < len(bar_colors_list):
            bg_bit = f"backgroundColor: ['{bar_colors_list[set_num]}'],"
        else:
            bg_bit = ""
        if data_labels_list and set_num < len(data_labels_list):
            label_bit = f"label: '{data_labels_list[set_num]}',"
        else:
            label_bit = ""
        print(
            f"""
            {{
                {label_bit}
                data: {points},
                categoryPercentage: 0.8,
                barPercentage: 1.0,
                {bg_bit}
            }},
            """
        )

    print(
        f"""
        ],
        }},

        options: {{
            plugins: {{
                {title_bit}
                legend: {{ display: false }},
                //chartAreaBorder: {{
                //    display: true,
                //    borderColor: 'black',
                //    borderWidth: 3,
                //}},
            }},
            scales: {{
                x: {{
                    border: {{display: true, width: 2, color:'black'}},
                    ticks: {{
                        display: {str(not mini).lower()},
                        autoSkip: false,
                        maxRotation: 90,
                        minRotation: 90
                        }},
                    grid: {{ display: false }},
                    {axis_label_bit}
                }},
                y: {{
                    display: {str(not mini).lower()},
                    grid: {{ display: false }},
                }}
            }},
            {tooltips_bit}
            maintainAspectRatio: false,
            responsive: true,
            animation: false,
            //plugins: [chartAreaBorder ],
        }},
        //plugins: [chartAreaBorder ],
      }});
      </script>
      </body>
      </html>
      """
    )


def randon_dict(length: int) -> dict:
    mydict = {random_string(3, 8): random.randint(0, 100) for _ in range(length)}
    return mydict


def randon_labels(length: int) -> list:
    mylist = [random_string(3, 8) for _ in range(length)]
    return mylist


def randon_data(length: int) -> list:
    mylist = [random.randint(0, 15) for _ in range(length)]
    return mylist


def random_string(min_length=4, max_length=None):
    """Create a random alphaetic string of a given length."""
    if not max_length or min_length == max_length:
        length = min_length
    else:
        length = random.randint(min_length, max_length)
    return "".join(random.choice(string.ascii_letters) for _ in range(length))


print(
    """Content-type: text/html

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chart.js Example</title>
</head>
<body>
"""
)

data = randon_dict(50)

for c1, c2 in [["tomato", "blue"], ["grey", "green"], ["black", "red"]]:
    size = random.randint(5, 30)
    data_lists = [randon_data(size), randon_data(size)]
    data_labels = randon_labels(size)
    chartjs_histogram(
        data_labels,
        data_lists,
        "1.5in",
        "1in",
        bar_colors_list=[c1, c2],
        data_labels_list=["Some category", "Another category"],
        mini=True,
        title="THis is a title",
        subtitle="http://www.example.com"
    )
    print( "<br>")
    chartjs_histogram(
        data_labels,
        data_lists,
        "7in",
        "4in",
        bar_colors_list=[c1, c2],
        data_labels_list=["Some category", "Another category"],
        mini=False,
        title="This is also a title",
    )
    print("<br><br>")