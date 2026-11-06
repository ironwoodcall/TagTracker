#!/usr/bin/env python3
"""Make a printable PDF of QR labels for trying out scanning.

For each tag ID it prints:
  - two IN labels  (#i-<tagid>) and two OUT labels (#o-<tagid>), captioned
    "IN <TAGID>" and "OUT <TAGID>" under the code, one of
    each for each side of the bike tag; tape IN away from the hole and OUT
    near it (design doc, Appendix A.1). OUT is printed smaller than IN
    (--out-dots; give two values to try two sizes, one per side);
  - a 2 x 4 cm fob insert with the fob URL code (HTTPS://CAPITALBIKE.CA/#o-<tagid>),
    version 3-H (design doc, Appendix A.2, option A);
  - and, to compare, a second fob insert at version 2-M.

Usage:
    python3 helpers/qr_labels.py oa6 ga2 pb5 bh0 wa0 gc9 -o qr_labels.pdf

Print the PDF at "Actual size" (100%), never "Fit to page", then check the
100 mm bar at the top of the page with a ruler.

Sizes use whole printer dots at 600 dpi, so every QR module prints the same
width. Needs the segno package (pip install segno); writes the PDF itself.
"""

from __future__ import annotations

import argparse
import re
import sys
import zlib

try:
    import segno
    from segno import consts
except ImportError:
    sys.exit("This needs the segno package: pip install segno")

URL_PREFIX = "HTTPS://CAPITALBIKE.CA/"  # upper case, so it packs as alphanumeric (A.2)

MM = 72 / 25.4  # points per mm
DOT = 72 / 600  # points per printer dot at 600 dpi
PAGE_W, PAGE_H = 8.5 * 72, 11 * 72  # US Letter
MARGIN = 12 * MM

LABEL_W, LABEL_H = 34 * MM, 21 * MM  # bike-tag label, cut line
FOB_W, FOB_H = 40 * MM, 20 * MM  # fob insert, cut line
GAP = 2 * MM

# Dots per module: IN codes 1-H (29 modules with border) at 14 dots = 17.2 mm
# (OUT codes are smaller: --out-dots, e.g. 11 dots = 13.5 mm, 10 = 12.3 mm);
# fob 3-H (37) at 11 dots = 17.2 mm; fob 2-M (33) at 12 dots = 16.8 mm.
DOTS_PER_MODULE = {"1-H": 14, "3-H": 11, "2-M": 12}

TAG_RE = re.compile(r"^[A-Za-z]{2}\d{1,2}$")


# Helvetica-Bold character widths (per 1000 units of font size), for centring.
_BOLD_WIDTHS = {
    " ": 278, "A": 722, "B": 722, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 556, "K": 722, "L": 611, "M": 833, "N": 722, "O": 778,
    "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722, "V": 667, "W": 944,
    "X": 667, "Y": 667, "Z": 611, **{d: 556 for d in "0123456789"},
}


def text_width(s: str, size: float, bold: bool = True) -> float:
    """Width in points of upper-case text in Helvetica-Bold."""
    return sum(_BOLD_WIDTHS.get(ch, 667) for ch in s) * size / 1000


def snap(x: float) -> float:
    """Round to the 600 dpi dot grid."""
    return round(x / DOT) * DOT


def make_code(segments, error: str, expect: str):
    """A QR code from segments, checked to be the expected version-error."""
    qr = segno.make(segments, error=error, boost_error=False, micro=False)
    if qr.designator != expect:
        sys.exit(f"Expected a {expect} code for {segments!r}, got {qr.designator}")
    return qr


class Page:
    """Just enough PDF drawing for this page."""

    def __init__(self):
        self.ops: list[str] = []

    def y(self, top: float) -> float:
        """PDF y from a distance down from the top of the page."""
        return PAGE_H - top

    def qr(self, qr, left: float, top: float, dots: int) -> float:
        """Draw a QR code (with its 4-module blank border). Returns its size in points."""
        module = dots * DOT
        left, top = snap(left), snap(top)
        matrix = qr.matrix
        border = 4
        self.ops.append("0 g")
        for r, row in enumerate(matrix):
            c = 0
            while c < len(row):
                if row[c]:
                    start = c
                    while c < len(row) and row[c]:
                        c += 1
                    x = left + (start + border) * module
                    y = self.y(top + (r + border + 1) * module)
                    self.ops.append(f"{x:.3f} {y:.3f} {(c - start) * module:.3f} {module:.3f} re")
                else:
                    c += 1
        self.ops.append("f")
        return (len(matrix) + 2 * border) * module

    def text(self, s: str, left: float, top_baseline: float, size: float, bold=False):
        s = s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        font = "F2" if bold else "F1"
        self.ops.append(f"BT /{font} {size:.2f} Tf {left:.3f} {self.y(top_baseline):.3f} Td ({s}) Tj ET")

    def dashed_box(self, left: float, top: float, w: float, h: float):
        self.ops.append(
            f"q 0.6 G 0.4 w [3 2] 0 d {left:.3f} {self.y(top + h):.3f} {w:.3f} {h:.3f} re S Q"
        )

    def line(self, x1, top1, x2, top2, width=0.6):
        self.ops.append(f"q 0 G {width} w {x1:.3f} {self.y(top1):.3f} m {x2:.3f} {self.y(top2):.3f} l S Q")

    def pdf(self) -> bytes:
        content = zlib.compress("\n".join(self.ops).encode("latin-1"))
        objs = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W:.0f} {PAGE_H:.0f}] "
                "/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>"
            ).encode(),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            f"<< /Length {len(content)} /Filter /FlateDecode >>\nstream\n".encode() + content + b"\nendstream",
        ]
        out = bytearray(b"%PDF-1.4\n")
        offsets = []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)


