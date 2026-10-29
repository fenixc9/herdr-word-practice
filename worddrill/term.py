"""Small ANSI cell renderer: width-aware text, styles, boxes, bars."""

from __future__ import annotations

import os
import re
import shutil
import time
import unicodedata

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
ITALIC = "\x1b[3m"
UNDERLINE = "\x1b[4m"
REVERSE = "\x1b[7m"

# Two palettes with the same key names, so every call site is palette-agnostic.
# Dark is Catppuccin Mocha, light is Latte; the light one exists because light-on-
# light text is how a perfectly working TUI ends up looking "blank".
HEX_DARK = {
    "base": "#1e1e2e", "mantle": "#181825", "crust": "#11111b",
    "surface0": "#313244", "surface1": "#45475a", "surface2": "#585b70",
    "overlay1": "#7f849c", "text": "#cdd6f4", "subtext": "#a6adc8",
    "mauve": "#cba6f7", "blue": "#89b4fa", "sapphire": "#74c7ec",
    "teal": "#94e2d5", "green": "#a6e3a1", "yellow": "#f9e2af",
    "peach": "#fab387", "red": "#f38ba8", "pink": "#f5c2e7",
    "lavender": "#b4befe",
}

HEX_LIGHT = {
    "base": "#eff1f5", "mantle": "#e6e9ef", "crust": "#dce0e8",
    "surface0": "#ccd0da", "surface1": "#bcc0cc", "surface2": "#9ca0b0",
    "overlay1": "#8c8fa1", "text": "#4c4f69", "subtext": "#5c5f77",
    "mauve": "#8839ef", "blue": "#1e66f5", "sapphire": "#209fb5",
    "teal": "#179299", "green": "#2f7d32", "yellow": "#a06a00",
    "peach": "#d1640a", "red": "#c1121f", "pink": "#d20f39",
    "lavender": "#5b5bd6",
}

# Accents that hold up on both a dark and a light background. This is the
# default, because a terminal multiplexer pane usually cannot tell us which one
# it is: primary text uses the terminal's own foreground, and these mid-tone
# accents stay legible either way.
HEX_UNIVERSAL = {
    "base": "#1e1e2e", "mantle": "#181825", "crust": "#11111b",
    "surface0": "#313244", "surface1": "#45475a", "surface2": "#585b70",
    "overlay1": "#7f849c", "text": "#cdd6f4", "subtext": "#a6adc8",
    "mauve": "#8b5cf6", "blue": "#3b82f6", "sapphire": "#0ea5e9",
    "teal": "#0d9488", "green": "#2f9e44", "yellow": "#b45309",
    "peach": "#d97706", "red": "#dc2626", "pink": "#db2777",
    "lavender": "#7c7ff2",
}

PALETTES = {"dark": HEX_DARK, "light": HEX_LIGHT, "auto": HEX_UNIVERSAL}
HEX = dict(HEX_UNIVERSAL)
PALETTE = "auto"


def set_palette(mode: str) -> str:
    """Switch the module palette. Returns the palette actually in effect."""
    global PALETTE
    choice = str(mode or "auto").lower()
    if choice not in PALETTES:
        choice = "auto"
    PALETTE = choice
    HEX.clear()
    HEX.update(PALETTES[choice])
    return PALETTE


