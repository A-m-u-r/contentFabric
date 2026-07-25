import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from saasshorts import (
    _avatar_clip_cache_valid,
    _avatar_request_prompt,
    _avatar_scene_parts_prompt,
    _avatar_scene_prompt,
    _broll_reference_image,
    _broll_slice_shot,
    _chunk_request_prompts,
    _parse_review_issues,
    _shot_request_prompt,
    composite_storyboard_video,
    generate_sliced_avatar_clips,
    generate_storyboard_chunk_clip,
    generate_storyboard_shot_clip,
    review_clip_quality,
)


class FreezeVsStretchTest(unittest.TestCase):
    """Short clips: b-roll gets a gentle slowdown, talking heads keep the freeze."""

    def _filter_for(self, shot, actual, slot):
        with patch("saasshorts.subprocess.run") as run_mock, \
             patch("saasshorts._get_media_duration", return_value=actual):
            composite_storyboard_video(
                [{"path": "/tmp/a.mp4", "duration": slot, "shot": shot}],
                "/tmp/voice.mp3", "/tmp/subs.ass", "/tmp/out.mp4",
            )
        cmd = run_mock.call_args[0][0]
        return cmd[cmd.index("-filter_complex") + 1]

    def test_short_broll_is_stretched_not_frozen(self):
        flt = self._filter_for({"visual_type": "broll"}, actual=4.5, slot=5.0)
        self.assertIn("setpts=1.111111*PTS", flt)
        self.assertNotIn("tpad", flt)

    def test_short_talking_shot_keeps_freeze(self):
        flt = self._filter_for({"visual_type": "talking"}, actual=4.5, slot=5.0)
        self.assertIn("tpad=stop_mode=clone", flt)
        self.assertNotIn("*PTS", flt)

    def test_very_short_broll_falls_back_to_freeze(self):
        # 30% deficit: stretching would look like slow motion — freeze instead.
        flt = self._filter_for({"visual_type": "broll"}, actual=3.5, slot=5.0)
        self.assertIn("tpad=stop_mode=clone", flt)

    def test_surplus_clip_still_trimmed(self):
        flt = self._filter_for({"visual_type": "broll"}, actual=5.5, slot=5.0)
        self.assertIn("trim=start=0:end=5.000", flt)
        self.assertNotIn("tpad", flt)


