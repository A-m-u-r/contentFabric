import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import saasshorts


class GeminiFalTextRouterTests(unittest.TestCase):
    def test_direct_success_never_calls_paid_fal_fallback(self):
        direct = SimpleNamespace(text='{"ok": true}')
        client = MagicMock()
        client.models.generate_content.return_value = direct

        with patch("saasshorts._fal_run") as fal_run:
            result = saasshorts._generate_analysis_content(
                client,
                contents=["prompt"],
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )

        self.assertIs(result, direct)
        fal_run.assert_not_called()

    def test_quota_exhaustion_uses_fal_gemini_pro(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError(
            "429 RESOURCE_EXHAUSTED"
        )
        fal_payload = {
            "output": '{"ok": true}',
            "usage": {"cost": 0.01},
            "_fal_request": {"request_id": "req-1"},
        }

        with patch.object(saasshorts, "GEMINI_MAX_RETRIES", 0), patch(
            "saasshorts._fal_run", return_value=fal_payload
        ) as fal_run:
            result = saasshorts._generate_analysis_content(
                client,
                contents=["original prompt"],
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )

        self.assertEqual(result.text, '{"ok": true}')
        self.assertTrue(result.paid_provider)
        self.assertEqual(fal_run.call_count, 1)
        self.assertEqual(fal_run.call_args.args[0], "openrouter/router")
        self.assertEqual(fal_run.call_args.args[1]["prompt"], "original prompt")
        self.assertEqual(
            fal_run.call_args.args[1]["model"],
            "google/gemini-3.1-pro-preview",
        )

    def test_quota_exhaustion_without_fal_key_explains_missing_fallback(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError(
            "429 RESOURCE_EXHAUSTED"
        )

        with patch.object(saasshorts, "GEMINI_MAX_RETRIES", 0):
            with self.assertRaisesRegex(
                saasshorts.GeminiTemporaryError,
                "fal.ai fallback key is missing",
            ):
                saasshorts._generate_analysis_content(
                    client,
                    contents=["prompt"],
                    text_model="pro",
                    fal_key=None,
                    fal_fallback_enabled=True,
                )

    def test_retryable_fal_pro_failure_uses_flash_once(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError(
            "503 UNAVAILABLE"
        )

        with patch.object(saasshorts, "GEMINI_MAX_RETRIES", 0), patch(
            "saasshorts._fal_run",
            side_effect=[
                RuntimeError("503 provider unavailable"),
                {"output": "flash result"},
            ],
        ) as fal_run:
            result = saasshorts._generate_analysis_content(
                client,
                contents=["prompt"],
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )

        self.assertEqual(result.text, "flash result")
        self.assertEqual(fal_run.call_count, 2)
        self.assertEqual(
            fal_run.call_args_list[1].args[1]["model"],
            "google/gemini-3-flash-preview",
        )

    def test_fal_request_translates_generation_config_and_web_search(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError(
            "429 RESOURCE_EXHAUSTED"
        )
        config = SimpleNamespace(max_output_tokens=4096, temperature=0.25)

        with patch.object(saasshorts, "GEMINI_MAX_RETRIES", 0), patch(
            "saasshorts._fal_run", return_value={"output": "research"}
        ) as fal_run:
            saasshorts._generate_analysis_content(
                client,
                contents=["research prompt"],
                config=config,
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
                fal_enable_web_search=True,
            )

        fal_input = fal_run.call_args.args[1]
        self.assertEqual(fal_input["max_tokens"], 4096)
        self.assertEqual(fal_input["temperature"], 0.25)
        self.assertIs(fal_input["enable_web_search"], True)

    def test_explicit_gemini_model_is_preserved_on_fal(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError(
            "429 RESOURCE_EXHAUSTED"
        )

        with patch.object(saasshorts, "GEMINI_MAX_RETRIES", 0), patch(
            "saasshorts._fal_run", return_value={"output": "ok"}
        ) as fal_run:
            saasshorts._generate_analysis_content(
                client,
                contents=["prompt"],
                text_model="gemini-2.5-pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )

        self.assertEqual(
            fal_run.call_args.args[1]["model"],
            "google/gemini-2.5-pro",
        )

    def test_nonretryable_google_error_never_calls_paid_fal(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError(
            "401 invalid Google API key"
        )

        with patch("saasshorts._fal_run") as fal_run:
            with self.assertRaisesRegex(RuntimeError, "invalid Google API key"):
                saasshorts._generate_analysis_content(
                    client,
                    contents=["prompt"],
                    text_model="pro",
                    fal_key="fal-key",
                    fal_fallback_enabled=True,
                )

        fal_run.assert_not_called()

    def test_fal_balance_error_does_not_start_flash(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError(
            "429 RESOURCE_EXHAUSTED"
        )

        with patch.object(saasshorts, "GEMINI_MAX_RETRIES", 0), patch(
            "saasshorts._fal_run",
            side_effect=RuntimeError("402 insufficient balance"),
        ) as fal_run:
            with self.assertRaisesRegex(
                saasshorts.GeminiTemporaryError,
                "insufficient balance",
            ):
                saasshorts._generate_analysis_content(
                    client,
                    contents=["prompt"],
                    text_model="pro",
                    fal_key="fal-key",
                    fal_fallback_enabled=True,
                )

        self.assertEqual(fal_run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
