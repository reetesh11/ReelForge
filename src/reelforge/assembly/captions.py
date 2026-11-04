"""Caption styling and the `.ass` subtitle builder (pure functions)."""

from __future__ import annotations

from dataclasses import dataclass

from reelforge.assembly.edl import CAPTION_PRESETS, HEIGHT, WIDTH, Edl, EdlCaption


@dataclass(frozen=True)
class SafeZone:
    """Pixels kept clear on a 1080x1920 frame."""

    top: int
    bottom: int
    left: int
    right: int


SAFE_ZONE = SafeZone(top=250, bottom=250, left=64, right=64)


@dataclass(frozen=True)
class WordTiming:
    """One spoken word; seconds relative to the start of its audio clip."""

    text: str
    start_s: float
    end_s: float


def has_devanagari(text: str) -> bool:
    return any("ऀ" <= ch <= "ॿ" for ch in text)


def resolve_style(caption_style: str, caption: EdlCaption) -> str:
    """The caption's own style, else the EDL style, else Hindi for Devanagari text."""
    if caption.style in CAPTION_PRESETS:
        return str(caption.style)
    if caption_style in CAPTION_PRESETS:
        return caption_style
    return "hindi_devanagari" if has_devanagari(caption.text) else "bold_pop"


def _stamp(seconds: float) -> str:
    cs = max(0, int(seconds * 100 + 0.5))
    h, rest = divmod(cs, 360000)
    m, rest = divmod(rest, 6000)
    s, c = divmod(rest, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def _escape(text: str) -> str:
    cleaned = text.replace("{", "(").replace("}", ")").replace("\r", "")
    return cleaned.replace("\n", "\\N").strip()


def _karaoke(words: list[WordTiming]) -> str:
    parts: list[str] = []
    lead = round(words[0].start_s * 100)
    if lead > 2:
        parts.append(f"{{\\k{lead}}}")
    for i, word in enumerate(words):
        end = words[i + 1].start_s if i + 1 < len(words) else word.end_s
        cs = max(1, round((end - word.start_s) * 100))
        gap = " " if i + 1 < len(words) else ""
        parts.append(f"{{\\k{cs}}}{_escape(word.text)}{gap}")
    return "".join(parts)


def _style_line(
    name: str,
    font: str,
    size: int,
    primary: str,
    secondary: str,
    *,
    bold: bool,
    outline: int,
    border_style: int = 1,
    back: str = "&H80000000",
) -> str:
    z = SAFE_ZONE
    return (
        f"Style: {name},{font},{size},{primary},{secondary},&H00000000,{back},"
        f"{-1 if bold else 0},0,0,0,100,100,0,0,{border_style},{outline},0,2,"
        f"{z.left},{z.right},{z.bottom},1"
    )


def build_ass(edl: Edl, words: dict[str, list[WordTiming]], *, devanagari_font_family: str) -> str:
    """Full `.ass` text: three styles inside the safe zone and one event per non-empty caption."""
    styles = {
        "bold_pop": _style_line(
            CAPTION_PRESETS["bold_pop"],
            "Helvetica Neue",
            88,
            "&H0000F0FF",
            "&H00FFFFFF",
            bold=True,
            outline=6,
        ),
        "clean_subtitle": _style_line(
            CAPTION_PRESETS["clean_subtitle"],
            "Helvetica Neue",
            60,
            "&H00FFFFFF",
            "&H00FFFFFF",
            bold=False,
            outline=3,
            border_style=3,
            back="&H99000000",
        ),
        "hindi_devanagari": _style_line(
            CAPTION_PRESETS["hindi_devanagari"],
            devanagari_font_family,
            76,
            "&H00FFFFFF",
            "&H00FFFFFF",
            bold=False,
            outline=5,
        ),
    }
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {WIDTH}",
        f"PlayResY: {HEIGHT}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        *styles.values(),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for cap in edl.captions:
        if not cap.text.strip():
            continue
        key = resolve_style(edl.caption_style, cap)
        timed = words.get(cap.scene_id) or []
        text = _karaoke(timed) if key == "bold_pop" and timed else _escape(cap.text)
        lines.append(
            f"Dialogue: 0,{_stamp(cap.start_s)},{_stamp(cap.end_s)},"
            f"{CAPTION_PRESETS[key]},,0,0,0,,{text}"
        )
    return "\n".join(lines) + "\n"
