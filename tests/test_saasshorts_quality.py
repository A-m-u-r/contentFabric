import json
import os
import tempfile
import unittest
from unittest.mock import patch

from saasshorts import (
    _broll_reference_image,
    _parse_review_issues,
    composite_storyboard_video,
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


if __name__ == "__main__":
    unittest.main()
