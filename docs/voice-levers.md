# Voice levers: what we can control in the voiceover

Single reference for every control we have over how a line is spoken. Written 2026-11-04 from the installed mlx-audio source, the upstream OmniVoice docs and our own spikes. **Status** says whether a lever is documented, measured by us, or only a hypothesis. Update the Status column as we test.

Scope: OmniVoice (`mlx-community/OmniVoice-bfloat16`), the TTS model ReelForge uses for cloned and preset voices. Other models are out of scope for now (see "Models we looked at and set aside").

## 1. How emotion works here

OmniVoice has **no emotion input**. `<happy>`, `<sad>`, `<fear>` (and `<anger>`, proposed) are **ReelForge markup**. The pipeline translates an emotion into a bundle of the levers below. The mapping table in section 7 is the single place that defines the translation.

## 2. Lever A: inline tags in the text

Atomic tokens that produce a real vocalisation. They add length to the take, and the shot's frame count follows the take.

| Tag | Intended use | Status |
| --- | --- | --- |
| `[dissatisfaction-hnn]` | grumpy, annoyed | **Measured and approved by the owner** (adds about 1.6 s) |
| `[sigh]` | sad, tired | Measured (adds about 0.4 s) |
| `[laughter]` | happy | Documented, untested |
| `[surprise-ah]` `[surprise-oh]` `[surprise-wa]` `[surprise-yo]` | fear, shock | Documented, untested |
| `[question-en]` `[question-ah]` `[question-oh]` `[question-ei]` `[question-yi]` | questioning tone | Documented, untested |
| `[confirmation-en]` | agreement | Documented, untested |

Placement: prefix and mid-line both worked in the spike (`1_hnn_prefix`, `3_hnn_mid`). Text-only levers also exist (punctuation `?!`, repeated words such as "टेस्ट… टेस्ट…"): tried in `~/reelforge-spikes/uncle_emotion/`, verdict not recorded.

Not applicable to Hindi: CMU pronunciation entries (English) and pinyin tones (Chinese).

## 3. Lever B: voice style (`instruct`)

Comma-separated, case-insensitive, at most one value per category, any category may be omitted.

| Category | Allowed values |
| --- | --- |
| Pitch | `very low pitch`, `low pitch`, `moderate pitch`, `high pitch`, `very high pitch` |
| Age | `child`, `teenager`, `young adult`, `middle-aged`, `elderly` |
| Style | `whisper` (the only one) |
| Gender | `male`, `female` |
| English accent | american, british, australian, canadian, indian, chinese, korean, japanese, portuguese, russian (English text only) |
| Chinese dialect | Chinese text only |

Notes:
- Upstream does not say whether `instruct` works together with cloning. In our spike it ran without error and changed the waveform with the same length, but the audible effect is **unverified**. A crude pitch measurement even showed "low pitch" with a higher median pitch (183 Hz against 129 Hz for the base), likely measurement noise.
- The model may ignore attributes; upstream advises simplifying the string if the output does not match.
- Accents and dialects are irrelevant for Hindi.

## 4. Lever C: pace

| Lever | Meaning | Status |
| --- | --- | --- |
| `duration_s` | Fixed output length in seconds. The model fits the speech into it, so a shorter target gives faster speech. | Exists in the MLX build. Effect on naturalness untested. |
| `speed` | Upstream: above 1.0 faster, below 1.0 slower. | **Ignored in the MLX build.** It is not in `generate()`'s signature and disappears into `**kwargs`. Evidence: scene 3 take at speed 0.9 is 0.937 s against 0.934 s at 1.0. |

**Known defect:** ReelForge passes `speed` to OmniVoice (`adapters/tts_worker.py`), so the speed slider on the voice screen does nothing for it. Fix: convert speed to `duration_s` (estimated length divided by speed) in the worker.

Default length (when `duration_s` is not given) is estimated from the text only: `estimate_duration(text, "Nice to meet you.", 25)` times 1.15. It does not use the reference clip's real speaking rate.

## 5. Lever D: generation settings

Effect on delivery is **not documented**; each needs measuring.

| Parameter | Default | Documented effect |
| --- | --- | --- |
| `guidance_scale` | 2.0 | Classifier-free guidance strength |
| `class_temperature` | 0.0 | Token sampling; 0 greedy, higher more random |
| `position_temperature` | 5.0 | Mask-position selection; 0 greedy, higher more random |
| `t_shift` | 0.1 | Noise schedule; smaller emphasises early steps |
| `layer_penalty_factor` | 5.0 | Penalises deeper codebook layers so lower layers unmask first |
| `num_steps` | 32 | Quality against speed; 16 is faster |
| `ref_audio_max_duration_s` | 10.0 | Reference clip limit |

Upstream also lists `denoise`, `preprocess_prompt` and `postprocess_output` (silence removal). They are not in the MLX `generate()` signature.

## 6. Lever E: things we add outside the model

ffmpeg-full 9.0.2 (arm64) has `rubberband` (pitch shift and time-stretch), `atempo`, `asetrate` and volume filters.

