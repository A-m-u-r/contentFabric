import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from saasshorts import (
    _AVATAR_MOTION_PROMPT,
    _avatar_clip_cache_valid,
    _broll_reference_image,
    _broll_slice_shot,
    _chunk_request_prompts,
    _ensure_slice_audio,
    _file_fingerprint,
    _mp3_encoder_delay,
    _parse_review_issues,
    _reel_layout,
    _room_tone_db,
    _self_voiced_clip,
    _shot_request_prompt,
    build_kling_v3_storyboard_request,
    composite_storyboard_video,
    generate_sliced_avatar_clips,
    generate_storyboard_chunk_clip,
    generate_storyboard_shot_clip,
    review_clip_quality,
)


class FreezeVsStretchTest(unittest.TestCase):
    """Short clips: b-roll gets a gentle slowdown, talking heads keep the freeze."""

    def _filter_for(self, shot, actual, slot, speech_offset=0.0):
        clip = {"path": "/tmp/a.mp4", "duration": slot, "shot": shot,
                "speech_offset": speech_offset}
        with patch("saasshorts.subprocess.run") as run_mock, \
             patch("saasshorts._get_media_duration", return_value=actual):
            composite_storyboard_video(
                [clip], "/tmp/voice.mp3", "/tmp/subs.ass", "/tmp/out.mp4",
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
        # Конец режется на полкадра раньше: `end` ровно по границе кадра
        # отдаёт кадр лишку (см. `_trim_end`).
        self.assertIn("trim=start=0:end=4.983", flt)
        self.assertNotIn("tpad", flt)


class LipSyncHeadSkipTest(unittest.TestCase):
    """Клип, снятый по mp3-слайсу, открывается тишиной энкодера — её срезаем.

    Иначе губы стоят на этой задержке позже мастер-озвучки: замер на джобе
    saas_b13f0229 дал +25 мс на каждом говорящем кадре.
    """

    def _filter_for(self, clip, actual):
        with patch("saasshorts.subprocess.run") as run_mock, \
             patch("saasshorts._get_media_duration", return_value=actual):
            composite_storyboard_video(
                [clip], "/tmp/voice.mp3", "/tmp/subs.ass", "/tmp/out.mp4",
            )
        cmd = run_mock.call_args[0][0]
        return cmd[cmd.index("-filter_complex") + 1]

    def test_talking_clip_starts_after_the_encoder_delay(self):
        flt = self._filter_for(
            {"path": "/tmp/a.mp4", "duration": 5.0, "shot": {"visual_type": "talking"},
             "speech_offset": 0.025},
            actual=5.5,
        )
        self.assertIn("trim=start=0.025:end=5.008", flt)
        self.assertNotIn("tpad", flt)

    def test_clip_without_offset_keeps_its_first_frame(self):
        flt = self._filter_for(
            {"path": "/tmp/a.mp4", "duration": 5.0, "shot": {"visual_type": "talking"}},
            actual=5.5,
        )
        self.assertIn("trim=start=0:end=4.983", flt)

    def test_head_skip_counts_against_the_usable_length(self):
        # 5.0s клип минус 0.2s головы не закрывает слот — добираем фризом,
        # а не сдвигом всех следующих кадров.
        flt = self._filter_for(
            {"path": "/tmp/a.mp4", "duration": 5.0, "shot": {"visual_type": "talking"},
             "speech_offset": 0.2},
            actual=5.0,
        )
        self.assertIn("trim=start=0.200:end=5.183", flt)
        self.assertIn("tpad=stop_mode=clone:stop_duration=0.200", flt)

    def test_offset_never_eats_the_whole_clip(self):
        flt = self._filter_for(
            {"path": "/tmp/a.mp4", "duration": 3.0, "shot": {"visual_type": "talking"},
             "speech_offset": 9.0},
            actual=3.0,
        )
        self.assertIn("trim=start=2.900:end=5.883", flt)


class Mp3EncoderDelayTest(unittest.TestCase):
    def test_delay_follows_the_slice_sample_rate(self):
        with patch("saasshorts.subprocess.run",
                   return_value=SimpleNamespace(stdout="48000\n", stderr="")):
            self.assertAlmostEqual(_mp3_encoder_delay("/tmp/slice_01.mp3"), 1105 / 48000, places=6)

    def test_unreadable_rate_falls_back_to_44_1k(self):
        with patch("saasshorts.subprocess.run",
                   return_value=SimpleNamespace(stdout="N/A\n", stderr="")):
            self.assertAlmostEqual(_mp3_encoder_delay("/tmp/slice_01.mp3"), 1105 / 44100, places=6)

    def test_pcm_slice_has_no_encoder_head(self):
        with patch("saasshorts.subprocess.run",
                   side_effect=AssertionError("ffprobe must not run for wav")):
            self.assertEqual(_mp3_encoder_delay("/tmp/slice_01.wav"), 0.0)


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

    def _draw(self, shot, actor_photo_path=""):
        """Run one b-roll frame against a fake fal, return (model, args)."""

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
                return FakeResp()

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "ref.png")
            with patch("saasshorts._fal_run", return_value={"images": [{"url": "https://fal.example/f.png"}]}) as fal_mock, \
                 patch("saasshorts._fal_upload_file", return_value="https://fal.example/actor.png"), \
                 patch("saasshorts.httpx.Client", FakeClient):
                result = _broll_reference_image(
                    shot, "key", out, log=lambda *_: None,
                    actor_photo_path=actor_photo_path,
                )
            self.assertEqual(result, out)
        return fal_mock.call_args[0][0], fal_mock.call_args[0][1]

    def test_broll_with_our_presenter_is_staged_from_the_actor_photo(self):
        """«Женский силуэт со спины» — это наша героиня, а не случайная женщина."""
        with tempfile.TemporaryDirectory() as tmp:
            photo = os.path.join(tmp, "actor.png")
            with open(photo, "wb") as f:
                f.write(b"actor")
            model, args = self._draw(
                {"generation_prompt": "a woman closes the fridge door, seen from behind",
                 "visual_type": "broll", "actor_in_frame": True},
                actor_photo_path=photo,
            )
        self.assertEqual(model, "fal-ai/flux-pro/kontext")
        self.assertEqual(args["image_url"], "https://fal.example/actor.png")
        self.assertIn("keep the exact same person", args["prompt"])
        self.assertIn("face stays out of frame", args["prompt"])
        self.assertIn("closes the fridge door", args["prompt"])

    def test_broll_lets_the_description_own_the_framing(self):
        """«Крупно руки» должно давать кисти, а не средний план со спины.

        Хвост промпта раньше диктовал композицию («этого человека видно со
        спины, через плечо»), был конкретнее описания и стоял позже — модель
        слушалась его. Лицо за кадром — требование, откуда снимать — нет.
        """
        with tempfile.TemporaryDirectory() as tmp:
            photo = os.path.join(tmp, "actor.png")
            with open(photo, "wb") as f:
                f.write(b"actor")
            _, args = self._draw(
                {"generation_prompt": "close up of her hands placing a berry on a plate",
                 "visual_type": "broll", "actor_in_frame": True},
                actor_photo_path=photo,
            )
        prompt = args["prompt"]
        # Описание идёт последним и приказом — ему и принадлежит композиция.
        self.assertTrue(prompt.rstrip().endswith("placing a berry on a plate."), prompt)
        self.assertIn("Recompose the shot as described", prompt)
        # Кроп по кистям разрешён наравне с видом со спины, а не вместо него.
        self.assertIn("tight crop on the hands and forearms", prompt)
        self.assertNotIn("this person seen from behind", prompt)

    def test_broll_without_the_flag_never_touches_the_actor_photo(self):
        with tempfile.TemporaryDirectory() as tmp:
            photo = os.path.join(tmp, "actor.png")
            with open(photo, "wb") as f:
                f.write(b"actor")
            model, args = self._draw(
                {"generation_prompt": "a fridge door closing", "visual_type": "broll"},
                actor_photo_path=photo,
            )
        self.assertEqual(model, "fal-ai/flux-2-pro")
        self.assertNotIn("image_url", args)
        self.assertIn("no people", args["prompt"])

    def test_presenter_broll_without_a_photo_falls_back_to_the_faceless_prompt(self):
        model, args = self._draw(
            {"generation_prompt": "a woman closes the fridge door",
             "visual_type": "broll", "actor_in_frame": True},
        )
        self.assertEqual(model, "fal-ai/flux-2-pro")
        self.assertIn("no people", args["prompt"])


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
        # Запреты живут в negative_prompt запроса, а не в описании кадра.
        self.assertNotIn("no burned-in text", prompt)
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


