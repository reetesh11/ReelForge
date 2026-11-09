"""A small typed builder for ffmpeg filter-graph scripts (`-filter_complex_script`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reelforge.assembly.edl import FPS, Edl, EdlAudio, EdlShot

SAMPLE_RATE = 48000
TARGET_LUFS = -14.0
TARGET_TP = -1.5
TARGET_LRA = 11.0
_SPECIAL = set(" \\'\":,;[]=\t\n")

Arg = str | int | float


def _text(value: Arg) -> str:
    if isinstance(value, float):
        return f"{value:.9f}".rstrip("0").rstrip(".") or "0"
    return str(value)


def escape(value: Arg) -> str:
    """Quote an option value for a filter graph when it holds characters that parse specially."""
    text = _text(value)
    if text and not any(c in _SPECIAL for c in text):
        return text
    return "'" + text.replace("'", "'\\''") + "'"


@dataclass(frozen=True)
class Filter:
    name: str
    args: list[Arg] | dict[str, Arg] | None = None

    def to_str(self) -> str:
        if not self.args:
            return self.name
        if isinstance(self.args, dict):
            body = ":".join(f"{k}={escape(v)}" for k, v in self.args.items())
        else:
            body = ":".join(escape(v) for v in self.args)
        return f"{self.name}={body}"


@dataclass(frozen=True)
class Chain:
    inputs: list[str]
    filters: list[Filter]
    outputs: list[str]

    def to_str(self) -> str:
        head = "".join(f"[{label}]" for label in self.inputs)
        tail = "".join(f"[{label}]" for label in self.outputs)
        return head + ",".join(f.to_str() for f in self.filters) + tail


@dataclass(frozen=True)
class FilterGraph:
    chains: list[Chain] = field(default_factory=list[Chain])

    def to_script(self) -> str:
        return ";\n".join(c.to_str() for c in self.chains)


@dataclass(frozen=True)
class Profile:
    name: str
    width: int
    height: int
    out_name: str
    preset: str
    crf: int
    audio_bitrate: str
    profile_v: str | None


PREVIEW = Profile("preview", 540, 960, "preview.mp4", "veryfast", 28, "96k", None)
FINAL = Profile("final", 1080, 1920, "final.mp4", "medium", 18, "192k", "high")
PROFILES: dict[str, Profile] = {"preview": PREVIEW, "final": FINAL}

STEREO = Filter(
    "aformat",
    {"sample_fmts": "fltp", "sample_rates": SAMPLE_RATE, "channel_layouts": "stereo"},
)


def build_normalise_graph(shot: EdlShot, width: int, height: int) -> FilterGraph:
    """One shot: constant 24 fps, trimmed to exact frames, scaled to cover and centre-cropped."""
    start = shot.in_frame
    frames = shot.frames
    return FilterGraph(
        [
            Chain(
                ["0:v"],
                [
                    Filter("fps", [FPS]),
                    Filter("trim", {"start_frame": start, "end_frame": start + frames}),
                    Filter("setpts", ["PTS-STARTPTS"]),
                    Filter("tpad", {"stop_mode": "clone", "stop": FPS}),
                    Filter("trim", {"end_frame": frames}),
                    Filter("setpts", ["PTS-STARTPTS"]),
                    Filter(
                        "scale",
                        {"w": width, "h": height, "force_original_aspect_ratio": "increase"},
                    ),
                    Filter("crop", [width, height]),
                    Filter("setsar", [1]),
                    Filter("format", {"pix_fmts": "yuv420p"}),
                    Filter("settb", ["1/24"]),
                ],
                ["v"],
            )
        ]
    )


def build_join_graph(edl: Edl) -> FilterGraph:
    """Cuts become `concat`, crossfades become `xfade`; inputs are the prepared shot files."""
    n = len(edl.video)
    if n == 1:
        return FilterGraph([Chain(["0:v"], [Filter("null")], ["v"])])
    chains: list[Chain] = []
    current = "0:v"
    length = edl.video[0].frames
    for i in range(1, n):
        label = "v" if i == n - 1 else f"j{i}"
        fade = edl.transition_frames(i)
        if fade > 0:
            f = Filter(
                "xfade",
                {
                    "transition": "fade",
                    "duration": fade / FPS,
                    "offset": (length - fade) / FPS,
                },
            )
        else:
            f = Filter("concat", {"n": 2, "v": 1, "a": 0})
        chains.append(Chain([current, f"{i}:v"], [f], [label]))
        length += edl.video[i].frames - fade
        current = label
    return FilterGraph(chains)


def build_dialogue_graph(edl: Edl) -> FilterGraph:
    """Silence of the reel's length plus each voice clip delayed to its offset."""
    total = edl.total_duration_s
    chains = [
        Chain(
            [],
            [Filter("anullsrc", {"r": SAMPLE_RATE, "cl": "stereo", "d": total})],
            ["bed"],
        )
    ]
    labels = ["bed"]
    for k, clip in enumerate(edl.dialogue, start=1):
        ms = int(round(clip.offset_s * 1000))
        filters = [
            Filter("atrim", {"duration": clip.duration_s}),
            Filter("asetpts", ["PTS-STARTPTS"]),
            Filter("aresample", [SAMPLE_RATE]),
            STEREO,
        ]
        if clip.gain_db:
            filters.append(Filter("volume", {"volume": f"{clip.gain_db}dB"}))
        filters.append(Filter("adelay", {"delays": f"{ms}|{ms}"}))
        chains.append(Chain([f"{k - 1}:a"], filters, [f"d{k}"]))
        labels.append(f"d{k}")
    chains.append(
        Chain(
            labels,
            [
                Filter(
                    "amix",
                    {
                        "inputs": len(labels),
                        "duration": "first",
                        "normalize": 0,
                        "dropout_transition": 0,
                    },
                ),
                STEREO,
            ],
            ["dlg"],
        )
    )
    return FilterGraph(chains)