class ParseReviewIssuesTest(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(_parse_review_issues('{"issues": ["чужой человек в кадре"]}'),
                         ["чужой человек в кадре"])

    def test_json_wrapped_in_prose_and_fences(self):
        text = 'Вот результат:\n```json\n{"issues": ["мусорный текст на планшете"]}\n```'
        self.assertEqual(_parse_review_issues(text), ["мусорный текст на планшете"])

    def test_garbage_returns_empty(self):
        self.assertEqual(_parse_review_issues("no json here"), [])
        self.assertEqual(_parse_review_issues('{"issues": "не список"}'), [])

    def test_empty_issues(self):
        self.assertEqual(_parse_review_issues('{"issues": []}'), [])


class ReviewClipQualityTest(unittest.TestCase):
    def test_cached_review_skips_ffmpeg_and_gemini(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = os.path.join(tmp, "clip.mp4")
            with open(f"{clip}.review.json", "w", encoding="utf-8") as f:
                json.dump({"issues": ["кэшированная проблема"]}, f)
            with patch("saasshorts.subprocess.run", side_effect=AssertionError("must not run ffmpeg")):
                issues = review_clip_quality(clip, {"visual_type": "broll"}, "fake-key")
        self.assertEqual(issues, ["кэшированная проблема"])


class ReviewGridAndPromptTest(unittest.TestCase):
    """Ложные срабатывания QC: полкадра разрешения + придирки к предметам."""

    def _review(self):
        captured = {}
        with tempfile.TemporaryDirectory() as tmp:
            clip = os.path.join(tmp, "clip.mp4")
            open(clip, "wb").close()

            def fake_ffmpeg(cmd, **kwargs):
                with open(f"{clip}.review.jpg", "wb") as f:
                    f.write(b"fake-jpeg")
                captured["cmd"] = cmd
                return None

            class FakeModels:
                def generate_content(self, model, contents):
                    captured["prompt"] = contents[-1]
                    return SimpleNamespace(text='{"issues": []}')

            class FakeClient:
                def __init__(self, api_key=None):
                    self.models = FakeModels()

            with patch("saasshorts.subprocess.run", side_effect=fake_ffmpeg), \
                 patch("saasshorts._get_media_duration", return_value=4.0), \
                 patch("google.genai.Client", FakeClient):
                captured["issues"] = review_clip_quality(
                    clip, {"visual_type": "broll"}, "key", log=lambda *_: None
                )
        return captured

    def test_grid_is_compressed_but_not_halved(self):
        captured = self._review()
        self.assertEqual(captured["issues"], [])
        # Раньше было scale=360:-2 — вдвое меньше 720px-клипа Kling, и Gemini
        # судил геометрию пальцев и зубцов вилки по мылу. Полное разрешение
        # слать тоже не нужно: токены картинки считаются по ~768px-тайлам.
        self.assertIn("scale='min(iw,540)'", " ".join(captured["cmd"]))
        self.assertNotIn("scale=360", " ".join(captured["cmd"]))

    def test_prompt_excludes_props_and_freeze_frame_artifacts(self):
        prompt = self._review()["prompt"]
        self.assertIn("cutlery", prompt)
        self.assertIn("freeze-frames", prompt)
        self.assertIn("zoom in", prompt)
        # Люди в b-roll и псевдотекст по-прежнему ловим.
        self.assertIn("no people", prompt)
        self.assertIn("pseudo-text", prompt)


class BrollReferenceImageTest(unittest.TestCase):
    def test_fal_failure_falls_back_to_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "ref.png")
            with patch("saasshorts._fal_run", side_effect=RuntimeError("boom")):
                result = _broll_reference_image({"generation_prompt": "coffee cup"}, "key", out,
                                                log=lambda *_: None)
        self.assertEqual(result, "")

    def test_success_downloads_flux_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "ref.png")

            class FakeResp:
                content = b"png-bytes"
                def raise_for_status(self):
                    return None

            class FakeClient:
                def __init__(self, *a, **k):
                    pass
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
                def get(self, url):
                    assert url == "https://fal.example/frame.png"
                    return FakeResp()

            with patch("saasshorts._fal_run", return_value={"images": [{"url": "https://fal.example/frame.png"}]}) as fal_mock, \
                 patch("saasshorts.httpx.Client", FakeClient):
                result = _broll_reference_image(
                    {"generation_prompt": "coffee cup on wooden table"}, "key", out,
                    log=lambda *_: None,
                )
            self.assertEqual(result, out)
            with open(out, "rb") as f:
                self.assertEqual(f.read(), b"png-bytes")
            prompt = fal_mock.call_args[0][1]["prompt"]
            self.assertIn("coffee cup on wooden table", prompt)
            self.assertIn("no people", prompt)
            self.assertEqual(fal_mock.call_args[0][0], "fal-ai/flux-2-pro")

    def test_existing_reference_reused_without_fal_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "ref.png")
            with open(out, "wb") as f:
                f.write(b"cached")
            with patch("saasshorts._fal_run", side_effect=AssertionError("must not call fal")):
                result = _broll_reference_image({"generation_prompt": "x"}, "key", out,
                                                log=lambda *_: None)
        self.assertEqual(result, out)