def luminance(hex_color: str) -> float:
    """Relative luminance (0 = black, 1 = white) of a #rrggbb color."""
    red, green, blue = _rgb(hex_color)
    channels = []
    for value in (red, green, blue):
        srgb = value / 255.0
        channels.append(srgb / 12.92 if srgb <= 0.03928
                        else ((srgb + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def color_supported() -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("WORDDRILL_NO_COLOR"):
        return False
    return os.environ.get("TERM", "") not in {"", "dumb"}


def truecolor_supported() -> bool:
    value = os.environ.get("COLORTERM", "").lower()
    if value in {"truecolor", "24bit"}:
        return True
    term_name = os.environ.get("TERM", "")
    return "256color" in term_name or "kitty" in term_name or "alacritty" in term_name


def _rgb(hex_color: str) -> tuple[int, int, int]:  # noqa: D401 - tiny helper
    hex_color = HEX.get(hex_color, hex_color).lstrip("#")
    return (int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16))


def _cube(hex_color: str) -> int:
    r, g, b = _rgb(hex_color)
    rr, gg, bb = (min(5, round(channel / 255 * 5)) for channel in (r, g, b))
    return 16 + 36 * rr + 6 * gg + bb


def fg(hex_color: str, colors: bool = True) -> str:
    if not colors:
        return ""
    if truecolor_supported():
        r, g, b = _rgb(hex_color)
        return f"\x1b[38;2;{r};{g};{b}m"
    return f"\x1b[38;5;{_cube(hex_color)}m"


def bg(hex_color: str, colors: bool = True) -> str:
    if not colors:
        return ""
    if truecolor_supported():
        r, g, b = _rgb(hex_color)
        return f"\x1b[48;2;{r};{g};{b}m"
    return f"\x1b[48;5;{_cube(hex_color)}m"


def char_width(char: str) -> int:
    if not char:
        return 0
    code = ord(char)
    if code == 0 or code < 32:
        return 0
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in {"W", "F"}:
        return 2
    if code in range(0x1F300, 0x1FAFF):  # emoji
        return 2
    return 1


def _skip_ansi(text: str, index: int) -> int:
    nxt = index + 1
    if nxt < len(text) and text[nxt] == "[":
        nxt += 1
        while nxt < len(text) and not ("@" <= text[nxt] <= "~"):
            nxt += 1
        return min(len(text), nxt + 1)
    return min(len(text), nxt + 1)


def text_width(text: str) -> int:
    width = 0
    index = 0
    while index < len(text):
        if text[index] == "\x1b":
            index = _skip_ansi(text, index)
            continue
        width += char_width(text[index])
        index += 1
    return width


def strip_ansi(text: str) -> str:
    out = []
    index = 0
    while index < len(text):
        if text[index] == "\x1b":
            index = _skip_ansi(text, index)
            continue
        out.append(text[index])
        index += 1
    return "".join(out)


def truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    out = []
    used = 0
    index = 0
    while index < len(text) and used < width:
        if text[index] == "\x1b":
            end = _skip_ansi(text, index)
            out.append(text[index:end])
            index = end
            continue
        w = char_width(text[index])
        if used + w > width:
            break
        out.append(text[index])
        used += w
        index += 1
    if used < width:
        out.append(" " * (width - used))
    return "".join(out)


def pad(text: str, width: int) -> str:
    used = text_width(text)
    if used >= width:
        return truncate(text, width)
    return text + " " * (width - used)


def wrap(text: str, width: int, max_lines: int | None = None) -> list[str]:
    if width <= 0:
        return []
    lines: list[str] = []
    current = ""
    used = 0
    for char in text:
        if char == "\n":
            lines.append(current)
            current = ""
            used = 0
            continue
        w = char_width(char)
        if used + w > width and current:
            split = current.rfind(" ")
            if split > 0 and used - text_width(current[split:]) > width // 2:
                carry = current[split + 1:]
                lines.append(current[:split].rstrip())
                current = carry
                used = text_width(carry)
            else:
                lines.append(current.rstrip())
                current = ""
                used = 0
            if char == " " and not current:
                continue
        current += char
        used += w
        if max_lines is not None and len(lines) >= max_lines:
            break
    if current or not lines:
        lines.append(current.rstrip())
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines:
            lines[-1] = truncate(lines[-1] + "…", width).rstrip()
    return lines


# Names that describe *hierarchy* rather than a hue. They must never be painted
# with a fixed color: the terminal's own foreground/background is the only thing
# guaranteed to contrast with the user's theme. Everything else is an accent.
STRUCTURAL = {
    "text": "",
    "subtext": DIM,
    "overlay1": DIM,
    "surface0": DIM,
    "surface1": DIM,
    "surface2": DIM,
}
STRUCTURAL_BG = {"base", "mantle", "crust"}


def style(text: str, fg_color: str | None = None, bg_color: str | None = None,
          bold: bool = False, dim: bool = False, italic: bool = False,
          underline: bool = False, reverse: bool = False,
          colors: bool = True) -> str:
    prefix = ""
    extra_dim = False
    if colors:
        if fg_color in STRUCTURAL:
            extra_dim = bool(STRUCTURAL[fg_color])
        elif fg_color:
            prefix += fg(fg_color, colors)
        if bg_color and bg_color not in STRUCTURAL_BG:
            prefix += bg(bg_color, colors)
        prefix += (BOLD if bold else "") + (DIM if (dim or extra_dim) else "")
        prefix += (ITALIC if italic else "") + (UNDERLINE if underline else "")
        prefix += REVERSE if reverse else ""
    return f"{prefix}{text}{RESET}" if prefix else text


def bar(fraction: float, width: int, filled: str = "▰", empty: str = "▱") -> str:
    fraction = max(0.0, min(1.0, fraction))
    cells = max(1, width)
    count = int(round(fraction * cells))
    if fraction > 0 and count == 0:
        count = 1
    return filled * count + empty * (cells - count)


def block_bar(value: int, maximum: int, width: int) -> str:
    if maximum <= 0:
        return "░" * width
    fraction = min(1.0, max(0.0, value / maximum))
    full = int(fraction * width)
    remainder = fraction * width - full
    out = "█" * full
    if full < width:
        out += "░▒▓█"[min(3, int(remainder * 4))]
        out += "░" * (width - len(out))
    return out[:width]


OSC11_QUERY = "\x1b]11;?\x1b\\"
_OSC11_RE = re.compile(rb"\x1b\]11;rgb:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})")


def parse_osc11(reply: bytes) -> str | None:
    """Return 'dark'/'light' for an OSC 11 background-color reply."""
    match = _OSC11_RE.search(reply)
    if not match:
        return None
    channels = [int(part, 16) / (65535 if len(part) == 4 else 255) for part in match.groups()]
    red, green, blue = (round(channel * 255) for channel in channels)
    return "light" if luminance(f"#{red:02x}{green:02x}{blue:02x}") > 0.5 else "dark"


def probe_background(fd: int | None, timeout: float = 0.12) -> str | None:
    """Ask the terminal for its background color. Best effort, never blocks long.

    Many terminals simply do not answer, which is fine: the caller keeps its
    default palette.
    """
    if fd is None:
        return None
    import select

    try:
        os.write(fd, OSC11_QUERY.encode())
    except OSError:
        return None
    reply = b""
    deadline = time.time() + timeout
    while time.time() < deadline and len(reply) < 256:
        remaining = max(0.0, deadline - time.time())
        ready, _, _ = select.select([fd], [], [], remaining)
        if not ready:
            break
        try:
            chunk = os.read(fd, 64)
        except OSError:
            break
        if not chunk:
            break
        reply += chunk
        if reply.endswith(b"\x07") or reply.endswith(b"\x1b\\"):
            break
    return parse_osc11(reply)


def terminal_size(default: tuple[int, int] = (100, 30)) -> tuple[int, int]:
    try:
        size = shutil.get_terminal_size((default[0], default[1]))
    except OSError:
        return default
    return max(20, size.columns), max(8, size.lines)


def emit(text: str) -> None:
    import sys

    sys.stdout.write(text)
    sys.stdout.flush()