class PromptNegationsTest(unittest.TestCase):
    """«Не рисуй текст» в описании кадра — это заказ на текст.

    У Kling V3 и Veo есть настоящее поле negative_prompt, туда всё и уезжает;
    у аватарного эндпойнта такого поля нет вовсе, поэтому там запретов быть
    не должно вообще.
    """

    def test_our_own_prompt_recipe_describes_only_what_is_in_frame(self):
        prompt = _shot_request_prompt({
            "shot_number": 1, "start": 0, "end": 4,
            "scene": "hands pour coffee", "camera": "close-up",
        })
        for banned in ("no text", "no burned-in text", "no watermark", "no logos"):
            self.assertNotIn(banned, prompt.lower())

    def test_bans_live_in_the_negative_prompt_instead(self):
        _, payload = build_kling_v3_storyboard_request(
            [{"shot_number": 1, "start": 0, "end": 5, "generation_prompt": "a wooden table"}],
            tier="standard",
        )
        self.assertNotIn("no ", payload["prompt"].lower())
        for banned in ("burned-in text", "subtitles", "captions", "watermark", "logos"):
            self.assertIn(banned, payload["negative_prompt"])


class AvatarClipCacheValidTest(unittest.TestCase):
    """Клип живёт ровно до тех пор, пока жив кадр, с которого он снят."""

    def _reference(self, tmp, content=b"frame"):
        ref = os.path.join(tmp, "ref_01.png")
        with open(ref, "wb") as f:
            f.write(content)
        return ref

    def _clip(self, tmp, meta=None):
        clip = os.path.join(tmp, "job_avatar_01.mp4")
        with open(clip, "wb") as f:
            f.write(b"clip")
        if meta is not None:
            with open(clip.replace(".mp4", "_base_fal.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f)
        return clip

    def test_missing_file_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(
                _avatar_clip_cache_valid(os.path.join(tmp, "nope.mp4"), self._reference(tmp))
            )

    def test_clip_without_meta_stays_valid(self):
        # Историю не знаем — самый дорогой артефакт не переснимаем наугад.
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(_avatar_clip_cache_valid(self._clip(tmp), self._reference(tmp)))

    def test_same_reference_frame_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = self._reference(tmp)
            clip = self._clip(tmp, {"payload": {}, "reference_fingerprint": _file_fingerprint(ref)})
            self.assertTrue(_avatar_clip_cache_valid(clip, ref))

    def test_edited_scene_gives_a_new_frame_and_invalidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = self._reference(tmp)
            clip = self._clip(tmp, {"payload": {}, "reference_fingerprint": _file_fingerprint(ref)})
            with open(ref, "wb") as f:
                f.write(b"a different staging of the same actor")
            self.assertFalse(_avatar_clip_cache_valid(clip, ref))

    def test_clip_shot_with_the_current_motion_prompt_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = self._reference(tmp)
            clip = self._clip(tmp, {
                "payload": {"prompt": _AVATAR_MOTION_PROMPT},
                "reference_fingerprint": _file_fingerprint(ref),
            })
            self.assertTrue(_avatar_clip_cache_valid(clip, ref))

    def test_clip_shot_with_the_old_prompt_is_never_reused(self):
        # Старый промпт — источник кракозябр в кадре, такие дубли не тащим дальше.
        with tempfile.TemporaryDirectory() as tmp:
            ref = self._reference(tmp)
            clip = self._clip(tmp, {
                "payload": {"prompt": "Vertical 9:16 UGC ad, no burned-in text"},
                "reference_fingerprint": _file_fingerprint(ref),
            })
            self.assertFalse(_avatar_clip_cache_valid(clip, ref))


class SlicedAvatarCacheTest(unittest.TestCase):
    """Retry of a sliced-avatar job regenerates only what the user actually changed.

    Talking shots are keyed by their reference frame (the avatar request has no
    prompt), b-roll by its Kling prompt.
    """

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

    def _seed_cached_clips(self, tmp, talking_reference, broll_meta_prompt):
        talking_clip = os.path.join(tmp, "job_avatar_01.mp4")
        broll_clip = os.path.join(tmp, "job_avatar_broll_02.mp4")
        for clip in (talking_clip, broll_clip):
            with open(clip, "wb") as f:
                f.write(b"cached")
        with open(talking_clip.replace(".mp4", "_base_fal.json"), "w", encoding="utf-8") as f:
            json.dump({"payload": {}, "reference_fingerprint": talking_reference}, f)
        with open(f"{broll_clip}.meta.json", "w", encoding="utf-8") as f:
            json.dump({"payload": {"prompt": broll_meta_prompt}}, f)
        return talking_clip, broll_clip

    def test_unchanged_shots_reuse_both_cached_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = os.path.join(tmp, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"img")
            shots = self._shots(ref)
            self._seed_cached_clips(
                tmp,
                talking_reference=_file_fingerprint(ref),
                broll_meta_prompt=_shot_request_prompt(_broll_slice_shot(shots[1], 3.0)),
            )
            clips = self._run(
                tmp, shots,
                head_mock=AssertionError("avatar must stay cached"),
                v3_mock=AssertionError("broll must stay cached"),
            )
        self.assertEqual(len(clips), 2)

    def test_edited_shots_regenerate_both_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            ref = os.path.join(tmp, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"img")
            shots = self._shots(ref)
            self._seed_cached_clips(
                tmp,
                talking_reference="fingerprint of a frame that no longer exists",
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

    def test_clips_report_the_head_the_assembly_has_to_skip(self):
        def fake_clip(*args, **kwargs):
            output_path = args[3] if len(args) > 3 else args[2]
            with open(output_path, "wb") as f:
                f.write(b"clip")
            return output_path

        with tempfile.TemporaryDirectory() as tmp:
            ref = os.path.join(tmp, "ref.png")
            with open(ref, "wb") as f:
                f.write(b"img")
            with patch("saasshorts._mp3_encoder_delay", return_value=0.025):
                clips = self._run(tmp, self._shots(ref),
                                  head_mock=fake_clip, v3_mock=fake_clip)
        self.assertEqual([clip["speech_offset"] for clip in clips], [0.025, 0.0])

    def test_broll_audio_reslice_does_not_delete_reusable_video(self):
        """B-roll не липсинкается, поэтому смена его аудиограниц не портит видео."""
        with tempfile.TemporaryDirectory() as tmp:
            audio_slice = os.path.join(tmp, "slice.mp3")
            clip = os.path.join(tmp, "broll.mp4")
            identity = f"{audio_slice}.id.txt"
            for path, data in (
                (audio_slice, b"old-audio"),
                (clip, b"paid-video"),
                (f"{clip}.meta.json", b"{}"),
            ):
                with open(path, "wb") as f:
                    f.write(data)
            with open(identity, "w", encoding="utf-8") as f:
                f.write("old")

            def fake_slice(source, start, end, output):
                with open(output, "wb") as f:
                    f.write(b"new-audio")
                return output

            with patch("saasshorts._get_media_duration", return_value=1.0), \
                 patch("saasshorts._slice_voiceover_segment", side_effect=fake_slice):
                _ensure_slice_audio(
                    os.path.join(tmp, "voice.mp3"),
                    0.0,
                    1.2,
                    audio_slice,
                    clip,
                    identity="new",
                    invalidate_video=False,
                    log=lambda *_: None,
                )

            self.assertTrue(os.path.exists(clip))
            self.assertTrue(os.path.exists(f"{clip}.meta.json"))


class ApprovedFrameReuseTest(unittest.TestCase):
    """Кадр, одобренный в предпросмотре, платный рендер не перерисовывает.

    Предпросмотр и рендер — разные джобы, а кадр кэшируется по промпту внутри
    папки своего джоба. Пока рендер не умел смотреть в чужую папку, он покупал
    заново ровно ту картинку, которую пользователь только что посмотрел и
    утвердил, — и получал другой сэмпл вместо одобренного.
    """

    @staticmethod
    def _fake_slice(audio_path, start, end, output_path):
        with open(output_path, "wb") as f:
            f.write(b"slice")
        return output_path

    @staticmethod
    def _fake_clip(*args, **kwargs):
        output_path = args[3] if len(args) > 3 else args[2]
        with open(output_path, "wb") as f:
            f.write(b"clip")
        return output_path

    def test_broll_takes_the_frame_approved_in_the_preview_job(self):
        seen = {}

        def fake_v3(shot, fal_key, output_path, tier="standard", **kwargs):
            seen["image_path"] = shot.get("image_path")
            return self._fake_clip(shot, fal_key, output_path)

        with tempfile.TemporaryDirectory() as root:
            preview = os.path.join(root, "saas_preview")
            render = os.path.join(root, "saas_render")
            os.makedirs(preview)
            os.makedirs(render)
            with open(os.path.join(preview, "job_frame_02.png"), "wb") as f:
                f.write(b"approved-frame")
            talking_ref = os.path.join(render, "ref.png")
            with open(talking_ref, "wb") as f:
                f.write(b"img")
            shots = [
                {"shot_number": 1, "start": 0, "end": 3, "visual_type": "talking",
                 "speech": "Первая фраза кадра.", "image_path": talking_ref,
                 "generation_prompt": "creator at a desk"},
                # Кадр лежит в папке джоба предпросмотра — так его и отдаёт фронт.
                {"shot_number": 2, "start": 3, "end": 6, "visual_type": "broll",
                 "speech": "Вторая фраза кадра.", "generation_prompt": "coffee cup close-up",
                 "local_url": "/videos/saas_preview/job_frame_02.png"},
            ]
            with patch("saasshorts._get_media_duration", return_value=6.0), \
                 patch("saasshorts._slice_voiceover_segment", side_effect=self._fake_slice), \
                 patch("saasshorts.generate_talking_head", side_effect=self._fake_clip), \
                 patch("saasshorts.generate_storyboard_shot_clip", side_effect=fake_v3), \
                 patch("saasshorts._broll_reference_image",
                       side_effect=AssertionError("одобренный кадр перерисовывать нельзя")):
                generate_sliced_avatar_clips(
                    shots, os.path.join(render, "voice.mp3"), [], "key", render, "job",
                    broll_image_first=True, log=lambda *_: None,
                )

        self.assertEqual(
            seen["image_path"],
            os.path.normpath(os.path.join(root, "saas_preview", "job_frame_02.png")),
        )

    def test_broll_without_an_approved_frame_still_draws_one(self):
        drawn = {"calls": 0}

        def fake_reference(shot, fal_key, output_path, **kwargs):
            drawn["calls"] += 1
            with open(output_path, "wb") as f:
                f.write(b"fresh-frame")
            return output_path

        with tempfile.TemporaryDirectory() as root:
            render = os.path.join(root, "saas_render")
            os.makedirs(render)
            talking_ref = os.path.join(render, "ref.png")
            with open(talking_ref, "wb") as f:
                f.write(b"img")
            shots = [
                {"shot_number": 1, "start": 0, "end": 3, "visual_type": "talking",
                 "speech": "Первая фраза кадра.", "image_path": talking_ref,
                 "generation_prompt": "creator at a desk"},
                {"shot_number": 2, "start": 3, "end": 6, "visual_type": "broll",
                 "speech": "Вторая фраза кадра.", "generation_prompt": "coffee cup close-up"},
            ]
            with patch("saasshorts._get_media_duration", return_value=6.0), \
                 patch("saasshorts._slice_voiceover_segment", side_effect=self._fake_slice), \
                 patch("saasshorts.generate_talking_head", side_effect=self._fake_clip), \
                 patch("saasshorts.generate_storyboard_shot_clip", side_effect=self._fake_clip), \
                 patch("saasshorts._broll_reference_image", side_effect=fake_reference):
                generate_sliced_avatar_clips(
                    shots, os.path.join(render, "voice.mp3"), [], "key", render, "job",
                    broll_image_first=True, log=lambda *_: None,
                )

        self.assertEqual(drawn["calls"], 1)


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


class TakeAsDeliveredTest(unittest.TestCase):
    """Дубль звучит своим звуком под своей картинкой, но ровно по своим словам.

    Юзер сравнил присланные модели mp4 с роликом и сказал прямо: присланные в
    порядке, ролик — нет (2026-07-31). Свой звук вернул липсинк; а вот картинку
    сверх слов оставлять нельзя. Модель округляет длину вверх (блок в 8 кадров,
    пол 64 кадра), под этим хвостом звучать нечему, и дописанная тишина падает
    в середину фразы: замер на variant_H — до 215 мс дыры там, где дубль
    обрывался на -10 dB, то есть прямо на слове.
    """

    HEAD = 1105 / 44100.0

    def _talking(self, slot=1.72):
        return {"path": "/tmp/take.mp4", "duration": slot, "audio_slice": "/tmp/slice.mp3",
                "speech_offset": self.HEAD, "shot": {"visual_type": "talking"}}

    def _broll(self, slot=2.0):
        return {"path": "/tmp/broll.mp4", "duration": slot,
                "shot": {"visual_type": "broll"}}

    def _filter_for(self, clips, actual=2.133):
        with tempfile.TemporaryDirectory() as tmp:
            subs = os.path.join(tmp, "subs.ass")
            with open(subs, "w", encoding="utf-8") as f:
                f.write("[Events]\nDialogue: 0,0:00:00.00,0:00:00.50,Subtitle,,0,0,0,,ХЭЙ\n")
            with patch("saasshorts.subprocess.run") as run_mock, \
                 patch("saasshorts._get_media_duration", return_value=actual), \
                 patch("saasshorts._take_level_match_db", return_value=0.0), \
                 patch("saasshorts._get_media_stream_duration", return_value=1.765):
                composite_storyboard_video(clips, "/tmp/voice.mp3", subs, "/tmp/out.mp4")
        cmd = run_mock.call_args[0][0]
        return cmd[cmd.index("-filter_complex") + 1]

    def test_take_is_cut_around_its_words_on_both_streams(self):
        flt = self._filter_for([self._talking()])
        # Picture and sound are cut at the same two points — the head of silence
        # the driving mp3 carried, and the end of the words — so the model's own
        # lip sync survives untouched while the sentence keeps running.
        self.assertIn("[0:v]trim=start=0.025:end=1.742", flt)
        self.assertIn("[0:a]aresample=48000", flt)
        self.assertIn("atrim=start=0.025:end=1.758", flt)
        self.assertNotIn("tpad", flt)

    def test_take_is_level_matched_and_faded_into_the_seam(self):
        clips = [self._talking()]
        with tempfile.TemporaryDirectory() as tmp:
            subs = os.path.join(tmp, "subs.ass")
            with open(subs, "w", encoding="utf-8") as f:
                f.write("[Events]\n")
            with patch("saasshorts.subprocess.run") as run_mock, \
                 patch("saasshorts._get_media_duration", return_value=2.133), \
                 patch("saasshorts._take_level_match_db", return_value=2.4), \
                 patch("saasshorts._get_media_stream_duration", return_value=1.765):
                composite_storyboard_video(clips, "/tmp/voice.mp3", subs, "/tmp/out.mp4")
        cmd = run_mock.call_args[0][0]
        flt = cmd[cmd.index("-filter_complex") + 1]
        self.assertIn("volume=2.40dB", flt)
        # Скругление стыка, а не пауза: 10 мс снимают щелчок между двумя
        # кодеками и не читаются как дырка в слове.
        self.assertIn("afade=t=in:st=0:d=0.01", flt)
        self.assertIn("afade=t=out:st=1.723:d=0.01", flt)

    def test_the_master_picks_the_sentence_up_where_the_take_dropped_it(self):
        flt = self._filter_for([self._talking(1.72), self._broll(2.0)])
        # Дубль отдаёт звук ровно до 1.733 в ролике — оттуда же мастер и
        # продолжает. Ничего между ними не вставлено: юзер услышал вставленную
        # тишину как «связь пропала на доли секунды» (2026-07-31).
        self.assertIn("atrim=end=1.733", flt)
        self.assertIn("atrim=start=1.733:end=3.733", flt)
        self.assertIn("concat=n=2:v=0:a=1[voicedry]", flt)

    def test_the_stitched_track_never_falls_into_absolute_silence(self):
        """Обрыв шума в ноль слышно как пропавшую связь, а не как паузу.

        Дубли приходят со своим шумом (-72.9...-83.4 dB на job saas_d6b674c6),
        мастер — со своим, а дописанная тишина и паузы озвучки это ровный ноль:
        замер на variant_H дал провалы до -240 dB длиной до 215 мс. Юзер: «как
        будто соединение с наушниками пропадает на доли секунды» (2026-07-31).
        """
        flt = self._filter_for([self._talking(1.72), self._broll(2.0)])
        self.assertIn("anoisesrc=color=pink", flt)
        # Длиной ровно в ролик: 1.7333 + 2.0.
        self.assertIn("duration=3.733", flt)
        # Тише самого тихого источника: -80 dB фона против -14.5 dB генератора.
        self.assertIn("volume=-65.5dB", flt)
        self.assertIn("[voicedry][roomtone]amix=inputs=2:duration=first:normalize=0"
                      "[voicecat]", flt)

    def test_room_tone_sits_just_under_the_noisiest_source(self):
        with patch("saasshorts._noise_floor_db", side_effect=[-78.4, -72.9, -83.4]):
            self.assertAlmostEqual(
                _room_tone_db(["/tmp/voice.mp3", "/tmp/a.mp4", "/tmp/b.mp4"]), -75.9)
        # Шумный дубль не тянет фон за собой на слышимый уровень.
        with patch("saasshorts._noise_floor_db", return_value=-40.0):
            self.assertAlmostEqual(_room_tone_db(["/tmp/voice.mp3"]), -66.0)

    def test_clip_without_its_own_audio_keeps_the_master_and_the_head_skip(self):
        """per_shot / multi_shot render mute clips — that path must not move."""
        flt = self._filter_for([
            {"path": "/tmp/a.mp4", "duration": 2.0, "speech_offset": 0.025,
             "shot": {"visual_type": "talking"}},
        ])
        self.assertIn("trim=start=0.025:end=2.008", flt)
        self.assertNotIn("voicecat", flt)

    def test_reel_time_stays_master_time(self):
        """Одна шкала на всех, иначе титры уезжают вслед за дублями.

        Границы кадров округляются от текущего времени мастера, а не
        накапливаются: сегмент всегда целое число кадров, а его начало в ролике
        не отходит от мастера дальше половины кадра.
        """
        clips = [self._talking(1.72), self._broll(2.0), self._talking(1.64),
                 self._broll(1.1), self._talking(2.58)]
        with patch("saasshorts._get_media_duration", return_value=2.667), \
             patch("saasshorts._get_media_stream_duration", return_value=2.624):
            layout = _reel_layout(clips)
        for segment in layout:
            self.assertAlmostEqual(segment["duration"] * 30, round(segment["duration"] * 30))
            self.assertLess(abs(segment["reel_start"] - segment["master_start"]), 1 / 60)
        self.assertAlmostEqual(layout[0]["duration"], 1.7333, places=3)
        self.assertAlmostEqual(layout[1]["reel_start"], 1.7333, places=3)
        self.assertAlmostEqual(sum(s["duration"] for s in layout),
                               layout[-1]["master_end"], delta=1 / 60)

    def test_a_take_gives_up_the_picture_it_has_no_sound_for(self):
        with patch("saasshorts._get_media_duration", return_value=2.133), \
             patch("saasshorts._get_media_stream_duration", return_value=1.765):
            layout = _reel_layout([self._talking(1.72), self._broll(2.0)])
        self.assertTrue(layout[0]["self_voiced"])
        self.assertFalse(layout[1]["self_voiced"])
        # Модель нарисовала 2.133с картинки под 1.765с звука — в монтаж идёт
        # 1.733с, ровно те кадры, под которыми звучат слова.
        self.assertAlmostEqual(layout[0]["head"], self.HEAD, places=3)
        self.assertAlmostEqual(layout[0]["duration"], 1.7333, places=3)
        self.assertLessEqual(layout[0]["head"] + layout[0]["duration"], 1.765)

    def test_a_take_without_a_readable_audio_stream_is_not_trusted(self):
        clip = self._talking()
        with patch("saasshorts._get_media_stream_duration", return_value=0.0):
            self.assertFalse(_self_voiced_clip(clip))


if __name__ == "__main__":
    unittest.main()
