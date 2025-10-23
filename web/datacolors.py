"""Generate blended colors based on n-dimensional data inputs.

Conceptually, there is a
- data space: numeric data in one or more dimensions
- color space: the range of colors which are determined by the data points
- configuration space: configuration for how the data ranges are
    converted, how the colours are combined, etc

A Dimension is a one-dimensional color factory.  It exposes methods to configure
the dimension's dataspace to colorspace, and various methods to return a color
for a particular data parameter (determiner).

MultiDimension is the 2+D color factory. It is made up of one or more Dimensions
and includes a parameter to control how the Dimensions' colors are blended.
Its methods for data->color conversions are about the same as for a single Dimension.

Each dataspace dimension determines a single color (dimension); when there
are multiple dimensions the resulting colors are then blended using any of
several blend methods.

MultiDimension is defined by the color blending method and one or more config dimensions
Each Dimension is defined by the interpolation_exponent of the relation between the
data parameter and the colorspace color range, and one or more ConfigPoints.
A MappingPoint relates a single data value in one dimension to a single output color.
A Dimension with only one MappingPoint simply always produces that color.
A Dimension with multiple ConfigPoints will interpolate colors along gradiants
defined by numerically adjacent ConfigPoints.  Out of range data values are
clamped to the min/max data values of the available ConfigPoints.

Example use:
factory = MultiDimension(LERP)
d1 = factory.add_dimension(interpolation_exponent=1)
d2 = factory.add_dimension(interpolation_exponent=0.5)
d1.add_config(-10,'blue')
d1.add_config(0,'beige')
d1.add_config(30,'orange')
d2.add_config(min_val,'white')
d2.add_config(max_val,'rgb(147,10,20)')

for (various x values, with text):
    print(f"<td style={factory.css_bg_fg(x)}>{x}</td>")

for (various x,y values with no text)
    print(f"<td style={factory.css_bg(x,y)}>&nbsp;<td>")

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

import re
import math

try:
    import numpy as np
except ImportError:  # pragma: no cover - numpy is optional at runtime
    np = None  # type: ignore

from color_names import COLOR_NAMES

BLEND_LERP = "lerp"  # linear interpolation
BLEND_ALPHA = BLEND_LERP
BLEND_ADDITIVE = "add"
BLEND_SUBTRACTIVE = "subtract"
BLEND_DIFFERENCE = "difference"
BLEND_MULTIPLICATIVE = "multiply"
BLEND_OVERLAY = "overlay"
BLEND_MIN = "min"
BLEND_MAX = "max"
BLEND_CIELAB = "cielab"

COLOR_SPACE_RGB = "rgb"
COLOR_SPACE_LAB = "lab"


class Color(tuple):
    """A single color and its behaviors."""

    # Regular expression pattern to match the rgb str format
    _rgb_pattern = re.compile(r"rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")

    # Reversed color names dict for similar_to()
    _reverse_color_names = {v: k for k, v in COLOR_NAMES.items()}

    def __new__(cls, color_init):
        """Create the color object.

        Initialize from any of
            Color object
            RGB tuple, e.g. (127, 0, 255)
            color name str, e.g. "seagreen"
            rgb string, e.g. "rgb(20, 56, 198)"
        """
        if isinstance(color_init, Color):
            return color_init

        rgb = None
        # if isinstance(color_init, Color):
        #    rgb = tuple(color_init)
        if isinstance(color_init, tuple):
            if len(color_init) == 3:
                rgb = color_init
            else:
                raise ValueError("RGB Tuple must have 3 elements")
        elif isinstance(color_init, str):
            color_init = color_init.lower().strip()
            if color_init.startswith("rgb("):
                rgb = cls._parse_rgb_str(color_init)
            elif color_init.startswith("#"):
                rgb = cls._parse_html_str(color_init)
            elif color_init in COLOR_NAMES:
                rgb = COLOR_NAMES[color_init]
            else:
                raise ValueError(f"Cannot get color from '{color_init}'")
        else:
            raise ValueError("Color definition must be a string or RGB tuple")

        cls._validate_rgb_tuple(rgb)
        return super(Color, cls).__new__(cls, rgb)

    @property
    def red(self):
        """Get color band from tuple."""
        return self[0]

    @property
    def green(self):
        """Get color band from tuple."""
        return self[1]

    @property
    def blue(self):
        """Get color band from tuple."""
        return self[2]

    @staticmethod
    def _validate_rgb_tuple(rgb):
        """Test that rgb is a valid RGB tuple."""
        if not all(0 <= c <= 255 for c in rgb):
            raise ValueError("RGB values must be between 0 and 255")

    @staticmethod
    def _parse_html_str(html_str: str) -> tuple:
        """Parse R,G,B from an html color str (e.g. "#ffe720").

        Precondition: already know it starts with "#".
        """
        try:
            r = int(html_str[1:3], 16)
            g = int(html_str[3:5], 16)
            b = int(html_str[5:7], 16)
        except ValueError as exc:
            raise ValueError("Invalid HTML color string.") from exc

        return (r, g, b)

    @staticmethod
    def _parse_rgb_str(rgb_str) -> tuple:
        """Get an RGB tuple from a str like 'rgb(30,77,220)'."""
        match = Color._rgb_pattern.match(rgb_str)
        if match:
            rgb = tuple(int(match.group(i)) for i in range(1, 4))
            Color._validate_rgb_tuple(rgb)
            return rgb
        raise ValueError("Invalid RGB string format")

    @staticmethod
    def _validate_rgb_tuple(color_tuple: tuple) -> bool:
        """Validate the RGB color tuple, raise error for any problems."""
        if color_tuple is None:
            raise ValueError("Can't get color from init parameter")
        if not isinstance(color_tuple, tuple) or len(color_tuple) != 3:
            raise ValueError("Color tuple must have exactly 3 elements.")
        if not all(isinstance(c, int) for c in color_tuple):
            raise TypeError("All elements of color tuple must be int.")
        if color_tuple != Color._clamp_tuple(color_tuple):
            raise ValueError(
                "All elements in the color tuple must be 0 to 255."
            )
        return True

    @staticmethod
    def _clamp_tuple(color_tuple: tuple) -> tuple:
        """Clamp the values of a color tuple to the range 0-255."""
        return tuple(max(0, min(255, value)) for value in color_tuple)

    @property
    def html_color(self):
        """Return color as an HTML color str (e.g. '#07f378')."""
        return f"#{self.red:02X}{self.green:02X}{self.blue:02X}"

    def luminance(self) -> float:
        """Calculate the color's luminance."""
        luminance = 0.299 * self.red + 0.587 * self.green + 0.114 * self.blue
        return luminance

    def css_fg(self) -> str:
        """Make a CSS (foreground) color style string component."""
        return f"color:{self.html_color};"

    def css_bg(self) -> str:
        """Make a CSS background color style string component."""
        return f"background:{self.html_color};"

    def css_bg_fg(self) -> str:
        """Make CSS style background color component with contrasting text color."""
        fg = "black" if self.luminance() >= 128 else "white"
        return f"color:{fg};background:{self.html_color};"

    def __str__(self):
        """Str representation.

        This is such that can be used to init a Color.
        """
        return f"rgb({self.red},{self.green},{self.blue})"

    def __repr__(self):
        """Color representation."""
        return f"<Color ({self.red},{self.green},{self.blue})>"

    def __eq__(self, other):
        """Test equality as having same RGB."""
        return (
            self.red == other.red
            and self.green == other.green
            and self.blue == other.blue
        )

    def similar_to(self):
        """Get human-readable name for what this color is kinda like.

        Distance to nearest color is expressed as % of maximum color
        distance possible (ie distance from white to black).
        Uses the color dictionary and its reverse, initialized above.

        """
        if (self.red, self.green, self.blue) in self._reverse_color_names:
            return self._reverse_color_names[(self.red, self.green, self.blue)]

        # Find the name and distance of closest color.
        closest_distance = float("inf")
        closest_color = None
        for this_name, this_rgb in COLOR_NAMES.items():
            this_r, this_g, this_b = this_rgb
            this_distance = math.sqrt(
                (self.red - this_r) ** 2
                + (self.green - this_g) ** 2
                + (self.blue - this_b) ** 2
            )
            closest_distance, closest_color = min(
                (closest_distance, closest_color), (this_distance, this_name)
            )

        # Closeness to the color is fraction of its distance compared
        # to max distance in the RGB color cube (dist from white to black)
        # pylint: disable-next=invalid-name
        WHITE_BLACK_DISTANCE = 441.67  # sqrt(3 * 255*255)
        closeness = closest_distance / WHITE_BLACK_DISTANCE
        return f"{closest_color} ({(1 - closeness)*100:.1f}% match)"

    @staticmethod
    def invert(color: "Color") -> "Color":
        """Inverts the color."""
        r = 255 - color[0]
        g = 255 - color[1]
        b = 255 - color[2]
        return Color(Color._clamp_tuple((r, g, b)))


    @staticmethod
    def blend_lerp(
        base_color: "Color", blend_color: "Color", alpha: float = 0.5
    ) -> "Color":
        """Blend two colours using linear interpolation.

        This seems to be the same thing as ALPHA.
        """
        alpha = max(0.0, min(1.0, alpha))  # Ensure alpha is within [0, 1]
        blended_color = Color(
            (
                int(
                    base_color.red + (blend_color.red - base_color.red) * alpha
                ),
                int(
                    base_color.green
                    + (blend_color.green - base_color.green) * alpha
                ),
                int(
                    base_color.blue
                    + (blend_color.blue - base_color.blue) * alpha
                ),
            )
        )
        return blended_color

    @staticmethod
    def _blend_additive(base_color: "Color", blend_color: "Color") -> "Color":
        """Additive blending of two RGB color tuples."""
        blended_color = (
            min(255, base_color.red + blend_color.red),
            min(255, base_color.green + blend_color.green),
            min(255, base_color.blue + blend_color.blue),
        )
        return Color(blended_color)

    @staticmethod
    def _blend_min(base_color: "Color", blend_color: "Color") -> "Color":
        """Min blending of two RGB color tuples."""
        blended_color = (
            min(base_color.red, blend_color.red),
            min(base_color.green, blend_color.green),
            min(base_color.blue, blend_color.blue),
        )
        return Color(blended_color)

    @staticmethod
    def _blend_max(base_color: "Color", blend_color: "Color") -> "Color":
        """Min blending of two RGB color tuples."""
        blended_color = (
            max(base_color.red, blend_color.red),
            max(base_color.green, blend_color.green),
            max(base_color.blue, blend_color.blue),
        )
        return Color(blended_color)

    @staticmethod
    def _blend_subtractive(
        base_color: "Color", blend_color: "Color"
    ) -> "Color":
        """Subtractive blending of two RGB color tuples."""
        blended_color = (
            max(0, base_color.red - blend_color.red),
            max(0, base_color.green - blend_color.green),
            max(0, base_color.blue - blend_color.blue),
        )
        return Color(blended_color)

    @staticmethod
    def _blend_difference(
        base_color: "Color", blend_color: "Color"
    ) -> "Color":
        """Difference blending of two RGB color tuples."""
        blended_color = (
            abs(base_color.red - blend_color.red),
            abs(base_color.green - blend_color.green),
            abs(base_color.blue - blend_color.blue),
        )
        return Color(blended_color)

    @staticmethod
    def _blend_multiply(base_color: "Color", blend_color: "Color") -> "Color":
        """Multiplicative blending of two RGB color tuples."""
        blended_color = (
            (base_color.red * blend_color.red) // 255,
            (base_color.green * blend_color.green) // 255,
            (base_color.blue * blend_color.blue) // 255,
        )
        return Color(blended_color)

    @staticmethod
    def _blend_overlay(base_color: "Color", blend_color: "Color") -> "Color":
        """Overlay blending of two RGB color tuples."""

        def overlay_channel(base, blend):
            if base <= 127:
                return (2 * base * blend) // 255
            else:
                return 255 - (2 * (255 - base) * (255 - blend)) // 255

        blended_color = (
            overlay_channel(base_color[0], blend_color[0]),
            overlay_channel(base_color[1], blend_color[1]),
            overlay_channel(base_color[2], blend_color[2]),
        )
        return Color(blended_color)

    @staticmethod
    def _require_numpy() -> None:
        """Ensure numpy is available for LAB conversions."""
        if np is None:
            raise RuntimeError(
                "CIELAB blending requires numpy. Install numpy to use this mode."
            )

    @staticmethod
    def _rgb_to_lab(color: "Color"):
        """Convert an RGB color to LAB coordinates."""
        Color._require_numpy()
        rgb = np.array(color, dtype=np.float64) / 255.0
        rgb_linear = np.where(
            rgb <= 0.04045,
            rgb / 12.92,
            ((rgb + 0.055) / 1.055) ** 2.4,
        )
        xyz = np.array(
            [
                [0.4124564, 0.3575761, 0.1804375],
                [0.2126729, 0.7151522, 0.0721750],
                [0.0193339, 0.1191920, 0.9503041],
            ],
            dtype=np.float64,
        ) @ rgb_linear
        white = np.array([0.95047, 1.0, 1.08883], dtype=np.float64)
        xyz_scaled = xyz / white
        epsilon = 216.0 / 24389.0
        kappa = 24389.0 / 27.0
        f_xyz = np.where(
            xyz_scaled > epsilon,
            np.cbrt(xyz_scaled),
            (kappa * xyz_scaled + 16.0) / 116.0,
        )
        L = 116.0 * f_xyz[1] - 16.0
        a_component = 500.0 * (f_xyz[0] - f_xyz[1])
        b_component = 200.0 * (f_xyz[1] - f_xyz[2])
        return np.array([L, a_component, b_component], dtype=np.float64)

    @staticmethod
    def _lab_to_rgb(lab_vector) -> "Color":
        """Convert LAB coordinates back to an RGB Color."""
        Color._require_numpy()
        lab = np.array(lab_vector, dtype=np.float64)
        L, a_component, b_component = lab
        fy = (L + 16.0) / 116.0
        fx = fy + a_component / 500.0
        fz = fy - b_component / 200.0
        epsilon = 216.0 / 24389.0
        kappa = 24389.0 / 27.0

        def inv(component):
            component_cubed = component**3
            if component_cubed > epsilon:
                return component_cubed
            return (116.0 * component - 16.0) / kappa

        xyz = np.array([inv(fx), inv(fy), inv(fz)], dtype=np.float64)
        white = np.array([0.95047, 1.0, 1.08883], dtype=np.float64)
        xyz *= white
        rgb_linear = np.array(
            [
                [3.2404542, -1.5371385, -0.4985314],
                [-0.9692660, 1.8760108, 0.0415560],
                [0.0556434, -0.2040259, 1.0572252],
            ],
            dtype=np.float64,
        ) @ xyz
        rgb_linear = np.clip(rgb_linear, 0.0, 1.0)
        rgb = np.where(
            rgb_linear <= 0.0031308,
            12.92 * rgb_linear,
            1.055 * np.power(rgb_linear, 1 / 2.4) - 0.055,
        )
        rgb = np.clip(np.rint(rgb * 255.0), 0, 255).astype(int)
        return Color(tuple(int(component) for component in rgb.tolist()))

    @staticmethod
    def _blend_cielab_colors(colors: list["Color"]) -> "Color":
        """Blend colors by averaging in LAB space."""
        Color._require_numpy()
        labs = np.array(
            [Color._rgb_to_lab(color) for color in colors],
            dtype=np.float64,
        )
        mean_lab = labs.mean(axis=0)
        return Color._lab_to_rgb(mean_lab)

    @staticmethod
    def _blend_cielab_pair(base_color: "Color", blend_color: "Color") -> "Color":
        """Blend two colors in LAB space."""
        return Color._blend_cielab_colors([base_color, blend_color])


    # Map blend methods to blend functions
    _blend_functions = {
        BLEND_MULTIPLICATIVE: _blend_multiply,
        BLEND_LERP: blend_lerp,
        BLEND_ALPHA: blend_lerp,  # Same as BLEND_LERP
        BLEND_ADDITIVE: _blend_additive,
        BLEND_SUBTRACTIVE: _blend_subtractive,
        BLEND_DIFFERENCE: _blend_difference,
        BLEND_MIN: _blend_min,
        BLEND_MAX: _blend_max,
        BLEND_OVERLAY: _blend_overlay,
        BLEND_CIELAB: _blend_cielab_pair,
    }

    @classmethod
    def blend(cls,colors_list: list["Color"], blend_method=BLEND_ALPHA) -> "Color":
        """Blend an unspecified number of colors together."""
        if not colors_list:
            raise ValueError("The list of colors must not be empty.")

        if len(colors_list) == 1:
            return colors_list[0]

        if blend_method == BLEND_CIELAB:
            return cls._blend_cielab_colors(colors_list)

        while len(colors_list) > 2:
            # Reduce list by blending the first two colors.
            colors_list = [Color.blend(colors_list[:2], blend_method)] + colors_list[2:]

        color1, color2 = colors_list[0:2]


        if blend_method in cls._blend_functions:
            result = cls._blend_functions[blend_method](color1, color2)
        else:
            raise ValueError(f"Invalid blend method: {blend_method}")

        return result



