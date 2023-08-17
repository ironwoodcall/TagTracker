"""Map (x,y) data values onto (RGB) colour space.



"""

import math

RED = "r"
GREEN = "g"
BLUE = "b"
AXIS_X = "AXIS_X"
AXIS_Y = "AXIS_Y"
RGB_LIST = [RED, GREEN, BLUE]


class ColourDimensionContention(Exception):
    pass


class ColourDimension:
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
        data_axis: str = "",
        colour_bottom: int = 255,
        colour_top: int = 0,
        exponent: float = 1,
        data_bottom: int = 0,
        data_top: int = 100,
    ) -> None:
        self.data_axis = data_axis  # "X", "Y", or "" if neither
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
        colour_val = round(
            self.colour_bottom
            + math.pow(data_value, self.exponent) * scale_factor
        )
        ##print(f"{data_range_exponented=};{colour_range=};{scale_factor=}")
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
            f"{self.data_axis=};{self.colour_bottom=};{self.colour_top=};"
            f"{self.exponent=};{self.data_bottom=};{self.data_top=}"
        )


class ColourMap:
    """Map X or X,Y data into a RGB colour space.


    What I want:

    I want to initialize it with:
    - RGB bottom tuple
    - for X (axis 0):
        - RGB top tuple
        - input data range (bottom, top)
        - exponent
    - same for Y (axis 1) [optional - if none, then is linear not 2d]

    I then want to call it with: data values (x,y) or just (x)
    And have it return: RGB values or RGB string
    -


    """

    def _assign_colours_to_one_data_axis(
        self,
        data_axis: str = AXIS_X,
        zero_rgb: tuple = (255, 255, 255),
        top_rgb: tuple = (128, 128, 128),
    ) -> None:
        """Initialize one data axis into colour_data_axes dict."""
        rgb_tuples = list(zip(RGB_LIST, zero_rgb, top_rgb))
        for colour_tuple in rgb_tuples:
            (colour, colour_bottom, colour_top) = colour_tuple
            # Save this as a colour/dim entry if it is either
            # not yet set, or if its bottom/top are not identical
            if (
                colour in self.colour_data_axes
                and self.colour_data_axes[colour]
                and colour_top == colour_bottom
            ):
                continue
            dimension = ColourDimension()
            dimension.colour_bottom = colour_bottom
            dimension.colour_top = colour_top
            dimension.data_axis = data_axis
            # Error if colour already set & is not static.
            if (
                colour in self.colour_data_axes
                and self.colour_data_axes[colour].colour_bottom
                != self.colour_data_axes[colour].colour_top
            ):
                raise ColourDimensionContention(
                    f"colour '{colour}' already assigned, can not assign "
                    f"to axis {data_axis}.\n"
                    f"Existing map: {self.colour_data_axes[colour].dump()};\n"
                    f"New map: {dimension.dump()}"
                )
            self.colour_data_axes[colour] = dimension

    def __init__(
        self,
    ) -> None:
        """Inititalize the empty colour map.

        In use, bool(self.colour_data_axes[AXIS_Y]) tells us whether
        this is a 1D map (False) or a 2D map (True).
        """
        self.colour_data_axes = {}
        self.colour_data_axes[AXIS_X] = {}
        self.colour_data_axes[AXIS_Y] = {}

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
    ):
        """This sets up a one or 2 d colourmap."""
        # Load colour dimensions for X 7 Y into self.colour_data_axes.
        self._assign_colours_to_one_data_axis(
            data_axis=AXIS_X,
            zero_rgb=zero_colour,
            top_rgb=x_max_colour,
        )
        if y_max_colour:
            self._assign_colours_to_one_data_axis(
                data_axis=AXIS_Y,
                zero_rgb=zero_colour,
                top_rgb=y_max_colour,
            )
        # Add the data range info.
        for dimension in self.colour_data_axes.values():
            dimension: ColourDimension
            if dimension.data_axis == AXIS_X:
                dimension.data_bottom = x_bottom
                dimension.data_top = x_top
                dimension.exponent = x_exponent
            else:
                dimension.data_bottom = y_bottom
                dimension.data_top = y_top
                dimension.exponent = y_exponent

    def get_rgb_tuple(self, x, y=None) -> tuple:
        """Return RGB tuple."""
        rgb_vals = []
        for colour in RGB_LIST:
            this_dim: ColourDimension = self.colour_data_axes[colour]
            input_val = x if this_dim.data_axis == AXIS_X else y

            colval = this_dim.get_colour_value(input_val)
            rgb_vals.append(colval)
            ##print(f"{colour=},{input_val=},{colval=},{rgb_vals=}")
        return rgb_vals

    def get_rgb_str(self, x, y=None) -> str:
        """Return html RGB string."""
        rgb_str = ",".join([f"{s}" for s in self.get_rgb_tuple(x, y)])
        return f"rgb({rgb_str})"