def bike_label(page: Page, tag: str, label: str, payload: str, left: float, top: float,
               dots: int = DOTS_PER_MODULE["1-H"]):
    page.dashed_box(left, top, LABEL_W, LABEL_H)
    qr = make_code(payload, "h", "1-H")
    size = 29 * dots * DOT  # including the 4-module blank border
    code_left, code_top = left + 1.2 * MM, top + 0.6 * MM
    page.qr(qr, code_left, code_top, dots)
    # "IN <tag>" / "OUT <tag>" in small type, centred under the code, just
    # outside its blank border.
    word = f"{label} {tag.upper()}"
    word_size = 6.5
    word_w = text_width(word, word_size, bold=True)
    cap_height = 0.72 * word_size
    page.text(word, code_left + (size - word_w) / 2, code_top + size + cap_height, word_size, bold=True)
    tx = code_left + size + 1.0 * MM
    page.text(tag.upper(), tx, top + 12 * MM, 13, bold=True)
    if dots != DOTS_PER_MODULE["1-H"]:
        page.text(f"{size / MM:.1f} mm", tx, top + 16.5 * MM, 5)


def fob_insert(page: Page, tag: str, version: str, left: float, top: float):
    page.dashed_box(left, top, FOB_W, FOB_H)
    segments = [(URL_PREFIX, consts.MODE_ALPHANUMERIC), (f"#o-{tag}", consts.MODE_BYTE)]
    qr = make_code(segments, version[-1].lower(), version)
    dots = DOTS_PER_MODULE[version]
    modules = {"3-H": 37, "2-M": 33}[version]
    size = modules * dots * DOT
    page.qr(qr, left + 1.2 * MM, top + (FOB_H - size) / 2, dots)
    tx = left + 1.2 * MM + size + 1.0 * MM
    page.text(tag.upper(), tx, top + 12.5 * MM, 17, bold=True)
    page.text(version, tx, top + 17.5 * MM, 5)


def build(tags: list[str], out_dots: list[int]) -> bytes:
    page = Page()
    top = MARGIN
    page.text("TagTracker scanning test: QR labels", MARGIN, top + 4 * MM, 11, bold=True)
    page.text(
        "Print at Actual size (100%), not Fit to page. The bar below must measure 100 mm.",
        MARGIN, top + 9 * MM, 8,
    )
    bar_top = top + 12 * MM
    page.line(MARGIN, bar_top, MARGIN + 100 * MM, bar_top, 0.8)
    for mm in range(0, 101, 10):
        page.line(MARGIN + mm * MM, bar_top - 1.5 * MM, MARGIN + mm * MM, bar_top + 1.5 * MM, 0.5)
    page.text("100 mm", MARGIN + 102 * MM, bar_top + 1 * MM, 7)

    top = bar_top + 7 * MM
    page.text(
        "Bike tag: one IN and one OUT per side. IN away from the hole, OUT (smaller) near it.   "
        "Fob insert: 2 x 4 cm, version 3-H.",
        MARGIN, top, 7,
    )
    top += 3 * MM
    for tag in tags:
        x = MARGIN
        outs = iter(out_dots * 2 if len(out_dots) == 1 else out_dots)
        for label in ("IN", "IN", "OUT", "OUT"):
            payload = f"#{label[0].lower()}-{tag}"
            dots = next(outs) if label == "OUT" else DOTS_PER_MODULE["1-H"]
            bike_label(page, tag, label, payload, x, top, dots)
            x += LABEL_W + GAP
        fob_insert(page, tag, "3-H", x + GAP, top)
        top += LABEL_H + 3 * MM

    top += 4 * MM
    page.text("Fob inserts, version 2-M, to compare with 3-H above.", MARGIN, top, 7)
    top += 3 * MM
    per_row = 4
    for i, tag in enumerate(tags):
        if i and i % per_row == 0:
            top += FOB_H + 3 * MM
        fob_insert(page, tag, "2-M", MARGIN + (i % per_row) * (FOB_W + 3 * GAP), top)
    top += FOB_H
    if top > PAGE_H - MARGIN:
        sys.exit(f"Too many tags for one page ({len(tags)}); try 8 or fewer.")
    return page.pdf()


def main():
    parser = argparse.ArgumentParser(description="Printable QR labels for a scanning test.")
    parser.add_argument("tags", nargs="+", help="tag IDs, e.g. oa6 ga2")
    parser.add_argument("-o", "--output", default="qr_labels.pdf", help="PDF to write")
    parser.add_argument(
        "--out-dots", type=int, nargs="+", default=[11], metavar="N",
        help="printer dots per module for OUT codes (IN uses 14): 11 = 13.5 mm, "
        "10 = 12.3 mm. Two values: one size per side. Default 11.",
    )
    args = parser.parse_args()
    if len(args.out_dots) > 2 or any(not 9 <= d <= 14 for d in args.out_dots):
        sys.exit("--out-dots takes one or two values from 9 to 14.")
    tags = [t.strip().lower() for t in args.tags]
    bad = [t for t in tags if not TAG_RE.match(t)]
    if bad:
        sys.exit(f"Not tag IDs (two letters, then 1-2 digits): {', '.join(bad)}")
    with open(args.output, "wb") as f:
        f.write(build(tags, args.out_dots))
    print(f"Wrote {args.output}: {len(tags)} tags. Print at Actual size (100%).")


if __name__ == "__main__":
    main()
