import hashlib
import json

from reelforge.assembly.edl import Edl, EdlAudio, EdlShot, edl_hash, load_edl, save_edl


def _edl(**over):
    shots = [
        EdlShot(scene_id="s1", artifact="a", source_duration_s=2.0, in_s=0.0, out_s=2.0),
        EdlShot(
            scene_id="s2", artifact="b", source_duration_s=2.0, in_s=0.0, out_s=2.0,
            transition_in_s=0.5,
        ),
    ]  # fmt: skip
    return Edl(project_id="p", video=shots, dialogue=[], captions=[], **over)


def _cue():
    return EdlAudio(
        cue_id="c", kind="sfx", artifact="x", start_s=1.0, end_s=2.0, gain_db=-6.0,
        fade_in_s=0.0, fade_out_s=0.0, duck=False,
    )  # fmt: skip


def test_without_cues_hash_and_file_keep_their_old_shape(tmp_path):
    edl = _edl()
    old = {k: v for k, v in edl.model_dump(mode="json").items() if k not in ("audio", "mix")}
    canonical = json.dumps(old, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert edl_hash(edl) == hashlib.sha256(canonical.encode()).hexdigest()
    path = tmp_path / "edl.json"
    save_edl(edl, path)
    assert "audio" not in json.loads(path.read_text())
    assert load_edl(path) == edl


def test_with_cues_the_hash_changes_and_the_file_carries_them(tmp_path):
    plain, with_cue = _edl(), _edl(audio=[_cue()])
    assert edl_hash(plain) != edl_hash(with_cue)
    path = tmp_path / "edl.json"
    save_edl(with_cue, path)
    data = json.loads(path.read_text())
    assert data["audio"][0]["cue_id"] == "c" and data["mix"]["duck_db"] == 9.0
    assert load_edl(path) == with_cue


def test_a_transition_shifts_the_shot_start_the_cues_follow():
    # 0.5 s crossfade into s2: s2 starts at 2.0 - 0.5
    assert _edl().shot_start_s(1) == 1.5