class MappingPoint(float):
    """A single dataspace point to color definition.

    Each is essentially a value point (e.g. 37.6) and a Color
    If handled naively it will feel like a float.
    """

    def __new__(cls, determiner, color):
        """Create new float object for the instance."""
        instance = super(MappingPoint, cls).__new__(cls, determiner)
        instance.color = Color(color)
        instance.lab = None
        if not instance.color:
            raise ValueError("Invalid color")
        return instance

    def __eq__(self, other):
        """Test for equality: both value and color."""
        if isinstance(other, MappingPoint):
            return (self.real == other.real) and (self.color == other.color)
        return False

    def dump(
        self, indent: str = "", index: int = None, quiet: bool = False
    ) -> list[str]:
        """Dump the contents of the MappingPoint as readable text.

        Returns the contents as a list of strings (lines) and by default, prints.

        :index, if present, is just a courtesy number to add to the text
        :indent is what to put at the start of each line (e.g. "  ")
        :quiet, if True, suppresses printing.
        """
        index = "" if index is None else index
        lines = [
            f"{indent}MappingPoint {index}:  {self.real:6.2f};  "
            f"{str(self.color):16s} --> {self.color.similar_to()}"
        ]
        if not quiet:
            for line in lines:
                print(line)
        return lines


class Dimension:
    """Dimension obects handle all the mappings for one data dimension.

    E.g. x, or y.  It has a collection of ConfigPoints and the exponent
    for the curve that is used in the interpolation between the ConfigPoints.
    Higher exponent (>1) emphasizes small differences at the top end of the
    range; low exponent (<1) emphasizes small differences at the bottom
    of the range.
    """

    def __init__(
        self,
        interpolation_exponent: float = 1,
        none_color: str = "white",
        label=None,
        color_space: str = COLOR_SPACE_RGB,
    ):
        """Set initial values for Dimension properties."""
        if interpolation_exponent < 0:
            raise ValueError("Interpolation exponent must be >= 0.")
        color_space = (color_space or COLOR_SPACE_LAB).lower()
        if color_space not in (COLOR_SPACE_RGB, COLOR_SPACE_LAB):
            raise ValueError(
                f"Unsupported color_space '{color_space}'. "
                f"Use '{COLOR_SPACE_RGB}' or '{COLOR_SPACE_LAB}'."
            )
        self.interpolation_exponent = interpolation_exponent
        self.configs = []
        self.ready = False
        self.min = None
        self.max = None
        self.range = None
        self.none_color = None if none_color is None else Color(none_color)
        self.label = label
        self.color_space = color_space

    def add_config(self, determiner: float, color: str) -> None:
        """Add a MappingPoint to this dimension."""
        pt = MappingPoint(determiner, color)
        if pt is None:
            raise ValueError("Bad determiner of color")
        if pt.real in [cp.real for cp in self.configs]:
            raise ValueError(
                f"MappingPoint with determiner {pt} already exists"
            )
        if self.color_space == COLOR_SPACE_LAB:
            pt.lab = Color._rgb_to_lab(pt.color)
        self.configs.append(pt)
        self.configs.sort()
        self.min = float(min(self.configs))
        self.max = float(max(self.configs))
        self.range = self.max - self.min
        self.ready = True

    def get_label(self) -> str:
        """Return the known or a default label for this Dimension.

        The default label will not be known until MappingPoint's are
        added. If a self.label is known to exist, use that.  Else
        use this."""

        if self.label:
            return self.label
        # Create a default label
        lab = " => ".join([p.color.similar_to() for p in self.configs])
        if self.interpolation_exponent != 1:
            lab = f"{lab}  exp={self.interpolation_exponent}"
        return lab

    def get_color(self, determiner: float) -> Color:
        """Blend within gradients to get a color for this determiner value."""
        if self.range <= 0:
            return self.configs[0].color
        if determiner is None:
            if self.none_color is None:
                raise TypeError("determiner is None and no default given")
            else:
                return Color(self.none_color)

        # Clamp determiner to self's range
        determiner = max(self.min, min(self.max, determiner))
        # Adjust determiner according to the self's interpolation_exponent
        determiner_range = determiner - self.min
        adjusted_determiner = self.min + (
            determiner_range**self.interpolation_exponent
        ) * (self.range ** (1 - self.interpolation_exponent))
        # Now clamp the adjusted deteriner's range
        adjusted_determiner = max(self.min, min(self.max, adjusted_determiner))

        # Find the two adjacent ConfigPoints for interpolation
        for j in range(len(self.configs) - 1):
            if adjusted_determiner <= self.configs[j + 1]:
                gradient_min = self.configs[j]
                gradient_max = self.configs[j + 1]
                break

        if gradient_min.real == gradient_max.real:
            raise ValueError("Gradient has the same min and max values.")

        # Interpolate between the two adjacent colors
        blend_factor = (adjusted_determiner - gradient_min.real) / float(
            gradient_max - gradient_min
        )
        if self.color_space == COLOR_SPACE_LAB:
            Color._require_numpy()
            if gradient_min.lab is None:
                gradient_min.lab = Color._rgb_to_lab(gradient_min.color)
            if gradient_max.lab is None:
                gradient_max.lab = Color._rgb_to_lab(gradient_max.color)
            lab_min = gradient_min.lab
            lab_max = gradient_max.lab
            interpolated_lab = lab_min + (lab_max - lab_min) * blend_factor
            return Color._lab_to_rgb(interpolated_lab)

        return Color.blend_lerp(
            gradient_min.color, gradient_max.color, blend_factor
        )

    def css_fg(self, determiner: float) -> str:
        """Make a CSS (foreground) color style string component."""
        fg = self.get_color(determiner)
        return Color(fg).css_fg()

    def css_bg(self, determiner: float) -> str:
        """Make a CSS background color style string component."""
        bg = self.get_color(determiner)
        return Color(bg).css_bg()

    def css_bg_fg(self, determiner: float) -> str:
        """Make CSS style background color component with contrasting text color."""
        bg = self.get_color(determiner)
        return Color(bg).css_bg_fg()

    def dump(
        self, indent: str = "", index: int = None, quiet: bool = False
    ) -> list[str]:
        """Dump the contents of the Dimension as readable text.

        Returns the contents as a list of strings (lines) and by default, prints.

        :index, if present, is just a courtesy number to add to the Dimension text
        :indent is what to put at the start of each line (e.g. "  ")
        :quiet, if True, suppresses printing.

        """
        index = "" if index is None else index
        lines = []
        lines.append(f"{indent}Dimension {index}:")
        lines.append(
            f"{indent}  ready: {self.ready}; configs: {len(self.configs)}; "
            f"min/max/range: {self.min}/{self.max}/{self.range}; "
            f"interpolation_exponent: {self.interpolation_exponent}; "
            f"color_space: {self.color_space}; "
            f"none_color: {self.none_color}"
        )
        for j, pt in enumerate(self.configs):
            pt: MappingPoint
            lines = lines + pt.dump("      ", j, quiet=True)
        if not quiet:
            for line in lines:
                print(line)
        return lines

    def unload(self) -> list:
        """Unload the Dimension's configuration info into nested list.

        (This list could be used to load a Dimension).

        Structure:
        returns: [interpolation_exponent, configlist]
            config_list: [MappingPoint, MappingPoint..]
            MappingPoint: [value, color_as_html_hex_string]

        Notes for later:  to use this as a way to save configurations...
        - str() can be saved, then turned back into this structure using eval()
        """
        config_list = [
            [con.real, con.color.html_color] for con in self.configs
        ]
        none_color = (
            None if self.none_color is None else self.none_color.html_color
        )
        return [self.interpolation_exponent, none_color, config_list]