class ColourMap01:
    """Map X or X,Y data into a RGB colour space.


    What I want:

    I want to initialize it with:
    - RGB bottom tuple
    - for X (axis 0):
        - RGB top tuple
        - input data range (bottom, top)
        - exponent
    - same for Y (axis 1) [optional - if none, then is linear not 2d]

    I then want to call it with: data values (x,y) or just (x)
    And have it return: RGB values or RGB string
    -


    """

    def _assign_colours_to_one_data_axis(
        self,
        data_axis: str = AXIS_X,
        zero_rgb: tuple = (255, 255, 255),
        top_rgb: tuple = (128, 128, 128),
    ) -> None:
        """Initialize one data axis into colour_data_axes dict."""
        rgb_tuples = list(zip(RGB_LIST, zero_rgb, top_rgb))
        for colour_tuple in rgb_tuples:
            (colour, colour_bottom, colour_top) = colour_tuple
            # Save this as a colour/dim entry if it is either
            # not yet set, or if its bottom/top are not identical
            if (
                colour in self.colour_data_axes
                and self.colour_data_axes[colour]
                and colour_top == colour_bottom
            ):
                continue
            dimension = ColourDimension()
            dimension.colour_bottom = colour_bottom
            dimension.colour_top = colour_top
            dimension.data_axis = data_axis
            # Error if colour already set & is not static.
            if (
                colour in self.colour_data_axes
                and self.colour_data_axes[colour].colour_bottom
                != self.colour_data_axes[colour].colour_top
            ):
                raise ColourDimensionContention(
                    f"colour '{colour}' already assigned, can not assign "
                    f"to axis {data_axis}.\n"
                    f"Existing map: {self.colour_data_axes[colour].dump()};\n"
                    f"New map: {dimension.dump()}"
                )
            self.colour_data_axes[colour] = dimension

    def __init__(
        self,
    ) -> None:
        self.colour_data_axes = {}

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
    ):
        """This sets up a one or 2 d colourmap."""
        if y_max_colour:
            self._assign_colours_to_one_data_axis(
                data_axis=AXIS_Y,
                zero_rgb=zero_colour,
                top_rgb=y_max_colour,
            )
        self._assign_colours_to_one_data_axis(
            data_axis=AXIS_X,
            zero_rgb=zero_colour,
            top_rgb=x_max_colour,
        )
        # All of R,G,B now are assigned to an axis, even if static.
        for dimension in self.colour_data_axes.values():
            dimension: ColourDimension
            if dimension.data_axis == AXIS_X:
                dimension.data_bottom = x_bottom
                dimension.data_top = x_top
                dimension.exponent = x_exponent
            else:
                dimension.data_bottom = y_bottom
                dimension.data_top = y_top
                dimension.exponent = y_exponent

    def get_rgb_tuple(self, x, y=None) -> tuple:
        """Return RGB tuple."""
        rgb_vals = []
        for colour in RGB_LIST:
            this_dim: ColourDimension = self.colour_data_axes[colour]
            input_val = x if this_dim.data_axis == AXIS_X else y

            colval = this_dim.get_colour_value(input_val)
            rgb_vals.append(colval)
            ##print(f"{colour=},{input_val=},{colval=},{rgb_vals=}")
        return rgb_vals

    def get_rgb_str(self, x, y=None) -> str:
        """Return html RGB string."""
        rgb_str = ",".join([f"{s}" for s in self.get_rgb_tuple(x, y)])
        return f"rgb({rgb_str})"




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



    #print("Test for single-data-axis map:")
    #busyness_colorer = ColourMap()
    #busyness_colorer.set_up_map((255, 255, 255), (100, 255, 255), x_exponent=2)
    #for x in [0, 10, 50, 90, 100]:
    #    print(f"{x} -> {busyness_colorer.get_rgb_str(x)}")
    #print("\nTest 2-axis map:")
    #busyness_colorer = ColourMap()
    #busyness_colorer.set_up_map(
    #    (255, 255, 255),
    #    (100, 255, 255),
    #    (255, 0, 128),
    #    x_exponent=3,
    #    y_exponent=1 / 3,
    #)
    #for x in [0, 5, 10, 20, 50, 100, 200]:
    #    for y in [0, 10, 50, 90, 100]:
    #        print(f"({x},{y}) -> {busyness_colorer.get_rgb_str(x,y)}")
    #
    #print("\nTest for contention error:")
    #busyness_colorer = ColourMap()
    #busyness_colorer.set_up_map(
    #    (255, 255, 255),
    #    (100, 255, 255),
    #    (70, 0, 128),
    #)



    1 0 0   0 1 1
    1 0 0



    import random
    colorer = ColourMap()
    colorer.set_up_map(
        (255,255,255),
        (255,0,0),
        (255,0,255),
        x_bottom=0,
        x_top=10,
        y_bottom=0,
        y_top=10,
        #x_exponent=2,
        #y_exponent=1 / 2,
    )


    print("Content-type: text/html\n\n\n")
    print("<html>")
    print(style())
    print("<body>")
    print("<table><tr><td>")

    print("<table>")
    for row in range(11):
        print("<tr>")
        for col in range(11):
            x = random.randint(0,100)
            y = random.randint(0,100)
            print(f"<td style='background-color: {colorer.get_rgb_str(row,col)}'>&nbsp</td>")
        print("</tr>")
    print("</table>")

    print("</td></tr></table>")
    print("</body></html>")