MIN_RAMP_S = 0.001
ENVELOPE_SAMPLES = 480  # gain envelopes are evaluated every 10 ms


def _num(value: float) -> str:
    return _text(round(value, 6))


def _ramp(start: float, up_s: float, end: float, down_s: float) -> str:
    """0 before `start`, rising to 1 over `up_s`, holding to `end`, falling to 0 over `down_s`."""
    up, down = max(up_s, MIN_RAMP_S), max(down_s, MIN_RAMP_S)
    return f"min(clip((t-{_num(start)})/{_num(up)},0,1),clip(1-(t-{_num(end)})/{_num(down)},0,1))"


def _max_of(parts: list[str]) -> str:
    out = parts[0]
    for part in parts[1:]:
        out = f"max({out},{part})"
    return out


def duck_expression(edl: Edl) -> str | None:
    """Gain of a ducked music cue over reel time: a drop of `duck_db` while dialogue speaks."""
    if not edl.dialogue or edl.mix.duck_db <= 0:
        return None
    depth = 1 - 10 ** (-edl.mix.duck_db / 20)
    lines = [
        _ramp(d.offset_s, edl.mix.attack_s, d.offset_s + d.duration_s, edl.mix.release_s)
        for d in edl.dialogue
        if d.duration_s > 0
    ]
    if not lines:
        return None
    return f"1-{_num(depth)}*{_max_of(lines)}"


def silence_expression(edl: Edl) -> str | None:
    """Gain of the music, sound effect and ambience bus: zero inside every silence cue."""
    fade = edl.mix.silence_fade_s
    spans = [_ramp(c.start_s, fade, c.end_s, fade) for c in edl.audio if c.kind == "silence"]
    if not spans:
        return None
    return f"1-{_max_of(spans)}"


def _envelope(expression: str) -> list[Filter]:
    return [
        Filter("asetnsamples", {"n": ENVELOPE_SAMPLES, "p": 0}),
        Filter("volume", {"volume": expression, "eval": "frame"}),
    ]


def _cue_chain(edl: Edl, cue: EdlAudio, index: int, label: str, duck: str | None) -> Chain:
    length = max(cue.end_s - cue.start_s, 0.0)
    filters: list[Filter] = [
        Filter("aresample", [SAMPLE_RATE]),
        STEREO,
        Filter("atrim", {"duration": length}),
        Filter("asetpts", ["PTS-STARTPTS"]),
        Filter("apad", {"whole_dur": length}),
    ]
    if cue.gain_db:
        filters.append(Filter("volume", {"volume": f"{_num(cue.gain_db)}dB"}))
    if cue.fade_in_s > 0:
        filters.append(Filter("afade", {"t": "in", "st": 0, "d": min(cue.fade_in_s, length)}))
    if cue.fade_out_s > 0:
        fade = min(cue.fade_out_s, length)
        filters.append(Filter("afade", {"t": "out", "st": length - fade, "d": fade}))
    ms = int(round(cue.start_s * 1000))
    filters.append(Filter("adelay", {"delays": f"{ms}|{ms}"}))
    if cue.duck and cue.kind == "music" and duck is not None:
        filters.append(Filter("asetpts", ["N/SR/TB"]))
        filters.extend(_envelope(duck))
    return Chain([f"{index}:a"], filters, [label])


