"""The robot as a pixel map, for terminals that cannot show the PNG.

Drawn by hand on the artwork's own unit grid, the way Claude Code draws its
mascot: every pixel is one flat colour from a small palette, and each
terminal cell shows two of them (``▀``, foreground on background).

This used to be the PNG shrunk to 20×18 with box resampling. The artwork's
units are about 26 px and do not line up with such a grid, so most output
pixels averaged two or three colours: grey seams around the screen, a
smeared eye and dash, feet that ran into each other. A map has no edges to
average.

Grid: 18 units wide × 16 tall, measured from ``assets/aria-robot.png``
(units ~26.4 × 27.3 px inside BOUNDS): ears 1 wide and 3 tall, a notched
cap, a 12 × 8 screen with a 2 × 2 eye and a 2 × 1 dash placed mirror-wise,
the body, the grey base, and four 2-wide feet. The orange seam between body
and base is thinner than a unit, so it is drawn as a ``▁`` on the last body
row instead of a pixel row.
"""

# Crop of assets/aria-robot.png that holds the robot, and the cells an
# inline image of it takes (an aspect-preserving image may need a row more).
BOUNDS = (389, 417, 865, 854)
IMAGE_COLUMNS = 20
IMAGE_ROWS = 10

WIDTH = 18
HEIGHT = 16

# "." is transparent: the terminal's own background shows through.
GRID = (
    "..BBBBBBBBBBBBBB..",
    ".BBBBBBBBBBBBBBBB.",
    ".BBSSSSSSSSSSSSBB.",
    ".BBSSSSSSSSSSSSBB.",
    ".BBSSSSSSSSSSSSBB.",
    "GBBSSEESSSSSSSSBBG",
    "GBBSSEESSSSDDSSBBG",
    "gBBSSSSSSSSSSSSBBg",
    ".BBSSSSSSSSSSSSBB.",
    ".BBSSSSSSSSSSSSBB.",
    ".BBBBBBBBBBBBBBBB.",
    ".BBBBBBBBBBBBBBBB.",
    ".AAAAAAAAAAAAAAAA.",
    "..FF..FF..FF..FF..",
    "..ff..ff..ff..ff..",
    "..................",
)

# Row (of GRID) whose bottom edge carries the orange seam.
SEAM_ROW = 11

# Sampled from the artwork. Light terminals get a deeper body, as the
# quadrant mascot in robot.py does: the artwork's cream vanishes on white.
PALETTES = {
    "dark": {
        "B": "#F4EBE4",  # cream shell
        "S": "#0E0E0E",  # screen
        "E": "#F4EBE2",  # square eye
        "D": "#FDB467",  # orange dash
        "G": "#BAB1A8",  # ear
        "g": "#7A7168",  # ear, shaded underside
        "A": "#B6ADA4",  # base
        "F": "#B9B0A7",  # feet
        "f": "#847B72",  # feet, shaded
        "seam": "#F9AF64",
    },
    "light": {
        "B": "#E6DDD0",
        "S": "#0E0E0E",
        "E": "#F6F2EA",
        "D": "#FDB467",
        "G": "#A39C93",
        "g": "#6F675F",
        "A": "#A39C93",
        "F": "#A39C93",
        "f": "#756D65",
        "seam": "#F2A456",
    },
}