class ClipCacheInvalidationTest(unittest.TestCase):
    """Editing a shot's Kling prompt must invalidate the cached clip on retry."""

    def _make_cached_clip(self, tmp, prompt):
        clip = os.path.join(tmp, "shot_01.mp4")
        with open(clip, "wb") as f:
            f.write(b"cached-clip")
        with open(f"{clip}.meta.json", "w", encoding="utf-8") as f:
            json.dump({"payload": {"prompt": prompt}}, f)
        with open(f"{clip}.review.json", "w", encoding="utf-8") as f:
            json.dump({"issues": []}, f)
        return clip

    def _shot(self, prompt):
        return {"shot_number": 1, "duration": 5, "scene": "kitchen", "speech": "hi", "generation_prompt": prompt}

    def test_cache_reused_when_prompt_unchanged(self):
        from saasshorts import _shot_request_prompt
        with tempfile.TemporaryDirectory() as tmp:
            # Meta stores the request prompt (normalized form), as real jobs do.
            cached_prompt = _shot_request_prompt(self._shot("coffee cup close-up"))
            clip = self._make_cached_clip(tmp, cached_prompt)
            with patch("saasshorts._fal_run", side_effect=AssertionError("must not call fal")):
                result = generate_storyboard_shot_clip(self._shot("coffee cup close-up"), "key", clip)
            self.assertEqual(result, clip)
            self.assertTrue(os.path.exists(f"{clip}.review.json"))

    def test_user_prompt_respected_with_guardrails_appended(self):
        from saasshorts import _shot_request_prompt
        prompt = _shot_request_prompt(self._shot("крупный план кофейной чашки на столе"))
        self.assertIn("крупный план кофейной чашки", prompt)
        self.assertIn("vertical 9:16", prompt)
        self.assertIn("no burned-in text", prompt)
        # Идемпотентность: повторная нормализация не должна менять промпт,
        # иначе кэш клипов вечно считал бы его «изменённым».
        reshot = self._shot("x")
        reshot["generation_prompt"] = prompt
        self.assertEqual(_shot_request_prompt(reshot), prompt)

    def test_cache_invalidated_when_prompt_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = self._make_cached_clip(tmp, "old prompt")
            with patch("saasshorts._fal_run", side_effect=RuntimeError("fal-called")):
                with self.assertRaisesRegex(RuntimeError, "fal-called"):
                    generate_storyboard_shot_clip(self._shot("new edited prompt"), "key", clip)
            # Stale artifacts are gone so the retry regenerates from scratch.
            self.assertFalse(os.path.exists(clip))
            self.assertFalse(os.path.exists(f"{clip}.review.json"))
            self.assertFalse(os.path.exists(f"{clip}.meta.json"))

    def test_legacy_clip_without_meta_is_kept(self):
        # Old jobs predate meta.json: never surprise the user with a paid regen.
        with tempfile.TemporaryDirectory() as tmp:
            clip = os.path.join(tmp, "shot_01.mp4")
            with open(clip, "wb") as f:
                f.write(b"legacy")
            with patch("saasshorts._fal_run", side_effect=AssertionError("must not call fal")):
                result = generate_storyboard_shot_clip(self._shot("any prompt"), "key", clip)
            self.assertEqual(result, clip)

    def test_broll_reference_regenerated_when_prompt_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = os.path.join(tmp, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"old-frame")
            with open(f"{ref}.prompt.txt", "w", encoding="utf-8") as f:
                f.write("stale prompt text")
            with patch("saasshorts._fal_run", side_effect=RuntimeError("flux-called")) as fal_mock:
                result = _broll_reference_image({"generation_prompt": "brand new scene"}, "key", ref,
                                                log=lambda *_: None)
            fal_mock.assert_called_once()
            self.assertEqual(result, "")  # failure path: fell back, stale file removed
            self.assertFalse(os.path.exists(ref))


class AvatarPromptTest(unittest.TestCase):
    """The UI's editable «Kling prompt» must drive talking shots too."""

    def test_generation_prompt_drives_avatar_framing(self):
        shot = {
            "scene": "kitchen counter",
            "camera": "close-up",
            "generation_prompt": "woman at a sunset window, vertical 9:16",
        }
        prompt = _avatar_scene_prompt(shot)
        self.assertIn("woman at a sunset window", prompt)
        self.assertIn("no readable on-screen text", prompt)
        self.assertNotIn("kitchen counter", prompt)

    def test_scene_fields_fallback_without_prompt(self):
        prompt = _avatar_scene_prompt({"scene": "kitchen counter", "camera": "close-up"})
        self.assertIn("kitchen counter", prompt)
        self.assertIn("close-up", prompt)

    def test_bare_shot_keeps_empty_contract(self):
        self.assertEqual(_avatar_scene_prompt({"speech": "только текст"}), "")