def build_mix_graph(edl: Edl) -> FilterGraph:
    """Dialogue (input 0) plus the cue files (inputs 1..N, in `edl.audio` order, silence has none).

    With no cues the dialogue is the whole mix.
    """
    total = edl.total_duration_s
    if not edl.audio:
        return FilterGraph(
            [
                Chain(
                    ["0:a"],
                    [
                        Filter("apad", {"whole_dur": total}),
                        Filter("atrim", {"duration": total}),
                        STEREO,
                    ],
                    ["mix"],
                )
            ]
        )
    duck = duck_expression(edl)
    chains: list[Chain] = []
    labels: list[str] = []
    for cue in edl.audio:
        if cue.artifact is None or cue.kind == "silence":
            continue
        label = f"c{len(labels) + 1}"
        chains.append(_cue_chain(edl, cue, len(labels) + 1, label, duck))
        labels.append(label)
    dialogue = [
        Filter("aresample", [SAMPLE_RATE]),
        STEREO,
        Filter("apad", {"whole_dur": total}),
        Filter("atrim", {"duration": total}),
    ]
    finish = [Filter("apad", {"whole_dur": total}), Filter("atrim", {"duration": total}), STEREO]
    if not labels:
        chains.append(Chain(["0:a"], [*dialogue, *finish], ["mix"]))
        return FilterGraph(chains)
    chains.append(Chain(["0:a"], dialogue, ["dlg"]))
    bus_filters: list[Filter] = []
    if len(labels) > 1:
        bus_filters.append(
            Filter(
                "amix",
                {
                    "inputs": len(labels),
                    "duration": "longest",
                    "normalize": 0,
                    "dropout_transition": 0,
                },
            )
        )
    gate = silence_expression(edl)
    if gate is not None:
        bus_filters.extend(_envelope(gate))
    if not bus_filters:
        bus_filters.append(Filter("anull"))
    chains.append(Chain(labels, bus_filters, ["bus"]))
    chains.append(
        Chain(
            ["dlg", "bus"],
            [
                Filter(
                    "amix",
                    {"inputs": 2, "duration": "first", "normalize": 0, "dropout_transition": 0},
                ),
                *finish,
            ],
            ["mix"],
        )
    )
    return FilterGraph(chains)


def build_loudnorm_graph(measured: dict[str, str] | None = None) -> FilterGraph:
    """Pass 1 (measure, `measured` is None) or pass 2 (apply the measured values, linear)."""
    args: dict[str, Arg] = {"I": TARGET_LUFS, "TP": TARGET_TP, "LRA": TARGET_LRA}
    filters: list[Filter] = []
    if measured is None:
        args["print_format"] = "json"
        filters.append(Filter("loudnorm", args))
    else:
        args.update(
            measured_I=measured["input_i"],
            measured_TP=measured["input_tp"],
            measured_LRA=measured["input_lra"],
            measured_thresh=measured["input_thresh"],
            offset=measured["target_offset"],
            linear="true",
            print_format="summary",
        )
        filters.extend([Filter("loudnorm", args), Filter("aresample", [SAMPLE_RATE]), STEREO])
    return FilterGraph([Chain(["0:a"], filters, ["n"])])


def build_encode_graph(profile: Profile, ass: str | None, fonts_dir: str | None) -> FilterGraph:
    """Final pass: size, optional caption burn-in, pixel format; audio to 48 kHz stereo."""
    video = [Filter("scale", {"w": profile.width, "h": profile.height})]
    if ass is not None:
        sub: dict[str, Arg] = {"filename": ass}
        if fonts_dir is not None:
            sub["fontsdir"] = fonts_dir
        video.append(Filter("subtitles", sub))
    video.append(Filter("format", {"pix_fmts": "yuv420p"}))
    return FilterGraph(
        [
            Chain(["0:v"], video, ["v"]),
            Chain(["1:a"], [Filter("aresample", [SAMPLE_RATE]), STEREO], ["a"]),
        ]
    )


def to_loudnorm_values(raw: Any) -> dict[str, str]:
    """Pick the five measured values out of loudnorm's JSON summary."""
    return {
        k: str(raw[k])
        for k in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
    }
