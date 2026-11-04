from reelforge.assembly.publish import licence_warnings


def test_warning_rules_for_models_and_uploads():
    credits = [
        {"model": "a", "version": "1", "licence": "Apache-2.0"},
        {"cue_id": "m", "kind": "music", "model": "b", "version": "2", "licence": "CC-BY-NC-4.0"},
        {"cue_id": "e", "kind": "sfx", "model": "c", "version": "3", "licence": ""},
        {"cue_id": "f", "kind": "sfx", "file_name": "x.wav", "licence": ""},
        {"cue_id": "g", "kind": "sfx", "file_name": "y.wav", "licence": "mine, 2026"},
    ]
    got = licence_warnings(credits)
    assert [c["cue_id"] for c in got if "cue_id" in c] == ["m", "e", "f"]
    assert got[-1] == {"cue_id": "f", "kind": "sfx", "file_name": "x.wav", "licence": ""}