class AvatarClipCacheValidTest(unittest.TestCase):
    shot = {"scene": "kitchen", "camera": "close-up", "generation_prompt": "sunset window"}

    def _clip(self, tmp, stored_prompt=None):
        clip = os.path.join(tmp, "job_avatar_01.mp4")
        with open(clip, "wb") as f:
            f.write(b"clip")
        if stored_prompt is not None:
            with open(clip.replace(".mp4", "_base_fal.json"), "w", encoding="utf-8") as f:
                json.dump({"payload": {"prompt": stored_prompt}}, f)
        return clip

    def test_missing_file_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(_avatar_clip_cache_valid(os.path.join(tmp, "nope.mp4"), self.shot))

    def test_clip_without_meta_stays_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(_avatar_clip_cache_valid(self._clip(tmp), self.shot))

    def test_current_prompt_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            stored = _avatar_request_prompt(_avatar_scene_prompt(self.shot))
            self.assertTrue(_avatar_clip_cache_valid(self._clip(tmp, stored), self.shot))

    def test_legacy_scene_recipe_stays_valid(self):
        # Clips generated before the generation_prompt switch must not be
        # surprise-regenerated: an avatar clip is the priciest artifact.
        with tempfile.TemporaryDirectory() as tmp:
            stored = _avatar_request_prompt(_avatar_scene_parts_prompt(self.shot))
            self.assertTrue(_avatar_clip_cache_valid(self._clip(tmp, stored), self.shot))

    def test_edited_prompt_invalidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            stored = _avatar_request_prompt("a completely different framing")
            self.assertFalse(_avatar_clip_cache_valid(self._clip(tmp, stored), self.shot))


class SlicedAvatarCacheTest(unittest.TestCase):
    """Retry of a sliced-avatar job regenerates only the prompt-edited shots."""

    TALKING_PROMPT = "creator at a desk, vertical 9:16, no burned-in text, no watermark"
    BROLL_PROMPT = "coffee cup close-up, vertical 9:16, no burned-in text, no watermark"

    def _shots(self, ref):
        return [
            {"shot_number": 1, "start": 0, "end": 3, "visual_type": "talking",
             "speech": "Первая фраза кадра.", "scene": "close-up", "image_path": ref,
             "generation_prompt": self.TALKING_PROMPT},
            {"shot_number": 2, "start": 3, "end": 6, "visual_type": "broll",
             "speech": "Вторая фраза кадра.",
             "generation_prompt": self.BROLL_PROMPT},
        ]

    @staticmethod
    def _fake_slice(audio_path, start, end, output_path):
        with open(output_path, "wb") as f:
            f.write(b"slice")
        return output_path

    def _run(self, tmp, shots, head_mock, v3_mock):
        with patch("saasshorts._get_media_duration", return_value=6.0), \
             patch("saasshorts._slice_voiceover_segment", side_effect=self._fake_slice), \
             patch("saasshorts.generate_talking_head", side_effect=head_mock), \
             patch("saasshorts.generate_storyboard_shot_clip", side_effect=v3_mock), \
             patch("saasshorts.generate_actor_image", side_effect=AssertionError("no actor gen")):
            return generate_sliced_avatar_clips(
                shots, os.path.join(tmp, "voice.mp3"), [], "key", tmp, "job",
                broll_image_first=False, log=lambda *_: None,
            )

    def _seed_cached_clips(self, tmp, shots, talking_meta_prompt, broll_meta_prompt):
        talking_clip = os.path.join(tmp, "job_avatar_01.mp4")
        broll_clip = os.path.join(tmp, "job_avatar_broll_02.mp4")
        for clip in (talking_clip, broll_clip):
            with open(clip, "wb") as f:
                f.write(b"cached")
        with open(talking_clip.replace(".mp4", "_base_fal.json"), "w", encoding="utf-8") as f:
            json.dump({"payload": {"prompt": talking_meta_prompt}}, f)
        with open(f"{broll_clip}.meta.json", "w", encoding="utf-8") as f:
            json.dump({"payload": {"prompt": broll_meta_prompt}}, f)
        return talking_clip, broll_clip

    def test_unchanged_prompts_reuse_both_cached_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = os.path.join(tmp, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"img")
            shots = self._shots(ref)
            self._seed_cached_clips(
                tmp, shots,
                talking_meta_prompt=_avatar_request_prompt(_avatar_scene_prompt(shots[0])),
                broll_meta_prompt=_shot_request_prompt(_broll_slice_shot(shots[1], 3.0)),
            )
            clips = self._run(
                tmp, shots,
                head_mock=AssertionError("avatar must stay cached"),
                v3_mock=AssertionError("broll must stay cached"),
            )
        self.assertEqual(len(clips), 2)

    def test_edited_prompts_regenerate_both_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = os.path.join(tmp, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"img")
            shots = self._shots(ref)
            self._seed_cached_clips(
                tmp, shots,
                talking_meta_prompt=_avatar_request_prompt("stale avatar framing"),
                broll_meta_prompt="stale broll prompt",
            )
            calls = {"head": 0, "v3": 0}

            def fake_head(image_path, audio_path, fal_key, output_path, tier="standard", **kwargs):
                calls["head"] += 1
                with open(output_path, "wb") as f:
                    f.write(b"new-clip")
                return output_path

            def fake_v3(shot, fal_key, output_path, tier="standard", **kwargs):
                calls["v3"] += 1
                with open(output_path, "wb") as f:
                    f.write(b"new-clip")
                return output_path

            self._run(tmp, shots, head_mock=fake_head, v3_mock=fake_v3)
        self.assertEqual(calls, {"head": 1, "v3": 1})


