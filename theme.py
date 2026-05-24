"""Pokemon-themed terminal color system.

Picks a random color pokemon on startup, derives a 3-color theme from its
dominant hues, and exposes themed print helpers + a questionary Style.
"""

import math
import os
import random
import re
import sys
import time
from collections import Counter

import questionary
from rich.console import Console

# Module-level state
console: Console = Console()
_primary = (255, 255, 255)
_secondary = (180, 220, 255)
_accent = (140, 200, 180)


# ── internal helpers ─────────────────────────────────────────────────────────

def _brightness(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def _dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _boost(c, target=160):
    """Scale color up so it reads clearly on a dark terminal."""
    b = _brightness(c)
    if b < target:
        scale = target / max(b, 1)
        return tuple(min(255, int(v * scale)) for v in c)
    return c


def _dominant(colors, n=3, threshold=45):
    """Return up to n dominant color clusters (most frequent first)."""
    # Filter: skip near-white, near-black, and greys
    usable = [
        c for c in colors
        if 50 < _brightness(c) < 230 and (max(c) - min(c)) > 25
    ]
    pool = usable or colors or [(180, 180, 200)]

    counter = Counter(pool)
    clusters: list[list] = []
    for color, count in counter.most_common():
        merged = False
        for cluster in clusters:
            if _dist(color, cluster[0]) < threshold:
                cluster[1] += count
                merged = True
                break
        if not merged:
            clusters.append([color, count])

    clusters.sort(key=lambda x: x[1], reverse=True)
    result = [c[0] for c in clusters[:n]]
    while len(result) < n:
        result.append(result[-1])
    return result


def _rgb(c):
    return f"rgb({c[0]},{c[1]},{c[2]})"


def _hex(c):
    return f"#{c[0]:02x}{c[1]:02x}{c[2]:02x}"


def _strip_ansi(text):
    return re.sub(r'\x1b\[[^m]*m', '', text)


def _write_at(row, col, char, rgb=None):
    sys.stdout.write(f'\033[{row};{col}H')
    if rgb:
        r, g, b = rgb
        sys.stdout.write(f'\033[38;2;{r};{g};{b}m{char}\033[0m')
    else:
        sys.stdout.write(char)


def _parse_art_lines(content):
    """Parse ANSI-colored art into a list of [(rgb_or_None, char)] per line."""
    lines = content.split('\n')
    while lines and not _strip_ansi(lines[-1]).strip():
        lines.pop()
    result = []
    for line in lines:
        segments = []
        i = 0
        fg = None
        while i < len(line):
            if line[i] == '\x1b' and i + 1 < len(line) and line[i + 1] == '[':
                j = i + 2
                while j < len(line) and line[j] != 'm':
                    j += 1
                body = line[i + 2:j]
                m = re.match(r'38;2;(\d+);(\d+);(\d+)$', body)
                if m:
                    fg = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif body in ('0', ''):
                    fg = None
                i = j + 1
            else:
                segments.append((fg, line[i]))
                i += 1
        result.append(segments)
    return result


def _render_line(segments, glint_center=None, glint_w=10, peak=0.85):
    """Render parsed segments to an ANSI string, with optional glint sweep."""
    out = []
    for col_i, (rgb, char) in enumerate(segments):
        if rgb is not None:
            if glint_center is not None:
                dist = abs(col_i - glint_center)
                if dist < glint_w:
                    t = peak * (1 - dist / glint_w) ** 2
                    r = min(255, int(rgb[0] + (255 - rgb[0]) * t))
                    g = min(255, int(rgb[1] + (255 - rgb[1]) * t))
                    b = min(255, int(rgb[2] + (255 - rgb[2]) * t))
                    out.append(f'\x1b[38;2;{r};{g};{b}m{char}')
                    continue
            out.append(f'\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{char}')
        else:
            out.append(char)
    out.append('\x1b[0m')
    return ''.join(out)


def _splash_border(art_height, art_width, border_color):
    """Animate = border from bottom-left, two branches meeting at top-right."""
    top_row, bottom_row = 1, art_height + 2
    left_col, right_col = 1, art_width + 2

    _write_at(bottom_row, left_col, '=', border_color)
    sys.stdout.flush()

    # Branch A: right along bottom → up right side → top-right
    path_a = [(bottom_row, c) for c in range(left_col + 1, right_col + 1)]
    path_a += [(r, right_col) for r in range(bottom_row - 1, top_row - 1, -1)]

    # Branch B: up left side → right along top → top-right
    path_b = [(r, left_col) for r in range(bottom_row - 1, top_row - 1, -1)]
    path_b += [(top_row, c) for c in range(left_col + 1, right_col + 1)]

    n = max(len(path_a), len(path_b))
    delay = max(0.006, min(0.020, 1.5 / n))

    for i in range(n):
        if i < len(path_a):
            _write_at(*path_a[i], '=', border_color)
        if i < len(path_b):
            _write_at(*path_b[i], '=', border_color)
        sys.stdout.flush()
        time.sleep(delay)


def _splash_shimmer(parsed_lines, art_height, art_width):
    """Sweep a diagonal glint from top-right to bottom-left across the art."""
    art_row0 = 2
    glint_w = max(6, art_width // 7)
    frames = 48
    sweep = art_width + art_height + glint_w * 2

    for frame in range(frames):
        t = sweep * frame / (frames - 1) - glint_w
        for r_i, segs in enumerate(parsed_lines):
            center = (art_width - 1) - t + r_i  # diagonal: top-right → bottom-left
            sys.stdout.write(f'\033[{art_row0 + r_i};2H{_render_line(segs, center, glint_w)}')
        sys.stdout.flush()
        time.sleep(0.028)

    # Restore original colors
    for r_i, segs in enumerate(parsed_lines):
        sys.stdout.write(f'\033[{art_row0 + r_i};2H{_render_line(segs)}')
    sys.stdout.flush()


# ── public API ───────────────────────────────────────────────────────────────

def initialize():
    """Pick a random color pokemon, run splash animation, and build the color theme."""
    global console, _primary, _secondary, _accent

    art_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "art", "ascii", "pokemon")
    cursor_hidden = False

    try:
        files = [f for f in os.listdir(art_dir) if f.endswith("_color.txt")]
        chosen = random.choice(files)
        path = os.path.join(art_dir, chosen)

        with open(path, "r") as f:
            content = f.read()

        # Build theme before display so border uses the pokemon's primary color
        raw = re.findall(r"\x1b\[38;2;(\d+);(\d+);(\d+)m", content)
        colors = [(int(r), int(g), int(b)) for r, g, b in raw]
        if colors:
            dom = _dominant(colors)
            _primary = _boost(dom[0])
            _secondary = _boost(dom[1])
            _accent = _boost(dom[2])

        parsed_lines = _parse_art_lines(content)
        art_height = len(parsed_lines)
        art_width = max((len(segs) for segs in parsed_lines), default=40)

        # Clear screen, hide cursor, render art with absolute positioning.
        # Absolute positioning prevents any terminal scrolling, which would shift
        # row 1 down before the top border is drawn (causing the artifact).
        sys.stdout.write('\033[2J\033[H\033[?25l')
        cursor_hidden = True
        for r_i, segs in enumerate(parsed_lines):
            sys.stdout.write(f'\033[{r_i + 2};2H{_render_line(segs)}')
        sys.stdout.flush()

        _splash_border(art_height, art_width, _primary)
        _splash_shimmer(parsed_lines, art_height, art_width)

        # Move cursor below splash area and restore visibility
        sys.stdout.write(f'\033[{art_height + 3};1H\033[?25h\n')
        cursor_hidden = False
        sys.stdout.flush()

    except Exception:
        if cursor_hidden:
            sys.stdout.write('\033[?25h\n')
            sys.stdout.flush()

    console = Console()


def qs_style() -> questionary.Style:
    """Return a questionary Style derived from the current pokemon theme.

    Question label and pointer use the pokemon color. The autocomplete
    dropdown is forced to black background / white text so items always
    read clearly regardless of which pokemon (color) was chosen.
    """
    p = _hex(_primary)
    return questionary.Style([
        # themed chrome
        ("question",                            f"fg:{p} bold"),
        ("pointer",                             f"fg:{p} bold"),
        ("answer",                              ""),
        ("instruction",                         "italic"),
        # completion dropdown — black bg, white text, always readable
        ("completion-menu.completion",          "bg:#000000 fg:#ffffff"),
        ("completion-menu.completion.current",  "bg:#444444 fg:#ffffff bold"),
        # scrollbar inside the dropdown
        ("scrollbar.background",                "bg:#111111"),
        ("scrollbar.button",                    "bg:#888888"),
    ])


def header(text):
    """Bold primary-color text — for banners and section titles."""
    console.print(text, style=f"bold {_rgb(_primary)}")


def info(text):
    """Secondary-color text — for status messages and labels."""
    console.print(text, style=_rgb(_secondary))


def detail(text):
    """Accent-color text — for data rows and list items."""
    console.print(text, style=_rgb(_accent))


def muted(text):
    """Dim text — for secondary info, debug output, and errors."""
    console.print(text, style="dim")
