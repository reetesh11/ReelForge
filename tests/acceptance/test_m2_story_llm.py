"""AC-4, AC-7, AC-9, AC-12: repair round, gap questions, suggested dialogue, Ollama adapter."""

from __future__ import annotations

import json

import httpx
import pytest
from rf_helpers import create_project, make_client, make_settings
from story_helpers import new_ctx, reply, story_dict, structure, versions

QUESTION = {"path": "scenes[1].setting", "question": "Where does scene 2 happen?"}


def _run(tmp_path, llm, **body):
    ctx = new_ctx(tmp_path, llm=llm)
    with make_client(ctx) as client:
        pid = create_project(client)["id"]
        job = structure(client, ctx, pid, **body)
        res = client.get(f"/api/v1/jobs/{job.id}").json()
        return client, pid, job, res, versions(client, pid)


# ---- AC-4 -------------------------------------------------------------------------------


def test_invalid_output_gets_exactly_one_repair_then_fails(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm

    bad = story_dict(fps="abc")
    llm = MockLlm(responses=[reply(bad)])
    _, _, job, res, vs = _run(tmp_path, llm)
    assert len(llm.calls) == 2
    assert job.status == "failed"
    assert job.error.startswith(
        "The model's story didn't match the schema after one repair attempt:"
    )
    assert "fps" in job.error and res["error"] == job.error
    assert vs == []
    first, second = llm.calls
    assert second[: len(first)] == first and len(second) == len(first) + 2
    assert second[-2] == {"role": "assistant", "content": reply(bad)}
    assert second[-1]["role"] == "user" and "fps" in second[-1]["content"]
    assert "must be an integer" in second[-1]["content"]


def test_non_json_output_also_one_repair(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm

    llm = MockLlm(responses=["not json at all"])
    _, _, job, _, vs = _run(tmp_path, llm)
    assert len(llm.calls) == 2 and job.status == "failed" and vs == []


def test_repair_valid_saves_version_with_two_calls(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm

    llm = MockLlm(responses=[reply(story_dict(fps="abc")), reply(story_dict())])
    _, _, job, res, vs = _run(tmp_path, llm)
    assert job.status == "succeeded", job.error
    assert len(llm.calls) == 2
    assert len(vs) == 1 and res["result"]["version"]["is_current"] is True


def test_valid_first_reply_makes_one_call(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm

    llm = MockLlm(responses=[reply(story_dict())])
    _, _, job, _, vs = _run(tmp_path, llm)
    assert job.status == "succeeded" and len(llm.calls) == 1 and len(vs) == 1


# ---- AC-12 ------------------------------------------------------------------------------


def _too_long():
    return story_dict(target_seconds=12, scenes=[
        {"id": f"s{i}", "action": "a", "duration": 4.0} for i in range(1, 6)
    ])


def _multiline_look():
    d = story_dict()
    d["characters"]["tomato"]["look"] = "round red tomato\nbig eyes"
    return d


def _bad_speaker():
    d = story_dict()
    d["scenes"][1]["speaker"] = "ghost"
    return d


@pytest.mark.parametrize(
    "bad",
    [
        story_dict(n_scenes=3),
        story_dict(n_scenes=9),
        _too_long(),
        _multiline_look(),
        _bad_speaker(),
    ],
    ids=["3-scenes", "9-scenes", "over-target", "multiline-look", "bad-speaker"],
)
def test_structural_rules_trigger_repair_round(tmp_path, bad):
    from reelforge.adapters.mock_llm import MockLlm

    llm = MockLlm(responses=[reply(bad), reply(story_dict())])
    _, _, job, _, vs = _run(tmp_path, llm)
    assert len(llm.calls) == 2 and job.status == "succeeded" and len(vs) == 1


def test_server_sets_target_language_and_version(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm
    from reelforge.story.yamlio import parse_story

    llm = MockLlm(responses=[reply(story_dict(language="english", target_seconds=30))])
    client, pid, job, _, _ = _run(tmp_path, llm, language="hindi", target_seconds=10)
    assert job.status == "succeeded", job.error
    st = parse_story(client.get(f"/api/v1/projects/{pid}/story").json()["yaml_text"])
    assert st.language == "hindi" and st.target_seconds == 10 and st.version == 1


# ---- AC-7 -------------------------------------------------------------------------------


def test_gap_question_removes_invented_value_and_saves_no_version(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm
    from reelforge.story.yamlio import parse_story

    d = story_dict()
    d["scenes"][1]["setting"] = "an invented castle"
    llm = MockLlm(responses=[reply(d, [QUESTION])])
    _, _, job, res, vs = _run(tmp_path, llm)
    assert job.status == "succeeded", job.error
    assert len(llm.calls) == 1  # questions skip the repair round
    r = res["result"]
    assert r["version"] is None and vs == []
    assert r["questions"] == [QUESTION]
    draft = parse_story(r["draft_yaml"])
    assert draft.scenes[1].setting is None
    assert draft.scenes[0].setting == "Place 1"


def test_gap_on_required_field_returns_only_questions(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm

    q = {"path": "characters.tomato.look", "question": "What is the tomato wearing?"}
    llm = MockLlm(responses=[reply(story_dict(), [q])])
    _, _, job, res, vs = _run(tmp_path, llm)
    assert job.status == "succeeded", job.error
    assert res["result"]["questions"] == [q]
    assert res["result"]["draft_yaml"] is None and res["result"]["version"] is None and vs == []


def test_suggested_flag_without_user_dialogue(tmp_path):
    from reelforge.story.yamlio import parse_story

    client, pid, job, _, _ = _run(tmp_path, None)
    assert job.status == "succeeded", job.error
    st = parse_story(client.get(f"/api/v1/projects/{pid}/story").json()["yaml_text"])
    lined = [s for s in st.scenes if s.line]
    assert lined and all(s.suggested is True for s in lined)
    assert all(s.suggested is None for s in st.scenes if not s.line)


def test_no_suggested_flag_when_user_gave_dialogue_and_accept_via_put(tmp_path):
    from reelforge.story.yamlio import parse_story

    client, pid, job, _, _ = _run(tmp_path, None, dialogue="Tomato: Arre Aloo!")
    assert job.status == "succeeded", job.error
    st = parse_story(client.get(f"/api/v1/projects/{pid}/story").json()["yaml_text"])
    assert all(not s.suggested for s in st.scenes)


def test_accepting_suggestion_removes_flag_on_save(tmp_path):
    from reelforge.story.yamlio import parse_story

    client, pid, _, _, _ = _run(tmp_path, None)
    text = client.get(f"/api/v1/projects/{pid}/story").json()["yaml_text"]
    assert "suggested: true" in text
    accepted = "\n".join(ln for ln in text.splitlines() if ln.strip() != "suggested: true") + "\n"
    r = client.put(f"/api/v1/projects/{pid}/story", content=accepted.encode(),
                   headers={"Content-Type": "text/plain"})
    assert r.status_code == 200, r.text
    st = parse_story(client.get(f"/api/v1/projects/{pid}/story").json()["yaml_text"])
    assert all(not s.suggested for s in st.scenes)


def test_answers_are_included_in_prompt(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm

    llm = MockLlm()
    ans = [{"path": QUESTION["path"], "question": QUESTION["question"], "answer": "a purple cave"}]
    _, _, job, _, vs = _run(tmp_path, llm, answers=ans)
    assert job.status == "succeeded" and len(vs) == 1
    assert "a purple cave" in json.dumps(llm.calls[0])


def test_adapter_error_fails_job_with_message_and_no_retry(tmp_path):
    from reelforge.adapters.base import AdapterError

    class Down:
        name = "down"

        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages, *, schema, temperature=0.3, heavy_next=False):
            self.calls += 1
            raise AdapterError("Ollama isn't reachable on port 11434.")

    llm = Down()
    _, _, job, _, vs = _run(tmp_path, llm)
    assert job.status == "failed" and job.error == "Ollama isn't reachable on port 11434."
    assert llm.calls == 1 and vs == []


# ---- AC-9 -------------------------------------------------------------------------------


def test_mock_llm_default_canned_story():
    import asyncio

    from reelforge.adapters.mock_llm import MockLlm
    from reelforge.story.schema import Story

    llm = MockLlm()
    out = json.loads(asyncio.run(llm.chat([{"role": "user", "content": "x"}], schema={})))
    assert out["questions"] == []
    story = Story.model_validate(out["story"])
    assert sorted(story.characters) == ["potato", "tomato"]
    assert [s.id for s in story.scenes] == ["s1", "s2", "s3", "s4", "s5"]
    assert sum(s.duration or 0 for s in story.scenes) == pytest.approx(10.0)
    assert len(llm.calls) == 1


def test_context_selects_backend(tmp_path):
    from reelforge.adapters.mock_llm import MockLlm
    from reelforge.adapters.ollama import OllamaAdapter

    assert isinstance(new_ctx(tmp_path / "a").llm, MockLlm)
    ctx = new_ctx(tmp_path / "b", llm_backend="ollama")
    assert isinstance(ctx.llm, OllamaAdapter) and ctx.llm.model == "qwen3:8b"


def _adapter(handler, model="qwen3:8b"):
    from reelforge.adapters.ollama import OllamaAdapter

    return OllamaAdapter("http://127.0.0.1:11434", model, transport=httpx.MockTransport(handler))


def _capture():
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "{\"ok\": 1}"}})

    return seen, handler


async def test_chat_request_shape():
    seen, handler = _capture()
    schema = {"type": "object", "properties": {"story": {}}}
    msgs = [{"role": "user", "content": "hi"}]
    out = await _adapter(handler).chat(msgs, schema=schema, temperature=0.3)
    assert out == '{"ok": 1}'
    (req,) = seen
    assert req.method == "POST" and req.url.path == "/api/chat"
    body = json.loads(req.content)
    assert body["model"] == "qwen3:8b" and body["messages"] == msgs and body["stream"] is False
    assert body["format"] == schema
    assert 0.2 <= body["options"]["temperature"] <= 0.4
    assert body["keep_alive"] != 0


async def test_chat_keep_alive_zero_only_when_heavy_next():
    seen, handler = _capture()
    a = _adapter(handler)
    await a.chat([{"role": "user", "content": "x"}], schema={}, heavy_next=True)
    await a.chat([{"role": "user", "content": "x"}], schema={}, heavy_next=False)
    assert json.loads(seen[0].content)["keep_alive"] == 0
    assert json.loads(seen[1].content)["keep_alive"] != 0


async def test_model_default_comes_from_models_toml(tmp_path):
    from reelforge.models_registry import load_models

    model = load_models(make_settings(tmp_path).models_path).get("llm").id
    assert model == "qwen3:8b"
    seen, handler = _capture()
    await _adapter(handler, model).chat([{"role": "user", "content": "x"}], schema={})
    assert json.loads(seen[0].content)["model"] == model


@pytest.mark.parametrize("t", [0.1, 0.5, 1.0])
async def test_temperature_out_of_range_rejected(t):
    seen, handler = _capture()
    with pytest.raises(ValueError):
        await _adapter(handler).chat([{"role": "user", "content": "x"}], schema={}, temperature=t)
    assert seen == []


async def test_chat_errors_have_user_messages():
    from reelforge.adapters.base import AdapterError

    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(AdapterError, match=r"^Ollama isn't reachable on port 11434\.$"):
        await _adapter(down).chat([{"role": "user", "content": "x"}], schema={})

    def missing(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'qwen3:8b' not found"})

    with pytest.raises(AdapterError, match=r"^qwen3:8b isn't pulled\.$"):
        await _adapter(missing).chat([{"role": "user", "content": "x"}], schema={})


async def test_health_uses_api_tags_and_reports_fixes():
    paths: list[tuple[str, str]] = []

    def ok(req: httpx.Request) -> httpx.Response:
        paths.append((req.method, req.url.path))
        return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})

    rep = await _adapter(ok).health()
    assert rep.ok is True and paths == [("GET", "/api/tags")]

    def empty(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": "llama3:8b"}]})

    rep = await _adapter(empty).health()
    assert (rep.ok, rep.detail, rep.fix) == (False, "qwen3:8b isn't pulled.", "ollama pull qwen3:8b")

    def down(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    rep = await _adapter(down).health()
    assert (rep.ok, rep.detail, rep.fix) == (
        False,
        "Ollama isn't reachable on port 11434.",
        "Start Ollama: ollama serve",
    )