class ChunkCacheInvalidationTest(unittest.TestCase):
    """Multi-shot chunks must also honor prompt edits on retry."""

    def _chunk_shots(self):
        return [
            {"shot_number": 1, "duration": 5, "scene": "kitchen", "speech": "hi",
             "generation_prompt": "cup close-up, vertical 9:16, no burned-in text, no watermark"},
            {"shot_number": 2, "duration": 5, "scene": "desk", "speech": "yo",
             "generation_prompt": "desk pan, vertical 9:16, no burned-in text, no watermark"},
        ]

    def _make_cached_chunk(self, tmp, prompts):
        clip = os.path.join(tmp, "chunk_01.mp4")
        with open(clip, "wb") as f:
            f.write(b"cached-chunk")
        with open(f"{clip}.meta.json", "w", encoding="utf-8") as f:
            json.dump({"payload": {"multi_prompt": [
                {"duration": "5", "prompt": prompt} for prompt in prompts
            ]}}, f)
        return clip

    def test_cache_reused_when_prompts_unchanged(self):
        shots = self._chunk_shots()
        with tempfile.TemporaryDirectory() as tmp:
            clip = self._make_cached_chunk(tmp, _chunk_request_prompts(shots))
            with patch("saasshorts._fal_run", side_effect=AssertionError("must not call fal")):
                result = generate_storyboard_chunk_clip(shots, "key", clip)
            self.assertEqual(result, clip)

    def test_cache_invalidated_when_prompt_changed(self):
        shots = self._chunk_shots()
        with tempfile.TemporaryDirectory() as tmp:
            clip = self._make_cached_chunk(tmp, ["old one", "old two"])
            with patch("saasshorts._fal_run", side_effect=RuntimeError("fal-called")):
                with self.assertRaisesRegex(RuntimeError, "fal-called"):
                    generate_storyboard_chunk_clip(shots, "key", clip)
            self.assertFalse(os.path.exists(clip))
            self.assertFalse(os.path.exists(f"{clip}.meta.json"))

    def test_legacy_chunk_without_meta_is_kept(self):
        shots = self._chunk_shots()
        with tempfile.TemporaryDirectory() as tmp:
            clip = os.path.join(tmp, "chunk_01.mp4")
            with open(clip, "wb") as f:
                f.write(b"legacy")
            with patch("saasshorts._fal_run", side_effect=AssertionError("must not call fal")):
                result = generate_storyboard_chunk_clip(shots, "key", clip)
            self.assertEqual(result, clip)


if __name__ == "__main__":
    unittest.main()
