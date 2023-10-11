"""Map (x,y) data values onto (RGB) colour space.

Copyright (C) 2023 Todd Glover

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

import math
import statistics
import random

ColourDef = tuple | str


_COLOURS = {
    "maroon": (128, 0, 0),
    "darkred": (139, 0, 0),
    "brown": (165, 42, 42),
    "firebrick": (178, 34, 34),
    "crimson": (220, 20, 60),
    "red": (255, 0, 0),
    "tomato": (255, 99, 71),
    "coral": (255, 127, 80),
    "indianred": (205, 92, 92),
    "lightcoral": (240, 128, 128),
    "darksalmon": (233, 150, 122),
    "salmon": (250, 128, 114),
    "lightsalmon": (255, 160, 122),
    "orangered": (255, 69, 0),
    "darkorange": (255, 140, 0),
    "orange": (255, 165, 0),
    "gold": (255, 215, 0),
    "darkgoldenrod": (184, 134, 11),
    "goldenrod": (218, 165, 32),
    "palegoldenrod": (238, 232, 170),
    "darkkhaki": (189, 183, 107),
    "khaki": (240, 230, 140),
    "olive": (128, 128, 0),
    "yellow": (255, 255, 0),
    "yellowgreen": (154, 205, 50),
    "darkolivegreen": (85, 107, 47),
    "olivedrab": (107, 142, 35),
    "lawngreen": (124, 252, 0),
    "chartreuse": (127, 255, 0),
    "greenyellow": (173, 255, 47),
    "darkgreen": (0, 100, 0),
    "green": (0, 128, 0),
    "forestgreen": (34, 139, 34),
    "lime": (0, 255, 0),
    "limegreen": (50, 205, 50),
    "lightgreen": (144, 238, 144),
    "palegreen": (152, 251, 152),
    "darkseagreen": (143, 188, 143),
    "mediumspringgreen": (0, 250, 154),
    "springgreen": (0, 255, 127),
    "seagreen": (46, 139, 87),
    "mediumaquamarine": (102, 205, 170),
    "mediumseagreen": (60, 179, 113),
    "lightseagreen": (32, 178, 170),
    "darkslategray": (47, 79, 79),
    "teal": (0, 128, 128),
    "darkcyan": (0, 139, 139),
    "aqua": (0, 255, 255),
    "cyan": (0, 255, 255),
    "lightcyan": (224, 255, 255),
    "darkturquoise": (0, 206, 209),
    "turquoise": (64, 224, 208),
    "mediumturquoise": (72, 209, 204),
    "paleturquoise": (175, 238, 238),
    "aquamarine": (127, 255, 212),
    "powderblue": (176, 224, 230),
    "cadetblue": (95, 158, 160),
    "steelblue": (70, 130, 180),
    "cornflowerblue": (100, 149, 237),
    "deepskyblue": (0, 191, 255),
    "dodgerblue": (30, 144, 255),
    "lightblue": (173, 216, 230),
    "skyblue": (135, 206, 235),
    "lightskyblue": (135, 206, 250),
    "midnightblue": (25, 25, 112),
    "navy": (0, 0, 128),
    "darkblue": (0, 0, 139),
    "mediumblue": (0, 0, 205),
    "blue": (0, 0, 255),
    "royalblue": (65, 105, 225),
    "blueviolet": (138, 43, 226),
    "indigo": (75, 0, 130),
    "darkslateblue": (72, 61, 139),
    "slateblue": (106, 90, 205),
    "mediumslateblue": (123, 104, 238),
    "mediumpurple": (147, 112, 219),
    "darkmagenta": (139, 0, 139),
    "darkviolet": (148, 0, 211),
    "darkorchid": (153, 50, 204),
    "mediumorchid": (186, 85, 211),
    "purple": (128, 0, 128),
    "thistle": (216, 191, 216),
    "plum": (221, 160, 221),
    "violet": (238, 130, 238),
    "magenta": (255, 0, 255),
    "fuchsia": (255, 0, 255),
    "orchid": (218, 112, 214),
    "mediumvioletred": (199, 21, 133),
    "palevioletred": (219, 112, 147),
    "deeppink": (255, 20, 147),
    "hotpink": (255, 105, 180),
    "lightpink": (255, 182, 193),
    "pink": (255, 192, 203),
    "antiquewhite": (250, 235, 215),
    "beige": (245, 245, 220),
    "bisque": (255, 228, 196),
    "blanchedalmond": (255, 235, 205),
    "wheat": (245, 222, 179),
    "cornsilk": (255, 248, 220),
    "lemonchiffon": (255, 250, 205),
    "lightgoldenrodyellow": (250, 250, 210),
    "lightyellow": (255, 255, 224),
    "saddlebrown": (139, 69, 19),
    "sienna": (160, 82, 45),
    "chocolate": (210, 105, 30),
    "peru": (205, 133, 63),
    "sandybrown": (244, 164, 96),
    "burlywood": (222, 184, 135),
    "tan": (210, 180, 140),
    "rosybrown": (188, 143, 143),
    "moccasin": (255, 228, 181),
    "navajowhite": (255, 222, 173),
    "peachpuff": (255, 218, 185),
    "mistyrose": (255, 228, 225),
    "lavenderblush": (255, 240, 245),
    "linen": (250, 240, 230),
    "oldlace": (253, 245, 230),
    "papayawhip": (255, 239, 213),
    "seashell": (255, 245, 238),
    "mintcream": (245, 255, 250),
    "slategray": (112, 128, 144),
    "lightslategray": (119, 136, 153),
    "lightsteelblue": (176, 196, 222),
    "lavender": (230, 230, 250),
    "floralwhite": (255, 250, 240),
    "aliceblue": (240, 248, 255),
    "ghostwhite": (248, 248, 255),
    "honeydew": (240, 255, 240),
    "ivory": (255, 255, 240),
    "azure": (240, 255, 255),
    "snow": (255, 250, 250),
    "black": (0, 0, 0),
    "dimgray": (105, 105, 105),
    "dimgrey": (105, 105, 105),
    "gray": (128, 128, 128),
    "grey": (128, 128, 128),
    "darkgray": (169, 169, 169),
    "darkgrey": (169, 169, 169),
    "silver": (192, 192, 192),
    "lightgray": (211, 211, 211),
    "lightgrey": (211, 211, 211),
    "gainsboro": (220, 220, 220),
    "whitesmoke": (245, 245, 245),
    "white": (255, 255, 255),
}


def _make_rgb(colour_in: ColourDef) -> tuple:
    """Converts a name to an RGB tuple.  If already tuple returns that."""
    if isinstance(colour_in, tuple):
        return colour_in
    if isinstance(colour_in, str):
        colour_in = colour_in.strip().lower().replace(" ", "")
        if colour_in in _COLOURS:
            return _COLOURS[colour_in]
        raise ValueError
    raise TypeError


_REDKEY = "r"
_GREENKEY = "g"
_BLUEKEY = "b"
_RGB_LIST = [_REDKEY, _GREENKEY, _BLUEKEY]

AXIS_X = "AXIS_X"
AXIS_Y = "AXIS_Y"

# Ways to combine colours
MIX_ADD = "MIX_ADD"
MIX_SUBTRACT = "MIX_SUBTRACT"
MIX_AVERAGE = "MIX_AVERAGE"
MIX_MIN = "MIX_MIN"
MIX_MAX = "MIX_MAX"


class ColourBand:
    """A single dimension for a colour.  E.g. R, G, B.

    Maps an input value to an output colour.
    Output colour values will always be held to be within the range of
     the colour range.
    Colour range is used to identify the value extremes for
    the colour values; there is no assumption that top > bottom.
    Input range is used to set the relationship between in & out
    but input values do not need to lie within that range.
    Exponent skews the factor to create greater differentiation
    at one end or another.
    """

    def __init__(
        self,
        colour_bottom: int = 255,
        colour_top: int = 0,
        exponent: float = 1,
        data_bottom: int = 0,
        data_top: int = 100,
    ) -> None:
        self.colour_bottom = colour_bottom
        self.colour_top = colour_top
        self.exponent = exponent
        self.data_bottom = data_bottom
        self.data_top = data_top

    def get_colour_value(self, data_value: int | float) -> int:
        """Return a colour value for a value input."""
        data_range_exponented = math.pow(
            self.data_top, self.exponent
        ) - math.pow(self.data_bottom, self.exponent)
        colour_range = self.colour_top - self.colour_bottom
        scale_factor = colour_range / data_range_exponented
        ##print(f"{data_value=};{data_range_exponented=};{colour_range=};{scale_factor=}")
        colour_val = round(
            self.colour_bottom
            + math.pow(data_value, self.exponent) * scale_factor
        )
        # Assure that return colour value is within range
        if self.colour_bottom < self.colour_top:
            colour_val = max(
                min(colour_val, self.colour_top), self.colour_bottom
            )
        else:
            colour_val = min(
                max(colour_val, self.colour_top), self.colour_bottom
            )
        return colour_val

    def dump(self) -> str:
        """Return contents of object as a string."""
        return (
            f"{self.colour_bottom=};{self.colour_top=};"
            f"{self.exponent=};{self.data_bottom=};{self.data_top=}"
        )


class ColourMap:
    """Map X or X,Y data into a RGB colour space.

    Create object, initialize with set_up_map(), then
    get colour values from the map with get_rgb_tuple() or get_rgb_str()

    Attributes:
        _colour_data_axes[AXIS][COLOUR_BAND] = ColourBand
        Where
            AXIS is AXIS_X or AXIS_Y
            COLOUR_BAND is _REDKEY, _GREENKEY, _BLUEKEY.
        In use, bool(self._colour_data_axes[AXIS_Y]) tells us whether
        this is a 1D map (False) or a 2D map (True).

    Public methods:
        __init__ - sets up _colour_data_axes dict
        set_up_map() - creates the mapping between the data axes (X,Y) and
            the colour bands
        get_rgb_tuple() - get (R,G,B) ints as a tuple for given (x) or (x,y)
        get_rgb_str() - same but returns as rgb string e.g. "rbg(13,157,99)"
    """

    def __init__(
        self,
    ) -> None:
        """Inititalize the empty colour map."""
        self._colour_data_axes = {}
        self._colour_data_axes[AXIS_X] = {}
        self._colour_data_axes[AXIS_Y] = {}
        # List of axes - either [AXIS_X] or [AXIS_X,AXIS_Y]
        self.axes = []

    def _assign_colours_for_one_data_axis(
        self,
        data_axis: str = AXIS_X,
        zero_rgb: ColourDef = "white",
        top_rgb: ColourDef = (128, 128, 128),
    ) -> None:
        """Initialize one data axis into _colour_data_axes dict."""
        zero_rgb = _make_rgb(zero_rgb)
        top_rgb = _make_rgb(top_rgb)
        rgb_tuples = list(zip(_RGB_LIST, zero_rgb, top_rgb))
        for colour, colour_bottom, colour_top in rgb_tuples:
            band = ColourBand()
            band.colour_bottom = colour_bottom
            band.colour_top = colour_top
            self._colour_data_axes[data_axis][colour] = band

    def set_up_map(
        self,
        zero_colour: ColourDef,
        x_max_colour: ColourDef,
        y_max_colour: ColourDef = None,
        x_bottom: float = 0,
        x_top: float = 100,
        y_bottom: float = 0,
        y_top: float = 100,
        x_exponent: float = 1,
        y_exponent: float = 1,
        mix_type: str = MIX_ADD,
    ):
        """This sets up a colour map for 1-axis (X) or 2-axis (X,Y) data."""
        # Load colour dimensions for X 7 Y into self._colour_data_axes.
        self._assign_colours_for_one_data_axis(
            data_axis=AXIS_X,
            zero_rgb=zero_colour,
            top_rgb=x_max_colour,
        )
        self.axes.append(AXIS_X)
        if y_max_colour:
            self._assign_colours_for_one_data_axis(
                data_axis=AXIS_Y,
                zero_rgb=zero_colour,
                top_rgb=y_max_colour,
            )
            self.axes.append(AXIS_Y)
        # Add the data range info.
        for axis in self.axes:
            for band in self._colour_data_axes[axis].values():
                band: ColourBand
                if axis == AXIS_X:
                    band.data_bottom = x_bottom
                    band.data_top = x_top
                    band.exponent = x_exponent
                else:
                    band.data_bottom = y_bottom
                    band.data_top = y_top
                    band.exponent = y_exponent
        # How will the colours get mixed?
        self.mix_type = mix_type

    def _combine_colours(self, colours: list[int]) -> int:
        """Mix a list of colours within a single colour band."""
        if len(colours) == 1:
            return colours[0]

        if self.mix_type == MIX_AVERAGE:
            # Average
            result = statistics.mean(colours)
        elif self.mix_type == MIX_MIN:
            # Min
            result = min(colours)
        elif self.mix_type == MIX_MAX:
            # Min
            result = max(colours)
        elif self.mix_type == MIX_SUBTRACT:
            # Fancy subtractive
            for i, c in enumerate(colours):
                if i == 0:
                    result = c
                else:
                    # do a fancy subtract of these 2 colours
                    result = 255 - abs((255 - result) - (255 - c))
                    result = max(min(255, result), 0)
        elif self.mix_type == MIX_ADD:
            # Fancy additive
            for i, c in enumerate(colours):
                if i == 0:
                    result = c
                else:
                    # do a fancy addition of these 2 colours
                    result = 255 - abs((255 - result) + (255 - c))
                    result = max(min(255, result), 0)
        else:
            # Unknown mix_type
            raise ValueError
        result = max(min(255, result), 0)
        return result

    def get_rgb_tuple(self, x, y=None) -> tuple:
        """Return RGB tuple."""
        rgb_vals_list = dict(zip(_RGB_LIST, ([], [], [])))
        x = x if x is not None else 0
        for axis in self.axes:
            input_val = x if axis == AXIS_X else y
            for colour in _RGB_LIST:
                this_band: ColourBand = self._colour_data_axes[axis][colour]
                color_val = this_band.get_colour_value(input_val)
                rgb_vals_list[colour].append(color_val)
        rgb_vals = []
        for colour in _RGB_LIST:
            # Blend colours within this band.
            val = self._combine_colours(rgb_vals_list[colour])
            val = min(max(val, 0), 255)
            rgb_vals.append(val)
        return rgb_vals

    def get_rgb_str(self, x, y=None) -> str:
        """Return html RGB string."""
        rgb_str = ",".join([f"{s}" for s in self.get_rgb_tuple(x, y)])
        return f"rgb({rgb_str})"

    def dump(self) -> str:
        """Return the object into a string."""
        dstr = "_colour_data_axes:\n"
        for axis in sorted(self._colour_data_axes.keys()):
            dstr = f"{dstr}  axis: {axis}\n"
            for colour in sorted(
                self._colour_data_axes[axis].keys(), reverse=True
            ):
                dstr = f"{dstr}    colour: {colour}:\n"
                band: ColourBand
                band = self._colour_data_axes[axis][colour]
                if isinstance(band, ColourBand):
                    dstr = f"{dstr}      {band.dump()}\n"
                else:
                    dstr = f"{dstr}      Object is type {type(band)}\n"
        return dstr


if __name__ == "__main__":

    def style() -> str:
        """Return a CSS stylesheet as a string."""
        return """
            <style>
                html {
            font-family: sans-serif;
            }

            table {
            border-collapse: collapse;
            border: 2px solid rgb(200,200,200);
            letter-spacing: 1px;
            font-size: 0.8rem;
            }

            td, th {
            border: 1px solid rgb(190,190,190);
            padding: 5px 15px;
            }

            th {
            background-color: rgb(235,235,235);
            }

            td {
            text-align: right;
            }

            tr:nth-child(even) td {
            background-color: rgb(250,250,250);
            }

            tr:nth-child(odd) td {
            background-color: rgb(245,245,245);
            }

            caption {
            padding: 10px;
            }
            </style>
        """

    if False:
        print("Content-type: text/plain\n\n")
        print("Test for single-data-axis map:")
        colorer = ColourMap()
        colorer.set_up_map((255, 255, 255), (100, 255, 255), x_exponent=2)
        print(f"{colorer.dump()}")
        for x in [0, 10, 50, 90, 100]:
            print(f"{x} -> {colorer.get_rgb_str(x)}")
        print("\nTest 2-axis map:")
        colorer = ColourMap()
        colorer.set_up_map(
            (255, 255, 255),
            (100, 255, 255),
            (255, 0, 128),
            x_exponent=3,
            y_exponent=1 / 3,
        )
        for x in [0, 5, 10, 20, 50, 100, 200]:
            for y in [0, 10, 50, 90, 100]:
                print(f"({x},{y}) -> {colorer.get_rgb_str(x,y)}")

        print("\nTest for contention error:")
        colorer = ColourMap()
        colorer.set_up_map(
            (255, 0, 0),
            (00, 255, 255),
            (0, 0, 255),
        )

    #    zero_colour=(200,200,200),
    #    x_max_colour=(255,20,20),
    #    y_max_colour=(0,0,255),
    #    x_exponent=.3, #1.25, #.3
    #    y_exponent=.75, #1.25, # .75

    colorer = ColourMap()
    colorer.set_up_map(
        zero_colour=(240, 240, 240),
        x_max_colour=(255, 40, 40),
        y_max_colour=(128, 128, 255),
        x_exponent=0.75,
        y_exponent=0.75,
        x_bottom=0,
        x_top=30,
        y_bottom=0,
        y_top=120,
    )

    print("Content-type: text/html\n\n\n")
    print("<html>")
    print(style())
    print("<body>")

    # Generate a pretend block list
    blocks = []
    for x in range(12, 48):
        blocks.append(x / 2)

    def num2time(num) -> str:
        """Make H:M for # of hrs."""
        h = int(num + 0.000001)
        m = round((num - h) * 60)
        s = f"{h}:{m:02d}"
        return s

    def print_gap():
        print(
            "<td style='border: 3px solid rgb(255,255,255);padding: 0px 0px;'></td>"
        )

    print("<table>")

    print("<tr><th>Date</th>")
    print("<th colspan=6>6:00-8:30</th>")
    print_gap()
    print("<th colspan=6>9:00-11:30</th>")
    print_gap()
    print("<th colspan=6>12:00-14:30</th>")
    print_gap()
    print("<th colspan=6>15:00-17:30</th>")
    print_gap()
    print("<th colspan=6>18:00-20:30</th>")
    print_gap()
    print("<th colspan=6>21:00-23:30</th>")
    print("</tr>")

    for y in range(21):
        print("<tr>")
        print(
            f"<td>2023-{random.randint(1,12):02}-{random.randint(1,30):02}</td>"
        )
        for x, block in enumerate(blocks):
            if x % 6 == 0 and x > 0:
                print_gap()

            block_factor = block / max(blocks)
            busy = random.randint(0, 30) * block_factor
            full = random.randint(0, 120) * block_factor
            content = num2time(block)
            content = ",".join([f"{c}" for c in colorer.get_rgb_tuple(x, y)])
            content = "&nbsp"
            # content = f"{x},{y}"
            print(
                f"<td style='background-color: {colorer.get_rgb_str(busy,full)}'>{content}</td>"
            )
        print("</tr>")
    print("</table>")

    print(f"<pre>\n{colorer.dump()}\n</pre>")
    print("</body></html>")
