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

    def test_fal_request_enables_mandatory_reasoning(self):
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
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )

        self.assertIs(fal_run.call_args.args[1]["reasoning"], True)


class GeminiFalAnalysisIntegrationTests(unittest.TestCase):
    def test_url_research_forwards_fal_key_and_enables_web_search(self):
        response = saasshorts.FalTextResponse('{"product_name": "Demo"}')

        with patch("google.genai.Client"), patch(
            "saasshorts._generate_analysis_content",
            return_value=response,
        ) as generate:
            result = saasshorts.research_saas_online(
                "https://example.com",
                "gemini-key",
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )

        self.assertEqual(result["product_name"], "Demo")
        self.assertEqual(generate.call_args.kwargs["fal_key"], "fal-key")
        self.assertTrue(generate.call_args.kwargs["fal_fallback_enabled"])
        self.assertTrue(generate.call_args.kwargs["fal_enable_web_search"])
        self.assertEqual(
            generate.call_args.kwargs["direct_model_chain"],
            ["gemini-3.1-pro-preview"],
        )

    def test_url_research_without_fal_preserves_direct_grounding_fallbacks(self):
        response = SimpleNamespace(
            text='{"product_name": "Demo"}',
            candidates=[],
        )

        with patch("google.genai.Client"), patch(
            "saasshorts._generate_analysis_content",
            return_value=response,
        ) as generate:
            saasshorts.research_saas_online(
                "https://example.com",
                "gemini-key",
                text_model="pro",
            )

        self.assertEqual(
            generate.call_args.kwargs["direct_model_chain"],
            ["gemini-3.1-pro-preview", "gemini-2.5-flash"],
        )

    def test_product_analysis_forwards_fal_fallback(self):
        scraped = {
            "url": "https://example.com",
            "title": "Demo",
            "meta_description": "Demo product",
            "headings": [],
            "main_content": "Product details",
            "additional_pages": "",
        }
        response = saasshorts.FalTextResponse('{"product_name": "Demo"}')

        with patch("google.genai.Client"), patch(
            "saasshorts._generate_analysis_content",
            return_value=response,
        ) as generate:
            result = saasshorts.analyze_saas(
                scraped,
                "gemini-key",
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )

        self.assertEqual(result["product_name"], "Demo")
        self.assertEqual(generate.call_args.kwargs["fal_key"], "fal-key")
        self.assertTrue(generate.call_args.kwargs["fal_fallback_enabled"])
        self.assertFalse(
            generate.call_args.kwargs.get("fal_enable_web_search", False)
        )

    def test_script_generation_forwards_fal_fallback(self):
        def request_once(ask, **_kwargs):
            ask()
            return []

        with patch("google.genai.Client"), patch(
            "saasshorts._generate_analysis_content",
            return_value=SimpleNamespace(text="[]"),
        ) as generate, patch(
            "saasshorts._request_gemini_script_batch",
            side_effect=request_once,
        ):
            result = saasshorts.generate_scripts(
                {"product_name": "Demo"},
                "gemini-key",
                num_scripts=1,
                text_model="pro",
                fal_key="fal-key",
                fal_fallback_enabled=True,
            )

        self.assertEqual(result, [])
        self.assertEqual(generate.call_args.kwargs["fal_key"], "fal-key")
        self.assertTrue(generate.call_args.kwargs["fal_fallback_enabled"])

    def test_malformed_paid_script_response_is_not_requested_twice(self):
        ask = MagicMock(return_value=saasshorts.FalTextResponse("not json"))

        with self.assertRaisesRegex(Exception, "broken scripts answer"):
            saasshorts._request_gemini_script_batch(
                ask,
                num_scripts=1,
                require_shots=False,
                label="scripts",
            )

        self.assertEqual(ask.call_count, 1)

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


class SaaSAnalyzeFalKeyTests(unittest.TestCase):
    def test_analyze_resolves_and_forwards_fal_key(self):
        import asyncio
        import app

        def resolve(provider, _user, _header, _use_platform_keys):
            return {"gemini": "gemini-key", "fal": "fal-key"}[provider]

        request = app.SaaSAnalyzeRequest(description="Test", text_model="pro")
        with patch("app.resolve_effective_api_key", side_effect=resolve), patch(
            "app.generate_scripts", return_value=[]
        ) as generate:
            asyncio.run(
                app.saasshorts_analyze(
                    request,
                    x_gemini_key="gemini-header",
                    x_fal_key="fal-header",
                    authorization=None,
                )
            )

        self.assertEqual(generate.call_args.kwargs["fal_key"], "fal-key")
        self.assertTrue(generate.call_args.kwargs["fal_fallback_enabled"])


if __name__ == "__main__":
    unittest.main()
