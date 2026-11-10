import asyncio
import json

from reelforge.voice.translit import needs_devanagari, to_devanagari


class FakeLlm:
    name = "fake"

    def __init__(self, table):
        self.table = table
        self.calls = []

    async def chat(self, messages, *, schema, temperature=0.3, heavy_next=False):
        self.calls.append(messages[-1]["content"])
        return json.dumps({"devanagari": self.table[messages[-1]["content"]]}, ensure_ascii=False)


def test_needs_devanagari_ignores_tags_and_devanagari():
    assert needs_devanagari("Maza nahi aaya!")
    assert not needs_devanagari("[sigh] मज़ा नहीं आया!")
    assert not needs_devanagari("[sigh]")


def test_converts_and_keeps_tags_and_spacing():
    llm = FakeLlm({"Maza nahi aaya!": "मज़ा नहीं आया!"})
    out = asyncio.run(to_devanagari(llm, "[sigh] Maza nahi aaya!"))
    assert out == "[sigh] मज़ा नहीं आया!"
    assert llm.calls == ["Maza nahi aaya!"]


def test_devanagari_text_is_not_sent_to_the_llm():
    llm = FakeLlm({})
    assert asyncio.run(to_devanagari(llm, "नमस्ते")) == "नमस्ते"
    assert llm.calls == []


def test_llm_failure_or_latin_reply_keeps_the_original():
    class Broken(FakeLlm):
        async def chat(self, *a, **k):
            raise RuntimeError("down")

    assert asyncio.run(to_devanagari(Broken({}), "Sorry Sir")) == "Sorry Sir"
    assert (
        asyncio.run(to_devanagari(FakeLlm({"Sorry Sir": "sorry sir"}), "Sorry Sir")) == "Sorry Sir"
    )
