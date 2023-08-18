"""Map (x,y) data values onto (RGB) colour space."""

import math
import statistics
import random

RED = "r"
GREEN = "g"
BLUE = "b"
RGB_LIST = [RED, GREEN, BLUE]

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
            COLOUR_BAND is RED, GREEN, BLUE.
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
        zero_rgb: tuple = (255, 255, 255),
        top_rgb: tuple = (128, 128, 128),
    ) -> None:
        """Initialize one data axis into _colour_data_axes dict."""
        rgb_tuples = list(zip(RGB_LIST, zero_rgb, top_rgb))
        for (colour, colour_bottom, colour_top) in rgb_tuples:
            band = ColourBand()
            band.colour_bottom = colour_bottom
            band.colour_top = colour_top
            self._colour_data_axes[data_axis][colour] = band

    def set_up_map(
        self,
        zero_colour: tuple,
        x_max_colour: tuple,
        y_max_colour: tuple = None,
        x_bottom: float = 0,
        x_top: float = 100,
        y_bottom: float = 0,
        y_top: float = 100,
        x_exponent: float = 1,
        y_exponent: float = 1,
        mix_type:str = MIX_ADD,
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

    def _combine_colours(self,colours:list[int]) -> int:
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
                    result = max(min(255,result),0)
        elif self.mix_type == MIX_ADD:
            # Fancy additive
            for i, c in enumerate(colours):
                if i == 0:
                    result = c
                else:
                    # do a fancy addition of these 2 colours
                    result = 255 - abs((255 - result) + (255 - c))
                    result = max(min(255,result),0)
        else:
            # Unknown mix_type
            raise ValueError
        result = max(min(255,result),0)
        return result

    def get_rgb_tuple(self, x, y=None) -> tuple:
        """Return RGB tuple."""
        rgb_vals_list = dict(zip(RGB_LIST,([],[],[])))
        for axis in self.axes:
            input_val = x if axis == AXIS_X else y
            for colour in RGB_LIST:
                this_band: ColourBand = self._colour_data_axes[axis][colour]
                color_val = this_band.get_colour_value(input_val)
                rgb_vals_list[colour].append(color_val)
        rgb_vals = []
        for colour in RGB_LIST:
            # Blend colours within this band.
            val = self._combine_colours(rgb_vals_list[colour])
            val = min(max(val,0),255)
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
            for colour in sorted(self._colour_data_axes[axis].keys(),reverse=True):
                dstr = f"{dstr}    colour: {colour}:\n"
                band:ColourBand
                band = self._colour_data_axes[axis][colour]
                if isinstance(band,ColourBand):
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
            (255, 0,0),
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
        zero_colour=(240,240,240),
        x_max_colour=(255,40,40),
        y_max_colour=(128,128,255),
        x_exponent=.75,
        y_exponent=.75,
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
    for x in range(12,48):
        blocks.append(x/2)

    def num2time(num) -> str:
        """Make H:M for # of hrs."""
        h = int(num + .000001)
        m = round((num - h) * 60)
        s = f"{h}:{m:02d}"
        return s

    def print_gap():
        print("<td style='border: 3px solid rgb(255,255,255);padding: 0px 0px;'></td>")

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
        print(f"<td>2023-{random.randint(1,12):02}-{random.randint(1,30):02}</td>")
        for x, block in enumerate(blocks):
            if x % 6 == 0 and x > 0:
                print_gap()

            block_factor = block/max(blocks)
            busy = random.randint(0,30) * block_factor
            full = random.randint(0,120) * block_factor
            content = num2time(block)
            content = ",".join([f"{c}" for c in colorer.get_rgb_tuple(x,y)])
            content = "&nbsp"
            #content = f"{x},{y}"
            print(f"<td style='background-color: {colorer.get_rgb_str(busy,full)}'>{content}</td>")
        print("</tr>")
    print("</table>")

    print(f"<pre>\n{colorer.dump()}\n</pre>")
    print("</body></html>")