"""story.yaml loading, validation and dumping (ruamel round-trip, never constructs objects)."""

from __future__ import annotations

import io
from typing import Any

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq, TaggedScalar
from ruamel.yaml.emitter import Emitter
from ruamel.yaml.error import MarkedYAMLError, YAMLError

from reelforge.story.errors import StoryError, StoryInvalid
from reelforge.story.schema import CrossFieldIssues, Story

UNSAFE_TAG = "unsafe or unsupported YAML tag"
_CORE_TAGS = {
    "tag:yaml.org,2002:str",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:null",
    "tag:yaml.org,2002:map",
    "tag:yaml.org,2002:seq",
}
_MAX_NODES = 100_000


class _SpacedEmitter(Emitter):
    """Writes flow mappings as `{ a: 1 }` (the Product Spec style)."""

    def write_indicator(
        self,
        indicator: Any,
        need_whitespace: Any,
        whitespace: bool = False,
        indention: bool = False,
    ) -> None:
        if indicator.endswith("{"):
            indicator += " "
        elif indicator == "}":
            indicator = " }"
        super().write_indicator(indicator, need_whitespace, whitespace, indention)  # pyright: ignore[reportUnknownMemberType]


def _yaml() -> YAML:
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.Emitter = _SpacedEmitter
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 4096
    return y


def _tag_of(node: Any) -> str | None:
    tag = getattr(node, "tag", None)
    if tag is None:
        return None
    value = getattr(tag, "value", tag)
    return str(value) if value else None


def _check_tags(node: Any, count: list[int]) -> None:
    count[0] += 1
    if count[0] > _MAX_NODES:
        raise StoryInvalid([StoryError(path="", message="story.yaml is too complex")])
    tag = _tag_of(node)
    if isinstance(node, TaggedScalar) or (tag is not None and tag not in _CORE_TAGS):
        raise StoryInvalid([StoryError(path="", message=UNSAFE_TAG)])
    if isinstance(node, CommentedMap):
        for key, value in node.items():  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            _check_tags(key, count)
            _check_tags(value, count)
    elif isinstance(node, CommentedSeq):
        for item in node:  # pyright: ignore[reportUnknownVariableType]
            _check_tags(item, count)


def _syntax_error(exc: Any) -> StoryError:
    mark: Any = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    message = str(getattr(exc, "problem", None) or getattr(exc, "context", None) or "invalid YAML")
    return StoryError(
        path="",
        message=message.strip(),
        line=int(mark.line) + 1 if mark is not None else None,
        column=int(mark.column) + 1 if mark is not None else None,
    )


def load_story_text(text: str) -> CommentedMap:
    if not text.strip():
        raise StoryInvalid([StoryError(path="", message="story.yaml is empty")])
    try:
        loader: Any = _yaml()
        doc = loader.load(text)
    except MarkedYAMLError as exc:
        raise StoryInvalid([_syntax_error(exc)]) from None
    except YAMLError as exc:
        raise StoryInvalid(
            [StoryError(path="", message=str(exc).strip() or "invalid YAML")]
        ) from None
    if doc is None:
        raise StoryInvalid([StoryError(path="", message="story.yaml is empty")])
    if not isinstance(doc, CommentedMap):
        raise StoryInvalid(
            [StoryError(path="", message="story.yaml must be a mapping at the top level")]
        )
    _check_tags(doc, [0])
    return doc


def dump_story_text(doc: CommentedMap) -> str:
    buf = io.StringIO()
    dumper: Any = _yaml()
    dumper.dump(doc, buf)
    return buf.getvalue()


def to_plain(node: Any) -> Any:
    """Convert a ruamel tree into plain dict/list/scalars."""
    if isinstance(node, dict):
        return {str(k) if not isinstance(k, str) else k: to_plain(v) for k, v in node.items()}  # type: ignore[reportUnknownVariableType]
    if isinstance(node, list):
        return [to_plain(v) for v in node]  # type: ignore[reportUnknownVariableType]
    if isinstance(node, bool):
        return bool(node)
    if isinstance(node, int):
        return int(node)
    if isinstance(node, float):
        return float(node)
    if isinstance(node, str):
        return str(node)
    return node


def _format_loc(loc: tuple[Any, ...]) -> str:
    out = ""
    for part in loc:
        if part == "[key]":
            continue
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else str(part)
    return out


def _message(err: Any) -> str:
    kind = err["type"]
    if kind == "extra_forbidden":
        return "unknown field"
    if kind in {"int_type", "int_parsing", "int_from_float", "int_parsing_size"}:
        return "must be an integer"
    if kind == "missing":
        return "field required"
    return str(err["msg"])


def story_errors(exc: ValidationError) -> list[StoryError]:
    out: list[StoryError] = []
    for err in exc.errors():
        path = _format_loc(tuple(err["loc"]))
        inner = (err.get("ctx") or {}).get("error")
        if isinstance(inner, CrossFieldIssues):
            out.extend(StoryError(path=p, message=m) for p, m in inner.issues)
        else:
            out.append(StoryError(path=path, message=_message(err)))
    return out


def validate_story_data(data: Any) -> Story:
    """Validate plain data; raises `StoryInvalid` listing every error."""
    try:
        return Story.model_validate(data)
    except ValidationError as exc:
        raise StoryInvalid(story_errors(exc)) from None


def parse_story(text: str) -> Story:
    return validate_story_data(to_plain(load_story_text(text)))


def story_to_yaml(story: Story) -> str:
    data = story.model_dump(mode="json", exclude_none=True)
    return dump_story_text(_to_commented(data))


def _to_commented(value: Any) -> Any:
    if isinstance(value, dict):
        m = CommentedMap()
        for k, v in value.items():  # type: ignore[reportUnknownVariableType]
            m[k] = _to_commented(v)
        return m
    if isinstance(value, list):
        return CommentedSeq([_to_commented(v) for v in value])  # type: ignore[reportUnknownVariableType]
    return value