class MultiDimension:
    """MultiDimension looks after n-dimensional mappings of colors."""

    def __init__(self, blend_method: str = BLEND_ALPHA):
        """Initialize empty MultiDimension (not much to it)."""
        self.blend_method = blend_method
        self.dimensions = []  # Each is a Dimension

    def add_dimension(
        self,
        interpolation_exponent: float = 1,
        none_color: str = "white",
        label: str = None,
        color_space: str = COLOR_SPACE_RGB,
    ) -> Dimension:
        """Add an empty Dimension to the MultiDimension."""
        d = Dimension(
            interpolation_exponent=interpolation_exponent,
            none_color=none_color,
            label=label,
            color_space=color_space,
        )
        self.dimensions.append(d)
        return d

    def get_color(self, *determiner_tuple: tuple) -> Color:
        """Calculate a color from the dimensions of this multi-dimension."""
        if not self.ready:
            raise ValueError("MultiDimension is not ready")

        if len(determiner_tuple) != self.num_dimensions:
            raise ValueError(
                f"Different number of dimensions in determiner ({len(determiner_tuple)}) "
                f"and configuration ({self.num_dimensions})."
            )

        # Calculate colors for each dimension
        colors_list = []
        for i, dimension in enumerate(self.dimensions):
            colors_list.append(dimension.get_color(determiner_tuple[i]))

        # Blend the dimensions' colors into one
        final_color = Color.blend(colors_list, self.blend_method)
        return final_color

    @property
    def num_dimensions(self):
        """Count number of dimensions."""
        return len(self.dimensions)

    @property
    def ready(self):
        """Test if the MultiDimension has enough configuration to work."""
        return (
            all(d.ready for d in self.dimensions) if self.dimensions else False
        )

    def css_fg(self, determiner: tuple) -> str:
        """Make a CSS (foreground) color style string component."""
        fg = self.get_color(*determiner)
        return Color(fg).css_fg()

    def css_bg(self, determiner: tuple) -> str:
        """Make a CSS background color style string component."""
        bg = self.get_color(*determiner)
        return Color(bg).css_bg()

    def css_bg_fg(self, determiner: tuple) -> str:
        """Make CSS style background color component with contrasting text color."""
        bg = self.get_color(*determiner)
        return Color(bg).css_bg_fg()

    def unload(self) -> list:
        """Unload the multi-dimension configu info into nested list.

        This list could be used to load (or copy) a MultiDimension.

        Structure:
        returns: [blend_method, dimension_list, dimension_list..]
            dimension_list: [interpolation_exponent, configlist]
            config_list: [MappingPoint, MappingPoint..]
            MappingPoint: [value, color_as_html_hex_string]

        Notes for later:  to use this as a way to save configurations...
        - str() can be saved, then turned back into this structure using eval()
        """
        dimlist = [dim.unload() for dim in self.dimensions]
        return [self.blend_method, dimlist]

    def dump(self, quiet: bool = False) -> list[str]:
        """Dump the contents of the MultiDimension.

        Returns the contents as a list of strings (lines).
        By default it also prints the info; quiet flag
        will suppress printing.
        """
        lines = []
        lines.append(f"MultiDimension {self}")
        lines.append(
            f"  ready: {self.ready}; dimensions: {len(self.dimensions)}; "
            f"blend method: {self.blend_method}"
        )
        for i, d in enumerate(self.dimensions):
            d: Dimension
            lines = lines + d.dump("  ", i, quiet=True)

        if not quiet:
            for line in lines:
                print(line)
        return lines
