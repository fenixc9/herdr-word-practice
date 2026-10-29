"""Small ANSI cell renderer: width-aware text, styles, boxes, bars."""

from __future__ import annotations

import os
import shutil
import unicodedata

RESET = "\x1b[0m"
BOLD = "\x1b[1m"
DIM = "\x1b[2m"
ITALIC = "\x1b[3m"
UNDERLINE = "\x1b[4m"
REVERSE = "\x1b[7m"

HEX = {
    "base": "#1e1e2e", "mantle": "#181825", "crust": "#11111b",
    "surface0": "#313244", "surface1": "#45475a", "surface2": "#585b70",
    "overlay1": "#7f849c", "text": "#cdd6f4", "subtext": "#a6adc8",
    "mauve": "#cba6f7", "blue": "#89b4fa", "sapphire": "#74c7ec",
    "teal": "#94e2d5", "green": "#a6e3a1", "yellow": "#f9e2af",
    "peach": "#fab387", "red": "#f38ba8", "pink": "#f5c2e7",
    "lavender": "#b4befe",
}


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


def _rgb(hex_color: str) -> tuple[int, int, int]:
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


def style(text: str, fg_color: str | None = None, bg_color: str | None = None,
          bold: bool = False, dim: bool = False, italic: bool = False,
          underline: bool = False, reverse: bool = False,
          colors: bool = True) -> str:
    prefix = ""
    if colors:
        if fg_color:
            prefix += fg(fg_color, colors)
        if bg_color:
            prefix += bg(bg_color, colors)
        prefix += (BOLD if bold else "") + (DIM if dim else "")
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