| Lever | Use | Caveat |
| --- | --- | --- |
| Pitch shift in semitones | higher for happy or fear, lower for sad | Beyond about 2 to 3 semitones it sounds artificial (to be confirmed by ear) |
| Tempo change | faster or slower delivery | Applies to the whole phrase |
| Gain in dB | louder anger, quieter sad | |
| Silence between phrases | pauses, hesitations | |
| Phrase splitting | approximates per-word control: split a line, synthesise each phrase separately, join | Seams may sound different; each phrase is a separate model call (about 1 s each) |

## 7. Lever F: the reference clip

For cloning, the reference clip's delivery strongly shapes the output. One reference per emotion for the same voice (a happy, a sad and a fearful clip) may be the strongest lever of all. **Hypothesis, untested; decided to be built in the emotion and age milestone (M6b, R12).** Emotional takes made with the levers above can themselves serve as references.

## 8. Not available

No direct emotion control, no pitch in Hz, no per-word control, no control over the intonation contour, no energy control.

## 9. Emotion mapping (draft, hypothesis)

To be replaced by measured values after the sweep. One row per emotion; the pipeline reads this table (later, a config file).

| Emotion | Tag | Pitch (`instruct`) | Duration scale | Post (semitones, gain) | Status |
| --- | --- | --- | --- | --- | --- |
| `<happy>` | `[laughter]` optional | high | x0.90 | +2 st | Hypothesis |
| `<sad>` | `[sigh]` | low | x1.25 | -2 st, -3 dB | Hypothesis |
| `<fear>` | `[surprise-ah]` | high or whisper | x0.85 | +1 st, pauses | Hypothesis |
| `<anger>` (confirmed by the owner) | `[dissatisfaction-hnn]` | low | x0.95 | +2 dB | Hypothesis; the tag part is approved |

## 10. Age factor

**Goal:** each character has an age in years (a number, decided by the owner), defined when the character is created, and the band derived from it is used when its voice is created.

Today a character has only `name`, `look` and `voice` (`story/schema.py`); age exists only as free text inside `look` ("late 60s", "about 7 years old").

| Years | Band (OmniVoice `instruct` age) |
| --- | --- |
| 0 to 12 | child |
| 13 to 19 | teenager |
| 20 to 39 | young adult |
| 40 to 59 | middle-aged |
| 60 and over | elderly |

How each voice model uses the age:

| Model | How age applies | Status |
| --- | --- | --- |
| OmniVoice, preset or designed voice | `instruct` age band | Documented |
| OmniVoice, cloned voice | The reference clip normally decides the voice character; age may be ignored or may shift it. Test before relying on it. | **Unknown** |
| Kokoro (fallback) | No age control. Approximate with the choice of preset voice and a small pitch and tempo shift in post. | Hypothesis |

## 11. Experiment log

| Date | Experiment | Result |
| --- | --- | --- |
| earlier | `~/reelforge-spikes/uncle_emotion/`: punctuation, elongation, faster, hotter sampling, stronger guidance | Verdict not recorded |
| 2026-11-04 | `~/reelforge-spikes/uncle_emotion_tags/`: tags and `instruct` on the cloned uncle, scene 1 line | Tags sound right to the owner. `instruct` effect unclear. |

Planned: a parameter sweep with the cloned uncle voice, varying one lever at a time and measuring duration, median pitch, pitch spread, loudness and brightness; then listening tests per emotion.

### How to run the sweep

Reference Mac only (real model). Run the script inside the mlx-audio environment, from the repo root:

```
<mlx_audio_path>/.venv/bin/python tools/voice_sweep.py --ref PATH --ref-text TEXT --out sweep.md
```

`--ref` is the cloned uncle's reference clip, `--ref-text` the words spoken in it, `--out` the Markdown table (it is also printed). Add `--model ID` to try another model id. The script changes one lever at a time (a no-lever baseline, `duration_s`, each `instruct` value, `guidance_scale`, `class_temperature`, `position_temperature`, `t_shift`, `num_steps`, each nonverbal tag) and measures duration, median pitch, pitch spread, loudness and brightness. Paste the results into the Status column and the experiment log, then edit `emotions.toml` only.

## 12. Models we looked at and set aside

Chatterbox Multilingual V3 (MIT, Hindi, cloning, `exaggeration` dial) is the only alternative worth a listening test if OmniVoice falls short. Indic Parler-TTS has the richest text-described emotion, speed and pitch but no voice cloning. svara-TTS (3B, licence not stated) and Qwen3-TTS (no Hindi, emotion and cloning mutually exclusive) are ruled out.

## Sources

- OmniVoice README: https://github.com/k2-fsa/OmniVoice
- Voice design reference: https://raw.githubusercontent.com/k2-fsa/OmniVoice/main/docs/voice-design.md
- Generation parameters: https://raw.githubusercontent.com/k2-fsa/OmniVoice/main/docs/generation-parameters.md
- Installed source: `~/tools/mlx-audio-env/.venv/lib/python3.12/site-packages/mlx_audio/tts/models/omnivoice/omnivoice.py`
- Chatterbox: https://huggingface.co/ResembleAI/chatterbox
- Indic Parler-TTS: https://huggingface.co/ai4bharat/indic-parler-tts
