"""
AI Shorts: AI-powered UGC video generator for products and businesses.

Generates viral TikTok/Instagram Reels content from a URL or product brief.
Pipeline:
  1. Scrape & analyze product/business website (Gemini)
  2. Generate video scripts (hook → problem → solution → CTA)
  3. Generate AI actor portrait (Flux Pro via fal.ai)
  4. Generate voiceover (ElevenLabs TTS)
  5. Generate talking head video (Kling Avatar v2 via fal.ai)
  6. Generate b-roll clips (Kling v2.6 via fal.ai)
  7. Composite final video with subtitles (FFmpeg)
"""

import os
import re
import glob
import json
import math
import time
import difflib
import hashlib
import shutil
import subprocess
import threading
import httpx
import numpy as np
import textwrap
from datetime import datetime, timezone
from urllib.parse import urljoin
from typing import Optional, List, Dict, Callable, Any
from collections import namedtuple
from concurrent.futures import ThreadPoolExecutor, as_completed


ELEVENLABS_API_BASE = "https://api.elevenlabs.io/v1"
FAL_QUEUE_BASE = "https://queue.fal.run"

# Default ElevenLabs voices (name → voice_id)
DEFAULT_VOICES = {
    "Rachel (Female, calm)": "21m00Tcm4TlvDq8ikWAM",
    "Drew (Male, confident)": "29vD33N1CtxCmqQRPOHJ",
    "Bella (Female, soft)": "EXAVITQu4vr4xnSDxMaL",
    "Antoni (Male, warm)": "ErXwobaYiN019PkySvjV",
    "Josh (Male, deep)": "TxGEqnHWrfWFTfGW9XjX",
    "Sam (Male, raspy)": "yoZ06aMxZJJ28mfd3POQ",
}


DEFAULT_FREE_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_FREE_GEMINI_GROUNDING_MODEL = "gemini-2.5-flash"
DEFAULT_GEMINI_FALLBACK_MODELS = "gemini-3-flash-preview,gemini-2.5-flash"

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", DEFAULT_FREE_GEMINI_MODEL)
GEMINI_FREE_GROUNDING_MODEL = os.environ.get(
    "GEMINI_FREE_GROUNDING_MODEL",
    DEFAULT_FREE_GEMINI_GROUNDING_MODEL,
)
GEMINI_FALLBACK_MODELS = [
    model.strip()
    for model in os.environ.get("GEMINI_FALLBACK_MODELS", DEFAULT_GEMINI_FALLBACK_MODELS).split(",")
    if model.strip()
]
GEMINI_PRO_MODEL = os.environ.get("GEMINI_PRO_MODEL", "gemini-3.1-pro-preview")
GEMINI_MAX_RETRIES = int(os.environ.get("GEMINI_MAX_RETRIES", "2"))
FAL_TEXT_ENDPOINT = os.environ.get("FAL_TEXT_ENDPOINT", "openrouter/router")
FAL_GEMINI_PRO_MODEL = os.environ.get(
    "FAL_GEMINI_PRO_MODEL", "google/gemini-3.1-pro-preview"
)
FAL_GEMINI_FLASH_MODEL = os.environ.get(
    "FAL_GEMINI_FLASH_MODEL", "google/gemini-3-flash-preview"
)
FAL_GEMINI_FAST_FALLBACK_MODEL = os.environ.get(
    "FAL_GEMINI_FAST_FALLBACK_MODEL", "google/gemini-2.5-flash"
)

GEMINI_FAST_TEXT_MODEL_KEYS = {"fast", "flash", "default"}
GEMINI_PRO_TEXT_MODEL_KEYS = {"pro", "quality", "power"}


class GeminiTemporaryError(Exception):
    """Raised when Gemini is temporarily unavailable after retry/fallback attempts."""


class FalTextResponse:
    """Small compatibility adapter for fal.ai text output."""

    def __init__(self, text: str, *, usage: Optional[dict] = None, request_meta: Optional[dict] = None):
        self.text = text
        self.usage = usage or {}
        self.request_meta = request_meta or {}
        self.paid_provider = True
        self.candidates = []


def resolve_gemini_text_model(text_model: Optional[str] = None) -> str:
    """Resolve a UI/API text-model preset to a Gemini model id."""
    key = (text_model or "fast").strip().lower()
    if key in GEMINI_FAST_TEXT_MODEL_KEYS:
        return GEMINI_MODEL
    if key in GEMINI_PRO_TEXT_MODEL_KEYS:
        return GEMINI_PRO_MODEL
    if key.startswith("gemini-"):
        return key
    return GEMINI_MODEL


def fal_gemini_text_model_chain(text_model: Optional[str] = None) -> list:
    """Map SaaS Shorts text presets to paid Google models served through fal.ai."""
    key = (text_model or "fast").strip().lower()
    if key in GEMINI_PRO_TEXT_MODEL_KEYS:
        models = [FAL_GEMINI_PRO_MODEL, FAL_GEMINI_FLASH_MODEL]
    elif key.startswith("gemini-"):
        models = [f"google/{key}", FAL_GEMINI_FLASH_MODEL]
    else:
        models = [FAL_GEMINI_FLASH_MODEL, FAL_GEMINI_FAST_FALLBACK_MODEL]
    return list(dict.fromkeys(models))


def gemini_text_model_chain(text_model: Optional[str] = None) -> list:
    preferred = resolve_gemini_text_model(text_model)
    models = [preferred]
    if preferred != GEMINI_MODEL:
        models.append(GEMINI_MODEL)
    models.extend(GEMINI_FALLBACK_MODELS)
    seen = set()
    chain = []
    for model in models:
        if model and model not in seen:
            chain.append(model)
            seen.add(model)
    return chain


def resolve_gemini_grounding_model(text_model: Optional[str] = None) -> str:
    """Resolve model for Google Search grounding without routing free mode to paid-only grounding."""
    key = (text_model or "fast").strip().lower()
    if key in GEMINI_FAST_TEXT_MODEL_KEYS:
        return GEMINI_FREE_GROUNDING_MODEL
    return resolve_gemini_text_model(text_model)


def gemini_grounding_model_chain(text_model: Optional[str] = None) -> list:
    preferred = resolve_gemini_grounding_model(text_model)
    models = [preferred]
    if preferred != GEMINI_FREE_GROUNDING_MODEL:
        models.append(GEMINI_FREE_GROUNDING_MODEL)
    seen = set()
    chain = []
    for model in models:
        if model and model not in seen:
            chain.append(model)
            seen.add(model)
    return chain


def _gemini_model_chain() -> list:
    return gemini_text_model_chain()


def _is_retryable_gemini_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "503",
            "unavailable",
            "high demand",
            "429",
            "rate limit",
            "resource_exhausted",
            "resource exhausted",
            "temporarily",
            "connecterror",
            "connection",
            "ssl",
            "eof",
            "timed out",
            "timeout",
        )
    )


def _generate_gemini_content(
    client,
    *,
    contents,
    config=None,
    text_model: Optional[str] = None,
    model_chain: Optional[list] = None,
):
    last_error = None
    models = model_chain or gemini_text_model_chain(text_model)

    for model_index, model in enumerate(models):
        for attempt in range(GEMINI_MAX_RETRIES + 1):
            try:
                if model_index > 0 or attempt > 0:
                    print(f"[Gemini] trying model={model} attempt={attempt + 1}")
                return client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
            except Exception as error:
                last_error = error
                retryable = _is_retryable_gemini_error(error)
                if not retryable:
                    raise

                if attempt < GEMINI_MAX_RETRIES:
                    delay = min(2 ** attempt, 8)
                    print(f"[Gemini] temporary failure on {model}; retrying in {delay}s: {error}")
                    time.sleep(delay)
                    continue

                if model_index < len(models) - 1:
                    next_model = models[model_index + 1]
                    print(f"[Gemini] {model} unavailable; falling back to {next_model}")
                    break

    raise GeminiTemporaryError(
        f"Gemini models are temporarily unavailable after retries: {last_error}"
    )


def _is_retryable_fal_text_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "429",
            "503",
            "unavailable",
            "high demand",
            "connection",
            "timed out",
            "timeout",
        )
    )


def _fal_text_input(prompt: str, *, config=None, enable_web_search: bool = False) -> dict:
    input_data = {"prompt": prompt, "reasoning": True}
    max_output_tokens = getattr(config, "max_output_tokens", None)
    if isinstance(max_output_tokens, int) and max_output_tokens > 0:
        input_data["max_tokens"] = max_output_tokens
    temperature = getattr(config, "temperature", None)
    if isinstance(temperature, (int, float)):
        input_data["temperature"] = temperature
    if enable_web_search:
        input_data["enable_web_search"] = True
    return input_data


def _generate_analysis_content(
    client,
    *,
    contents,
    config=None,
    text_model: Optional[str] = None,
    direct_model_chain: Optional[list] = None,
    fal_key: Optional[str] = None,
    fal_fallback_enabled: bool = False,
    fal_enable_web_search: bool = False,
):
    """Generate analysis text while leaving non-analysis Gemini routing unchanged."""
    model_chain = direct_model_chain
    if fal_fallback_enabled and model_chain is None:
        model_chain = [resolve_gemini_text_model(text_model)]
    last_error = None
    try:
        return _generate_gemini_content(
            client,
            contents=contents,
            config=config,
            text_model=text_model,
            model_chain=model_chain,
        )
    except GeminiTemporaryError as direct_error:
        last_error = direct_error
        if not fal_fallback_enabled:
            raise
        if not fal_key:
            raise GeminiTemporaryError(
                "Google quota is exhausted or temporarily unavailable, "
                "and the fal.ai fallback key is missing"
            ) from direct_error

    prompt_parts = contents if isinstance(contents, (list, tuple)) else [contents]
    prompt = "\n".join(str(part) for part in prompt_parts if part is not None)
    fal_input = _fal_text_input(
        prompt,
        config=config,
        enable_web_search=fal_enable_web_search,
    )
    for fal_model in fal_gemini_text_model_chain(text_model):
        try:
            payload = _fal_run(
                FAL_TEXT_ENDPOINT,
                {**fal_input, "model": fal_model},
                fal_key,
            )
            payload_error = str(payload.get("error") or "").strip()
            if payload_error:
                raise RuntimeError(payload_error)
            output = payload.get("output")
            if not isinstance(output, str) or not output.strip():
                raise RuntimeError("fal.ai returned no text output")
            return FalTextResponse(
                output,
                usage=payload.get("usage"),
                request_meta=payload.get("_fal_request"),
            )
        except Exception as error:
            last_error = error
            if not _is_retryable_fal_text_error(error):
                break

    raise GeminiTemporaryError(f"Gemini via fal.ai is unavailable: {last_error}")


# ═══════════════════════════════════════════════════════════════════════
# Phase 1: Website Scraping, Web Research & Analysis
# ═══════════════════════════════════════════════════════════════════════

def research_saas_online(
    url: str,
    gemini_key: str,
    text_model: Optional[str] = None,
    fal_key: Optional[str] = None,
    fal_fallback_enabled: bool = False,
) -> dict:
    """
    Use Gemini with Google Search grounding to deeply research a product or business
    across the internet: reviews, Reddit threads, Twitter, competitor comparisons,
    pricing complaints, user testimonials, etc.
    """
    from google import genai
    from google.genai import types

    print(f"[SaaSShorts] 🔍 Researching {url} across the web (Google Search grounding)...")

    client = genai.Client(api_key=gemini_key)

    # Extract domain name for search queries
    domain = url.replace("https://", "").replace("http://", "").split("/")[0]

    prompt = f"""You are a world-class product and business market researcher. Research this product or business thoroughly using Google Search.

Product URL: {url}
Domain: {domain}

SEARCH AND INVESTIGATE:
1. What does this product or business do? (search their website, Product Hunt, G2, Capterra, marketplaces, reviews, and social posts when relevant)
2. What are REAL user reviews saying? (G2, Capterra, TrustPilot, Reddit, Twitter/X)
3. What are the most common complaints and pain points users mention?
4. Who are their main competitors and how do they compare?
5. What is their pricing and do users think it's worth it?
6. What is their target market and ideal customer profile?
7. Are there any viral posts, memes, or discussions about this product?
8. What content creators or influencers have talked about them?

Return a comprehensive JSON research report:
{{
    "product_name": "...",
    "website_url": "{url}",
    "what_it_does": "Detailed description of the product based on web research",
    "target_market": "Who this product is for",
    "pricing_info": "Pricing details found online (plans, costs, free tier)",
    "user_sentiment": "overall positive/mixed/negative",
    "real_reviews": [
        {{"source": "G2/Reddit/Twitter/etc", "quote": "actual user quote or paraphrase", "sentiment": "positive/negative/neutral"}},
        ...
    ],
    "common_complaints": ["complaint 1 from real users", "complaint 2", ...],
    "common_praise": ["what users love 1", "what users love 2", ...],
    "competitors": [
        {{"name": "competitor", "comparison": "how they compare"}}
    ],
    "viral_potential": ["angle 1 based on real discussions", "angle 2", ...],
    "key_differentiators": ["what makes them unique based on research"],
    "content_angles_from_web": ["angles found from existing content about this product"]
}}

Be thorough. Use REAL data from your search results, not made-up information."""

    response = _generate_analysis_content(
        client,
        contents=[prompt],
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
        direct_model_chain=(
            [resolve_gemini_grounding_model(text_model)]
            if fal_fallback_enabled
            else gemini_grounding_model_chain(text_model)
        ),
        text_model=text_model,
        fal_key=fal_key,
        fal_fallback_enabled=fal_fallback_enabled,
        fal_enable_web_search=True,
    )

    # Extract grounding sources
    sources = []
    try:
        metadata = response.candidates[0].grounding_metadata
        if metadata and metadata.grounding_chunks:
            for chunk in metadata.grounding_chunks:
                if chunk.web:
                    sources.append({"title": chunk.web.title, "url": chunk.web.uri})
        if metadata and metadata.web_search_queries:
            print(f"[SaaSShorts]   Searches performed: {metadata.web_search_queries}")
    except Exception:
        pass

    # Parse response text as JSON
    raw = response.text
    if not raw:
        print("[SaaSShorts] ⚠️ Gemini returned empty response for web research")
        return {"raw_research": "", "product_name": domain, "grounding_sources": sources}

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    try:
        research = json.loads(text)
    except json.JSONDecodeError:
        research = {"raw_research": text, "product_name": domain}

    research["grounding_sources"] = sources
    print(f"[SaaSShorts] ✅ Web research complete: {len(sources)} sources found")
    return research


def scrape_website(url: str) -> dict:
    """Scrape a product or business website to extract key content for analysis."""
    from bs4 import BeautifulSoup

    print(f"[SaaSShorts] 🌐 Scraping {url}...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "iframe"]):
        tag.decompose()

    # Extract metadata
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": "description"})
    if meta_tag:
        meta_desc = meta_tag.get("content", "")

    og_desc = ""
    og_tag = soup.find("meta", attrs={"property": "og:description"})
    if og_tag:
        og_desc = og_tag.get("content", "")

    title = soup.title.string.strip() if soup.title and soup.title.string else ""

    # Extract headings
    headings = []
    for h in soup.find_all(["h1", "h2", "h3"]):
        text = h.get_text(strip=True)
        if text and len(text) < 200:
            headings.append(text)

    # Main text content
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text[:10000]

    # Find subpages to scrape
    base_host = httpx.URL(url).host
    subpages = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if any(kw in href for kw in ["pricing", "features", "about", "product", "why", "how-it-works", "use-case"]):
            try:
                full_url = urljoin(url, a["href"])
                full_host = httpx.URL(full_url).host
                if base_host and full_host and base_host == full_host:
                    subpages.add(full_url)
            except Exception:
                pass

    # Scrape subpages (max 3)
    additional = ""
    for sub_url in list(subpages)[:3]:
        try:
            print(f"[SaaSShorts]   → Subpage: {sub_url}")
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                resp = client.get(sub_url, headers=headers)
                if resp.status_code == 200:
                    sub_soup = BeautifulSoup(resp.text, "html.parser")
                    for tag in sub_soup(["script", "style", "nav", "footer", "header", "noscript"]):
                        tag.decompose()
                    sub_text = sub_soup.get_text(separator="\n", strip=True)[:5000]
                    additional += f"\n\n--- {sub_url} ---\n{sub_text}"
        except Exception as e:
            print(f"[SaaSShorts]   ⚠️ Failed: {e}")

    result = {
        "url": url,
        "title": title,
        "meta_description": meta_desc or og_desc,
        "headings": headings[:20],
        "main_content": text,
        "additional_pages": additional[:15000],
        "pages_scraped": 1 + min(len(subpages), 3),
    }

    print(f"[SaaSShorts] ✅ Scraped {result['pages_scraped']} pages, {len(text)} chars")
    return result


def analyze_saas(
    scraped_data: dict,
    gemini_key: str,
    web_research: dict = None,
    text_model: Optional[str] = None,
    fal_key: Optional[str] = None,
    fal_fallback_enabled: bool = False,
) -> dict:
    """
    Deep analysis of a product or business combining website scraping + web research.
    Uses Gemini 3 Flash for synthesis.
    """
    from google import genai
    from google.genai import types

    print(f"[SaaSShorts] 🧠 Analyzing {scraped_data['url']} (with web research)...")

    client = genai.Client(api_key=gemini_key)

    # Build web research context
    research_context = ""
    if web_research:
        research_context = f"""
=== WEB RESEARCH (from Google Search) ===
Product: {web_research.get('product_name', 'Unknown')}
What it does: {web_research.get('what_it_does', 'N/A')}
Target market: {web_research.get('target_market', 'N/A')}
Pricing: {web_research.get('pricing_info', 'N/A')}
User sentiment: {web_research.get('user_sentiment', 'N/A')}

Real user reviews:
{json.dumps(web_research.get('real_reviews', [])[:8], indent=2)}

Common complaints from real users:
{json.dumps(web_research.get('common_complaints', []), indent=2)}

What users love:
{json.dumps(web_research.get('common_praise', []), indent=2)}

Competitors:
{json.dumps(web_research.get('competitors', []), indent=2)}

Viral angles from existing content:
{json.dumps(web_research.get('viral_potential', []), indent=2)}

Key differentiators:
{json.dumps(web_research.get('key_differentiators', []), indent=2)}

Content angles found online:
{json.dumps(web_research.get('content_angles_from_web', []), indent=2)}
"""

    prompt = f"""You are an expert product marketing analyst and UGC content strategist. Analyze this product or business for creating viral UGC-style marketing videos.

You have TWO sources of information:
1. The product's OWN WEBSITE (scraped content)
2. EXTERNAL WEB RESEARCH (real reviews, Reddit, competitor analysis, user sentiment from Google Search)

Combine BOTH to create the most accurate and compelling analysis possible. Prioritize REAL user pain points and sentiments from the web research.

Website: {scraped_data['url']}
Title: {scraped_data['title']}
Meta: {scraped_data['meta_description']}
Headings: {json.dumps(scraped_data['headings'][:15])}

=== WEBSITE CONTENT ===
{scraped_data['main_content'][:6000]}

=== ADDITIONAL PAGES ===
{scraped_data['additional_pages'][:8000]}
{research_context}

Return a JSON object:
{{
    "product_name": "Name of the product or business",
    "one_liner": "One-sentence description",
    "target_audience": ["audience 1", "audience 2", "audience 3"],
    "pain_points": [
        {{"pain": "specific pain point (from real user feedback if available)", "intensity": "high/medium/low", "emotional_trigger": "frustration/fear/time-waste/money-loss/overwhelm", "source": "website/user-reviews/reddit/general"}}
    ],
    "key_features": ["feature 1", "feature 2", "feature 3"],
    "unique_selling_points": ["usp 1", "usp 2"],
    "competitors": [
        {{"name": "competitor", "comparison": "how they compare"}}
    ],
    "pricing_model": "freemium/subscription/one-time/usage-based",
    "pricing_details": "specific pricing info if found",
    "industry": "category",
    "user_sentiment_summary": "what real users think overall",
    "emotional_hooks": [
        "Stop wasting X hours on...",
        "Your competitors are already using...",
        "I wish I knew about this sooner..."
    ],
    "transformation_story": "Before (with real pain) → After (with product) narrative",
    "viral_angles": [
        {{"angle": "description", "platform": "tiktok/instagram/both", "style": "ugc/educational/shock/story", "why_viral": "reason this angle works"}}
    ]
}}

IMPORTANT: Use REAL pain points from user reviews when available. Real frustrations make the best UGC content.
Include 5-8 pain points, 4-6 emotional hooks, and 4+ viral angles."""

    response = _generate_analysis_content(
        client,
        contents=[prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
        text_model=text_model,
        fal_key=fal_key,
        fal_fallback_enabled=fal_fallback_enabled,
    )

    raw = response.text
    if not raw:
        raise Exception("Gemini returned empty response for product analysis")

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    try:
        analysis = json.loads(text)
    except json.JSONDecodeError as e:
        raise Exception(f"Failed to parse analysis JSON: {e}\nRaw: {text[:500]}")

    # Attach web research sources for reference
    if web_research and web_research.get("grounding_sources"):
        analysis["_web_sources"] = web_research["grounding_sources"]

    print(f"[SaaSShorts] ✅ Analysis: {analysis.get('product_name', '?')} ({len(analysis.get('pain_points', []))} pain points)")
    return analysis


def _repair_gemini_json(text: str) -> str:
    """Fix the JSON glitches Gemini emits on large batches.

    Two are common and safe to auto-correct because valid JSON strings can
    contain neither a raw newline nor an unescaped quote:
      • a missing comma between two values on adjacent lines — a value-ender
        (``}`` ``]`` ``"``) on one line, a value-starter (``"`` ``{`` ``[``) on
        the next (the "Expecting ',' delimiter" error);
      • a trailing comma right before a closing ``}``/``]``.
    """
    text = re.sub(r'([}\]"])[ \t]*\r?\n(\s*["{\[])', r'\1,\n\2', text)
    text = re.sub(r',(\s*[}\]])', r'\1', text)
    return text


def _close_truncated_json(text: str) -> str:
    """Close the brackets a cut-off answer left open.

    Gemini stops mid-object when it runs out of output budget (its cap counts
    thinking tokens, so a long storyboard batch can end mid-word). Rewind to the
    last container that closed cleanly and shut everything still open, so the
    shots that made it through survive instead of the whole batch failing.
    Returns "" when nothing complete came through.
    """
    stack = []
    in_string = False
    escape = False
    cut = None
    cut_stack = None
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "[{":
            stack.append("]" if ch == "[" else "}")
        elif ch in "]}":
            if stack:
                stack.pop()
            if stack:  # a nested container closed: everything up to here is whole
                cut, cut_stack = i + 1, list(stack)
    if not stack:
        return text  # nothing left open — the text is complete as it is
    if cut is None:
        return ""
    return text[:cut] + "".join(reversed(cut_stack))


def _salvage_json_array(text: str) -> list:
    """Best-effort parse of a top-level JSON array that is malformed or cut off.

    Gemini can hit its output token cap mid-string on large multi-script
    batches (unterminated tail), or drop a comma inside one object. We scan for
    every top-level ``{...}`` span and parse each independently — repairing it
    first and skipping the ones that still won't parse — so a single broken
    script never discards the ones that came out clean. The cut-off object at
    the tail is closed and kept too: with one script requested it is the only
    one there is.
    """
    depth = 0
    in_string = False
    escape = False
    obj_start = None
    spans = []
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
            if depth == 0 and obj_start is not None:
                spans.append((obj_start, i + 1))
                obj_start = None
    if obj_start is not None:
        spans.append((obj_start, len(text)))  # never closed: closed below
    salvaged = []
    for obj_start, obj_end in spans:
        chunk = text[obj_start:obj_end]
        for candidate in (chunk, _repair_gemini_json(chunk), _close_truncated_json(chunk)):
            if not candidate:
                continue
            try:
                salvaged.append(json.loads(candidate))
            except json.JSONDecodeError:
                continue  # one unrecoverable object must not drop the rest
            break
    return salvaged


# What had to be done to Gemini's answer before it parsed. The last two mean
# content was lost, which is worth another request; the first two are free.
_JSON_CLEAN = ""
_JSON_REPAIRED = "repaired malformed JSON"
_JSON_TRUNCATED = "answer was cut off — closed the open brackets"
_JSON_SALVAGED = "salvaged the objects that closed cleanly"


def _clean_gemini_json_array(raw: str) -> tuple:
    """Strip the code fence and slice down to the top-level array.

    Returns ``(sliced, unsliced)`` — the second keeps everything after the last
    ``]``, because on a truncated answer that closer belongs to a nested list
    and the scripts after it are still salvageable.
    """
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    start = text.find("[")
    end = text.rfind("]")
    unsliced = text[start:] if start != -1 else text
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return text, unsliced


def _parse_gemini_script_array(raw: str) -> tuple:
    """Parse Gemini's array of scripts, repairing the ways it breaks in practice.

    Returns ``(scripts, note)``; the note is one of the ``_JSON_*`` constants and
    says what had to be fixed, so the caller can tell a free repair from a
    request that lost content.
    """
    text, unsliced = _clean_gemini_json_array(raw)
    repaired = _repair_gemini_json(text)
    attempts = (
        (_JSON_CLEAN, text),
        (_JSON_REPAIRED, repaired),
        (_JSON_TRUNCATED, _close_truncated_json(repaired)),
    )
    for note, candidate in attempts:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            parsed = [parsed]
        scripts = [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
        if scripts:
            return scripts, note
    salvaged = [item for item in _salvage_json_array(unsliced) if isinstance(item, dict)]
    return salvaged, _JSON_SALVAGED if salvaged else _JSON_CLEAN


def _script_batch_quality(scripts: list, note: str, issues=()) -> tuple:
    """Rank two answers to the same request: a clean parse beats a patched one.

    An empty batch ranks below everything — an answer that parsed perfectly and
    carried nothing is worse than a cut-off one we salvaged shots from.
    """
    if not scripts:
        return (0, 0, 0, 0)
    return (
        2 if not issues else 1,
        2 if note in (_JSON_CLEAN, _JSON_REPAIRED) else 1,
        len(scripts),
        sum(len(script.get("shots") or ()) for script in scripts),
    )


def _gemini_finish_reason(response) -> str:
    """MAX_TOKENS here means the answer was cut off, not that the model failed."""
    try:
        return str(response.candidates[0].finish_reason)
    except Exception:
        return "unknown"


def _describe_gemini_json_failure(raw: str, response=None) -> str:
    """Point at the character that broke the parse — the head of the answer never shows it."""
    text, _ = _clean_gemini_json_array(raw)
    reason = f" finish_reason={_gemini_finish_reason(response)}" if response is not None else ""
    if not text:
        return f"empty answer{reason}"
    try:
        json.loads(text)
    except json.JSONDecodeError as error:
        span = 200
        if error.pos >= len(text):
            where = f"...{text[-span:]} <<< ANSWER ENDS HERE"
        else:
            where = f"...{text[max(0, error.pos - span):error.pos]} >>>HERE>>> {text[error.pos:error.pos + span]}..."
        return f"{error} ({len(text)} chars,{reason})\n{where}"
    return f"no script objects in the answer ({len(text)} chars,{reason})\nRaw: {text[:500]}"


def _script_spoken_text(script: dict) -> str:
    """Return the narration source that actually reaches the voiceover."""
    for collection_key, text_key in (("shots", "speech"), ("segments", "narration")):
        collection = script.get(collection_key)
        if isinstance(collection, list):
            spoken = " ".join(
                (item.get(text_key) or "").strip()
                for item in collection
                if isinstance(item, dict) and (item.get(text_key) or "").strip()
            ).strip()
            if spoken:
                return spoken
    return (script.get("full_narration") or "").strip()


_ACTOR_DIRECTION_ONLY_RULES = """ACTOR IDENTITY AND APPEARANCE:
- The selected reference image is the only source of the actor's identity and appearance.
- Never describe or invent age, nationality, ethnicity, skin tone, facial features, body
  type, hair, hairstyle, makeup, clothing, outfit, jewelry, or accessories.
- Refer to the person only as "the actor" or "the same actor from the reference image".
- You may describe only pose, position, gaze, expression, emotion, gesture, movement,
  and the actor's relationship to the camera or nearby objects.
- Describe the location, background, props, lighting, and camera separately from the actor."""


def _finalize_generated_script(script: dict) -> dict:
    """Replace generated metadata with narration-derived, identity-neutral values."""
    # Actor identity belongs to the user's selected/uploaded reference, never to
    # the script model. Drop the field even if a model returns an old schema.
    script.pop("actor_description", None)
    narration = _script_spoken_text(script)
    script["full_narration"] = narration
    script["duration_seconds"] = _estimate_speech_duration(narration)
    script["duration_source"] = "narration_estimate"
    return script


def _record_duration_verdict(script: dict) -> dict:
    """Сверить оценку длины с выбранным хронометражом и записать вердикт.

    До этого `minimum`/`maximum` существовали только внутри текста промпта: ни
    одной проверки в коде, `duration_seconds` считался и молча писался. Человек
    выбирал 15 секунд, получал 24 и узнавал об этом уже по готовому ролику.
    Проверка ничего не переписывает — она делает расхождение видимым.
    """
    target = normalize_target_duration(script.get("target_duration_seconds"))
    preset = TARGET_VIDEO_DURATION_PRESETS[target]
    estimate = script.get("duration_seconds") or 0
    if estimate < preset["minimum"]:
        script["duration_target_status"] = "short"
    elif estimate > preset["maximum"]:
        script["duration_target_status"] = "long"
    else:
        script["duration_target_status"] = "ok"
    if script["duration_target_status"] != "ok":
        print(
            f"[SaaSShorts] ⚠️ «{script.get('title') or 'сценарий'}»: просили ~{target} с, "
            f"текста набралось на {estimate} с "
            f"(допуск {preset['minimum']}-{preset['maximum']} с)."
        )
    return script


def refine_storyboard_broll_alignment(
    scripts: list,
    gemini_key: str,
    text_model: Optional[str] = None,
    language: str = "en",
) -> list:
    """Make one non-blocking semantic review pass over generated B-roll shots.

    The script writer knows the spoken claim, but a video-generation prompt can
    still drift into generic wellness stock footage. This review keeps the
    editable storyboard intact unless Gemini returns a complete, targeted
    replacement for a non-manual B-roll shot.
    """
    if not gemini_key:
        return scripts

    candidates = []
    for script_index, script in enumerate(scripts):
        shots = script.get("shots") if isinstance(script, dict) else None
        if not isinstance(shots, list):
            continue
        for shot_index, shot in enumerate(shots):
            if not isinstance(shot, dict) or not _is_broll_shot(shot) or shot.get("prompt_manual"):
                continue
            previous_speech = ""
            next_speech = ""
            if shot_index:
                previous = shots[shot_index - 1]
                previous_speech = (previous.get("speech") or "").strip() if isinstance(previous, dict) else ""
            if shot_index + 1 < len(shots):
                following = shots[shot_index + 1]
                next_speech = (following.get("speech") or "").strip() if isinstance(following, dict) else ""
            candidates.append({
                "script_index": script_index,
                "shot_number": shot.get("shot_number", shot_index + 1),
                "speech": (shot.get("speech") or "").strip(),
                "previous_speech": previous_speech,
                "next_speech": next_speech,
                "role": (shot.get("role") or "").strip(),
                "scene": (shot.get("scene") or "").strip(),
                "camera": (shot.get("camera") or "").strip(),
                "actor_action": (shot.get("actor_action") or shot.get("action") or "").strip(),
                "actor_in_frame": _shot_wants_actor(shot),
                "generation_prompt": (shot.get("generation_prompt") or "").strip(),
            })
    if not candidates:
        return scripts

    target_language = {"ru": "Russian", "es": "Spanish"}.get(language, "English")
    prompt = f"""You are the final semantic storyboard reviewer for vertical 9:16 social videos.
Review every B-roll shot below in one batch. The exact `speech` is the source of truth.
Target UI language: {target_language}. Write scene, camera, and actor_action only in
{target_language}. Write generation_prompt only in English.

{_ACTOR_DIRECTION_ONLY_RULES}
Apply the identity rule to every replacement. `actor_in_frame` may control pose and
visibility, but it never permits you to invent or restate the presenter's appearance.

Keep the visual only when it directly demonstrates the spoken claim or uses one immediately
understandable visual analogy. Reject generic niche filler unrelated to the nouns, action, or
claim in the speech. Avocado, salad, measuring tape, yoga mat, supplements, scales, and food
prep are forbidden unless the exact spoken line is about that object or action.

Each visual must have one clear subject and one action. Never request generated readable text,
numbers, charts, labels, signs, or screens: percentages, ages, dates and values belong in a
deterministic overlay added later. A conceptually necessary faceless human is allowed: back view,
cropped body or hands, silhouette, or non-identifiable profile. Never request an identifiable
generated face unless an actor reference is actually available.

`actor_in_frame` says whether the person in that insert is the presenter herself. Return it with
every decision: true when your visual shows the same person who speaks (from behind, over the
shoulder, her hands, her silhouette), false when it shows objects, food or an interior. A person
in a `false` shot would be a stranger appearing mid-reel, so either mark it true or keep people out.

Do not rewrite speech, timing, overlay text, shot order, or talking-head shots. Return `keep`
only when the current visual is semantically relevant. For `replace`, provide a localized scene,
camera and actor_action for the UI plus a complete English generation prompt.

Shots JSON:
{json.dumps(candidates, ensure_ascii=False, indent=1)}

Return ONLY a JSON array:
[
  {{
    "script_index": 0,
    "shot_number": 3,
    "decision": "keep" or "replace",
    "scene": "localized user-facing scene",
    "camera": "localized user-facing camera",
    "actor_action": "localized user-facing action",
    "actor_in_frame": true or false,
    "generation_prompt": "English prompt",
    "reason": "short internal reason"
  }}
]"""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_key)
        response = _generate_gemini_content(
            client,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json", max_output_tokens=8192
            ),
            text_model=text_model,
        )
        text = (response.text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        decisions = json.loads(_repair_gemini_json(text))
        if not isinstance(decisions, list):
            raise ValueError("B-roll review response is not a JSON array")
    except Exception as error:
        print(f"[SaaSShorts] WARNING: B-roll semantic review skipped: {error}")
        return scripts

    candidates_by_key = {
        (candidate["script_index"], str(candidate["shot_number"])): candidate
        for candidate in candidates
    }
    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        decision_name = decision.get("decision")
        if not isinstance(decision_name, str) or decision_name.strip().lower() != "replace":
            continue
        try:
            script_index = int(decision.get("script_index"))
        except (TypeError, ValueError):
            continue
        shot_number = str(decision.get("shot_number", ""))
        if (script_index, shot_number) not in candidates_by_key:
            continue
        raw_scene = decision.get("scene")
        raw_generation_prompt = decision.get("generation_prompt")
        raw_camera = decision.get("camera", "")
        raw_actor_action = decision.get("actor_action", "")
        if raw_camera is None:
            raw_camera = ""
        if raw_actor_action is None:
            raw_actor_action = ""
        if (
            not isinstance(raw_scene, str)
            or not isinstance(raw_generation_prompt, str)
            or not isinstance(raw_camera, str)
            or not isinstance(raw_actor_action, str)
        ):
            continue
        scene = raw_scene.strip()
        generation_prompt = raw_generation_prompt.strip()
        if not scene or not generation_prompt:
            continue
        shots = scripts[script_index]["shots"]
        shot = next((item for item in shots if str(item.get("shot_number")) == shot_number), None)
        if not isinstance(shot, dict) or not _is_broll_shot(shot) or shot.get("prompt_manual"):
            continue
        camera = raw_camera.strip()
        actor_action = raw_actor_action.strip()
        shot["scene"] = scene
        if camera:
            shot["camera"] = camera
        if actor_action:
            shot["actor_action"] = actor_action
            shot["action"] = actor_action
        # The review rewrites what is in the insert, so it also owns whether the
        # presenter is in it — a replaced visual must not keep the old answer.
        if decision.get("actor_in_frame") is not None:
            shot["actor_in_frame"] = _shot_wants_actor(decision)
        shot["_script_language"] = (
            shot.get("_script_language")
            or scripts[script_index].get("language")
            or language
        )
        shot["_generation_prompt_language"] = "en"
        shot["generation_prompt"] = _build_storyboard_generation_prompt({
            **shot,
            "generation_prompt": generation_prompt,
        })
        shot["_prompt_source_scene"] = scene
    return scripts


def _gemini_json_array(
    prompt: str,
    gemini_key: str,
    text_model: Optional[str] = None,
    label: str = "request",
    max_output_tokens: int = 8192,
) -> Optional[list]:
    """Один текстовый запрос к Gemini, отдающий JSON-массив; None при любой беде.

    Проходы по раскадровке не блокирующие: сорванный запрос обязан оставить
    сценарий таким, каким он был, а не уронить генерацию.
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_key)
        response = _generate_gemini_content(
            client,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=max_output_tokens,
            ),
            text_model=text_model,
        )
        text = (response.text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        parsed = json.loads(_repair_gemini_json(text))
        if not isinstance(parsed, list):
            raise ValueError("response is not a JSON array")
        return parsed
    except Exception as error:
        print(f"[SaaSShorts] WARNING: {label} skipped: {error}")
        return None


# Место действия ролика — свой запрос и своё поле. Раньше сетом работал промпт
# первого говорящего кадра целиком, и в плиты вместе с комнатой уезжало всё
# остальное, что там оказалось: «holding a steady selfie pose» — и обе камеры
# вышли одним анфасом (замер 03.08, разница поворота 0.005 против рабочих 0.30);
# «a beautiful woman» — и редактор нарисовал своё лицо вместо выбранного (джоб
# f14d08b1). Поле, у которого одна работа, нечем заполнить не по делу.
_SET_WRITER_RULES = """WHAT A SET IS:
- A set is a PLACE to shoot in: the room, the light, the surfaces, the props.
- One or two sentences, concrete and photographable: what furniture, what surfaces, what stands on them, where the light comes from.
- NO people. Do not mention the presenter, an actor, a woman, a man, hands or anyone else — the app puts the person into the picture itself.
- NO appearance of anybody: no age, hair, skin, build, clothing or make-up.
- NO camera: no shot type, no angle, no framing, no "static camera", no "looking at the camera", no aspect ratio.
- NO action and NO moment: not what happens, only where it happens.
- No readable text anywhere: no signs, labels, screens, numbers or writing on objects.
- Ordinary, plausible, unbranded: a real home or workspace that suits the topic, never a studio and never stock-photo staging."""


# «Одно место на ролик» — правило по умолчанию, а не закон: снятое в одной
# комнате читается как одна съёмка и стоит две плиты. Опцией место меняется по
# ходу — тогда мест несколько, и каждое стоит своих плит. Меняется не каждый
# кадр: соседние шоты одной локации разводит вторая камера, а платит человек за
# каждую новую комнату.
_SHOTS_PER_LOCATION = 3
_MAX_LOCATIONS = 3


def generate_storyboard_sets(
    scripts: list,
    gemini_key: str,
    text_model: Optional[str] = None,
    language: str = "en",
    locations: int = 1,
) -> list:
    """Дописать каждому сценарию место действия: `set_scene` (UI) и `set_prompt` (в плиты).

    `locations` > 1 — опция «менять локации»: мест несколько, они лягут в
    `set_prompts`/`set_scenes` списком, а первое дублируется в `set_prompt` для
    всего, что умеет читать только одно место.
    """
    if not gemini_key:
        return scripts
    locations = max(1, min(int(locations or 1), _MAX_LOCATIONS))

    payload = []
    for index, script in enumerate(scripts):
        if not isinstance(script, dict):
            continue
        lines = [
            (shot.get("speech") or "").strip()
            for shot in (script.get("shots") or [])
            if isinstance(shot, dict) and (shot.get("speech") or "").strip()
        ]
        payload.append({
            "script_index": index,
            "title": (script.get("title") or "").strip(),
            "speech": lines[:4],
        })
    if not payload:
        return scripts

    lang_name = {"ru": "Russian", "es": "Spanish"}.get(language, "English")
    if locations > 1:
        task = (
            f"For each script below, pick {locations} places the reel moves between, in order. "
            "They can be different parts of one home — another corner, the next room, the "
            "balcony — or different places entirely, whichever suits the lines better. The "
            "person wears the same clothes in all of them, so pick places where that holds."
        )
        shape = ('[{{"script_index": 0, "sets": [{{"set_scene": "...", "set_prompt": "..."}}]}}]'
                 .replace("{{", "{").replace("}}", "}"))
    else:
        task = ("For each script below, pick ONE place the whole reel is shot in. It must suit "
                "what the person is talking about, and it must stay believable for a phone video.")
        shape = '[{"script_index": 0, "set_scene": "...", "set_prompt": "..."}]'
    prompt = f"""You choose the location for vertical 9:16 social videos.
{task}

{_SET_WRITER_RULES}

Write `set_scene` in {lang_name} — the user reads it in the app.
Write `set_prompt` in English — it goes to the image model as is.
Both describe the same place; `set_prompt` is not a translation but the same room
written for a model: nouns, materials, colours, light.

Scripts JSON:
{json.dumps(payload, ensure_ascii=False, indent=1)}

Return ONLY a JSON array:
{shape}"""

    decisions = _gemini_json_array(
        prompt, gemini_key, text_model=text_model, label="Storyboard set", max_output_tokens=4096,
    )
    if not decisions:
        return scripts

    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        try:
            index = int(decision.get("script_index"))
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(scripts) or not isinstance(scripts[index], dict):
            continue
        # Несколько мест приезжают списком, одно — плоскими полями. Разбираем оба
        # вида одним кодом: список из одного места и есть обычный случай.
        chosen = decision.get("sets") if isinstance(decision.get("sets"), list) else [decision]
        places = [
            ((place.get("set_prompt") or "").strip(), (place.get("set_scene") or "").strip())
            for place in chosen if isinstance(place, dict) and (place.get("set_prompt") or "").strip()
        ][:locations]
        if not places:
            continue
        set_prompt, set_scene = places[0]
        scripts[index]["set_prompt"] = set_prompt
        scripts[index]["set_scene"] = set_scene or set_prompt
        if locations > 1:
            scripts[index]["set_prompts"] = [prompt_text for prompt_text, _ in places]
            scripts[index]["set_scenes"] = [scene or prompt_text for prompt_text, scene in places]
            # Человек попросил менять места — значит, текст мест доезжает до плит.
            # Без этого флага он был бы отброшен как сочинённый вслепую.
            scripts[index]["set_changes"] = True
        # Кто выбрал место, решает, попадёт ли текст в плиты. Написанное здесь
        # сочинено вслепую: про фото ведущего эта модель ничего не знает, а на
        # нём комната уже есть. Перебивать её выдумкой можно только по просьбе
        # человека — иначе дневная кухня с фото переезжает в вечернюю из текста.
        scripts[index]["set_source"] = "ai"
    return scripts


# Кадр говорящий и кадр-перебивка живут по противоположным правилам камеры: у
# перебивки промпт уходит в Kling дословно и камера там нужна, у говорящего
# камеру ставит сборка и любое слово о ней только мешает. Пока обе инструкции
# лежали в одном запросе со всем остальным, модель их регулярно путала —
# отсюда «static camera» в говорящем кадре. Здесь они разведены по разным
# абзацам одного запроса, а сам запрос не занят больше ничем.
def generate_storyboard_visuals(
    scripts: list,
    gemini_key: str,
    text_model: Optional[str] = None,
    language: str = "en",
) -> list:
    """Дописать кадрам картинку: `scene` для интерфейса и `generation_prompt` для модели."""
    if not gemini_key:
        return scripts

    payload = []
    for script_index, script in enumerate(scripts):
        if not isinstance(script, dict):
            continue
        shots = script.get("shots")
        if not isinstance(shots, list):
            continue
        for order, shot in enumerate(shots, start=1):
            if not isinstance(shot, dict) or shot.get("prompt_manual"):
                continue
            payload.append({
                "script_index": script_index,
                "shot_number": shot.get("shot_number", order),
                "set_prompt": (script.get("set_prompt") or "").strip(),
                "visual_type": "broll" if _is_broll_shot(shot) else "talking",
                "actor_in_frame": _shot_wants_actor(shot),
                "role": (shot.get("role") or "").strip(),
                "speech": (shot.get("speech") or "").strip(),
            })
    if not payload:
        return scripts

    lang_name = {"ru": "Russian", "es": "Spanish"}.get(language, "English")
    prompt = f"""You turn a written storyboard into pictures for vertical 9:16 social videos.
Every shot below already has its spoken line. Give each one what is in frame.

{_ACTOR_DIRECTION_ONLY_RULES}

Write `scene` in {lang_name} — the user reads and edits it in the app.
Write `generation_prompt` in English — it is the only text the video model sees.
Every generation_prompt says vertical 9:16, realistic phone video, natural light.
Never request readable text of any kind: no labels, signs, numbers, dates, stickers or
screens — video models render text as garbage glyphs. Write what IS in frame; a "no text"
clause only makes the model draw text.

TALKING SHOTS (visual_type "talking"):
- The place is already chosen and is NOT yours. It is in `set_prompt`, it is the same for every
  talking shot of the reel, and you must not restate it, change it, or invent a new room, window
  or time of day.
- `scene` is the MOMENT: posture, hands, expression — what changes in the person right now. One
  short phrase.
- `generation_prompt` is that same moment in English plus "the same actor from the reference
  image", and nothing else.
- NO camera wording at all: no shot type, no angle, no framing, no "static camera", no "looking
  at the camera", no "selfie pose", no "facing the viewer". The app owns the camera here and
  rotates its own cameras between talking shots; a prompt that fixes the pose or the gaze pins
  the actor face-on and every camera comes back the same picture.
- The person stays put: only facial expression and small head movement. No walking, drinking,
  standing up or big arm gestures — motion breaks lip-sync.

B-ROLL SHOTS (visual_type "broll"):
- Here the camera IS yours: `generation_prompt` must state the shot type and any camera move,
  because it goes to the video model as written.
- The insert must demonstrate the exact spoken line: literally show the claim, or use one
  immediately understandable visual analogy. One clear subject, one action. No generic wellness
  filler — avocado, salad, measuring tape, yoga mat, supplements, scales, food prep — unless that
  exact line is about it. Avoid objects with digital displays entirely.
- With `actor_in_frame` true the insert shows the same presenter: identify the same actor from
  the reference image, seen from behind, over the shoulder, her hands or her silhouette.
- With `actor_in_frame` false there is no presenter: do not mention the actor or any reference
  image, and pick subjects with no identifiable face.

Shots JSON:
{json.dumps(payload, ensure_ascii=False, indent=1)}

Return ONLY a JSON array:
[{{"script_index": 0, "shot_number": 1, "scene": "...", "generation_prompt": "...",
  "camera": "shot type and move, {lang_name}, B-roll only — empty string for talking shots"}}]"""

    decisions = _gemini_json_array(
        prompt, gemini_key, text_model=text_model, label="Storyboard visuals",
        max_output_tokens=16384,
    )
    if not decisions:
        return scripts

    for decision in decisions:
        if not isinstance(decision, dict):
            continue
        try:
            script_index = int(decision.get("script_index"))
        except (TypeError, ValueError):
            continue
        if not 0 <= script_index < len(scripts) or not isinstance(scripts[script_index], dict):
            continue
        shots = scripts[script_index].get("shots")
        if not isinstance(shots, list):
            continue
        shot_number = str(decision.get("shot_number", ""))
        shot = next(
            (item for item in shots
             if isinstance(item, dict) and str(item.get("shot_number")) == shot_number),
            None,
        )
        if shot is None or shot.get("prompt_manual"):
            continue
        scene = (decision.get("scene") or "").strip()
        generation_prompt = (decision.get("generation_prompt") or "").strip()
        if not scene or not generation_prompt:
            continue
        camera = (decision.get("camera") or "").strip()
        shot["scene"] = scene
        # Камера — поле интерфейса, и у говорящих кадров ей взяться неоткуда:
        # ракурс там ставит сборка. Пустую строку не пишем, чтобы карточка не
        # показывала пустую подпись вместо честного «камеру выбирает сборка».
        if camera and _is_broll_shot(shot):
            shot["camera"] = camera
        shot["_script_language"] = (
            shot.get("_script_language") or scripts[script_index].get("language") or language
        )
        shot["_generation_prompt_language"] = "en"
        shot["generation_prompt"] = generation_prompt
        shot["_prompt_source_scene"] = scene
    return scripts


def _normalized_hook_text(text: str) -> str:
    without_tags = re.sub(r"\[[^\]]+\]", " ", text or "")
    separated = re.sub(r"[-‐‑‒–—―]+", " ", without_tags)
    words = re.findall(r"[^\W_]+(?:'[^\W_]+)*", separated, flags=re.UNICODE)
    return " ".join(words).casefold()


def _script_hook_text(script: dict) -> str:
    """Return the first spoken narration field, before any fallback narration."""
    for collection_key, text_key in (("shots", "speech"), ("segments", "narration")):
        collection = script.get(collection_key)
        if isinstance(collection, list):
            for item in collection:
                if isinstance(item, dict) and (item.get(text_key) or "").strip():
                    return (item.get(text_key) or "").strip()
    return (script.get("full_narration") or "").strip()


def _hook_opening(script: dict, words: int = 3) -> str:
    return " ".join(_normalized_hook_text(_script_hook_text(script)).split()[:words])


_CANNED_HOOK_OPENINGS = (
    "stop stop stop",
    "okay listen",
    "okay so",
    "all right enough",
    "hey everyone",
    "hey",
    "hello everyone",
    "hello",
    "hi",
    "watch until the end",
    "wait until the end",
    "hola a todos",
    "hola",
    "buenas a todos",
    "mira hasta el final",
    "espera hasta el final",
    "quédate hasta el final",
    "\u043f\u0440\u0438\u0432\u0435\u0442 \u0432\u0441\u0435\u043c",
    "\u0432\u0441\u0435\u043c \u043f\u0440\u0438\u0432\u0435\u0442",
    "\u0442\u0430\u043a \u0441\u043b\u0443\u0448\u0430\u0439",
    "\u0432\u0441\u0435 \u0445\u0432\u0430\u0442\u0438\u0442",
    "\u0432\u0441\u0451 \u0445\u0432\u0430\u0442\u0438\u0442",
    "\u0441\u0442\u043e\u043f \u0441\u0442\u043e\u043f \u0441\u0442\u043e\u043f",
    "\u0434\u043e\u0441\u043c\u043e\u0442\u0440\u0438 \u0434\u043e \u043a\u043e\u043d\u0446\u0430",
    "\u0441\u043c\u043e\u0442\u0440\u0438 \u0434\u043e \u043a\u043e\u043d\u0446\u0430",
)

_HOOK_TYPES = frozenset((
    "result_first",
    "mistake_prohibition",
    "counterintuitive_claim",
    "data_point",
    "pain_question",
    "personal_confession_demo",
    "open_loop",
))


def _starts_with_hook_phrase(text: str, phrase: str) -> bool:
    return bool(re.match(rf"^{re.escape(phrase)}(?:\s|$)", text))


def _topic_supplied_hook(topic: Optional[str]) -> str:
    match = re.search(r"(?im)^\s*(?:Hook|\u0425\u0443\u043a)\s*:\s*(.+?)\s*$", topic or "")
    return match.group(1).strip() if match else ""


def _validate_script_batch_hooks(scripts: list, supplied_hook: str = "") -> list:
    """Return hook-quality issues while allowing the caller to salvage a batch."""
    issues = []
    seen = {}
    for index, script in enumerate(scripts, start=1):
        opening = _hook_opening(script)
        full_hook = _normalized_hook_text(_script_hook_text(script))
        if not opening:
            continue
        if any(_starts_with_hook_phrase(full_hook, canned) for canned in _CANNED_HOOK_OPENINGS):
            issues.append(f"script {index} uses a canned filler opening: {opening}")
        if opening in seen:
            issues.append(f"scripts {seen[opening]} and {index} repeat opening: {opening}")
        else:
            seen[opening] = index

    if len(scripts) > 1:
        seen_types = {}
        for index, script in enumerate(scripts, start=1):
            hook_type = (script.get("hook_type") or "").strip().casefold()
            if hook_type not in _HOOK_TYPES:
                issues.append(f"script {index} has missing or unsupported hook_type")
                continue
            if hook_type in seen_types:
                issues.append(f"scripts {seen_types[hook_type]} and {index} repeat hook_type: {hook_type}")
            else:
                seen_types[hook_type] = index

    required_opening = _normalized_hook_text(supplied_hook)
    first_opening = _normalized_hook_text(_script_hook_text(scripts[0])) if scripts else ""
    if required_opening and not first_opening.startswith(required_opening):
        issues.append("script 1 does not start directly with the supplied hook")
    return issues


def _request_gemini_script_batch(ask, *, num_scripts: int, require_shots: bool, label: str, batch_validator=None) -> list:
    """Ask Gemini for a batch of scripts and hand back the ones that parsed.

    A dropped comma is patched in place and costs nothing. An answer cut off
    mid-object is different: it silently drops shots the user is about to pay to
    render, so it is worth one more request — we keep whichever attempt came out
    better rather than trusting the retry blindly.
    """
    best = None
    for attempt in range(2):
        try:
            response = ask()
        except Exception:
            if best is None:
                raise  # nothing to fall back on — the caller must see the failure
            break  # the extra request failed; keep what the first answer gave us
        scripts, note = _parse_gemini_script_array(response.text or "")
        if require_shots:
            scripts = [script for script in scripts if script.get("shots")]
        issues = tuple(batch_validator(scripts)) if scripts and batch_validator else ()
        if best is None or _script_batch_quality(scripts, note, issues) > _script_batch_quality(best[0], best[1], best[3]):
            best = (scripts, note, response, issues)
        if getattr(response, "paid_provider", False) is True:
            break
        if scripts and not issues and note not in (_JSON_TRUNCATED, _JSON_SALVAGED):
            break
        if attempt == 0 and not issues:
            print(
                f"[SaaSShorts] Incomplete {label} answer "
                f"({note or 'nothing parsed'}, finish_reason={_gemini_finish_reason(response)}) "
                "- asking Gemini once more."
            )

    scripts, note, response, issues = best
    if not scripts:
        # The diagnostic belongs in the log, not on the user's screen: it is
        # kilobytes of JSON, and all they can act on is "try again".
        print(
            f"[SaaSShorts] ❌ Unparseable {label} answer: "
            f"{_describe_gemini_json_failure(response.text or '', response)}"
        )
        if getattr(response, "paid_provider", False) is True:
            raise Exception(
                f"Gemini via fal.ai returned a broken {label} answer. "
                "Please try generating again."
            )
        raise Exception(
            f"Gemini returned a broken {label} answer twice in a row. Please try generating again."
        )
    if note:
        print(f"[SaaSShorts] {note} - kept {len(scripts)}/{num_scripts} {label}(s).")
    return scripts


TARGET_VIDEO_DURATION_DEFAULT = 20
_TARGET_DURATION_TOLERANCE = 2
# Во что обходится речь. Единственный источник этих коэффициентов: и бюджет,
# который просят у модели, и замер готового сценария считаются по ним, иначе
# просить одно, а мерить другим — и удивляться, что 15 секунд вышли 24.
_SPEECH_WORDS_PER_SECOND = 2.2
_SPEECH_TAG_SECONDS = 0.8
_SPEECH_PAUSE_SECONDS = 0.4

# Пол клипа у каждой модели свой, и он не «минимум на всякий случай», а цена
# любого кадра: короче его модель не отдаёт и короче не считает. Кадр, которому
# досталось меньше пола, оплачивается целиком, а на экране живёт свою короткую
# долю — разница и есть деньги за воздух.
#
# Kling V3 (перебивки) — три секунды.
#
# Kling Avatar (говорящие) — замерено по всем 24 клипам на диске (прогоны от
# 4e4f6776 до d6b674c6, оба разрешения — 720x1280 и 1072x1920). Длина клипа
# ведёт себя так: пол в 64 кадра при 30 fps, а выше пола длина округляется
# вверх до блока в 8 кадров. Пять клипов с аудио 1.228 / 1.672 / 1.698 / 1.750 с
# вернулись ровно 2.133 с; 2.247 → 2.400; 2.612 → 2.667; 4.389 → 4.533. Модель
# описывает 21 клип из 24.
#
# Три несходящихся — 5.538 / 6.609 / 6.792 с аудио, все вернулись ровно 7.200 с.
# Общего у них только разрешение 720x1280, но в той же группе 16 клипов модели
# подчиняются, так что объяснения у выброса пока нет. На счёт он влияет в нашу
# пользу — модель занижает, а не завышает.
_KLING_MIN_CLIP_SECONDS = 3
_KLING_MAX_CLIP_SECONDS = 15
_KLING_AVATAR_FPS = 30
_KLING_AVATAR_BLOCK_FRAMES = 8
_KLING_AVATAR_MIN_FRAMES = 64
_KLING_AVATAR_MIN_CLIP_SECONDS = _KLING_AVATAR_MIN_FRAMES / _KLING_AVATAR_FPS


def _affordable_beats(target: int) -> int:
    """Сколько склеек ролик такой длины оплачивает без переплаты.

    Смесь берём из правила раскадровки — не больше одной перебивки на два
    говорящих кадра, — и по ней считаем средний пол бита. Больше этого числа
    склеек не помещается: не в хронометраж, а в счёт.
    """
    average_floor = (2 * _KLING_AVATAR_MIN_CLIP_SECONDS + _KLING_MIN_CLIP_SECONDS) / 3
    return max(2, int(target / average_floor))


def _duration_preset(target: int, beats: tuple, audio_tags: int, pauses: int) -> dict:
    """Бюджеты одного хронометража, посчитанные той же формулой, что и замер.

    Раньше бюджет слов и число визуальных битов жили отдельными числами,
    подобранными руками, — и разъехались: битов стало почти вдвое больше, слова
    не тронули, а каждый бит приносит свой аудиотег и свою паузу. На «15 секунд»
    выходило 24: `_estimate_speech_duration` берёт 0.8 с за тег и 0.4 с за паузу,
    и восемь битов — это десять секунд поверх слов. Теперь бюджет слов — это
    остаток от цели после оплаты тегов и паузе, посчитанный по тем же
    коэффициентам, которыми длину потом и измеряют.

    Слова на реплику — тоже не отдельное правило, а то же деление на биты. Пока
    в промпте стояло «4-8 слов на реплику» рядом с «6-8 битов», модель имела
    полное право написать 48 слов при бюджете 26 и формально всё соблюсти.

    Сверху биты упираются в то, что ролик может оплатить. Каждый бит — отдельный
    клип, а клип короче своего пола не бывает: биту, которому досталось меньше,
    всё равно выставят пол. На верхней границе прежних диапазонов это выходило
    боком — 15 секунд при восьми битах оплачивались как 19.7, а 45 при двадцати
    двух как 53.1. Разница — воздух, и на десяти роликах в день она заметна.
    """
    low, high = beats
    high = min(high, _affordable_beats(target))
    # Диапазон должен остаться диапазоном: схлопнувшись в одно число, он даёт и
    # слова на реплику одним числом («4-4»), а это уже не бюджет, а приказ.
    low = max(2, min(low, high - 1))
    speech_seconds = (
        target - audio_tags * _SPEECH_TAG_SECONDS - pauses * _SPEECH_PAUSE_SECONDS
    )
    words = round(speech_seconds * _SPEECH_WORDS_PER_SECOND)
    return {
        "minimum": target - _TARGET_DURATION_TOLERANCE,
        "maximum": target + _TARGET_DURATION_TOLERANCE,
        "words": f"{words}-{words + 4}",
        "visual_beats": f"{low}-{high}",
        "audio_tags": audio_tags,
        "pauses": pauses,
        "words_per_beat": f"{max(2, round(words / high))}-{max(3, round(words / low))}",
    }


# Биты — сколько склеек держит ритм на этой длине; теги и паузы — сколько
# актёрских ремарок и многоточий ролик может себе позволить, они стоят времени.
TARGET_VIDEO_DURATION_PRESETS = {
    15: _duration_preset(15, (6, 8), audio_tags=3, pauses=2),
    20: _duration_preset(20, (8, 10), audio_tags=4, pauses=3),
    30: _duration_preset(30, (11, 15), audio_tags=6, pauses=4),
    45: _duration_preset(45, (16, 22), audio_tags=9, pauses=6),
}


def normalize_target_duration(
    value,
    default: int = TARGET_VIDEO_DURATION_DEFAULT,
) -> int:
    """Return a supported approximate script-duration target."""
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = default
    return normalized if normalized in TARGET_VIDEO_DURATION_PRESETS else default


def _target_duration_prompt(
    target: int,
    storyboard: bool,
) -> str:
    """Prompt-only duration guidance shared by UGC and storyboard scripts."""
    target = normalize_target_duration(target)
    preset = TARGET_VIDEO_DURATION_PRESETS[target]
    format_line = (
        f"- Use {preset['visual_beats']} visual beats across the reel. One visual beat is one "
        f"complete shot, carrying {preset['words_per_beat']} spoken words."
        if storyboard
        else "- Use exactly five segments. Their combined narration, not each segment, must fit "
        "the word budget."
    )
    # Теги и паузы названы поимённо и с ценой. Без этого модель считала их
    # бесплатными украшениями и ставила по одному на каждый кадр — это и есть те
    # девять лишних секунд, из-за которых «15 секунд» превращались в 24.
    return f"""
TARGET VIDEO DURATION:
- Every script in this batch should be approximately {target} seconds.
- Keep the finished narration within {preset['minimum']}-{preset['maximum']} seconds.
- Aim for {preset['words']} spoken words total, excluding audio-direction tags.
- Audio tags and marked pauses are spent time, not decoration: a bracketed tag such as
  [whispers] costs about {_SPEECH_TAG_SECONDS} s of the reel and an ellipsis or dash pause about
  {_SPEECH_PAUSE_SECONDS} s. This target already pays for at most {preset['audio_tags']} tags and
  {preset['pauses']} marked pauses in the whole script — do not add more, and never put one on
  every shot.
{format_line}
- The word budget is the total for the whole script. Beats × words-per-beat must land inside it:
  more beats means shorter lines, never more words.
- Apply this same duration target independently to every script in the batch.
"""


def _target_duration_timeline(target: int) -> list:
    """Five illustrative UGC segment boundaries ending at the selected target."""
    target = normalize_target_duration(target)
    return [round(target * index / 5) for index in range(6)]


def generate_scripts(
    analysis: dict,
    gemini_key: str,
    num_scripts: int = 3,
    style: str = "ugc",
    language: str = "en",
    actor_gender: str = "female",
    topic: str = None,
    script_format: str = "ugc",
    text_model: Optional[str] = None,
    target_duration_seconds: int = TARGET_VIDEO_DURATION_DEFAULT,
    broll_between_talking: bool = False,
    changing_locations: bool = False,
    fal_key: Optional[str] = None,
    fal_fallback_enabled: bool = False,
) -> list:
    """Generate video scripts based on product/business analysis.

    `broll_between_talking` — не ставить два говорящих кадра подряд. Выключено
    по умолчанию, и намеренно: перебивка это отдельный платный клип, который
    тарифицируется от трёх секунд, так что чередование заметно поднимает смету.

    `changing_locations` — менять место по ходу ролика. Тоже выключено и тоже
    из-за денег: каждая новая комната это своя плита на каждую камеру, которая
    в ней снимает. Заодно это единственный случай, когда сочинённое моделью
    место доезжает до кадров: обычно комнату держит фото ведущего.
    """
    from google import genai
    from google.genai import types

    lang_name = {"es": "Spanish", "ru": "Russian"}.get(language, "English")
    target_duration_seconds = normalize_target_duration(target_duration_seconds)
    print(f"[SaaSShorts] 📝 Generating {num_scripts} scripts ({style}, {lang_name})...")

    client = genai.Client(api_key=gemini_key)

    style_guide = {
        "ugc": (
            "Natural, authentic UGC style. Person talking to camera like sharing a discovery "
            "with a friend. Casual, genuine, first person, imperfect phrasing welcome."
        ),
        "educational": (
            "Educational explainer. Structure: the hook names a concrete mistake or question the "
            "viewer has -> 2-3 numbered actionable points ('первое... второе...') -> one-line "
            "takeaway. Confident 'знающая подруга' tone, zero fluff, every point specific enough "
            "to apply today."
        ),
        "shock": (
            "Shock/discovery format. The FIRST spoken line is a surprising counterintuitive claim "
            "or number that contradicts what the viewer believes. Then immediately justify it, "
            "resolve the tension, and end with what to do instead. High-energy opening, calmer "
            "confident resolution."
        ),
        "story": (
            "First-person storytelling arc, one continuous mini-narrative (NOT a list). Structure: "
            "setup anchored to a specific moment ('в прошлый вторник...') -> struggle or failure -> "
            "turning point (the discovery) -> result with one concrete, believable detail. "
            "Past tense, personal."
        ),
        "comparison": (
            "Before/after comparison. Contrast the old painful way vs the new way point by point "
            "('раньше... теперь...'). Make the 'before' visceral and specific, the 'after' "
            "measurable. End with how to switch."
        ),
    }

    lang_instructions = ""
    if language == "es":
        lang_instructions = """
LANGUAGE: ALL narrations, subtitles, captions, and hashtags MUST be in SPANISH (Spain/Latin America).
Use natural casual Spanish like a real person would speak on TikTok. Contractions, slang OK.
Examples of Spanish UGC hooks: "Tres campos de factura evitan este error", "Deja de aprobar facturas sin esta regla", "Este dato revela dónde se pierde el margen"
"""
    elif language == "ru":
        lang_instructions = """
LANGUAGE: ALL narrations, subtitles, captions, and hashtags MUST be in RUSSIAN.
Use natural casual Russian like a real person would speak in Reels/TikTok. Keep it punchy, direct, and conversational.
Examples of Russian UGC hooks: "Ты срываешься вечером не потому, что слабая", "Хватит начинать заново каждый понедельник", "Вот что съесть в 17:00, чтобы вечером не снести холодильник".

SPEECH STYLE (critical — the speech/narration text goes straight to TTS and must sound like LIVE spoken Russian, not written copy):
- Short punchy sentences. Fragments are fine ("Это не работает. Вообще.").
- Mark natural pauses and hesitations with ellipses "…" and dashes "—": "а сладкое… ну, это самый быстрый путь".
- Ask the viewer rhetorical questions: "Знакомо?", "Когда? Где?".
- Write ALL numbers in words: "двадцать минут", never "20 минут".
- REQUIRED: add 2-3 ElevenLabs audio tags per script inside speech/narration, in English square brackets: [sighs], [excited], [whispers]. They are acting directions and are never spoken; without them the TTS delivery sounds flat and robotic. NEVER put a tag as the last token of a line, and NEVER put tags in overlay_text, captions, or hashtags.
"""
    else:
        lang_instructions = """
LANGUAGE: ALL narrations, subtitles, captions, and hashtags MUST be in ENGLISH.
Use natural casual American English like a real person on TikTok. Contractions, slang OK.
Examples of English UGC hooks: "Three invoice fields prevent this approval error", "Stop approving invoices manually when cash flow is tight", "This dashboard metric exposes the leak"
"""

    topic_instructions = ""
    if topic:
        topic_instructions = f"""
CURRENT VIDEO TOPIC:
{topic}

Every generated script MUST focus on this exact topic. Do not drift into generic product promotion.
"""

    supplied_hook = _topic_supplied_hook(topic)
    supplied_hook_instruction = (
        f'\nThe topic contains a supplied hook: "{supplied_hook}". Script 1 MUST start directly with it; a leading audio tag is allowed.\n'
        if supplied_hook else ""
    )
    hook_instructions = f"""
HOOK REQUIREMENTS:
- Start with a topic-specific claim, mistake, question, result, data point, confession, demo, or open loop. Never put filler before the actual claim.
- Do not use greetings, "watch until the end" filler, or canned openings such as "stop stop stop", "okay listen", or "all right enough".
- Every script MUST include `hook_type` with exactly one of: result_first, mistake_prohibition, counterintuitive_claim, data_point, pain_question, personal_confession_demo, open_loop.
- Every script in this batch MUST use a different hook type and a different first-three-word opening.
- The first spoken words must carry topic-specific meaning, not a generic pattern interrupt.{supplied_hook_instruction}
"""

    if script_format == "storyboard_v3":
        duration_instructions = _target_duration_prompt(
            target_duration_seconds,
            storyboard=True,
        )
        # Из пресета, а не отдельной константой: «4-8 слов на реплику» рядом с
        # «6-8 битов» разрешало 48 слов при бюджете 26 — и правило, и бюджет
        # обязаны считаться от одного числа.
        shot_words = TARGET_VIDEO_DURATION_PRESETS[
            normalize_target_duration(target_duration_seconds)]["words_per_beat"]
        # Ритм перебивок — единственное место, где сценариста просят о другом.
        # По умолчанию перебивка редкая: она стоит целый клип и тарифицируется
        # от трёх секунд. Опцией — обязательная между говорящими кадрами: их
        # чередование само по себе и есть монтаж, за который платят.
        broll_rhythm, broll_run_rule, broll_cadence_rule = (
            (
                "- Roughly every other shot is a B-roll insert: the reel alternates between the "
                "presenter and what she is talking about, so plan the beats in pairs.",
                "- Two talking shots in a row are not allowed. If two consecutive beats both "
                "belong on camera, merge them into one talking shot rather than leaving them "
                "adjacent — a shorter reel beats a broken rhythm.",
                "- Every B-roll insert still has to earn its place: it shows the thing that "
                "exact line is about. If a line names nothing showable, that line belongs in "
                "the neighbouring talking shot, not in an invented insert.",
            ) if broll_between_talking else (
                "- Treat B-roll shares as soft creative guidance, never as quotas: aim for "
                "approximately 35-45% of the spoken timeline; 25-50% is an acceptable soft "
                "range when the exact subject needs less or more visual demonstration.",
                "- A visual change does not have to be B-roll. The app already cuts between a "
                "medium and a close camera on the same set, so a run of talking shots is not "
                "monotonous by itself — do not invent scenery changes to break it up.",
                "- B-roll is therefore the exception, not the rhythm. Never two B-roll shots in "
                "a row, and no more than one B-roll for every two talking shots.",
            )
        )
        prompt = f"""You are a senior short-form ad storyboard writer for TikTok/Instagram Reels.
Generate {num_scripts} storyboard-based video scripts for this product/business.
{lang_instructions}
{topic_instructions}
{hook_instructions}
PRODUCT ANALYSIS:
{json.dumps(analysis, indent=2)}

STYLE: {style_guide.get(style, style_guide['ugc'])}

Return a JSON array. Each script MUST be a storyboard for Kling V3 video generation:
[
  {{
    "title": "Short internal title",
    "hook_type": "result_first",
    "format": "storyboard_v3",
    "storyboard_pacing": "dynamic",
    "style": "{style}",
    "duration_seconds": {target_duration_seconds},
    "target_duration_seconds": {target_duration_seconds},
    "target_platform": "instagram",
    "hook_text": "2-6 word overlay hook",
    "shots": [
      {{
        "shot_number": 1,
        "start": 0,
        "end": 3,
        "role": "hook",
        "transition": "cut",
        "speech": "Exact line the actor says",
        "emotion": "excited",
        "overlay_text": "Short text on screen",
        "visual_type": "talking",
        "actor_in_frame": false
      }}
    ],
    "full_narration": "All shot speech joined exactly",
    "caption_keywords": ["2-4 emotionally loaded words from the narration, in the script language, for subtitle color-accents"],
    "hashtags": ["#reels"],
    "caption": "Suggested caption"
  }}
]

RULES:
{duration_instructions}
STORYBOARD PACING PROFILE:
- Set storyboard_pacing to "dynamic".
- One shot = one visual beat of about 2.5-4 seconds (5 at the absolute limit). Nothing shorter: the video model has no clip below two seconds, so a beat under that is paid for in full and still flashes past. Use the visual-beat count selected above for this duration — it is a ceiling as much as a target.
- The first shot and the last shot MUST be talking. The first shot delivers the hook; the last shot delivers the CTA or closing payoff.
- Never place two B-roll shots next to each other. Return to a talking shot between B-roll inserts.
{broll_rhythm}
- Approximately 10-20% may show the same actor from the reference image performing a directly relevant action. Approximately 15-30% may show a product, object, process, space, result, or immediately understandable visual analogy without the actor.
- Vary B-roll subject types across the script. Do not repeatedly show the actor from behind, the actor's hands, food preparation, or the same prop. Presenter B-roll must earn its place by making the exact spoken claim easier to understand.
{broll_run_rule}
- Every B-roll shot must be visually distinct from its neighbours (new subject or action) — the point of many short shots is variety, not the same insert repeated.
- You write the TEXT of this reel, not its pictures. Do not return scene, camera, actor_action or generation_prompt: a separate pass draws every shot from your beats, and a location or a camera invented here would only be thrown away.
- visual_type per shot: "talking" = the actor speaks to camera, lips visible; "broll" = an insert while the voiceover keeps playing. Choose it by the line itself — "talking" for the lines that carry the argument, "broll" for a line that names a thing, a process or a result, and only where a picture makes that exact line easier to understand.
- ALL talking shots happen in ONE place, chosen once for the whole reel. Never build a beat around a change of scenery: the app stages the talking shots itself and rotates its own cameras between them.
- A "broll" shot is the most expensive shot there is: the video model has no clip shorter than three seconds, so an insert carrying half a second of speech is billed as three full seconds and then flashes past. Give every B-roll shot a COMPLETE thought of its own — one whole sentence of 7-12 words — so it fills the time it costs. If a beat is too short for that, keep it on camera.
{broll_cadence_rule}
- A sentence that starts on camera finishes on camera. Cutting away mid-sentence is a deliberate accent, not a default: use it at most ONCE in the whole script, where the break itself is the point. Every other cut lands on a full stop.
- actor_in_frame per shot: true ONLY when a "broll" shot shows the SAME person who speaks in the talking shots (seen from behind, over the shoulder, her hands, her silhouette), false when the insert shows objects, food, an interior or anybody else. It is the difference between our presenter walking into her own kitchen and a random stranger appearing mid-reel — say it explicitly, we cannot guess it from the scene text. Always false for "talking" shots.
- Each shot MUST include role, visual_type, actor_in_frame, overlay_text, speech and transition — and nothing about the picture.
- Each shot MUST include emotion — one of: excited, warm, confident, calm, urgent, playful. Vary it across shots to follow the narrative arc.
- role must be one of: hook, problem, explanation, solution, proof, cta.
- transition should be "cut" or "smooth_0.3s".
- speech and overlay_text must be in {lang_name} — the user reads them in the app UI.
{_ACTOR_DIRECTION_ONLY_RULES}
- Apply the identity rule to every field you return. Do not return an actor_description field.
- Never build a beat around readable text — a number on a label, a date on a photo, a screen: the pass that draws the shot cannot render text, so the comparison has to work as a picture or not exist.
- Nothing in a "talking" beat may require the actor to move: no exercising, walking, drinking or standing up. Motion breaks lip-sync, and one authored talking shot is one paid take.
- Each TALKING shot's speech is ONE spoken phrase of {shot_words} words, 8 words HARD max ("broll" shots are the exception and carry a whole sentence, as above). Stay at the top of that range rather than the bottom: the video model never returns a clip shorter than about two seconds, so a two-word beat is billed as a full clip and then flashes past. Split narration at natural phrase boundaries so beats normally last about 2.5-4 seconds. One authored talking shot is one paid Avatar take; never request an internal jump cut or framing change inside it.
- Do not buy variety with extra shots. The app already adds a slow local camera push inside a talking shot, and that costs nothing, while one more shot costs a whole clip. Use the fewest shots that carry the meaning.
- Adding a shot does NOT add words: the total word budget above stays the same, the lines just get shorter. Match the selected total duration and word budget while keeping every talking shot at or under 8 seconds of speech, the practical limit of one Avatar take; when in doubt use fewer, fuller shots rather than more, thinner ones.
- Do not ask Kling to generate Russian audio. The app adds Russian voiceover later.
- Keep marketing copy punchy. If the user provided exact topic wording, preserve it.
- Actor gender is {actor_gender}; use it only for grammar when necessary, never to invent appearance.
- Avoid laptops, monitors, headset, microphones, studio AI background unless the product explicitly needs them.
"""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=32768,
        )
        scripts = _request_gemini_script_batch(
            lambda: _generate_analysis_content(
                client,
                contents=[prompt],
                config=config,
                text_model=text_model,
                fal_key=fal_key,
                fal_fallback_enabled=fal_fallback_enabled,
            ),
            num_scripts=num_scripts,
            require_shots=True,  # a script without shots is nothing to storyboard
            label="storyboard script",
            batch_validator=lambda batch: _validate_script_batch_hooks(batch, supplied_hook=supplied_hook),
        )

        for script in scripts:
            script["format"] = "storyboard_v3"
            script["storyboard_pacing"] = "dynamic"
            script["language"] = language
            script["target_duration_seconds"] = target_duration_seconds

        # Место и картинка — отдельными запросами, каждый со своими правилами.
        # Порядок обязателен: художник по кадрам должен видеть уже выбранный
        # сет, иначе говорящий кадр опять начнёт описывать свою комнату.
        scripts = generate_storyboard_sets(
            scripts, gemini_key, text_model=text_model, language=language,
            locations=_MAX_LOCATIONS if changing_locations else 1)
        scripts = generate_storyboard_visuals(
            scripts, gemini_key, text_model=text_model, language=language)

        for script in scripts:
            for shot in script.get("shots") or []:
                if (shot.get("generation_prompt") or "").strip():
                    shot["_generation_prompt_language"] = "en"
            script["shots"] = normalize_storyboard_shots(script)
            # The AI writes scene and generation_prompt together, so the prompt
            # matches this scene: stamp it as the baseline. Later, if the user
            # edits «Что в кадре», the prompt is rebuilt from the new scene.
            for shot in script["shots"]:
                shot["_prompt_source_scene"] = (shot.get("scene") or "").strip()
            _finalize_generated_script(script)
            _record_duration_verdict(script)
        print(f"[SaaSShorts] Generated {len(scripts)} storyboard scripts")
        return scripts

    duration_instructions = _target_duration_prompt(
        target_duration_seconds,
        storyboard=False,
    )
    ugc_bounds = _target_duration_timeline(target_duration_seconds)
    prompt = f"""You are a viral short-form video scriptwriter for TikTok/Instagram Reels.
Generate {num_scripts} video scripts to promote this product/business.
{lang_instructions}
{topic_instructions}
{hook_instructions}
PRODUCT ANALYSIS:
{json.dumps(analysis, indent=2)}

STYLE: {style_guide.get(style, style_guide['ugc'])}

{duration_instructions}

YOU MUST USE EXACTLY THIS 5-SEGMENT STRUCTURE. NO EXCEPTIONS:
1. HOOK ({ugc_bounds[0]}-{ugc_bounds[1]}s): type="hook", visual="actor_talking", broll_prompt=null — Avatar says a punchy hook.
2. B-ROLL 1 ({ugc_bounds[1]}-{ugc_bounds[2]}s): type="problem", visual="broll", broll_prompt="..." (REQUIRED) — Visual of the problem.
3. BODY ({ugc_bounds[2]}-{ugc_bounds[3]}s): type="solution", visual="actor_talking", broll_prompt=null — Avatar presents the solution.
4. B-ROLL 2 ({ugc_bounds[3]}-{ugc_bounds[4]}s): type="demo", visual="broll", broll_prompt="..." (REQUIRED) — Visual of the product.
5. CTA ({ugc_bounds[4]}-{ugc_bounds[5]}s): type="cta", visual="actor_talking", broll_prompt=null — Avatar says CTA with link in bio.

CRITICAL — READ CAREFULLY:
- EXACTLY 5 segments. Not 3, not 4, not 6. FIVE.
- Segments 2 and 4 MUST have visual="broll" and a non-null broll_prompt string.
- Segments 1, 3, 5 MUST have visual="actor_talking" and broll_prompt=null.
- duration_seconds should reflect the selected approximate {target_duration_seconds}-second target.
- full_narration = all narration text joined together.

Return a JSON array:
[
    {{
        "title": "Short internal title",
        "hook_type": "result_first",
        "style": "{style}",
        "duration_seconds": {target_duration_seconds},
        "target_duration_seconds": {target_duration_seconds},
        "target_platform": "tiktok",
        "hook_text": "Hook overlay text (2-5 words max)",
        "segments": [
            {{
                "type": "hook",
                "start": {ugc_bounds[0]},
                "end": {ugc_bounds[1]},
                "narration": "Punchy hook the actor says",
                "visual": "actor_talking",
                "broll_prompt": null,
                "emotion": "excited",
                "subtitle_text": "Hook phrase"
            }},
            {{
                "type": "problem",
                "start": {ugc_bounds[1]},
                "end": {ugc_bounds[2]},
                "narration": "Voiceover describing the pain point",
                "visual": "broll",
                "broll_prompt": "REQUIRED: visual of the problem relevant to the product, e.g. realistic everyday close-up of objects/food/hands showing the pain point. No people, no faces. No readable screens or text.",
                "emotion": "frustrated",
                "subtitle_text": "Pain phrase",
                "bullets": ["2-3 short punchy words naming the pain, in the script language"]
            }},
            {{
                "type": "solution",
                "start": {ugc_bounds[2]},
                "end": {ugc_bounds[3]},
                "narration": "Actor introduces the product naturally",
                "visual": "actor_talking",
                "broll_prompt": null,
                "emotion": "confident",
                "subtitle_text": "Solution phrase"
            }},
            {{
                "type": "demo",
                "start": {ugc_bounds[3]},
                "end": {ugc_bounds[4]},
                "narration": "Voiceover showing the product in action",
                "visual": "broll",
                "broll_prompt": "REQUIRED: visual of the product/result, e.g. real-world result or product in use, close-up of objects/hands. No people, no faces. No readable screens, UI or text.",
                "emotion": "excited",
                "subtitle_text": "Result phrase",
                "bullets": ["2-3 short benefit words, in the script language"]
            }},
            {{
                "type": "cta",
                "start": {ugc_bounds[4]},
                "end": {ugc_bounds[5]},
                "narration": "Short CTA mentioning link in bio",
                "visual": "actor_talking",
                "broll_prompt": null,
                "emotion": "confident",
                "subtitle_text": "Link in bio"
            }}
        ],
        "full_narration": "ALL segment narration joined in timeline order",
        "hashtags": ["#reels", "#product", "#ugc"],
        "caption": "Suggested Instagram/TikTok caption"
    }}
]

RULES:
- EXACTLY 5 segments in order: actor, broll, actor, broll, actor
- EXACTLY 2 broll segments with detailed broll_prompt (NOT null)
- full_narration = ALL segment narration joined in timeline order, including b-roll voiceover lines.
- Follow the selected target duration and total spoken-word budget above.
- Keep narrations punchy, conversational, with contractions
{_ACTOR_DIRECTION_ONLY_RULES}
- Apply the identity rule to every segment and broll_prompt. Do not return an actor_description field.
- B-roll prompts: cinematic, specific, detailed visual descriptions
- Each script should use a different pain point / angle
- CTA MUST be natural for the selected language. For English/Spanish, mention "link in bio" / "enlace en la bio". For Russian, use a DM CTA if the product context suggests it, e.g. "Напиши НЕДЕЛЯ — пришлю чеклист", otherwise use "ссылка в профиле".
- Write ALL text in {lang_name}
- Actor gender is {actor_gender}; use it only for grammar when necessary, never to invent appearance.
- Avoid laptops, monitors, headsets, microphones, gaming chairs, and visible screens unless the product explicitly needs them. """

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        max_output_tokens=32768,
    )
    scripts = _request_gemini_script_batch(
        lambda: _generate_analysis_content(
            client,
            contents=[prompt],
            config=config,
            text_model=text_model,
            fal_key=fal_key,
            fal_fallback_enabled=fal_fallback_enabled,
        ),
        num_scripts=num_scripts,
        require_shots=False,
        label="script",
        batch_validator=lambda batch: _validate_script_batch_hooks(batch, supplied_hook=supplied_hook),
    )

    for script in scripts:
        script["target_duration_seconds"] = target_duration_seconds
        _finalize_generated_script(script)
        _record_duration_verdict(script)

    print(f"[SaaSShorts] ✅ Generated {len(scripts)} scripts")
    return scripts


def generate_content_plan(
    business: dict,
    gemini_key: str,
    num_items: int = 12,
    period_days: int = 30,
    language: str = "ru",
    text_model: Optional[str] = None,
) -> list:
    """Monthly Reels/TikTok content plan for a saved business profile.

    Text-only Gemini call: returns video ideas the user later feeds into the
    script generator one by one, so each item must carry a self-sufficient
    topic sentence.
    """
    from google import genai
    from google.genai import types

    lang_name = {"es": "Spanish", "ru": "Russian"}.get(language, "English")
    name = (business.get("name") or "").strip() or "Product"
    description = (business.get("description") or "").strip()
    base_topic = (business.get("topic") or "").strip()

    print(f"[SaaSShorts] 📅 Generating content plan: {num_items} videos / {period_days} days for {name}...")

    client = genai.Client(api_key=gemini_key)

    topic_context = f"\nRecurring theme the owner cares about: {base_topic}" if base_topic else ""
    prompt = f"""You are a short-form content strategist for Instagram Reels / TikTok.
Build a {period_days}-day posting plan of {num_items} vertical videos for this business.

BUSINESS: {name}
DESCRIPTION: {description}{topic_context}

LANGUAGE: every user-facing text field MUST be in {lang_name}, written like a native content creator speaks.

Return a JSON array of exactly {num_items} items, ordered by day:
[
  {{
    "day": 1,
    "title": "Short working title (3-6 words)",
    "topic": "One or two full sentences describing exactly what this video is about — it will be fed to a script generator as the brief, so make it self-sufficient",
    "hook": "The first spoken line — a punchy pattern-interrupt hook",
    "goal": "one of: прогрев, вовлечение, доверие, продажа" ,
    "format_hint": "ugc or storyboard_v3",
    "cta": "Short call to action for the end of the video"
  }}
]

RULES:
- Spread "day" values across the {period_days}-day period (roughly even, no two items on the same day).
- Vary content types across the plan: pain-point videos, myth-busting, how-to tips, personal story, social proof, objection handling, direct offer.
- Follow a warm-up arc: early items build trust and engagement, selling items appear later and stay under 30% of the plan.
- goal must be exactly one of: прогрев, вовлечение, доверие, продажа.
- format_hint: "ugc" for talking-head style items, "storyboard_v3" for items that need scene variety.
- Hooks must be specific to this business, no generic clickbait.
- Hooks must start with the actual claim, not a greeting, "watch until the end" filler, or canned preamble.
- Across the plan, vary hook taxonomy: result-first, specific mistake/prohibition, counterintuitive claim, concrete data point, exact pain question, personal confession/demo, and open loop.
- Across the plan, vary the first three spoken words of every hook.
- Do NOT invent product features that are not in the description."""

    response = _generate_gemini_content(
        client,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=16384,
        ),
        text_model=text_model,
    )

    raw = response.text
    if not raw:
        raise Exception("Gemini returned empty response for content plan generation")

    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    start = text.find("[")
    end = text.rfind("]")
    unsliced = text[start:] if start != -1 else text
    if start != -1 and end != -1:
        text = text[start : end + 1]

    try:
        items = json.loads(text)
    except json.JSONDecodeError as e:
        items = _salvage_json_array(unsliced) if start != -1 else []
        if not items:
            raise Exception(f"Failed to parse content plan JSON: {e}\nRaw: {text[:500]}")
        print(
            f"[SaaSShorts] ⚠️ Content plan response truncated — "
            f"recovered {len(items)}/{num_items} complete item(s)."
        )

    normalized = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        normalized.append({
            "day": int(item.get("day") or (i + 1)),
            "title": (item.get("title") or "").strip() or f"Видео {i + 1}",
            "topic": (item.get("topic") or "").strip(),
            "hook": (item.get("hook") or "").strip(),
            "goal": (item.get("goal") or "").strip().lower(),
            "format_hint": (item.get("format_hint") or "ugc").strip().lower(),
            "cta": (item.get("cta") or "").strip(),
        })
    normalized.sort(key=lambda item: item["day"])

    print(f"[SaaSShorts] ✅ Content plan ready: {len(normalized)} items")
    return normalized


def _estimate_speech_duration(text: str) -> int:
    """Estimate spoken duration from narration, pauses, and audio directions."""
    raw = text or ""
    tags = re.findall(r"\[[^\]]+\]", raw)
    spoken = re.sub(r"\[[^\]]+\]", " ", raw).strip()
    words = [word for word in re.split(r"\s+", spoken) if word]
    pauses = len(re.findall(r"\.{3}|…|—", raw))
    if not words and not tags:
        return 0
    seconds = (
        len(words) / _SPEECH_WORDS_PER_SECOND
        + len(tags) * _SPEECH_TAG_SECONDS
        + pauses * _SPEECH_PAUSE_SECONDS
    )
    return max(5, min(90, round(seconds)))


def _split_text_for_segments(text: str, parts: int = 5) -> list:
    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return [""] * parts

    chunks = [""] * parts
    for i, sentence in enumerate(sentences):
        idx = min(parts - 1, round(i * parts / max(1, len(sentences))))
        chunks[idx] = f"{chunks[idx]} {sentence}".strip()
    return chunks


def _parse_timecode_seconds(value: str) -> float:
    value = (value or "").strip()
    match = re.match(r"(?:(\d+):)?(\d{1,2})(?:[.,](\d{1,3}))?$", value)
    if not match:
        return 0.0
    minutes = int(match.group(1) or 0)
    seconds = int(match.group(2) or 0)
    millis = match.group(3) or ""
    fraction = float(f"0.{millis}") if millis else 0.0
    return minutes * 60 + seconds + fraction


def _extract_labeled_line(block: str, labels: list) -> str:
    for label in labels:
        pattern = rf"{label}\s*[:：]\s*(.+)"
        match = re.search(pattern, block, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip().strip("«»\"")
    return ""


def _extract_storyboard_field(block: str, labels: list) -> str:
    for label in labels:
        pattern = rf"{label}\s*[:：]\s*(.*)"
        match = re.search(pattern, block, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).strip()
        if not value:
            for line in block[match.end():].splitlines():
                value = line.strip().lstrip(">").strip()
                if value:
                    break
        return value.strip().strip("«»\"“”*")
    return ""


def _storyboard_role_from_text(text: str, fallback: str = "") -> str:
    value = (text or "").strip().lower()
    role_map = [
        ("hook", ("hook", "хук")),
        ("problem", ("problem", "проблем")),
        ("explanation", ("explanation", "объяснен", "объяснени")),
        ("solution", ("solution", "решени")),
        ("proof", ("proof", "доказательств")),
        ("cta", ("cta", "призыв")),
        ("demo", ("demo", "демо")),
    ]
    for role, markers in role_map:
        if any(marker in value for marker in markers):
            return role
    return fallback or "shot"


def _storyboard_transition_from_text(text: str) -> str:
    value = (text or "").strip().lower()
    if not value:
        return "cut"
    if "плав" in value or "smooth" in value or "fade" in value:
        return "smooth_0.3s"
    if "резк" in value or "cut" in value or "склей" in value:
        return "cut"
    return value


def build_custom_storyboard_script(
    custom_script: str,
    analysis: dict,
    style: str = "ugc",
    language: str = "en",
    actor_gender: str = "female",
    topic: str = None,
) -> dict:
    """Convert a user-provided storyboard into shots without rewriting copy."""
    text = custom_script.strip()
    title_base = (topic or analysis.get("product_name") or "Storyboard").strip()
    title = title_base[:80] or "Storyboard"
    matches = list(re.finditer(r"(?im)^\s*(?:#+\s*)?(?:КАДР|РљРђР”Р |SHOT)\s*(\d+)[^\n]*", text))
    blocks = []
    if matches:
        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            blocks.append(text[start:end].strip())

    shots = []
    if blocks:
        transition_map = {}
        for match in re.finditer(r"\|\s*(\d+)\s*(?:→|->|в†’)\s*\d+\s*\|[^|]*\|\s*([^|]+)\|", text):
            try:
                transition_map[int(match.group(1))] = _storyboard_transition_from_text(match.group(2))
            except ValueError:
                pass

        cursor = 0.0
        for idx, block in enumerate(blocks, start=1):
            header_line = block.splitlines()[0] if block.splitlines() else ""
            time_match = re.search(r"(\d{1,2}:\d{2}(?:[.,]\d+)?)\s*(?:–|—|-|вЂ“|вЂ”)\s*(\d{1,2}:\d{2}(?:[.,]\d+)?)", block)
            if time_match:
                start = _parse_timecode_seconds(time_match.group(1))
                end = _parse_timecode_seconds(time_match.group(2))
            else:
                start = cursor
                end = cursor + 3
            if end <= start:
                end = start + 3
            cursor = end

            role = _storyboard_role_from_text(header_line, f"shot_{idx}")
            actor_action = _extract_storyboard_field(block, ["Что делает", "Действие", "Action", "Actor action"])
            scene = _extract_storyboard_field(block, ["Сцена", "Scene", "Локация", "Location"]) or actor_action or header_line
            camera = _extract_storyboard_field(block, ["Камера", "Camera"])
            speech = _extract_storyboard_field(block, ["Она говорит", "Он говорит", "Говорит", "Speech", "Line"])
            overlay_text = _extract_storyboard_field(block, ["Текст на экране", "Текст", "Text", "Overlay"])
            transition = _storyboard_transition_from_text(
                _extract_storyboard_field(block, ["Переход", "Transition"]) or transition_map.get(idx, "cut")
            )
            prompt_bits = [
                "vertical 9:16 realistic phone video",
                "same actor/character",
                scene,
                actor_action,
                camera,
                "natural light",
            ]
            shots.append({
                "shot_number": idx,
                "start": start,
                "end": end,
                "role": role,
                "scene": scene,
                "camera": camera,
                "action": actor_action,
                "actor_action": actor_action,
                "speech": speech,
                "overlay_text": overlay_text,
                "transition": transition,
                "visual_type": "talking" if speech else "broll",
                "generation_prompt": ", ".join(bit for bit in prompt_bits if bit),
            })
    else:
        duration = _estimate_speech_duration(text)
        chunks = [chunk for chunk in _split_text_for_segments(text, 6) if chunk]
        cursor = 0
        shot_duration = max(3, min(5, round(duration / max(1, len(chunks)))))
        for idx, chunk in enumerate(chunks, start=1):
            role = "hook" if idx == 1 else ("cta" if idx == len(chunks) else "body")
            shots.append({
                "shot_number": idx,
                "start": cursor,
                "end": cursor + shot_duration,
                "role": role,
                "scene": "Actor in a realistic social video scene",
                "camera": "vertical handheld social video",
                "action": "speaks directly to camera",
                "actor_action": "speaks directly to camera",
                "speech": chunk,
                "overlay_text": chunk[:50],
                "transition": "cut",
                "visual_type": "talking",
                "generation_prompt": "vertical 9:16 realistic phone video, same actor/character, natural light",
            })
            cursor += shot_duration

    shots = normalize_storyboard_shots({"shots": shots, "language": language})
    full_narration = " ".join(shot.get("speech", "") for shot in shots if shot.get("speech")).strip()
    return {
        "title": title,
        "format": "storyboard_v3",
        "language": language,
        "style": style,
        "duration_seconds": int(max((shot.get("end", 0) for shot in shots), default=0)),
        "target_platform": "instagram",
        "hook_text": (shots[0].get("overlay_text") or shots[0].get("speech", "")[:50]) if shots else title,
        "shots": shots,
        "full_narration": full_narration or text,
        "hashtags": ["#reels", "#shorts", "#ugc"] if language != "ru" else ["#рилс", "#привычки", "#питание"],
        "caption": topic or analysis.get("description") or title,
        "custom_script": True,
    }

def build_custom_script(
    custom_script: str,
    analysis: dict,
    style: str = "ugc",
    language: str = "en",
    actor_gender: str = "female",
    topic: str = None,
    script_format: str = "ugc",
) -> dict:
    """Create an AI Shorts script object without rewriting user narration."""
    if script_format == "storyboard_v3":
        return build_custom_storyboard_script(custom_script, analysis, style, language, actor_gender, topic=topic)

    narration = custom_script.strip()
    if not narration:
        raise ValueError("Custom script is empty")

    duration = _estimate_speech_duration(narration)
    chunks = _split_text_for_segments(narration, 5)
    title_base = (topic or analysis.get("product_name") or "Custom Script").strip()
    title = title_base[:80] or "Custom Script"
    product_name = analysis.get("product_name") or title
    product_desc = analysis.get("description") or analysis.get("value_proposition") or product_name
    language_cta = {
        "ru": "Напиши НЕДЕЛЯ",
        "es": "Enlace en la bio",
        "en": "Link in bio",
    }.get(language, "Link in bio")

    hook_words = re.sub(r"\s+", " ", narration).split(" ")[:6]
    hook_text = " ".join(hook_words).strip(" .,!?") or title

    broll_problem = (
        f"Vertical smartphone-style b-roll showing the problem behind: {topic or product_desc}. "
        "Realistic home setting, natural light, authentic everyday scene."
    )
    broll_demo = (
        f"Vertical smartphone-style b-roll showing the product/result for {product_name}: "
        "phone tracker, checklist, simple food prep, clean table, filmed on a phone."
    )

    # Keep a familiar 5-part structure for preview and b-roll timing. The final
    # voiceover uses full_narration exactly, so this does not rewrite the script.
    t1 = min(5, max(3, round(duration * 0.20)))
    t2 = min(duration - 7, t1 + max(3, round(duration * 0.15)))
    t3 = min(duration - 4, t2 + max(4, round(duration * 0.28)))
    t4 = min(duration - 2, t3 + max(3, round(duration * 0.18)))

    return {
        "title": title,
        "style": style,
        "duration_seconds": duration,
        "target_platform": "instagram",
        "hook_text": hook_text,
        "segments": [
            {
                "type": "hook",
                "start": 0,
                "end": t1,
                "narration": chunks[0],
                "visual": "actor_talking",
                "broll_prompt": None,
                "emotion": "direct",
                "subtitle_text": hook_text,
            },
            {
                "type": "problem",
                "start": t1,
                "end": t2,
                "narration": chunks[1],
                "visual": "broll",
                "broll_prompt": broll_problem,
                "emotion": "frustrated",
                "subtitle_text": chunks[1][:80] or "Problem",
            },
            {
                "type": "solution",
                "start": t2,
                "end": t3,
                "narration": chunks[2],
                "visual": "actor_talking",
                "broll_prompt": None,
                "emotion": "confident",
                "subtitle_text": chunks[2][:80] or "Solution",
            },
            {
                "type": "demo",
                "start": t3,
                "end": t4,
                "narration": chunks[3],
                "visual": "broll",
                "broll_prompt": broll_demo,
                "emotion": "calm",
                "subtitle_text": chunks[3][:80] or "Demo",
            },
            {
                "type": "cta",
                "start": t4,
                "end": duration,
                "narration": chunks[4],
                "visual": "actor_talking",
                "broll_prompt": None,
                "emotion": "confident",
                "subtitle_text": language_cta,
            },
        ],
        "full_narration": narration,
        "hashtags": ["#reels", "#shorts", "#ugc"] if language != "ru" else ["#рилс", "#привычки", "#питание"],
        "caption": topic or product_desc,
        "custom_script": True,
    }


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Asset Generation
# ═══════════════════════════════════════════════════════════════════════

class FalUnreachable(Exception):
    """Запрос не дошёл до fal: DNS, обрыв соединения, отказ сети.

    Отдельный тип нужен ради двух решений выше по стеку, и оба про деньги.
    Такую попытку нельзя записывать в вердикты модерации — модель фотографию не
    видела, — и нельзя считать оплаченной: генерации не было. Всё остальное
    (404, 422, FAILED, таймаут) до fal дошло и разбирается по-другому.
    """


def _fal_run(model_id: str, input_data: dict, fal_key: str, timeout: int = 600) -> dict:
    """
    Submit a job to fal.ai queue, poll for completion, return result.
    Uses the URLs returned by the submit response (as per fal.ai docs).
    """

    def _with_request_meta(result: Any, request_id: Optional[str], status_url: str = "", response_url: str = "") -> dict:
        payload = dict(result) if isinstance(result, dict) else {"result": result}
        payload["_fal_request"] = {
            "model_id": model_id,
            "request_id": request_id,
            "status_url": status_url,
            "response_url": response_url,
        }
        return payload

    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }

    # ── Step 1: Submit to queue ──
    submit_url = f"{FAL_QUEUE_BASE}/{model_id}"
    print(f"[fal.ai] Submitting to {submit_url}...")

    resp = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(submit_url, headers=headers, json=input_data)
            break
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            # Connect never happened, so the request did not reach fal:
            # retrying cannot enqueue a duplicate (paid) job.
            if attempt == 2:
                raise FalUnreachable(f"fal.ai submit request failed for {model_id} at {submit_url}: {e}") from e
            wait = 3 * (attempt + 1)
            print(f"[fal.ai] Submit connect failed ({e}), retrying in {wait}s...")
            time.sleep(wait)
        except httpx.RequestError as e:
            raise FalUnreachable(f"fal.ai submit request failed for {model_id} at {submit_url}: {e}") from e

    if resp.status_code >= 400:
        print(f"[fal.ai] Submit error: {resp.text[:500]}")
        raise Exception(f"fal.ai error ({resp.status_code}): {resp.text[:300]}")

    try:
        submit_data = resp.json()
    except json.JSONDecodeError:
        raise Exception(f"fal.ai invalid JSON: {resp.text[:300]}")

    request_id = submit_data.get("request_id")
    if not request_id:
        # Synchronous result (no queue)
        return _with_request_meta(submit_data, None)

    # Use the URLs from the submit response (guaranteed correct per docs)
    status_url = submit_data.get("status_url", f"{FAL_QUEUE_BASE}/{model_id}/requests/{request_id}/status")
    response_url = submit_data.get("response_url", f"{FAL_QUEUE_BASE}/{model_id}/requests/{request_id}")

    print(f"[fal.ai] Queued: {request_id}")
    print(f"[fal.ai] Status URL: {status_url}")

    # ── Step 2: Poll for completion ──
    poll_headers = {"Authorization": f"Key {fal_key}"}
    start = time.time()

    while time.time() - start < timeout:
        elapsed = int(time.time() - start)
        try:
            with httpx.Client(timeout=30.0) as client:
                poll_resp = client.get(f"{status_url}?logs=1", headers=poll_headers)
            status_data = poll_resp.json()
        except Exception as e:
            print(f"[fal.ai] Poll error (retrying): {e}")
            time.sleep(5)
            continue

        status = status_data.get("status", "UNKNOWN")

        if status == "COMPLETED":
            print(f"[fal.ai] ✅ Completed in {elapsed}s! Fetching result...")
            for attempt in range(3):
                try:
                    with httpx.Client(timeout=120.0) as client:
                        result_resp = client.get(response_url, headers=poll_headers)
                        result_resp.raise_for_status()
                        return _with_request_meta(result_resp.json(), request_id, status_url, response_url)
                except httpx.RequestError as e:
                    if attempt == 2:
                        raise Exception(f"fal.ai result fetch failed for {model_id} at {response_url}: {e}") from e
                    print(f"[fal.ai] Result fetch failed ({e}), retrying in 5s...")
                    time.sleep(5)
                except httpx.HTTPStatusError as e:
                    raise Exception(f"fal.ai result fetch error ({e.response.status_code}) for {model_id}: {e.response.text[:300]}") from e

        elif status in ("FAILED", "CANCELLED"):
            error = status_data.get("error", "unknown error")
            raise Exception(f"fal.ai job {status}: {error}")

        # Log progress
        queue_pos = status_data.get("queue_position", "")
        pos_info = f" (pos: {queue_pos})" if queue_pos != "" else ""
        print(f"[fal.ai] {model_id}: {status}{pos_info} ({elapsed}s)")
        time.sleep(5)

    # One last fetch prevents losing a paid result if the job completed just
    # after the local polling window or during a transient status request error.
    try:
        with httpx.Client(timeout=120.0) as client:
            poll_resp = client.get(f"{status_url}?logs=1", headers=poll_headers)
            status_data = poll_resp.json()
        if status_data.get("status") == "COMPLETED":
            print(f"[fal.ai] Completed after timeout window. Fetching result for {request_id}...")
            try:
                with httpx.Client(timeout=120.0) as client:
                    result_resp = client.get(response_url, headers=poll_headers)
                    result_resp.raise_for_status()
                    return _with_request_meta(result_resp.json(), request_id, status_url, response_url)
            except httpx.RequestError as e:
                raise Exception(f"fal.ai result fetch failed for {model_id} at {response_url}: {e}") from e
            except httpx.HTTPStatusError as e:
                raise Exception(f"fal.ai result fetch error ({e.response.status_code}) for {model_id}: {e.response.text[:300]}") from e
    except Exception as e:
        print(f"[fal.ai] Final fetch after timeout failed: {e}")

    raise Exception(
        f"fal.ai job timed out after {timeout}s for {model_id} "
        f"(request_id={request_id}, status_url={status_url})"
    )


def _fal_upload_file(file_path: str, fal_key: str) -> str:
    """Upload a local file to fal.ai CDN storage and return public URL."""
    headers = {"Authorization": f"Key {fal_key}"}

    filename = os.path.basename(file_path)
    cache_path = f"{file_path}.fal_url.txt"
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_url = f.read().strip()
            if cached_url.startswith(("http://", "https://")):
                print(f"[fal.ai] Reusing uploaded {filename} -> {cached_url}")
                return cached_url
        except Exception as e:
            print(f"[fal.ai] Upload URL cache ignored for {filename}: {e}")

    ext = os.path.splitext(filename)[1].lower()
    content_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".mp4": "video/mp4",
        ".webp": "image/webp",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    file_size = os.path.getsize(file_path)
    print(f"[fal.ai] Uploading {filename} ({file_size} bytes)...")

    upload_info = None
    last_error = None
    for attempt in range(1, 4):
        try:
            with httpx.Client(timeout=180.0) as client:
                resp = client.post(
                    "https://rest.alpha.fal.ai/storage/upload/initiate",
                    headers={**headers, "Content-Type": "application/json"},
                    json={"file_name": filename, "content_type": content_type},
                )
                resp.raise_for_status()
                upload_info = resp.json()
            break
        except Exception as e:
            last_error = e
            print(f"[fal.ai] Upload init failed for {filename} (attempt {attempt}/3): {e}")
            if attempt < 3:
                time.sleep(3 * attempt)

    if not upload_info:
        raise Exception(f"fal.ai upload init failed for {filename}: {last_error}")

    upload_url = upload_info["upload_url"]
    file_url = upload_info["file_url"]

    # Upload file content
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    uploaded = False
    last_error = None
    for attempt in range(1, 4):
        try:
            with httpx.Client(timeout=600.0) as client:
                resp = client.put(
                    upload_url,
                    content=file_bytes,
                    headers={"Content-Type": content_type},
                )
                resp.raise_for_status()
            uploaded = True
            break
        except Exception as e:
            last_error = e
            print(f"[fal.ai] Upload failed for {filename} (attempt {attempt}/3): {e}")
            if attempt < 3:
                time.sleep(5 * attempt)

    if not uploaded:
        raise Exception(f"fal.ai upload failed for {filename}: {last_error}")

    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(file_url)
    except Exception as e:
        print(f"[fal.ai] Could not write upload URL cache for {filename}: {e}")

    print(f"[fal.ai] Uploaded {filename} → {file_url}")
    return file_url


def generate_actor_images(
    description: str, fal_key: str, output_dir: str, title_slug: str, num_options: int = 3,
    product_description: str = None,
) -> List[str]:
    """Generate multiple hyper-realistic actor portrait options using Flux 2 Pro."""
    print(f"[SaaSShorts] 🎨 Generating {num_options} actor image options (Flux 2 Pro)...")

    # Clean description: strip obvious actions, but preserve user-specified outfit/background.
    clean_desc = description
    for remove in ["hablando", "talking", "sentad", "sitting"]:
        if remove in clean_desc.lower():
            idx = clean_desc.lower().find(remove)
            if idx > 10:
                clean_desc = clean_desc[:idx].rstrip(" ,.")

    import random
    img_num = random.randint(1000, 9999)
    realism_guardrails = (
        "Vertical 9:16 smartphone portrait for Instagram Reels, upper torso visible, centered face, "
        "natural headroom, hands and shoulders inside frame. "
        "Sharp realistic smartphone portrait, natural skin texture, normal human facial asymmetry, "
        "not over-smoothed, not CGI, not beauty-filtered, not a studio headshot. "
        "Use only the outfit/background/details explicitly described by the user. "
        "If no background is described, use a simple neutral wall or clean home interior. "
        "Do NOT include laptop, computer monitor, visible screens, headphones, headset, microphone, "
        "office desk, gaming chair, heavy blur, artificial bokeh, text, logos, extra hands, or props."
    )

    if product_description:
        prompt = f"""IMG_{img_num}.jpg Realistic candid selfie portrait of {clean_desc}, casually holding {product_description}, showing it to the camera with a natural subtle smile. Product clearly visible in hand. Casual and real, not an ad. {realism_guardrails}"""
    else:
        prompt = f"""IMG_{img_num}.jpg Realistic candid selfie portrait of {clean_desc}, looking directly at the camera with a calm natural expression and subtle confident smile. Not posed, casual and real. {realism_guardrails}"""

    print(f"[SaaSShorts]   Prompt: {prompt[:120]}...{' (with product)' if product_description else ''}")

    paths = []
    # Flux 2 Pro — #1 for photorealistic faces
    def _gen_one(i):
        result = _fal_run(
            "fal-ai/flux-2-pro",
            {
                "prompt": prompt,
                "image_size": "portrait_16_9",
                "safety_tolerance": 5,
                "seed": random.randint(0, 999999),
            },
            fal_key,
            timeout=1200,
        )
        images = result.get("images") or result.get("output", [])
        if not images:
            raise Exception(f"No images in actor result: {list(result.keys())}")
        img_url = images[0]["url"] if isinstance(images[0], dict) else images[0]
        img_path = os.path.join(output_dir, f"{title_slug}_actor_option_{i}.png")
        with httpx.Client(timeout=60.0) as client:
            img_resp = client.get(img_url)
            with open(img_path, "wb") as f:
                f.write(img_resp.content)
        print(f"[SaaSShorts] ✅ Actor option {i+1}: {img_path}")
        return img_path

    with ThreadPoolExecutor(max_workers=num_options) as executor:
        futures = [executor.submit(_gen_one, i) for i in range(num_options)]
        for future in as_completed(futures):
            paths.append(future.result())

    return sorted(paths)


def generate_actor_image(
    description: str, fal_key: str, output_path: str
) -> str:
    """Generate a single actor image using Recraft V4."""
    output_dir = os.path.dirname(output_path)
    title_slug = os.path.basename(output_path).replace("_actor.png", "")
    paths = generate_actor_images(description, fal_key, output_dir, title_slug, num_options=1)
    if paths:
        import shutil
        shutil.move(paths[0], output_path)
    return output_path


_AUDIO_TAG_RE = re.compile(r"\[[A-Za-z][^\]\n]*\]")
_WHISPER_TAG_RE = re.compile(r"\[(?:whispers?|whispering)\]", re.IGNORECASE)


def _strip_audio_tags(text: str) -> str:
    """Remove ElevenLabs v3 audio tags ([sighs], [excited]...) for TTS engines that would read them aloud."""
    return re.sub(r"\s{2,}", " ", _AUDIO_TAG_RE.sub(" ", text or "")).strip()


def _shot_performance(shot: dict) -> str:
    explicit = str((shot or {}).get("_performance") or "").strip().lower()
    if explicit in {"normal", "whisper"}:
        return explicit
    return "whisper" if _WHISPER_TAG_RE.search((shot or {}).get("speech") or "") else "normal"


def generate_voiceover(
    text: str,
    elevenlabs_key: str,
    output_path: str,
    voice_id: str = "21m00Tcm4TlvDq8ikWAM",
    model_id: str = "eleven_v3",
) -> str:
    """Generate voiceover audio using ElevenLabs TTS. Returns the model actually used.

    Defaults to eleven_v3 in Creative mode (stability 0.0): lively human
    delivery that honors [sighs]/[excited]-style audio tags in the text.
    Falls back to multilingual_v2 with the legacy settings when the account
    has no v3 access; tags are stripped there since v2 would voice them.
    The fallback voice sounds noticeably more robotic, so the caller must
    persist the returned model — otherwise "why does it sound AI" is
    undebuggable after the fact.
    """
    print(f"[SaaSShorts] 🎙️ Generating voiceover ({len(text)} chars, {model_id})...")

    url = f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": elevenlabs_key,
        "Content-Type": "application/json",
    }

    def request_body(model: str) -> dict:
        if model == "eleven_v3":
            return {
                "text": text,
                "model_id": model,
                "voice_settings": {"stability": 0.0},
            }
        return {
            "text": _strip_audio_tags(text),
            "model_id": model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.4,
                "use_speaker_boost": True,
            },
        }

    def post_with_retries(client, body, attempts=3):
        # Retry transient failures here so a network blip doesn't cascade into
        # the MiniMax provider fallback (a completely different voice).
        last_error = None
        for attempt in range(attempts):
            if attempt:
                time.sleep(2 ** attempt)
            try:
                resp = client.post(url, headers=headers, json=body)
            except httpx.RequestError as e:
                last_error = e
                print(f"[SaaSShorts] ⚠️ ElevenLabs network error (attempt {attempt + 1}/{attempts}): {e}")
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = Exception(f"ElevenLabs TTS error ({resp.status_code}): {resp.text[:200]}")
                print(f"[SaaSShorts] ⚠️ ElevenLabs transient error {resp.status_code} (attempt {attempt + 1}/{attempts})")
                continue
            return resp
        raise last_error

    used_model = model_id
    with httpx.Client(timeout=180.0) as client:
        resp = post_with_retries(client, request_body(model_id))
        if resp.status_code != 200 and model_id == "eleven_v3":
            print(f"[SaaSShorts] ⚠️ eleven_v3 failed ({resp.status_code}), retrying with multilingual_v2...")
            used_model = "eleven_multilingual_v2"
            resp = post_with_retries(client, request_body(used_model))
        if resp.status_code != 200:
            raise Exception(f"ElevenLabs TTS error ({resp.status_code}): {resp.text}")

        with open(output_path, "wb") as f:
            f.write(resp.content)

    print(f"[SaaSShorts] ✅ Voiceover: {output_path} (model: {used_model})")
    return used_model


def generate_voiceover_minimax(
    text: str,
    fal_key: str,
    output_path: str,
    voice_id: str = "Russian_AmbitiousWoman",
    language: str = "en",
) -> str:
    """Generate voiceover audio using fal.ai MiniMax Speech-02 HD."""
    text = _strip_audio_tags(text)
    print(f"[SaaSShorts] Generating fal MiniMax voiceover ({len(text)} chars, {voice_id})...")

    language_boost = {
        "ru": "Russian",
        "es": "Spanish",
        "en": "English",
    }.get(language, "auto")

    result = _fal_run(
        "fal-ai/minimax/speech-02-hd",
        {
            "text": text,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
                "english_normalization": False,
            },
            "audio_setting": {
                "sample_rate": "44100",
                "bitrate": "256000",
                "format": "mp3",
                "channel": "1",
            },
            "language_boost": language_boost,
            "output_format": "url",
        },
        fal_key,
        timeout=600,
    )

    audio = result.get("audio") or result.get("file") or result.get("output")
    audio_url = audio.get("url") if isinstance(audio, dict) else audio
    if not audio_url:
        raise Exception(f"fal MiniMax TTS returned no audio URL: {result}")

    try:
        with httpx.Client(timeout=180.0) as client:
            resp = client.get(audio_url)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)
    except httpx.RequestError as e:
        raise Exception(f"fal MiniMax audio download failed at {audio_url}: {e}") from e
    except httpx.HTTPStatusError as e:
        raise Exception(f"fal MiniMax audio download error ({e.response.status_code}): {e.response.text[:300]}") from e

    print(f"[SaaSShorts] fal MiniMax voiceover: {output_path}")
    return output_path


def _minimax_voice_for(language: str, actor_gender: str, voice_id: str = None) -> str:
    if voice_id:
        return voice_id
    if language == "ru":
        return "Russian_ReliableMan" if actor_gender == "male" else "Russian_AmbitiousWoman"
    if language == "es":
        return "Spanish_ReliableMan" if actor_gender == "male" else "Spanish_ConfidentWoman"
    return "Deep_Voice_Man" if actor_gender == "male" else "Wise_Woman"


DEFAULT_ELEVENLABS_VOICES_BY_LANGUAGE = {
    "ru": "D5RRIJYa9pFwxiSpbGbR",  # Victoria — native Russian, warm UGC voice
    "en": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "es": "21m00Tcm4TlvDq8ikWAM",  # Rachel (multilingual handles Spanish)
}


# Английские фронтенд-фолбэки: для не-английского текста считаем их «выбор не
# сделан» — Rachel, читающая русский сценарий, всегда ошибка состояния UI.
_GENERIC_ENGLISH_FALLBACK_VOICES = {"21m00Tcm4TlvDq8ikWAM"}  # Rachel


def _elevenlabs_voice_for(language: str, voice_id: str = None) -> str:
    """Default ElevenLabs voice per script language when the user picked none."""
    if voice_id and not (language == "ru" and voice_id in _GENERIC_ENGLISH_FALLBACK_VOICES):
        return voice_id
    return DEFAULT_ELEVENLABS_VOICES_BY_LANGUAGE.get(language, "21m00Tcm4TlvDq8ikWAM")


def _voice_provenance(
    config: dict,
    *,
    provider_used: str,
    model_used: str,
    elevenlabs_voice_id: str,
    minimax_voice_id: str,
) -> dict:
    """Describe the voice that actually produced the audio, including fallbacks."""
    minimax = provider_used == "fal_minimax"
    voice_id = minimax_voice_id if minimax else elevenlabs_voice_id
    configured_name = (
        config.get("minimax_voice_name") if minimax else config.get("voice_name")
    )
    return {
        "voice_id": voice_id or "",
        "voice_name": (configured_name or "").strip() or voice_id or "",
        "voice_model": model_used or "",
        "voice_selection_source": config.get("voice_selection_source") or "request",
    }


def _tts_signature(
    text: str,
    provider: str,
    elevenlabs_voice_id: str,
    minimax_voice_id: str,
    language: str,
    actor_gender: str,
) -> str:
    payload = {
        "text": text,
        "provider": provider,
        "elevenlabs_voice_id": elevenlabs_voice_id,
        "minimax_voice_id": minimax_voice_id,
        "language": language,
        "actor_gender": actor_gender,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _read_tts_metadata(audio_path: str) -> dict:
    meta_path = f"{audio_path}.meta.json"
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_tts_metadata(audio_path: str, metadata: dict) -> None:
    meta_path = f"{audio_path}.meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def generate_voiceover_with_fallback(
    text: str,
    output_path: str,
    *,
    provider: str,
    fal_key: str,
    elevenlabs_key: str = None,
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM",
    minimax_voice_id: str = None,
    language: str = "en",
    actor_gender: str = "female",
    log: Callable[[str], None] = print,
) -> dict:
    """Generate TTS with an optional ElevenLabs -> fal MiniMax fallback."""
    if not (text or "").strip():
        # Synthesising an empty string yields a sub-second silent blip that later
        # collapses to a headerless MP3 and makes Kling reject the whole job with
        # an opaque 422. Fail here, where the cause ("no spoken lines") is obvious.
        raise ValueError(
            "Voiceover text is empty — add spoken lines to the script before generating video."
        )
    provider = (provider or "auto").lower()
    minimax_voice_id = _minimax_voice_for(language, actor_gender, minimax_voice_id)

    if provider == "fal_minimax" or (provider == "auto" and not elevenlabs_key):
        if provider == "auto" and not elevenlabs_key:
            log("[1/6] ElevenLabs key missing; using fal MiniMax TTS fallback.")
        generate_voiceover_minimax(text, fal_key, output_path, minimax_voice_id, language)
        return {"path": output_path, "provider": "fal_minimax", "voice_id": minimax_voice_id, "model": "minimax-speech-02-hd"}

    if provider not in ("auto", "elevenlabs"):
        raise Exception(f"Unknown TTS provider: {provider}")
    if not elevenlabs_key:
        raise Exception("ElevenLabs API key is required for ElevenLabs TTS.")

    try:
        used_model = generate_voiceover(text, elevenlabs_key, output_path, elevenlabs_voice_id)
        if used_model != "eleven_v3":
            log(f"[1/6] ⚠️ ElevenLabs used {used_model} (v3 unavailable) — delivery will sound flatter than the approved v3 Creative voice.")
        return {"path": output_path, "provider": "elevenlabs", "voice_id": elevenlabs_voice_id, "model": used_model}
    except Exception as error:
        if provider != "auto":
            raise
        log(f"[1/6] ElevenLabs TTS failed; falling back to fal MiniMax TTS: {error}")
        generate_voiceover_minimax(text, fal_key, output_path, minimax_voice_id, language)
        return {"path": output_path, "provider": "fal_minimax", "voice_id": minimax_voice_id, "model": "minimax-speech-02-hd"}


def get_elevenlabs_voices(elevenlabs_key: str) -> list:
    """Fetch available voices from ElevenLabs."""
    headers = {"xi-api-key": elevenlabs_key}

    voices_data = []
    try:
        next_page_token = None
        with httpx.Client(timeout=20.0) as client:
            for _ in range(5):
                params = {
                    "page_size": 100,
                    "include_total_count": "true",
                    "sort": "created_at_unix",
                    "sort_direction": "desc",
                }
                if next_page_token:
                    params["next_page_token"] = next_page_token

                resp = client.get(
                    "https://api.elevenlabs.io/v2/voices",
                    headers=headers,
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                voices_data.extend(data.get("voices", []))
                if not data.get("has_more") or not data.get("next_page_token"):
                    break
                next_page_token = data.get("next_page_token")
    except Exception:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(f"{ELEVENLABS_API_BASE}/voices", headers=headers)
            if resp.status_code != 200:
                return []
            data = resp.json()
            voices_data = data.get("voices", [])

    voices = []
    seen = set()
    for v in voices_data:
        voice_id = v.get("voice_id")
        if not voice_id or voice_id in seen:
            continue
        seen.add(voice_id)
        voices.append({
            "voice_id": voice_id,
            "name": v.get("name", ""),
            "category": v.get("category", ""),
            "labels": v.get("labels", {}),
            "description": v.get("description", ""),
            "preview_url": v.get("preview_url", ""),
            "verified_languages": v.get("verified_languages", []),
            "is_owner": v.get("is_owner", False),
            "created_at_unix": v.get("created_at_unix"),
        })

    return voices


# ═══════════════════════════════════════════════════════════════════════
# Phase 3: Video Generation
# ═══════════════════════════════════════════════════════════════════════

KLING_AVATAR_TIERS = {
    "standard": {
        "model_id": "fal-ai/kling-video/ai-avatar/v2/standard",
        "cost_per_second": 0.0562,
        "label": "Kling Avatar v2 Standard",
    },
    "pro": {
        "model_id": "fal-ai/kling-video/ai-avatar/v2/pro",
        "cost_per_second": 0.115,
        "label": "Kling Avatar v2 Pro",
    },
}


def build_kling_avatar_request(
    image_url: str,
    audio_url: str,
    prompt: str = "",
    tier: str = "standard",
) -> tuple[str, dict]:
    """Build fal.ai Kling Avatar v2 model id and payload for Standard/Pro.

    The avatar model is driven by the reference frame and the audio; the prompt
    field only hurts. Side-by-side on the same image and audio (2026-07-26):
    without a prompt the frame is clean, with our prompt Kling paints garbled
    caption-like text along the bottom — the very thing the prompt asked it not
    to do, because the model has no negative prompting and "no text, no
    watermark, no subtitles" just seeds it with text. So an empty prompt is
    left out of the payload entirely.
    """
    tier = (tier or "standard").strip().lower()
    if tier not in KLING_AVATAR_TIERS:
        raise ValueError(f"Unsupported Kling Avatar tier: {tier}")
    payload = {
        "image_url": image_url,
        "audio_url": audio_url,
    }
    if (prompt or "").strip():
        payload["prompt"] = prompt
    return KLING_AVATAR_TIERS[tier]["model_id"], payload


def kling_avatar_cost_per_second(tier: str = "standard") -> float:
    tier = (tier or "standard").strip().lower()
    if tier not in KLING_AVATAR_TIERS:
        raise ValueError(f"Unsupported Kling Avatar tier: {tier}")
    return KLING_AVATAR_TIERS[tier]["cost_per_second"]


def kling_avatar_label(tier: str = "standard") -> str:
    tier = (tier or "standard").strip().lower()
    if tier not in KLING_AVATAR_TIERS:
        raise ValueError(f"Unsupported Kling Avatar tier: {tier}")
    return KLING_AVATAR_TIERS[tier]["label"]


KLING_V3_STORYBOARD_TIERS = {
    "standard": {
        "family": "kling_v3",
        "text_model_id": "fal-ai/kling-video/v3/standard/text-to-video",
        "image_model_id": "fal-ai/kling-video/v3/standard/image-to-video",
        "cost_per_second": 0.084,
        "label": "Kling V3 Standard",
    },
    "pro": {
        "family": "kling_v3",
        "text_model_id": "fal-ai/kling-video/v3/pro/text-to-video",
        "image_model_id": "fal-ai/kling-video/v3/pro/image-to-video",
        "cost_per_second": 0.112,
        "label": "Kling V3 Pro",
    },
}

STORYBOARD_VIDEO_TIERS = {
    **KLING_V3_STORYBOARD_TIERS,
    "veo31_quality": {
        "family": "veo31",
        "text_model_id": "fal-ai/veo3.1",
        "image_model_id": "fal-ai/veo3.1/image-to-video",
        "cost_per_second": 0.20,
        "label": "Veo 3.1 Quality",
        "resolution": "1080p",
    },
}

STORYBOARD_VIDEO_MODE_TIERS = {
    "storyboard_v3_standard": "standard",
    "storyboard_v3_pro": "pro",
    "storyboard_veo31_quality": "veo31_quality",
}

STORYBOARD_VIDEO_MODES = set(STORYBOARD_VIDEO_MODE_TIERS)


def is_storyboard_script(script: dict) -> bool:
    """Return true when a script should use the Kling V3 storyboard pipeline."""
    fmt = (script or {}).get("format") or (script or {}).get("script_format")
    return fmt == "storyboard_v3" or bool((script or {}).get("shots"))


def storyboard_tier_from_video_mode(video_mode: str) -> str:
    mode = (video_mode or "").strip().lower()
    if mode in STORYBOARD_VIDEO_MODE_TIERS:
        return STORYBOARD_VIDEO_MODE_TIERS[mode]
    return "pro" if mode.endswith("_pro") else "standard"


def kling_v3_cost_per_second(tier: str = "standard") -> float:
    tier = (tier or "standard").strip().lower()
    if tier not in KLING_V3_STORYBOARD_TIERS:
        raise ValueError(f"Unsupported Kling V3 tier: {tier}")
    return KLING_V3_STORYBOARD_TIERS[tier]["cost_per_second"]


def storyboard_video_cost_per_second(tier: str = "standard") -> float:
    tier = (tier or "standard").strip().lower()
    if tier not in STORYBOARD_VIDEO_TIERS:
        raise ValueError(f"Unsupported storyboard video tier: {tier}")
    return STORYBOARD_VIDEO_TIERS[tier]["cost_per_second"]


def storyboard_video_label(tier: str = "standard") -> str:
    tier = (tier or "standard").strip().lower()
    if tier not in STORYBOARD_VIDEO_TIERS:
        raise ValueError(f"Unsupported storyboard video tier: {tier}")
    return STORYBOARD_VIDEO_TIERS[tier]["label"]


def storyboard_video_family(tier: str = "standard") -> str:
    tier = (tier or "standard").strip().lower()
    if tier not in STORYBOARD_VIDEO_TIERS:
        raise ValueError(f"Unsupported storyboard video tier: {tier}")
    return STORYBOARD_VIDEO_TIERS[tier].get("family", "kling_v3")


def _veo31_duration(seconds: int | float) -> str:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        value = 8
    if value <= 4:
        return "4s"
    if value <= 6:
        return "6s"
    return "8s"


def _shot_duration(shot: dict) -> int:
    try:
        start = float(shot.get("start", 0))
        end = float(shot.get("end", 0))
        duration = end - start
    except (TypeError, ValueError):
        duration = 0
    if duration <= 0:
        duration = float(shot.get("duration", 0) or 0)
    return max(_KLING_MIN_CLIP_SECONDS,
               min(_KLING_MAX_CLIP_SECONDS, int(round(duration or 5))))


_ACTOR_REFERENCE_PROMPT_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\b(?:actor|actors|presenter|presenters|avatar|avatars)\b",
    r"\b(?:the|this|same|selected|our)\s+(?:character|person|woman|man|girl|guy)\b",
    r"\b(?:character|person|woman|man|girl|guy)\s+from\s+"
    r"(?:the\s+)?(?:reference|source)\b",
    r"\b(?:reference|source)\s+(?:image|photo|portrait)\b",
    r"\b(?:акт[её]р\w*|актрис\w*|ведущ\w*|аватар\w*|персонаж\w*|"
    r"героин\w*|геро(?:й|я|ю|ем|е|и))\b",
    r"\b(?:тот\s+же|та\s+же|тот\s+самый|та\s+самая|выбранн\w*|наш\w*)\s+"
    r"(?:человек\w*|женщин\w*|мужчин\w*|девушк\w*)\b",
    r"\b(?:референс\w*|исходн\w*)\s+(?:изображен\w*|фото|портрет\w*)\b",
    r"\b(?:actriz|actrices|presentador\w*|personaje\w*)\b",
    r"\b(?:mism\w*|seleccionad\w*|nuestr\w*)\s+"
    r"(?:persona\w*|mujer\w*|hombre\w*|chic[oa]s?)\b",
    r"\b(?:imagen|foto|retrato)\s+(?:de\s+)?(?:referencia|origen)\b",
))

_NEUTRAL_BROLL_ENGLISH_IDENTITY_REPLACEMENTS = tuple(
    (re.compile(pattern, re.IGNORECASE), replacement)
    for pattern, replacement in (
        (
            r"\b(?:the|this|same|selected|our)\s+"
            r"(?:actor|presenter|avatar|character)"
            r"(?:\s+from\s+(?:the\s+)?(?:reference|source)"
            r"(?:\s+(?:image|photo|portrait))?)?\b",
            "a faceless person",
        ),
        (
            r"\b(?:actor|presenter|avatar|character)\s+from\s+"
            r"(?:the\s+)?(?:reference|source)"
            r"(?:\s+(?:image|photo|portrait))?\b",
            "a faceless person",
        ),
        (
            r"\b(?:same|selected|our|reference|source)\s+"
            r"(?:person|woman|man|girl|guy)"
            r"(?:\s+from\s+(?:the\s+)?(?:reference|source)"
            r"(?:\s+(?:image|photo|portrait))?)?\b",
            "a faceless person",
        ),
        (
            r"\b(?:person|woman|man|girl|guy)\s+from\s+"
            r"(?:the\s+)?(?:reference|source)"
            r"(?:\s+(?:image|photo|portrait))?\b",
            "a faceless person",
        ),
        (
            r"\b(?:actor|presenter|avatar)\b",
            "a faceless person",
        ),
        (
            r"\b(?:reference|source)\s+(?:image|photo|portrait)\b",
            "",
        ),
    )
)

_NEUTRAL_BROLL_ENGLISH_FALLBACK = (
    "vertical 9:16 realistic phone video, a single relevant object or process "
    "in natural motion, steady handheld smartphone camera, natural light, "
    "authentic smartphone footage"
)


def _mentions_selected_actor_reference(value: str) -> bool:
    """Whether prompt text explicitly binds a subject to the saved presenter."""
    return any(pattern.search(value or "") for pattern in _ACTOR_REFERENCE_PROMPT_PATTERNS)


def _ensure_neutral_broll_english_prompt(
    value: str,
    script_language: str = "",
    prompt_language: str = "",
) -> str:
    """Keep automatic neutral prompts English; localized UI text must not reach video."""
    prompt = (value or "").strip(" ,;")
    words = re.findall(r"[A-Za-z]+", prompt)
    source_language = (script_language or "").strip().lower().split("-", 1)[0]
    declared_prompt_language = (prompt_language or "").strip().lower().split("-", 1)[0]
    if (
        not prompt.isascii()
        or len(words) < 4
        or (
            source_language
            and source_language != "en"
            and declared_prompt_language != "en"
        )
    ):
        return _NEUTRAL_BROLL_ENGLISH_FALLBACK
    if "9:16" not in prompt:
        prompt = f"{prompt}, vertical 9:16"
    return prompt


def _sanitize_neutral_broll_english_prompt(
    value: str,
    script_language: str = "",
    prompt_language: str = "",
) -> str:
    """Remove selected-presenter bindings without translating localized UI fields."""
    sanitized = value or ""
    for pattern, replacement in _NEUTRAL_BROLL_ENGLISH_IDENTITY_REPLACEMENTS:
        sanitized = pattern.sub(replacement, sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized)
    sanitized = re.sub(r"\s+([,;])", r"\1", sanitized)
    sanitized = re.sub(r"([,;])(?:\s*\1)+", r"\1", sanitized).strip(" ,;")
    if _mentions_selected_actor_reference(sanitized):
        return _NEUTRAL_BROLL_ENGLISH_FALLBACK
    return _ensure_neutral_broll_english_prompt(
        sanitized,
        script_language=script_language,
        prompt_language=prompt_language,
    )


def _build_storyboard_generation_prompt(shot: dict) -> str:
    existing = (shot.get("generation_prompt") or "").strip()
    neutral_broll = _is_broll_shot(shot) and not _shot_wants_actor(shot)
    script_language = shot.get("_script_language") or ""
    prompt_language = shot.get("_generation_prompt_language") or ""
    if existing:
        # Уважать промпт пользователя (он редактируется в UI): гардрейлы формата
        # дописываем, а не заменяем ими весь текст. Идемпотентно — повторный
        # normalize не меняет строку, иначе кэш клипов считал бы её «новым промптом».
        if shot.get("prompt_manual") or not neutral_broll:
            additions = []
            if "9:16" not in existing:
                additions.append("vertical 9:16")
            return ", ".join([existing] + additions)
        if not _mentions_selected_actor_reference(existing):
            return _ensure_neutral_broll_english_prompt(
                existing,
                script_language=script_language,
                prompt_language=prompt_language,
            )
        return _sanitize_neutral_broll_english_prompt(
            existing,
            script_language=script_language,
            prompt_language=prompt_language,
        )

    scene = (shot.get("scene") or shot.get("visual") or "realistic social video scene").strip()
    actor_action = (shot.get("actor_action") or shot.get("action") or "natural movement").strip()
    camera = (shot.get("camera") or "vertical 9:16 steady handheld smartphone video").strip()
    if neutral_broll:
        if _mentions_selected_actor_reference(scene):
            scene = "realistic social video scene"
        if _mentions_selected_actor_reference(actor_action):
            actor_action = ""
        if _mentions_selected_actor_reference(camera):
            camera = "vertical 9:16 steady handheld smartphone video"
    identity = (
        "same actor from the reference image"
        if not neutral_broll
        else ""
    )
    bits = [
        "vertical 9:16 realistic phone video",
        identity,
        scene,
        actor_action,
        camera,
        "natural light",
        "authentic smartphone footage",
    ]
    prompt = ", ".join(bit for bit in bits if bit)
    if neutral_broll:
        return _ensure_neutral_broll_english_prompt(
            prompt,
            script_language=script_language,
            prompt_language=prompt_language,
        )
    return prompt


def _needs_prompt_rebuild(shot: dict) -> bool:
    """True when «Что в кадре» (scene) drifted from the prompt the user last saw.

    `scene` is the human source of truth for the picture; the English Kling
    prompt is derived from it. `_prompt_source_scene` records the scene the
    current prompt was built from. A hand-edited prompt (`prompt_manual`) pins it
    and is never overwritten. A missing baseline (legacy/custom scripts, or the
    very first run) trusts the existing prompt — we only rebuild once the scene
    actually changes afterwards.
    """
    if shot.get("prompt_manual"):
        return False
    baseline = shot.get("_prompt_source_scene")
    if baseline is None:
        return False
    return (shot.get("scene") or "").strip() != (baseline or "").strip()


def _rebuild_prompts_from_scene(
    shots: list,
    gemini_key: Optional[str],
    actor_description: str = "",
    log: Callable[[str], None] = print,
) -> None:
    """Rebuild each shot's English Kling prompt from its edited RU «Что в кадре».

    So editing «Что в кадре» actually changes the rendered shot. Only shots whose
    scene drifted (and whose prompt isn't hand-pinned) are rebuilt, in a single
    batched Gemini call. Every shot without a baseline gets one stamped so future
    scene edits are detectable. `actor_description` remains in the signature for
    saved callers but is intentionally never sent to Gemini. On any failure the
    existing prompts are kept.
    """
    stale = [s for s in shots if _needs_prompt_rebuild(s)]
    # Stamp a baseline for shots that never had one (AI scripts stamp at creation;
    # this covers custom/legacy). Done for all shots, rebuilt or not.
    for s in shots:
        if s.get("_prompt_source_scene") is None and not s.get("prompt_manual"):
            s["_prompt_source_scene"] = (s.get("scene") or "").strip()
    if not stale or not gemini_key:
        return
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_key)
        payload = [
            {
                "n": i,
                "visual_type": "broll" if _is_broll_shot(s) else "talking",
                "actor_in_frame": _shot_wants_actor(s),
                "scene": (s.get("scene") or "").strip(),
                "action": (s.get("actor_action") or s.get("action") or "").strip(),
                "camera": (s.get("camera") or "").strip(),
                "role": (s.get("role") or "").strip(),
                "speech": (s.get("speech") or "").strip(),
            }
            for i, s in enumerate(stale)
        ]
        prompt = (
            "You convert Russian shot descriptions into English video-generation prompts "
            "for Kling V3 (vertical 9:16 realistic phone video).\n"
            f"{_ACTOR_DIRECTION_ONLY_RULES}\n"
            "Apply the identity rule even when an input scene contains appearance details: "
            "omit those details from the output prompt.\n"
            "For each shot, write ONE English prompt that fully describes the scene, action "
            "and camera on its own. Rules: vertical 9:16, natural light, authentic smartphone "
            "footage. For talking shots, identify the same actor from the reference image. "
            "For B-roll with actor_in_frame=true, identify the same actor from the reference "
            "image while keeping the face away from camera. For B-roll with "
            "actor_in_frame=false, do not mention the actor or reference image. Describe only "
            "what IS in frame — "
            "never write 'no text', 'no watermark' or any other ban, those go to the model in "
            "a separate field and in the description they only make it draw them. "
            "For visual_type 'broll', use the exact speech as the visual source of "
            "truth: literally demonstrate the claim or use one clear visual analogy. Do not use "
            "generic wellness filler (avocado, salad, measuring tape, yoga mat, supplements, "
            "scales or food prep) unless the speech explicitly concerns it. A faceless human "
            "action is allowed when conceptually necessary (back view, cropped body/hands, "
            "silhouette, non-identifiable profile); never request an identifiable face. Never "
            "request readable on-screen text, numbers, charts or screens.\n"
            f"Shots JSON: {json.dumps(payload, ensure_ascii=False)}\n"
            'Return ONLY a JSON array: [{"n": <n>, "prompt": "<english prompt>"}].'
        )
        resp = _generate_gemini_content(
            client,
            contents=[prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json", max_output_tokens=4096
            ),
        )
        text = (resp.text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        result = json.loads(text)
        by_n = {int(item["n"]): (item.get("prompt") or "").strip() for item in result if "n" in item}
        for i, s in enumerate(stale):
            new_prompt = by_n.get(i)
            if new_prompt:
                s["_generation_prompt_language"] = "en"
                s["generation_prompt"] = _build_storyboard_generation_prompt(
                    {**s, "generation_prompt": new_prompt}
                )
                s["_prompt_source_scene"] = (s.get("scene") or "").strip()
                log(f"  Кадр {s.get('shot_number', i + 1)}: промпт перестроен из «Что в кадре».")
    except Exception as e:
        log(f"  ⚠️ Не удалось перестроить промпты из «Что в кадре» ({e}); оставляю прежние.")


_SHOT_FILL_FIELDS = ("scene", "camera", "actor_action", "role", "emotion", "transition", "visual_type")


def fill_storyboard_shot_details(
    script: dict,
    shots: list,
    gemini_key: str,
    text_model: str = "fast",
    language: str = "ru",
    actor_gender: str = "female",
) -> list:
    """Fill in scene / camera / action / prompt for shots that only carry speech.

    A shot restored from the archive (or added by hand) has a line and nothing
    else. The video model never sees the speech — it renders `generation_prompt`,
    built from the scene — so an empty shot produces a random picture. This asks
    Gemini for the missing fields only, in the context of the neighbouring shots,
    so the restored shot matches the rest of the storyboard.
    """
    targets = [s for s in shots if (s.get("speech") or "").strip() or (s.get("scene") or "").strip()]
    if not targets or not gemini_key:
        return shots

    from google import genai
    from google.genai import types

    lang_name = {"ru": "Russian", "es": "Spanish"}.get(language, "English")
    context = [
        {
            "shot_number": s.get("shot_number"),
            "speech": (s.get("speech") or "").strip(),
            "scene": (s.get("scene") or "").strip(),
            "visual_type": s.get("visual_type") or "",
        }
        for s in shots
    ]
    payload = [
        {
            "shot_number": s.get("shot_number"),
            "speech": (s.get("speech") or "").strip(),
            "scene": (s.get("scene") or "").strip(),
            "camera": (s.get("camera") or "").strip(),
            "actor_action": (s.get("actor_action") or s.get("action") or "").strip(),
        }
        for s in targets
    ]
    prompt = f"""You are a storyboard director for vertical social videos (9:16).

Video: "{script.get('title') or ''}"
Topic: {script.get('_video_topic') or script.get('topic') or ''}
{_ACTOR_DIRECTION_ONLY_RULES}

Full storyboard for context (already existing shots):
{json.dumps(context, ensure_ascii=False, indent=1)}

Fill in the MISSING production fields for these shots (keep any value that is
already filled in — only replace empty ones):
{json.dumps(payload, ensure_ascii=False, indent=1)}

RULES:
- Apply the identity rule to every returned field. If an input scene contains
  appearance details, omit them instead of copying them into the result.
- scene, camera, actor_action must be written in {lang_name} — the user reads them in the app.
- visual_type: "talking" (the actor speaks to camera, lips visible) or "broll"
  (insert shot over the voiceover). B-roll must be grounded in that exact speech:
  literally demonstrate the claim or use one clear visual analogy, never generic
  wellness filler such as avocado, salad, measuring tape, yoga mat, supplements,
  scales or food prep unless the spoken line is about it. A faceless human action
  is allowed when conceptually necessary (back view, cropped body/hands, silhouette,
  non-identifiable profile); never request an identifiable face. Prefer "talking"
  for lines that carry the argument, "broll" for lines that describe a thing or a
  result. Never put two "broll" shots in a row given the surrounding storyboard.
- actor_in_frame: true ONLY when a "broll" shot shows the SAME person who speaks in
  the talking shots (from behind, over the shoulder, her hands, her silhouette),
  false when the insert is objects, food, an interior or a different person. Always
  false for "talking" shots. This cannot be inferred from the scene text, so state it.
- In "talking" shots the actor stays put and stays calm: subtle expressions and
  small head movement only. No exercising, walking, drinking or big gestures —
  motion breaks lip-sync. Say what the person is doing, never how they are filmed
  or where they look — the app owns the camera for talking shots.
- Every "broll" shot must be visually distinct from its neighbours in the storyboard above.
- ALL talking shots happen in ONE place, the one the first talking shot above is
  set in. Never write a new room, a new window, a new time of day or a changed
  angle for a talking shot: the app stages them itself and rotates the camera
  between them, so such a line describes something the viewer will never see.
  A talking scene describes the MOMENT instead — posture, gaze, what the hands do.
- role: one of hook, problem, explanation, solution, proof, cta.
- emotion: one of excited, warm, confident, calm, urgent, playful.
- transition: "cut" or "smooth_0.3s".
- No readable text anywhere: no labels, signs, numbers, stickers, no phone/laptop
  screens facing camera — video models render text as garbage glyphs.
- generation_prompt MUST be English and fully describe scene and action on its own:
  vertical 9:16, realistic phone video, natural light. State a shot type only for
  "broll"; for talking shots the app owns the camera. For talking shots
  and B-roll with actor_in_frame=true, identify the same actor from the reference image.
  For B-roll with actor_in_frame=false, do not mention the actor or reference image.
  Describe only
  what IS in frame — never write "no text", "no watermark" or any other ban, those
  reach the model in a separate field and inside the description they only make it
  draw them. For "broll" pick subjects with no identifiable face and nothing written
  on them; a faceless human action is allowed when the speech requires it.

Return ONLY a JSON array:
[{{"shot_number": <n>, "scene": "...", "camera": "...", "actor_action": "...",
  "role": "...", "emotion": "...", "transition": "...", "visual_type": "...",
  "actor_in_frame": false, "overlay_text": "...", "generation_prompt": "..."}}]"""

    client = genai.Client(api_key=gemini_key)
    resp = _generate_gemini_content(
        client,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", max_output_tokens=8192
        ),
        text_model=text_model,
    )
    text = (resp.text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    filled = json.loads(_repair_gemini_json(text))
    by_number = {}
    for item in filled if isinstance(filled, list) else []:
        try:
            by_number[int(item.get("shot_number"))] = item
        except (TypeError, ValueError):
            continue

    out = []
    for index, shot in enumerate(targets, start=1):
        item = by_number.get(shot.get("shot_number")) or by_number.get(index) or {}
        merged = dict(shot)
        for field in _SHOT_FILL_FIELDS:
            value = (item.get(field) or "").strip()
            if value and not (merged.get(field) or "").strip():
                merged[field] = value
        if merged.get("actor_action") and not (merged.get("action") or "").strip():
            merged["action"] = merged["actor_action"]
        # A bool, so it can't ride the string loop above. The user's own toggle
        # wins: we only answer for shots that never stated it.
        if "actor_in_frame" not in merged and item.get("actor_in_frame") is not None:
            merged["actor_in_frame"] = _shot_wants_actor(item)
        if not (merged.get("overlay_text") or "").strip():
            merged["overlay_text"] = (item.get("overlay_text") or "").strip()
        # The prompt is what the video model actually renders — always (re)build it
        # through the shared builder so the guardrails stay attached.
        if not merged.get("prompt_manual"):
            generated_prompt = (item.get("generation_prompt") or "").strip()
            merged["_script_language"] = (
                merged.get("_script_language")
                or script.get("language")
                or language
            )
            if generated_prompt:
                merged["_generation_prompt_language"] = "en"
            merged["generation_prompt"] = _build_storyboard_generation_prompt(
                {
                    **merged,
                    "generation_prompt": generated_prompt
                    or merged.get("generation_prompt")
                    or "",
                }
            )
            merged["_prompt_source_scene"] = (merged.get("scene") or "").strip()
        out.append(merged)
    return out


def normalize_storyboard_shots(script: dict) -> list:
    """Normalize shot dictionaries for Kling V3 generation and UI edits."""
    raw_shots = script.get("shots") or []
    script_language = (script.get("language") or "").strip().lower()
    set_prompt = (script.get("set_prompt") or "").strip()
    set_prompts = [s.strip() for s in (script.get("set_prompts") or [])
                   if isinstance(s, str) and s.strip()]
    # Правка места руками бьёт по первой локации: человек редактирует одно поле,
    # `set_prompt`, и оно обязано выиграть у списка, из которого выросло. Иначе
    # первая комната ролика осталась бы той, что он только что переписал.
    if set_prompts and set_prompt:
        set_prompts = [set_prompt] + set_prompts[1:]
    # Место доезжает до плит, когда его выбрал человек — или когда человек
    # попросил их менять. И то и другое — его решение, а не догадка модели.
    set_chosen = bool(set_prompt) and (
        (script.get("set_source") or "").strip().lower() == "user"
        or bool(script.get("set_changes")))
    if not raw_shots and script.get("segments"):
        raw_shots = []
        for index, segment in enumerate(script.get("segments") or [], start=1):
            narration = segment.get("narration") or ""
            raw_shots.append({
                "shot_number": index,
                "start": segment.get("start", index - 1),
                "end": segment.get("end", index),
                "role": segment.get("type") or f"shot_{index}",
                "scene": segment.get("broll_prompt") or segment.get("visual") or "",
                "actor_action": segment.get("action") or "speaks directly to camera",
                "camera": segment.get("camera") or "vertical 9:16 steady handheld smartphone video",
                "speech": narration,
                "emotion": segment.get("emotion") or "",
                "overlay_text": segment.get("subtitle_text") or narration[:50],
                "transition": segment.get("transition") or "cut",
                "generation_prompt": segment.get("generation_prompt") or segment.get("broll_prompt") or narration,
            })

    shots = []
    cursor = 0
    for index, shot in enumerate(raw_shots, start=1):
        duration = _shot_duration(shot)
        start = shot.get("start")
        end = shot.get("end")
        try:
            start = float(start)
            end = float(end)
        except (TypeError, ValueError):
            start = cursor
            end = cursor + duration
        if end <= start:
            end = start + duration
        cursor = end

        speech = (shot.get("speech") or shot.get("narration") or "").strip()
        scene = (shot.get("scene") or shot.get("visual") or "").strip()
        actor_action = (shot.get("actor_action") or shot.get("action") or "").strip()
        camera = (shot.get("camera") or "vertical 9:16 steady handheld smartphone video").strip()
        role = _storyboard_role_from_text(shot.get("role") or shot.get("type") or "", f"shot_{index}")
        overlay_text = (shot.get("overlay_text") or shot.get("subtitle_text") or "").strip()
        transition = _storyboard_transition_from_text(shot.get("transition") or "cut")
        normalized = {
            **shot,
            "shot_number": int(shot.get("shot_number") or index),
            "start": start,
            "end": end,
            "duration": int(round(end - start)),
            "role": role,
            "scene": scene,
            "actor_action": actor_action,
            "action": actor_action,
            "camera": camera,
            "speech": speech,
            "emotion": (shot.get("emotion") or "").strip().lower(),
            "overlay_text": overlay_text,
            "transition": transition,
            "visual_type": (shot.get("visual_type") or ("talking" if speech else "broll")).strip().lower(),
        }
        shot_language = (shot.get("_script_language") or script_language).strip().lower()
        if shot_language:
            normalized["_script_language"] = shot_language
        # Сет — свойство сценария, но до плит доезжают одни кадры: и слайсер, и
        # рендер получают список шотов без обёртки. Штампуем его сюда, чтобы
        # `_pinned_avatar_set` не пришлось угадывать место по первой реплике.
        if set_prompt:
            normalized["_set_prompt"] = set_prompt
        if set_chosen:
            normalized["_set_chosen"] = True
        # Only coerce when the storyboard actually stated it: an absent flag must
        # stay absent so `fill_storyboard_shot_details` can still decide, while a
        # user's explicit "no" is never re-decided for them.
        if "actor_in_frame" in shot:
            normalized["actor_in_frame"] = _shot_wants_actor(shot)
        normalized["generation_prompt"] = _build_storyboard_generation_prompt(normalized)
        shots.append(normalized)
    _assign_shot_locations(shots, set_prompts if set_chosen else [])
    return shots


def _assign_shot_locations(shots: list, set_prompts: List[str]) -> None:
    """Раздать говорящим кадрам номер локации — по три кадра на место.

    Меняем место не на каждом кадре: соседние шоты внутри локации разводит
    вторая камера, а каждая новая комната — это ещё одна платная плита на
    камеру. Локации по кругу: четвёртая тройка возвращается в первую комнату и
    берёт её плиту даром.
    """
    if len(set_prompts) < 2:
        return
    for shot in shots:
        shot["_set_prompts"] = set_prompts
    talking = [shot for shot in shots if not _is_broll_shot(shot)]
    for order, shot in enumerate(talking):
        shot["_set_index"] = (order // _SHOTS_PER_LOCATION) % len(set_prompts)

def split_storyboard_shots(shots: list, max_duration: int = 15) -> list:
    """Split storyboard shots into chunks that fit Kling V3 multi-shot limits."""
    chunks = []
    current = []
    current_duration = 0
    for shot in normalize_storyboard_shots({"shots": shots}):
        duration = _shot_duration(shot)
        if current and current_duration + duration > max_duration:
            chunks.append(current)
            current = []
            current_duration = 0
        current.append(shot)
        current_duration += duration
    if current:
        chunks.append(current)
    return chunks


# The single place where "things we do not want in frame" is allowed to be
# spelled out: Kling V3 and Veo both take a real negative prompt. In the
# positive prompt these same words are an order to draw them.
_STORYBOARD_NEGATIVE_PROMPT = (
    "blur, distort, low quality, deformed face, extra fingers, "
    "burned-in text, subtitles, captions, letters, numbers, logos, watermark, "
    "signage, user interface"
)


def build_kling_v3_storyboard_request(
    shots: list,
    tier: str = "standard",
    generation_mode: str = "single_shot",
    aspect_ratio: str = "9:16",
    start_image_url: str = "",
) -> tuple[str, dict]:
    """Build a fal.ai request for one shot or a multi-shot storyboard."""
    tier = (tier or "standard").strip().lower()
    if tier not in STORYBOARD_VIDEO_TIERS:
        raise ValueError(f"Unsupported storyboard video tier: {tier}")

    normalized = normalize_storyboard_shots({"shots": shots})
    if not normalized:
        raise ValueError("Storyboard requires at least one shot")

    if len(normalized) == 1:
        first_shot = normalized[0]
        start_image_url = start_image_url or first_shot.get("image_url") or first_shot.get("start_image_url") or ""

    use_image_to_video = bool(start_image_url)
    model_key = "image_model_id" if use_image_to_video else "text_model_id"
    tier_config = STORYBOARD_VIDEO_TIERS[tier]
    model_id = tier_config[model_key]

    if tier_config.get("family") == "veo31":
        if generation_mode == "multi_shot" and len(normalized) > 1:
            raise ValueError("Veo 3.1 storyboard mode supports one prompt per fal.ai request")
        shot = normalized[0]
        payload = {
            "prompt": shot.get("generation_prompt") or shot.get("scene") or shot.get("speech") or "vertical social video shot",
            "aspect_ratio": aspect_ratio,
            "duration": _veo31_duration(_shot_duration(shot)),
            "negative_prompt": _STORYBOARD_NEGATIVE_PROMPT,
            "resolution": tier_config.get("resolution", "1080p"),
            "generate_audio": False,
            "auto_fix": False,
            "safety_tolerance": "4",
        }
        if use_image_to_video:
            payload["image_url"] = start_image_url
        return model_id, payload

    payload = {
        "duration": str(min(15, sum(_shot_duration(shot) for shot in normalized))),
        "generate_audio": False,
        "negative_prompt": _STORYBOARD_NEGATIVE_PROMPT,
    }
    if use_image_to_video:
        payload["start_image_url"] = start_image_url
    else:
        payload["aspect_ratio"] = aspect_ratio

    if generation_mode == "multi_shot" and len(normalized) > 1:
        payload["shot_type"] = "customize"
        payload["multi_prompt"] = [
            {
                "duration": str(_shot_duration(shot)),
                "prompt": shot.get("generation_prompt") or shot.get("scene") or shot.get("speech") or "vertical social video shot",
            }
            for shot in normalized
        ]
    else:
        shot = normalized[0]
        payload["prompt"] = shot.get("generation_prompt") or shot.get("scene") or shot.get("speech") or "vertical social video shot"
        payload["duration"] = str(_shot_duration(shot))

    return model_id, payload


def _resolve_storyboard_start_image_url(shot: dict, fal_key: str) -> str:
    """Return a public URL for a storyboard reference frame when one is present."""
    for key in ("image_url", "start_image_url"):
        value = (shot.get(key) or "").strip()
        if value.startswith(("http://", "https://")):
            return value

    local_ref = (shot.get("image_path") or shot.get("local_path") or "").strip()
    if not local_ref:
        local_url = (shot.get("local_url") or "").strip()
        if local_url.startswith("/videos/"):
            local_ref = os.path.join("output", local_url.replace("/videos/", "", 1))

    if not local_ref:
        return ""

    abs_path = os.path.abspath(local_ref)
    output_root = os.path.abspath("output")
    try:
        is_inside_output = os.path.commonpath([abs_path, output_root]) == output_root
    except ValueError:
        is_inside_output = False
    if not is_inside_output or not os.path.exists(abs_path):
        return ""

    return _fal_upload_file(abs_path, fal_key)


def prepare_kling_actor_image(image_path: str, output_path: str) -> str:
    """Prepare a native 9:16 actor image before sending it to Kling Avatar."""
    if (
        os.path.exists(output_path)
        and os.path.getsize(output_path) > 0
        and os.path.getmtime(output_path) >= os.path.getmtime(image_path)
    ):
        return output_path

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    for stale_path in (output_path, f"{output_path}.fal_url.txt"):
        try:
            if os.path.exists(stale_path):
                os.remove(stale_path)
        except OSError:
            pass

    # Use cover-crop instead of padding so Kling receives a true vertical
    # portrait, not a horizontal photo embedded inside a vertical canvas.
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920:(iw-ow)/2:(ih-oh)/2,"
        "setsar=1,format=rgb24"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", image_path,
        "-vf", vf,
        "-frames:v", "1",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[SaaSShorts] ✅ Kling 9:16 actor image: {output_path}")
    return output_path


def _file_fingerprint(path: str) -> str:
    """Content hash of a local file, or "" when it cannot be read."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return ""


# Words that name something we do NOT want in frame. Kling Avatar has no
# negative prompting, so "no burned-in text, no watermark" reads to it as a
# request for text and it paints garbled captions along the bottom (verified
# side-by-side on the same image and audio, 2026-07-26). Anything we want gone
# has to be expressed as the state we do want instead.
_AVATAR_PROMPT_BANNED_WORDS = (
    "text", "caption", "subtitle", "letter", "word", "logo", "watermark",
    "sign", "label", "typography", "glyph", "character", "number", "symbol",
    "screen", "interface", "tattoo", "print",
)

# Short, positive, motion-only. The frame itself (scene, outfit, framing) comes
# from the reference image, so the prompt holds the body still: with no prompt at
# all Kling invents leg-crossing and hand-shuffling that reads as fidgeting.
# Length is deliberate — fal's own schema defaults this field to "." and the
# comparable Longcat avatar endpoint defaults to a single plain sentence, so two
# sentences is already the upper end of what these models expect here.
#
# Держать неподвижным тело и держать неподвижным лицо — разные задачи, и раньше
# промпт не различал их. «Small head movements» и «one locked-off take» стояли
# рядом с «hands resting calmly» и гасили заодно мимику: движение лица между
# соседними кадрами вышло 2.70 и 3.09 против 4.94 и 3.66 на прежних дублях —
# лицо читалось переколотым ботоксом. Поэтому неподвижность сказана только про
# руки, ноги и камеру, а лицу движение прямо разрешено — перечислением того, что
# должно двигаться: негативного промпта у Kling нет (см.
# `_AVATAR_PROMPT_BANNED_WORDS`), «не замирай» он прочтёт как «замри».
#
# Но разрешать надо по одной вещи за раз. Первая редакция просила заодно щёки,
# прищур «when the tone warms» и «the head turns and nods» — и рот перестал
# попадать в звук: у Kling один бюджет движения, губы оказались одной задачей из
# пяти, и он отработал выражение лица, держа рот в застывшей улыбке с зубами.
# Замер на ролике 03.08 13:06 (`voice_test/lip_population_2026_08_03.py`):
# раскрытие рта на самых громких кадрах МЕНЬШЕ, чем на самых тихих, −0.003 у
# обоих дублей — единственные отрицательные значения за всю историю замеров
# (прежние дубли и ручной клип 26.07: от 0.000 до +0.029). Ход рта у первого
# дубля 4.2 против 6.0-9.3 у всех остальных.
#
# Отсюда порядок слов: губы названы первыми и отдельной фразой, «щёки поднимаются
# и глаза щурятся» (анатомическое описание улыбки — рот, а не глаза) убрано, а
# тормоз на голову возвращён. Брови и лоб остаются: мимика, ради которой правка и
# делалась, живёт там и рта не занимает.
#
# «From the first sound to the last», а не «through every word»: `word` стоит в
# `_AVATAR_PROMPT_BANNED_WORDS`, и назвать его — попросить нарисовать текст.
#
# Позу промпт не называет, а только запрещает менять. Раньше здесь стояло «stays
# seated», хотя плита — единственный источник правды о позе — рисует человека
# стоящим: закреплённый сет обоих роликов 03.08 начинается со «standing in a cozy
# living room». Сесть модель всё равно не может, первый кадр задан плитой, так что
# указание либо игнорировалось, либо тратило то самое внимание, которого не
# хватило губам. Неподвижность рук и ног остаётся: без неё Kling придумывает
# перекладывание ног и рук.
_AVATAR_MOTION_PROMPT = (
    "The person holds the pose they are already in, hands resting calmly, legs still, speaking "
    "straight to the camera. The lips follow the audio from the first sound to the last, the jaw "
    "opens and closes with the syllables. The brows and forehead work with the meaning, natural blinking, "
    "small head movements, one locked-off take. The camera stays where it is."
)

_AVATAR_WHISPER_MOTION_PROMPT = (
    "The person leans slightly closer to the camera, chin lowered, one hand resting near the "
    "mouth, whispering confidentially. The lips follow the audio from the first sound to the "
    "last, the jaw opens and closes with the syllables. The brows draw in and lift with the meaning, natural "
    "blinking, tiny head movements, one locked-off take. The camera stays where it is."
)


def _avatar_prompt_issues(prompt: str) -> list:
    """Words in an avatar prompt that the model will draw instead of avoid."""
    lowered = (prompt or "").lower()
    return [word for word in _AVATAR_PROMPT_BANNED_WORDS if re.search(rf"\b{word}s?\b", lowered)]


def generate_talking_head(
    image_path: str,
    audio_path: str,
    fal_key: str,
    output_path: str,
    tier: str = "standard",
    motion_prompt: Optional[str] = None,
) -> str:
    """Generate talking head video using Kling Avatar v2 Standard/Pro on fal.ai.

    Framing comes from `image_path` — the shot's own reference frame — and the
    performance from the audio. `motion_prompt` may select a restrained whisper
    performance; both recipes deliberately name nothing we want kept out of
    frame (see `_AVATAR_PROMPT_BANNED_WORDS`).
    """
    import shutil

    tier = (tier or "standard").strip().lower()
    print(f"[SaaSShorts] 🗣️ Generating talking head ({kling_avatar_label(tier)})...")

    # Upload a native 9:16 image to Kling so the model generates for Reels
    # framing instead of producing a wide frame that we crop later.
    kling_image_path = output_path.replace(".mp4", "_actor_9x16.png")
    image_url = _fal_upload_file(
        prepare_kling_actor_image(image_path, kling_image_path),
        fal_key,
    )
    # Fingerprint the frame we were handed, not the 9:16 render of it: that is
    # what the cache check can recompute later.
    reference_fingerprint = _file_fingerprint(image_path)
    motion_prompt = motion_prompt or _AVATAR_MOTION_PROMPT
    attempts_config = [
        {"name": "base", "audio_path": audio_path, "prompt": motion_prompt},
    ]
    attempts = []
    selected_attempt = None
    model_id = ""

    for index, attempt_config in enumerate(attempts_config, start=1):
        attempt_name = attempt_config["name"]
        attempt_audio_path = attempt_config["audio_path"]
        attempt_output = output_path.replace(".mp4", f"_{attempt_name}.mp4")
        attempt_meta_path = output_path.replace(".mp4", f"_{attempt_name}_fal.json")
        audio_url = _fal_upload_file(attempt_audio_path, fal_key)
        model_id, payload = build_kling_avatar_request(
            image_url,
            audio_url,
            attempt_config["prompt"],
            tier=tier,
        )
        attempt_record = {
            "name": attempt_name,
            "output_path": attempt_output,
            "audio_path": attempt_audio_path,
            "model_id": model_id,
            "payload": payload,
            # What this clip was actually built from, for the cache check: the
            # payload only carries a one-off fal upload URL.
            "reference_fingerprint": reference_fingerprint,
        }

        try:
            result = _fal_run(model_id, payload, fal_key, timeout=1200)
            video = result.get("video")
            video_url = video.get("url") if isinstance(video, dict) else video
            if not video_url:
                raise Exception(f"No video URL in Kling result: {result}")
            with httpx.Client(timeout=180.0) as client:
                vid_resp = client.get(video_url)
                vid_resp.raise_for_status()
                with open(attempt_output, "wb") as f:
                    f.write(vid_resp.content)

            quality = inspect_talking_head_quality(attempt_output, attempt_audio_path)
            attempt_record.update({
                "video_url": video_url,
                "fal_request": result.get("_fal_request", {}),
                "quality": quality,
            })
            _write_json_file(attempt_meta_path, {
                "attempt": attempt_name,
                "tier": tier,
                "model_id": model_id,
                "payload": payload,
                "reference_fingerprint": reference_fingerprint,
                "fal_request": result.get("_fal_request", {}),
                "result": result,
                "quality": quality,
            })
            attempts.append(attempt_record)

            if quality.get("status") == "ok":
                selected_attempt = attempt_record
                break
        except Exception as e:
            attempt_record["error"] = str(e)
            attempts.append(attempt_record)
            _write_json_file(attempt_meta_path, {
                "attempt": attempt_name,
                "tier": tier,
                "model_id": model_id,
                "payload": payload,
                "error": str(e),
            })

    if not selected_attempt:
        selected_attempt = select_best_talking_head_attempt(attempts)

    shutil.copy2(selected_attempt["output_path"], output_path)
    selected_quality = selected_attempt.get("quality") or inspect_talking_head_quality(
        output_path,
        selected_attempt.get("audio_path") or audio_path,
    )
    warnings = []
    for attempt in attempts:
        warnings.extend(attempt.get("quality", {}).get("warnings", []))
        if attempt.get("error"):
            warnings.append(f"Kling attempt {attempt.get('name')} failed: {attempt['error']}")
    warnings = list(dict.fromkeys(warnings))
    quality_report = {
        "status": selected_quality.get("status", "needs_review"),
        "selected_attempt": selected_attempt.get("name"),
        "selected_audio_path": selected_attempt.get("audio_path"),
        "paid_attempts": len([attempt for attempt in attempts if not attempt.get("error")]),
        "attempts": attempts,
        "warnings": warnings if selected_quality.get("status") != "ok" else [],
    }
    _write_json_file(talking_head_quality_path(output_path), quality_report)

    print(f"[SaaSShorts] ✅ Talking head: {output_path}")
    return output_path


def generate_talking_head_lowcost(
    image_path: str,
    audio_path: str,
    fal_key: str,
    output_path: str,
) -> str:
    """
    Low-cost talking head: Hailuo 2.3 Fast img2video → VEED Lipsync.
    ~$0.39 vs ~$1.69 for Kling Avatar v2.
    """
    print(f"[SaaSShorts] 🗣️ Generating talking head (Low Cost: Hailuo + VEED Lipsync)...")

    # Step 1: Generate 6s video from image using MiniMax Hailuo 2.3 Fast ($0.19)
    # Cache the Hailuo clip so retries don't re-generate it
    hailuo_cache_path = output_path.replace(".mp4", "_hailuo_cache.mp4")

    if os.path.exists(hailuo_cache_path) and os.path.getsize(hailuo_cache_path) > 0:
        print(f"[SaaSShorts]   Hailuo clip cached, skipping generation.")
        hailuo_video_url = _fal_upload_file(hailuo_cache_path, fal_key)
    else:
        image_url = _fal_upload_file(image_path, fal_key)

        hailuo_result = _fal_run(
            "fal-ai/minimax/hailuo-2.3-fast/standard/image-to-video",
            {
                "image_url": image_url,
                "prompt": (
                    "Person talking to camera, subtle head nods and natural micro-expressions. "
                    "Gentle head movement, slight shoulder sway. Eye contact with camera. "
                    "Natural blinking. Soft ambient lighting. Smooth cinematic motion."
                ),
            },
            fal_key,
            timeout=1200,
        )

        print(f"[SaaSShorts]   Hailuo response keys: {list(hailuo_result.keys())}")
        if "video" in hailuo_result:
            hailuo_video_url = hailuo_result["video"]["url"] if isinstance(hailuo_result["video"], dict) else hailuo_result["video"]
        elif "video_url" in hailuo_result:
            hailuo_video_url = hailuo_result["video_url"]
        elif "output" in hailuo_result:
            hailuo_video_url = hailuo_result["output"]["url"] if isinstance(hailuo_result["output"], dict) else hailuo_result["output"]
        else:
            raise Exception(f"No video in Hailuo result: {hailuo_result}")

        # Save Hailuo clip locally for retry cache
        with httpx.Client(timeout=180.0) as client:
            vid_resp = client.get(hailuo_video_url)
            with open(hailuo_cache_path, "wb") as f:
                f.write(vid_resp.content)

        print(f"[SaaSShorts]   Hailuo 2.3 Fast 6s clip ready (cached for retry).")

    # Step 2: Upload audio for lip-sync
    audio_url = _fal_upload_file(audio_path, fal_key)

    # Step 3: VEED Lipsync — high quality lip-sync with loop ($0.20 for 30s)
    lipsync_result = _fal_run(
        "veed/lipsync",
        {
            "video_url": hailuo_video_url,
            "audio_url": audio_url,
        },
        fal_key,
        timeout=1200,
    )

    print(f"[SaaSShorts]   VEED Lipsync response keys: {list(lipsync_result.keys())}")
    if "video" in lipsync_result:
        lipsync_video_url = lipsync_result["video"]["url"] if isinstance(lipsync_result["video"], dict) else lipsync_result["video"]
    else:
        raise Exception(f"No video in VEED Lipsync result: {lipsync_result}")

    with httpx.Client(timeout=180.0) as client:
        vid_resp = client.get(lipsync_video_url)
        with open(output_path, "wb") as f:
            f.write(vid_resp.content)

    print(f"[SaaSShorts] ✅ Talking head (low cost): {output_path}")
    return output_path


SYNC_LIPSYNC_MODELS = {"sync-3", "lipsync-2-pro", "lipsync-2"}
SYNC_LIPSYNC_MODES = {"cut_off", "loop", "bounce", "silence", "remap"}


def _nonempty(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0


def _looks_blank(path: str, *, dark_threshold: float = 8.0, flat_std_threshold: float = 3.0) -> bool:
    """True if the image is effectively empty — near-black or one flat color.

    Flux occasionally returns a solid black (or otherwise uniform) PNG when its
    moderation trips or a generation fails. The file is a valid non-empty PNG, so
    `_nonempty` passes, but it renders as a black square in the storyboard. Catch
    it by pixel statistics: a near-zero mean means near-black; a near-zero std
    means a single flat color with no detail. A real photo — even a dim one —
    keeps plenty of variance, so this stays conservative to avoid false rejects.
    """
    try:
        from PIL import Image
        import numpy as np

        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((64, 64))  # stats are scale-invariant; downscale for speed
            arr = np.asarray(im, dtype="float32")
        if arr.size == 0:
            return True
        return float(arr.mean()) < dark_threshold or float(arr.std()) < flat_std_threshold
    except Exception:
        # If we can't inspect it, don't block: a questionable frame beats a false
        # reject that would kill a perfectly good generation.
        return False


def _newest_existing(paths: List[str]) -> Optional[str]:
    existing = [path for path in paths if _nonempty(path)]
    if not existing:
        return None
    return sorted(existing, key=lambda path: os.path.getmtime(path), reverse=True)[0]


def _newest_glob(patterns: List[str], exclude: Callable[[str], bool] = None) -> Optional[str]:
    candidates = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))
    if exclude:
        candidates = [path for path in candidates if not exclude(path)]
    return _newest_existing(candidates)


def build_sync_lipsync_request(
    video_url: str,
    audio_url: str,
    model: str = "sync-3",
    sync_mode: str = "cut_off",
) -> tuple[str, dict]:
    """Build fal.ai Sync Lipsync model id and payload."""
    model = (model or "sync-3").strip()
    sync_mode = (sync_mode or "cut_off").strip()

    if model not in SYNC_LIPSYNC_MODELS:
        raise ValueError(f"Unsupported lip-sync model: {model}")
    if sync_mode not in SYNC_LIPSYNC_MODES:
        raise ValueError(f"Unsupported lip-sync mode: {sync_mode}")

    payload = {
        "video_url": video_url,
        "audio_url": audio_url,
        "sync_mode": sync_mode,
    }
    if model == "sync-3":
        return "fal-ai/sync-lipsync/v3", payload

    payload["model"] = model
    return "fal-ai/sync-lipsync/v2", payload


def resolve_saas_lipsync_assets(output_dir: str) -> dict:
    """
    Find cached assets needed for post-generation lip-sync and recomposition.
    Handles empty slugs from non-Latin titles, e.g. __head.mp4 / __voice.mp3.
    """
    if not os.path.isdir(output_dir):
        raise FileNotFoundError(f"AI Shorts job output directory not found: {output_dir}")

    talking_head = _newest_glob(
        [os.path.join(output_dir, "*_head.mp4")],
        exclude=lambda path: "_head_lipsync_" in os.path.basename(path),
    )
    if not talking_head:
        raise FileNotFoundError("Cached talking-head video not found for lip-sync")

    base_name = os.path.basename(talking_head)
    prefix = base_name[:-len("_head.mp4")] if base_name.endswith("_head.mp4") else os.path.splitext(base_name)[0]

    audio = _newest_existing([
        os.path.join(output_dir, f"{prefix}_voice.mp3"),
        os.path.join(output_dir, f"{prefix}_voice.wav"),
    ]) or _newest_glob([
        os.path.join(output_dir, "*_voice.mp3"),
        os.path.join(output_dir, "*_voice.wav"),
    ])
    if not audio:
        raise FileNotFoundError("Cached voiceover audio not found for lip-sync")

    subtitles = _newest_existing([
        os.path.join(output_dir, f"{prefix}_subs.ass"),
        os.path.join(output_dir, f"{prefix}_subs.srt"),
    ]) or _newest_glob([
        os.path.join(output_dir, "*_subs.ass"),
        os.path.join(output_dir, "*_subs.srt"),
    ])
    if not subtitles:
        raise FileNotFoundError("Cached subtitles not found for recomposition")

    final = _newest_existing([
        os.path.join(output_dir, f"{prefix}_final.mp4"),
    ]) or os.path.join(output_dir, f"{prefix}_final.mp4")

    actor_image = _newest_existing([
        os.path.join(output_dir, f"{prefix}_actor.png"),
        os.path.join(output_dir, "selected_actor.png"),
    ]) or _newest_glob([
        os.path.join(output_dir, "*_actor.png"),
        os.path.join(output_dir, "selected_actor.*"),
    ])

    metadata = {}
    meta_path = os.path.join(output_dir, "gallery_metadata.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception:
            metadata = {}

    broll_clips = []
    broll_segments = [
        seg for seg in metadata.get("segments", [])
        if seg.get("visual") == "broll" and seg.get("broll_prompt")
    ]
    for i, seg in enumerate(broll_segments):
        broll_path = _newest_existing([
            os.path.join(output_dir, f"{prefix}_broll_mockup_{i}.mp4"),
            os.path.join(output_dir, f"{prefix}_broll_ai_{i}.mp4"),
            os.path.join(output_dir, f"{prefix}_broll_{i}.mp4"),
        ]) or _newest_glob([
            os.path.join(output_dir, f"*_broll_*_{i}.mp4"),
            os.path.join(output_dir, f"*_broll_{i}.mp4"),
        ])
        if broll_path:
            broll_clips.append({
                "path": broll_path,
                "start": seg["start"],
                "end": seg["end"],
            })

    return {
        "prefix": prefix,
        "talking_head": talking_head,
        "audio": audio,
        "subtitles": subtitles,
        "final": final,
        "actor_image": actor_image or "",
        "broll_clips": broll_clips,
        "hook_text": metadata.get("hook_text", ""),
        "metadata": metadata,
    }


def generate_sync_lipsync_video(
    video_path: str,
    audio_path: str,
    fal_key: str,
    output_path: str,
    model: str = "sync-3",
    sync_mode: str = "cut_off",
) -> str:
    """Run a standalone Sync Lipsync pass on an existing talking-head video."""
    print(f"[SaaSShorts] Running standalone lip-sync ({model}, {sync_mode})...")

    video_url = _fal_upload_file(video_path, fal_key)
    audio_url = _fal_upload_file(audio_path, fal_key)
    model_id, payload = build_sync_lipsync_request(video_url, audio_url, model, sync_mode)

    result = _fal_run(model_id, payload, fal_key, timeout=2400)
    video = result.get("video")
    output_url = video.get("url") if isinstance(video, dict) else video
    if not output_url:
        raise Exception(f"No video in Sync Lipsync result: {result}")

    with httpx.Client(timeout=300.0) as client:
        resp = client.get(output_url)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)

    print(f"[SaaSShorts] Lip-synced head: {output_path}")
    return output_path


def estimate_sync_lipsync_cost(model: str, duration_seconds: float) -> Optional[float]:
    """Estimate Sync Lipsync cost for UI metadata."""
    duration_minutes = max(duration_seconds, 0) / 60
    if model == "sync-3":
        return round(duration_minutes * 8.0, 2)
    if model == "lipsync-2":
        return round(duration_minutes * 3.0, 2)
    if model == "lipsync-2-pro":
        return round(duration_minutes * 5.0, 2)
    return None


def _video_version_index(version_id: str) -> Optional[int]:
    match = re.fullmatch(r"v(\d+)", str(version_id or "").strip().lower())
    return int(match.group(1)) if match else None


def _next_lipsync_final_path(output_dir: str, prefix: str, metadata: dict, model: str) -> str:
    """Create a new final-video path for a lip-sync version without touching the current final."""
    versions = (metadata.get("versions") if isinstance(metadata, dict) else []) or []
    indexes = [
        index
        for index in (_video_version_index(item.get("id")) for item in versions if isinstance(item, dict))
        if index is not None
    ]

    version_pattern = os.path.join(output_dir, f"{prefix}_final_v*.mp4")
    for path in glob.glob(version_pattern):
        match = re.search(r"_final_v(\d+)_", os.path.basename(path))
        if match:
            indexes.append(int(match.group(1)))

    next_index = max(indexes or [1]) + 1
    safe_model = re.sub(r"[^a-z0-9]+", "_", (model or "lipsync").lower()).strip("_") or "lipsync"

    while True:
        candidate = os.path.join(output_dir, f"{prefix}_final_v{next_index:03d}_{safe_model}.mp4")
        if not os.path.exists(candidate):
            return candidate
        next_index += 1


def apply_lipsync_to_saas_job(
    output_dir: str,
    fal_key: str,
    model: str = "sync-3",
    sync_mode: str = "cut_off",
    log: Callable[[str], None] = print,
) -> dict:
    """Post-process an existing AI Shorts job with standalone lip-sync."""
    assets = resolve_saas_lipsync_assets(output_dir)
    safe_model = re.sub(r"[^a-z0-9]+", "_", model.lower()).strip("_") or "sync_3"
    lipsynced_head = os.path.join(output_dir, f"{assets['prefix']}_head_lipsync_{safe_model}.mp4")
    versioned_final = _next_lipsync_final_path(output_dir, assets["prefix"], assets["metadata"], model)

    log(f"[LipSync 1/3] Uploading cached talking head and voiceover to fal.ai ({model}).")
    voiceover_preparation = prepare_voiceover_for_video_generation(assets["audio"], log=log)
    lipsync_audio = voiceover_preparation["path"]

    generate_sync_lipsync_video(
        assets["talking_head"],
        lipsync_audio,
        fal_key,
        lipsynced_head,
        model=model,
        sync_mode=sync_mode,
    )

    log("[LipSync 2/3] Re-compositing final video with the lip-synced head.")
    try:
        spoken_words = transcribe_audio_for_subs(lipsync_audio)
    except Exception:
        spoken_words = []
    composite_video(
        lipsynced_head,
        assets["broll_clips"],
        assets["subtitles"],
        assets["hook_text"],
        versioned_final,
        jump_cut_words=spoken_words,
    )

    duration = _get_media_duration(lipsync_audio)
    log("[LipSync 3/3] Final video updated.")

    return {
        "video_path": versioned_final,
        "video_filename": os.path.basename(versioned_final),
        "previous_video_path": assets["final"],
        "lipsynced_head": lipsynced_head,
        "actor_image": assets["actor_image"],
        "duration": duration,
        "lipsync_model": model,
        "lipsync_sync_mode": sync_mode,
        "lipsync_cost_estimate": estimate_sync_lipsync_cost(model, duration),
        "voiceover_preparation": voiceover_preparation,
        "metadata": assets["metadata"],
    }


def generate_broll(
    prompt: str, fal_key: str, output_path: str, duration: str = "5"
) -> str:
    """
    Generate b-roll: Recraft V4 image + Ken Burns zoom effect via FFmpeg.
    """
    print(f"[SaaSShorts] 🎬 Generating b-roll image + Ken Burns effect...")

    dur_secs = int(duration)
    img_path = output_path.replace(".mp4", "_img.png")

    # Step 1: Generate a high-quality still image with Flux 2 Pro.
    # Keep the UGC smartphone aesthetic so b-roll matches the actor shots
    # instead of looking like stock photography.
    result = _fal_run(
        "fal-ai/flux-2-pro",
        {
            "prompt": (
                f"{prompt}. Authentic vertical smartphone photo, natural light, "
                "realistic everyday scene, candid phone footage, natural imperfections, "
                "plain unbranded surfaces, not a studio shot."
            ),
            "image_size": "portrait_16_9",
            "safety_tolerance": 5,
        },
        fal_key,
        timeout=1200,
    )

    # Flux 2 Pro returns images in "images" or "output" key
    images = result.get("images") or result.get("output", [])
    if not images:
        raise Exception(f"No images in b-roll result: {list(result.keys())}")
    img_url = images[0]["url"] if isinstance(images[0], dict) else images[0]

    with httpx.Client(timeout=60.0) as client:
        img_resp = client.get(img_url)
        with open(img_path, "wb") as f:
            f.write(img_resp.content)

    # Step 2: Ken Burns effect — slow zoom in with slight pan
    fps = 30
    total_frames = dur_secs * fps
    # Zoom from 1.0x to 1.15x over duration (subtle, cinematic)
    zoompan_filter = (
        f"scale=2160:3840,"
        f"zoompan=z='1+0.15*on/{total_frames}':"
        f"x='iw/2-(iw/zoom/2)+10*on/{total_frames}':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d={total_frames}:s=1080x1920:fps={fps},"
        f"setsar=1"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", img_path,          # Input 0: image
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",  # Input 1: silent audio
        "-vf", zoompan_filter,
        "-t", str(dur_secs),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        output_path,
    ]

    subprocess.run(cmd, check=True, capture_output=True)

    # Cleanup temp image
    if os.path.exists(img_path):
        os.remove(img_path)

    print(f"[SaaSShorts] ✅ B-roll (Ken Burns): {output_path}")
    return output_path


# ═══════════════════════════════════════════════════════════════════════
# Phase 4: Compositing (FFmpeg)
# ═══════════════════════════════════════════════════════════════════════

def _write_text_asset(path: str, text: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _ffmpeg_filter_path(path: str) -> str:
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _wrapped_text(text: str, width: int = 24, max_lines: int = 4) -> str:
    text = " ".join(str(text or "").replace("\n", " ").split())
    lines = textwrap.wrap(text, width=width, max_lines=max_lines, placeholder="...")
    return "\n".join(lines)


_PICTOGRAPH_RE = re.compile(
    "["
    "\\U0001F000-\\U0001FAFF"  # emoji, symbols & pictographs
    "\\u2600-\\u27BF"          # misc symbols, dingbats
    "\\u2B00-\\u2BFF"          # arrows incl. the CTA "down arrow"
    "\\u2190-\\u21FF"          # plain arrows
    "\\u2900-\\u297F"          # supplemental arrows
    "\\uFE0E\\uFE0F\\u200D\\u20E3"  # variation selectors, ZWJ, keycap
    "]+"
)


def _strip_pictographs(text: str) -> str:
    """Bundled fonts have no emoji glyphs — libass would render tofu boxes."""
    return re.sub(r"\s{2,}", " ", _PICTOGRAPH_RE.sub("", str(text or ""))).strip()


_CAPTION_QUIET_PUNCTUATION_RE = re.compile(r"[;…]|(?<!\d)[.,:]|[.,:](?!\d)")


def _format_caption_display_text(text: str) -> str:
    """Remove low-signal punctuation from kinetic captions, preserving numeric separators."""
    cleaned = _CAPTION_QUIET_PUNCTUATION_RE.sub("", str(text or ""))
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _escape_ass_text(text: str) -> str:
    """Escape user text for ASS while keeping it readable."""
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", "\\N")
    )


def _pick_caption_highlight_word(text: str, keywords: Optional[list] = None) -> str:
    """Pick the word to color-accent in a subtitle chunk.

    Script-provided caption_keywords (written by Gemini per product) win;
    otherwise fall back to the longest sufficiently heavy word.
    """
    words = re.findall(r"[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9-]{2,}", text.upper())
    if not words:
        return ""
    priority = {str(k).upper() for k in (keywords or []) if str(k).strip()}
    for word in words:
        if word in priority:
            return word
    longest = max(words, key=len)
    return longest if len(longest) >= 8 else ""


def _highlight_ass_caption(text: str, reset_style: str = "Subtitle", keywords: Optional[list] = None) -> str:
    safe_text = _escape_ass_text(text.upper())
    target = _pick_caption_highlight_word(text, keywords=keywords)
    if not target:
        return safe_text
    pattern = re.compile(rf"(?<![A-ZА-ЯЁ0-9-]){re.escape(target)}(?![A-ZА-ЯЁ0-9-])")
    # Color-only reset (not \r): \r would cancel the line's pop-in transform mid-flight.
    replacement = r"{\c&H0066D1FF&}" + target + r"{\c&HFFFFFF&}"
    return pattern.sub(lambda _: replacement, safe_text, count=1)


# Pop-in: fade + 85%→100% scale over 90ms. Subtle CapCut-style life instead of
# captions that snap on like dictionary entries.
_SUB_POP_TAG = r"{\fad(60,40)\fscx85\fscy85\t(0,90,\fscx100\fscy100)}"


def generate_product_broll(
    segment: dict,
    script: dict,
    output_path: str,
    duration: str = "5",
) -> str:
    """
    Generate clean product-style b-roll locally with FFmpeg.
    This avoids synthetic stock-looking AI scenes and does not spend fal credits.
    """
    print("[SaaSShorts] Generating product mockup b-roll...")

    dur_secs = int(duration)
    base = output_path.replace(".mp4", "")
    product_name = (
        script.get("_product_name")
        or script.get("product_name")
        or script.get("title")
        or "Product"
    )
    segment_type = segment.get("type", "demo")
    language = script.get("language", "en")

    if segment_type == "problem":
        eyebrow = "ПРОБЛЕМА" if language == "ru" else "PROBLEM"
        default_bullets = ["триггер", "тяга", "автопилот"] if language == "ru" else ["trigger", "craving", "autopilot"]
    else:
        eyebrow = "ПЛАН" if language == "ru" else "PLAN"
        default_bullets = ["чеклист", "трекер", "7 дней"] if language == "ru" else ["checklist", "tracker", "7 days"]

    # Prefer script-provided bullets (Gemini writes them per product); the
    # defaults only make sense for habit/nutrition content.
    script_bullets = [str(b).strip() for b in (segment.get("bullets") or []) if str(b).strip()]
    bullets = script_bullets[:3] if script_bullets else default_bullets

    source_text = segment.get("subtitle_text") or segment.get("narration") or product_name
    title_text = _wrapped_text(product_name, width=22, max_lines=2)
    body_text = _wrapped_text(source_text, width=24, max_lines=3)

    eyebrow_path = _write_text_asset(f"{base}_eyebrow.txt", eyebrow)
    title_path = _write_text_asset(f"{base}_title.txt", title_text)
    body_path = _write_text_asset(f"{base}_body.txt", body_text)
    bullet_paths = [
        _write_text_asset(f"{base}_bullet_{i}.txt", f"✓ {bullet}")
        for i, bullet in enumerate(bullets)
    ]

    font_regular = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    font_bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    fade_out_start = max(dur_secs - 0.25, 0)

    vf_parts = [
        "drawbox=x=0:y=0:w=1080:h=1920:color=0x101014@1:t=fill",
        "drawbox=x=86:y=230:w=908:h=1340:color=0x1b1b22@1:t=fill",
        "drawbox=x=116:y=260:w=848:h=1280:color=0xffffff@0.035:t=fill",
        "drawbox=x=150:y=330:w=780:h=1060:color=0x0d1117@1:t=fill",
        "drawbox=x=190:y=390:w=700:h=90:color=0x8b5cf6@0.18:t=fill",
        (
            f"drawtext=fontfile={font_bold}:textfile='{_ffmpeg_filter_path(eyebrow_path)}':"
            "fontcolor=0xC4B5FD:fontsize=34:x=190:y=292"
        ),
        (
            f"drawtext=fontfile={font_bold}:textfile='{_ffmpeg_filter_path(title_path)}':"
            "fontcolor=white:fontsize=56:line_spacing=12:x=190:y=515"
        ),
        (
            f"drawtext=fontfile={font_regular}:textfile='{_ffmpeg_filter_path(body_path)}':"
            "fontcolor=0xD4D4D8:fontsize=38:line_spacing=12:x=190:y=710"
        ),
    ]

    for i, path in enumerate(bullet_paths):
        y = 980 + i * 115
        vf_parts.extend([
            f"drawbox=x=190:y={y}:w=700:h=78:color=0xffffff@0.08:t=fill",
            (
                f"drawtext=fontfile={font_bold}:textfile='{_ffmpeg_filter_path(path)}':"
                f"fontcolor=white:fontsize=34:x=225:y={y + 18}"
            ),
        ])

    vf_parts.extend([
        "drawbox=x=220:y=1325:w=640:h=6:color=0x8b5cf6@0.65:t=fill",
        f"fade=t=in:st=0:d=0.2,fade=t=out:st={fade_out_start:.2f}:d=0.25",
        "setsar=1",
    ])

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x101014:s=1080x1920:r=30:d={dur_secs}",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-vf", ",".join(vf_parts),
        "-t", str(dur_secs),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    for path in [eyebrow_path, title_path, body_path, *bullet_paths]:
        if os.path.exists(path):
            os.remove(path)

    print(f"[SaaSShorts] Product mockup b-roll: {output_path}")
    return output_path


def _get_media_duration(path: str) -> float:
    """Get duration of a media file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout.strip()
        if output:
            return float(output)
    except Exception as e:
        print(f"[SaaSShorts] ⚠️ ffprobe failed for {path}: {e}")
    return 30.0  # Fallback to 30s estimate


def _get_media_stream_duration(path: str, stream_type: str) -> float:
    """Get the first audio/video stream duration without using container fallback."""
    selector = "v:0" if stream_type == "video" else "a:0"
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", selector,
        "-show_entries", "stream=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        for line in result.stdout.splitlines():
            value = line.strip()
            if value and value.upper() != "N/A":
                return float(value)
    except Exception as e:
        print(f"[SaaSShorts] ffprobe stream duration failed for {path}: {e}")
    return 0.0


# No real talking-head voiceover is under a second: anything shorter is a failed
# TTS artifact (empty text, dropped request) that must not reach the video model.
_MIN_VOICEOVER_SECONDS = 1.0


def _decodable_audio_duration(path: str) -> Optional[float]:
    """Duration of a real, decodable audio stream, or None when unusable.

    Unlike `_get_media_duration`, this never masks a decode failure with a 30s
    estimate. Callers use it to reject a voiceover ffmpeg/Kling cannot load
    (e.g. an over-trimmed clip collapsed to a headerless MP3 stub), so a broken
    file fails fast with a clear cause instead of surfacing three steps later as
    an opaque "No completed talking-head attempts".
    """
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        return None
    # Probe the audio stream first, then the container: a valid VBR MP3 may report
    # only one of the two, so we treat the file as broken only when both are absent.
    probes = (
        ("-select_streams", "a:0", "-show_entries", "stream=duration"),
        ("-show_entries", "format=duration"),
    )
    for probe in probes:
        cmd = [
            "ffprobe", "-v", "error", *probe,
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
        except Exception as e:
            print(f"[SaaSShorts] audio decode probe failed for {path}: {e}")
            continue
        for line in result.stdout.splitlines():
            value = line.strip()
            if not value or value.upper() == "N/A":
                continue
            try:
                seconds = float(value)
            except ValueError:
                continue
            if seconds > 0:
                return seconds
    return None


def talking_head_quality_path(video_path: str) -> str:
    """Sidecar path for quality diagnostics tied to a generated talking head."""
    if video_path.lower().endswith(".mp4"):
        return video_path[:-4] + "_quality.json"
    return f"{video_path}.quality.json"


def _write_json_file(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _read_json_file(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def inspect_talking_head_quality(
    talking_head_path: str,
    reference_audio_path: str,
    threshold: float = 0.3,
) -> dict:
    """
    Compare generated talking-head stream lengths with the reference audio.

    This is deliberately diagnostic only: it does not trim, stretch, or retime
    the generated video.
    """
    reference_audio_duration = _get_media_duration(reference_audio_path)
    video_stream_duration = _get_media_stream_duration(talking_head_path, "video")
    embedded_audio_duration = _get_media_stream_duration(talking_head_path, "audio")

    video_reference_delta = video_stream_duration - reference_audio_duration
    embedded_reference_delta = embedded_audio_duration - reference_audio_duration if embedded_audio_duration else None

    warnings = []
    if video_stream_duration <= 0:
        warnings.append("Could not read talking-head video stream duration.")
    elif abs(video_reference_delta) > threshold:
        direction = "longer" if video_reference_delta > 0 else "shorter"
        warnings.append(
            f"Kling returned video {abs(video_reference_delta):.2f}s {direction} than the reference voiceover."
        )

    if embedded_audio_duration <= 0:
        warnings.append("Generated talking head has no readable embedded audio stream.")
    elif embedded_reference_delta is not None and abs(embedded_reference_delta) > threshold:
        direction = "longer" if embedded_reference_delta > 0 else "shorter"
        warnings.append(
            f"Embedded talking-head audio is {abs(embedded_reference_delta):.2f}s {direction} than the reference voiceover."
        )

    status = "needs_review" if warnings else "ok"
    return {
        "status": status,
        "threshold": threshold,
        "reference_audio_duration": round(reference_audio_duration, 3),
        "video_stream_duration": round(video_stream_duration, 3),
        "embedded_audio_duration": round(embedded_audio_duration, 3),
        "video_reference_delta": round(video_reference_delta, 3),
        "embedded_reference_delta": round(embedded_reference_delta, 3) if embedded_reference_delta is not None else None,
        "abs_video_reference_delta": round(abs(video_reference_delta), 3),
        "abs_embedded_reference_delta": round(abs(embedded_reference_delta), 3) if embedded_reference_delta is not None else None,
        "warnings": warnings,
    }


def select_best_talking_head_attempt(attempts: list) -> dict:
    """Pick the first passing attempt, otherwise the attempt closest to audio length."""
    completed = [attempt for attempt in attempts if attempt.get("output_path") and not attempt.get("error")]
    if not completed:
        # Surface the underlying provider error (e.g. Kling's 422 audio_load_error)
        # instead of a bare "no attempts": the real cause is otherwise buried in a
        # per-attempt JSON sidecar and the failure looks inexplicable.
        errors = "; ".join(
            f"{attempt.get('name', '?')}: {attempt['error']}"
            for attempt in attempts
            if attempt.get("error")
        )
        raise Exception(
            f"No completed talking-head attempts ({errors})"
            if errors
            else "No completed talking-head attempts"
        )

    for attempt in completed:
        if attempt.get("quality", {}).get("status") == "ok":
            return attempt

    return min(
        completed,
        key=lambda attempt: attempt.get("quality", {}).get("abs_video_reference_delta", float("inf")),
    )


def create_kling_tail_padded_audio(audio_path: str, output_path: str, tail_silence: float = 0.45) -> str:
    """Create a retry-only audio file with a short silent tail for Kling."""
    if (
        os.path.exists(output_path)
        and os.path.getsize(output_path) > 0
        and os.path.getmtime(output_path) >= os.path.getmtime(audio_path)
    ):
        return output_path

    for stale_path in (output_path, f"{output_path}.fal_url.txt"):
        try:
            if os.path.exists(stale_path):
                os.remove(stale_path)
        except OSError:
            pass

    cmd = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-af", f"apad=pad_dur={tail_silence}",
        "-c:a", "libmp3lame", "-b:a", "128k",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def prepared_voiceover_path(audio_path: str) -> str:
    """Path for the voiceover file cleaned for video/lip-sync generation."""
    root, ext = os.path.splitext(audio_path)
    return f"{root}_clean{ext or '.mp3'}"


def _parse_audio_silence_events(log_text: str, duration: float) -> dict:
    """Parse ffmpeg silencedetect output into leading/trailing silence metrics."""
    starts = [
        float(match.group(1))
        for match in re.finditer(r"silence_start:\s*([0-9.]+)", log_text or "")
    ]
    ends = [
        float(match.group(1))
        for match in re.finditer(r"silence_end:\s*([0-9.]+)", log_text or "")
    ]

    leading_silence = 0.0
    if starts and starts[0] <= 0.08 and ends:
        leading_silence = max(0.0, ends[0])

    trailing_silence = 0.0
    if starts:
        last_start = starts[-1]
        last_end = ends[-1] if ends else duration
        if duration <= 0 or abs(duration - last_end) <= 0.25 or last_end >= duration - 0.25:
            trailing_silence = max(0.0, duration - last_start)

    return {
        "leading_silence": round(leading_silence, 3),
        "trailing_silence": round(trailing_silence, 3),
        "silence_events": len(starts),
    }


def inspect_voiceover_silence(
    audio_path: str,
    threshold_db: int = -45,
    min_silence: float = 0.15,
    duration: float = None,
) -> dict:
    """Detect leading/trailing silence in a voiceover file."""
    duration = _get_media_duration(audio_path) if duration is None else duration
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", audio_path,
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_silence}",
        "-f", "null",
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if getattr(result, "returncode", 0) not in (0, None):
        raise RuntimeError((result.stderr or result.stdout or "ffmpeg silencedetect failed").strip())

    metrics = _parse_audio_silence_events(
        f"{getattr(result, 'stdout', '')}\n{getattr(result, 'stderr', '')}",
        duration,
    )
    metrics["duration"] = round(duration, 3)
    metrics["threshold_db"] = threshold_db
    metrics["min_silence"] = min_silence
    return metrics


def prepare_voiceover_for_video_generation(
    audio_path: str,
    log: Callable[[str], None] = print,
) -> dict:
    """
    Create a clean voiceover file for audio-driven video models.

    Kling Avatar v2 derives output length and lip movement from the submitted
    audio file, so trailing TTS silence must be removed before upload.
    """
    clean_path = prepared_voiceover_path(audio_path)
    meta_path = f"{clean_path}.meta.json"
    source_stat = os.stat(audio_path)
    source_signature = {
        "source_path": audio_path,
        "source_size": source_stat.st_size,
        "source_mtime_ns": source_stat.st_mtime_ns,
    }

    def _finalize(report: dict) -> dict:
        # Last line of defence before the audio reaches Kling: reject anything
        # empty, undecodable, or sub-second (a failed/empty TTS). This guards
        # every return path — including a stale cache hit that still points at a
        # corrupt clip — so the job fails with a clear cause, not a downstream 422.
        usable = _decodable_audio_duration(report.get("path"))
        if usable is None or usable < _MIN_VOICEOVER_SECONDS:
            raise ValueError(
                "Voiceover audio is empty or too short to animate "
                f"({'unreadable' if usable is None else f'{usable:.2f}s'}) — "
                "add spoken lines to the script before generating video."
            )
        return report

    cached = _read_json_file(meta_path)
    if (
        cached.get("source_size") == source_signature["source_size"]
        and cached.get("source_mtime_ns") == source_signature["source_mtime_ns"]
        and os.path.exists(clean_path)
        and os.path.getsize(clean_path) > 0
    ):
        return _finalize(cached)

    for stale_path in (clean_path, f"{clean_path}.fal_url.txt", meta_path):
        try:
            if os.path.exists(stale_path):
                os.remove(stale_path)
        except OSError:
            pass

    original_duration = _get_media_duration(audio_path)
    try:
        silence = inspect_voiceover_silence(audio_path, duration=original_duration)
        # Trim head silence, then areverse to trim tail silence the same way.
        # A positive stop_periods would cut at the FIRST internal pause and
        # truncate speech: conversational voiceovers are full of such pauses.
        edge_trim = "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB"
        filter_expr = f"{edge_trim},areverse,{edge_trim},areverse"
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-af", filter_expr,
            "-c:a", "libmp3lame", "-b:a", "192k",
            clean_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        clean_duration = _decodable_audio_duration(clean_path)
        if clean_duration is None:
            # silenceremove collapsed the clip to an unreadable stub. Drop it and
            # fall back to the raw audio below (which _finalize then re-checks).
            try:
                os.remove(clean_path)
            except OSError:
                pass
            raise RuntimeError("cleaned audio is empty or undecodable")
        expected_speech = original_duration - silence.get("leading_silence", 0.0) - silence.get("trailing_silence", 0.0)
        if clean_duration + 1.0 < expected_speech:
            try:
                os.remove(clean_path)
            except OSError:
                pass
            raise RuntimeError(
                f"trimmed audio is {clean_duration:.2f}s, expected ~{expected_speech:.2f}s of speech"
            )
        trimmed = clean_duration < original_duration - 0.05
        report = {
            **source_signature,
            "path": clean_path,
            "original_path": audio_path,
            "original_duration": round(original_duration, 3),
            "duration": round(clean_duration, 3),
            "leading_silence": silence.get("leading_silence", 0.0),
            "trailing_silence": silence.get("trailing_silence", 0.0),
            "silence_events": silence.get("silence_events", 0),
            "trimmed": trimmed,
            "status": "trimmed" if trimmed else "normalized",
        }
        _write_json_file(meta_path, report)
        if report["trailing_silence"] >= 0.2 or trimmed:
            log(
                "[2/6] Voiceover cleaned: "
                f"{report['original_duration']:.2f}s -> {report['duration']:.2f}s "
                f"(tail silence ~{report['trailing_silence']:.2f}s)."
            )
    except Exception as error:
        report = {
            **source_signature,
            "path": audio_path,
            "original_path": audio_path,
            "original_duration": round(original_duration, 3),
            "duration": round(original_duration, 3),
            "leading_silence": 0.0,
            "trailing_silence": 0.0,
            "silence_events": 0,
            "trimmed": False,
            "status": "fallback_raw_audio",
            "warning": f"Voiceover cleanup skipped: {error}",
        }
        log(f"[2/6] Voiceover cleanup skipped: {error}")

    return _finalize(report)


def _format_ass_time(seconds: float) -> str:
    """Format time for ASS subtitle format: H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def transcribe_audio_for_subs(audio_path: str, language: Optional[str] = None) -> list:
    """
    Transcribe audio with word-level timestamps using faster-whisper.
    Returns list of {"word": str, "start": float, "end": float}.

    `language` ("ru", "en"...) skips auto-detection: the base model misdetects
    short clips and degrades badly on accented speech without the hint.
    """
    from faster_whisper import WhisperModel

    print(f"[SaaSShorts] 🎙️ Transcribing audio for subtitles...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, word_timestamps=True, language=language)

    words = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                words.append({
                    "word": w.word.strip(),
                    "start": w.start,
                    "end": w.end,
                })

    print(f"[SaaSShorts] ✅ Transcribed {len(words)} words")
    return words


def _align_asr_words_to_script(asr_words: list, script_text: str, log: Callable[[str], None] = print) -> list:
    """
    Replace Whisper's guessed words with the known script text, keeping ASR timings.

    The voiceover is TTS of `script_text`, so the words are known in advance and
    the small Whisper model only needs to supply timings — its misheard words
    («слабое» for «слабая») must never reach the subtitles. Tokens are matched
    by normalized form; script words Whisper missed get timings interpolated
    between matched neighbours. Falls back to the raw ASR words when the audio
    clearly diverges from the script (wrong file, improvised speech).
    """
    if not asr_words:
        return asr_words

    # Punctuation-only tokens («—») carry no alignment signal: glue them to the
    # previous word so subtitles keep them without skewing the match.
    script_tokens: list = []
    for token in _strip_audio_tags(script_text or "").split():
        if _normalize_align_token(token) or not script_tokens:
            script_tokens.append(token)
        else:
            script_tokens[-1] += " " + token
    if not script_tokens:
        return asr_words

    norm_script = [_normalize_align_token(t) for t in script_tokens]
    norm_asr = [_normalize_align_token(w.get("word", "")) for w in asr_words]
    matcher = difflib.SequenceMatcher(None, norm_script, norm_asr, autojunk=False)

    timed: list = [None] * len(script_tokens)
    matched = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                w = asr_words[j1 + k]
                timed[i1 + k] = (float(w["start"]), float(w["end"]))
            matched += i2 - i1
        elif tag == "replace":
            # Same stretch of speech, different transcription: spread the
            # script words evenly over the ASR block's time span.
            start = float(asr_words[j1]["start"])
            end = max(start, float(asr_words[j2 - 1]["end"]))
            count = i2 - i1
            for k in range(count):
                timed[i1 + k] = (
                    start + (end - start) * k / count,
                    start + (end - start) * (k + 1) / count,
                )
        # "delete": script words Whisper missed — interpolated below.
        # "insert": extra ASR words (hallucinations) — dropped.

    ratio = matched / max(len(norm_script), len(norm_asr))
    if ratio < 0.3:
        log(
            f"[SaaSShorts] ⚠️ Script/audio mismatch (only {ratio:.0%} of words match) — "
            "keeping raw transcription for subtitles"
        )
        return asr_words

    # Interpolate timings for script words Whisper missed.
    i = 0
    total = len(script_tokens)
    while i < total:
        if timed[i] is not None:
            i += 1
            continue
        j = i
        while j < total and timed[j] is None:
            j += 1
        if i > 0:
            left = timed[i - 1][1]
        elif j < total:
            left = max(0.0, timed[j][0] - 0.3 * (j - i))
        else:
            left = 0.0
        right = timed[j][0] if j < total else left + 0.3 * (j - i)
        right = max(right, left)
        for k in range(j - i):
            timed[i + k] = (
                left + (right - left) * k / (j - i),
                left + (right - left) * (k + 1) / (j - i),
            )
        i = j

    aligned = []
    prev_end = 0.0
    for token, (start, end) in zip(script_tokens, timed):
        start = max(float(start), prev_end)
        end = max(float(end), start)
        aligned.append({"word": token, "start": round(start, 3), "end": round(end, 3)})
        prev_end = end
    log(f"[SaaSShorts] Subtitles use script text ({matched}/{len(script_tokens)} words matched ASR exactly)")
    return aligned


_CAPTION_SENTENCE_END_RE = re.compile(r"[.!?…]+[\"»')]*$")


def _chunk_caption_words(words: list, max_words: int) -> list:
    """Group ASR words into caption chunks, breaking early at sentence ends.

    A fixed word stride splits captions mid-phrase («ПРЕДАЛО? ВЕС» — the end of
    one sentence glued to the start of the next); cutting on sentence-final
    punctuation keeps every caption inside a single phrase.
    """
    chunks = []
    group = []
    for word in words:
        group.append(word)
        token = str(word.get("word") or "").strip()
        if len(group) >= max_words or _CAPTION_SENTENCE_END_RE.search(token):
            chunks.append(group)
            group = []
    if group:
        chunks.append(group)
    return chunks


def _speech_onset_mask(audio_path: str, hop: float = 0.01) -> Optional[list]:
    """Per-`hop` map of "is there voice here", straight from frame energy."""
    try:
        import numpy as np

        sample_rate = 16000
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", audio_path, "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"],
            capture_output=True, check=True,
        ).stdout
        samples = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
        frame = int(sample_rate * hop)
        count = len(samples) // frame
        if count < 2:
            return None
        rms = np.sqrt((samples[:count * frame].reshape(count, frame) ** 2).mean(axis=1))
        peak = float(rms.max())
        if peak <= 0:
            return None
        # 6% of the loudest frame ≈ 24 dB below peak: quiet consonants stay in,
        # the breathy [sighs] tag of a real job (-40 dB) stays out.
        return (rms > max(peak * 0.06, 1e-4)).tolist()
    except Exception:
        return None


def _snap_captions_to_speech(
    chunks: list,
    audio_path: str,
    max_lead: float = 0.12,
    max_shift: float = 1.5,
) -> int:
    """Never let a caption appear before its words are audible.

    Whisper hands the silence in front of a word to that word, so after a long
    pause — an `[sighs]` tag renders as a ~1s breath — the caption pops up half
    a second early and then hangs there over silence. On screen that reads as
    the audio drifting away from the picture. Captions that already sit on
    speech are left alone, and a caption is never pushed past its own end.
    """
    voiced = _speech_onset_mask(audio_path)
    if not voiced:
        return 0
    hop = 0.01
    moved = 0
    for chunk in chunks:
        start = float(chunk["start"])
        end = float(chunk["end"])
        index = int(start / hop)
        if index >= len(voiced) or voiced[index]:
            continue
        limit = min(len(voiced), int((start + max_shift) / hop) + 1)
        onset = next((i for i in range(index, limit) if voiced[i]), None)
        if onset is None:
            continue
        new_start = min(max(start, onset * hop - max_lead), end - 0.15)
        if new_start - start > 0.05:
            chunk["start"] = new_start
            moved += 1
    return moved


def generate_tiktok_subs(audio_path: str, output_path: str, max_words: int = 1, words: Optional[list] = None) -> str:
    """
    Generate TikTok-style ASS subtitles from audio using Whisper transcription.

    Style: Big bold centered text, one word at a time, white with black outline.
    Matches actual spoken words with precise timestamps.

    Pass precomputed `words` to reuse an existing transcription.
    """
    if words is None:
        words = transcribe_audio_for_subs(audio_path)
    if not words:
        # Fallback: empty subtitle file
        with open(output_path, "w") as f:
            f.write("")
        return output_path

    chunks = []
    for group in _chunk_caption_words(words, max_words):
        text = _format_caption_display_text(
            _strip_pictographs(" ".join(w["word"] for w in group))
        ).upper()
        if not text:
            continue
        start = group[0]["start"]
        end = group[-1]["end"]
        chunks.append({"text": text, "start": start, "end": end})

    # Build ASS file with TikTok style
    ass_content = """[Script Info]
Title: TikTok Style Subs
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTok,Montserrat ExtraBold,72,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,3,2,2,96,96,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    for chunk in chunks:
        start = _format_ass_time(chunk["start"])
        end = _format_ass_time(chunk["end"])
        text = chunk["text"].replace("\n", "\\N")
        ass_content += f"Dialogue: 0,{start},{end},TikTok,,0,0,0,,{_SUB_POP_TAG}{text}\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    print(f"[SaaSShorts] ✅ TikTok subs: {len(chunks)} captions from {len(words)} words")
    return output_path


def generate_storyboard_ass_subtitles(
    audio_path: str,
    shots: list,
    output_path: str,
    max_words: int = 1,
    words: Optional[list] = None,
    caption_keywords: Optional[list] = None,
) -> str:
    """Generate CapCut-style ASS speech captions (outline + soft shadow, pop-in).

    Top hook/overlay plates were removed by user decision (2026-07-10): they
    crowded the frame and duplicated the spoken hook. `shots` stays in the
    signature for caller compatibility. Pass precomputed `words` to reuse an
    existing transcription and `caption_keywords` (from the script) to drive
    subtitle color-accents.
    """
    if words is None:
        words = transcribe_audio_for_subs(audio_path)
    chunks = []
    for group in _chunk_caption_words(words, max_words):
        text = _format_caption_display_text(
            _strip_pictographs(" ".join(w["word"] for w in group))
        ).upper()
        if not text:
            continue
        chunks.append({
            "text": text,
            "start": group[0]["start"],
            "end": group[-1]["end"],
        })

    snapped = _snap_captions_to_speech(chunks, audio_path)
    if snapped:
        print(f"[SaaSShorts] Captions snapped to speech onset: {snapped}")

    ass_content = """[Script Info]
Title: Storyboard Reels Caption Preset
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subtitle,Montserrat ExtraBold,72,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,0,0,0,0,100,100,0,0,1,3,2,2,96,96,520,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    for chunk in chunks:
        start = _format_ass_time(chunk["start"])
        end = _format_ass_time(chunk["end"])
        text = _highlight_ass_caption(chunk["text"], reset_style="Subtitle", keywords=caption_keywords)
        ass_content += f"Dialogue: 0,{start},{end},Subtitle,,0,0,0,,{_SUB_POP_TAG}{text}\n"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    print(f"[SaaSShorts] Storyboard ASS: {len(chunks)} captions")
    return output_path


def generate_srt_from_script(segments: list, output_path: str) -> str:
    """Fallback: generate basic SRT from script segments (used if no audio available)."""
    srt_content = ""
    index = 1
    for seg in segments:
        text = seg.get("subtitle_text") or seg.get("narration", "")
        if not text:
            continue
        words = text.split()
        chunk_size = 3
        start_time = seg["start"]
        end_time = seg["end"]
        duration = end_time - start_time
        chunks = [words[i : i + chunk_size] for i in range(0, len(words), chunk_size)]
        chunk_dur = duration / max(len(chunks), 1)
        for i, chunk in enumerate(chunks):
            cs = start_time + i * chunk_dur
            ce = min(start_time + (i + 1) * chunk_dur, end_time)
            h, m, s, ms = int(cs//3600), int((cs%3600)//60), int(cs%60), int((cs-int(cs))*1000)
            h2, m2, s2, ms2 = int(ce//3600), int((ce%3600)//60), int(ce%60), int((ce-int(ce))*1000)
            srt_content += f"{index}\n{h:02d}:{m:02d}:{s:02d},{ms:03d} --> {h2:02d}:{m2:02d}:{s2:02d},{ms2:03d}\n{' '.join(chunk).upper()}\n\n"
            index += 1
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    return output_path


def _select_jump_cut_points(
    words: list,
    duration: float,
    min_gap: float = 2.2,
    max_gap: float = 3.8,
) -> list:
    """
    Pick jump-cut timestamps for talking-head footage.

    Within each pacing window prefers the word boundary with the longest pause
    after it, so cuts land between phrases instead of mid-word. Falls back to
    a fixed grid when no transcription is available.
    """
    if duration <= min_gap + 1.2:
        return []

    tail_guard = duration - 1.2

    boundaries = []
    for i, w in enumerate(words or []):
        try:
            end = float(w["end"])
            nxt = float(words[i + 1]["start"]) if i + 1 < len(words) else end
        except (KeyError, TypeError, ValueError):
            continue
        boundaries.append({"t": end, "pause": max(0.0, nxt - end)})

    cuts = []
    if not boundaries:
        step = (min_gap + max_gap) / 2
        t = step
        while t < tail_guard:
            cuts.append(round(t, 3))
            t += step
        return cuts

    last_cut = 0.0
    while True:
        window = [b for b in boundaries if last_cut + min_gap <= b["t"] <= last_cut + max_gap]
        if window:
            cut_t = max(window, key=lambda b: b["pause"])["t"]
        else:
            later = [b for b in boundaries if b["t"] > last_cut + max_gap]
            if not later:
                break
            cut_t = min(b["t"] for b in later)
        if cut_t >= tail_guard:
            break
        cuts.append(round(cut_t, 3))
        last_cut = cut_t
    return cuts


def _punch_in_subsegments(start: float, end: float, cuts: list, edge_guard: float = 0.6) -> list:
    """Split [start, end] at the cut points that fall safely inside it."""
    points = sorted(c for c in cuts if start + edge_guard < c < end - edge_guard)
    times = [start] + points + [end]
    return [(times[i], times[i + 1]) for i in range(len(times) - 1)]


def composite_video(
    talking_head_path: str,
    broll_clips: List[Dict],
    srt_path: str,
    hook_text: str,
    output_path: str,
    jump_cut_words: Optional[List[Dict]] = None,
    punch_in: bool = True,
    music_path: Optional[str] = None,
    # Бед нормализуется к _MUSIC_BED_DBFS, так что это просто подстройка сверху.
    music_volume: float = 1.0,
) -> str:
    """
    Composite talking head + b-roll inserts + subtitles into final video.

    broll_clips: [{"path": "/path/to/clip.mp4", "start": 12, "end": 17}]

    Talking-head stretches are split into jump-cut shots with an alternating
    punch-in zoom so the final edit reads like manual cutting instead of one
    static avatar take. Cuts are video-only: audio is the talking head's
    continuous track, loudness-normalized, with an optional ducked music bed.
    """
    print(f"[SaaSShorts] 🎞️ Compositing final video...")

    # ASS carries its own styles; both variants get fontsdir for bundled fonts.
    sub_filter = _subtitle_filter(srt_path)

    # Normalize all segments to vertical cover. This avoids the old landscape
    # letterbox look where the avatar was tiny inside a 9:16 black frame.
    norm = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920:(iw-ow)/2:(ih-oh)/2,"
        "fps=30,setsar=1"
    )
    # ~15% zoom after norm, biased above center so the face keeps headroom
    punch_zoom = "crop=938:1668:(iw-ow)/2:(ih-oh)*0.3,scale=1080:1920,setsar=1"

    th_duration = _get_media_duration(talking_head_path)
    cuts = _select_jump_cut_points(jump_cut_words or [], th_duration) if punch_in else []

    # Build the segment timeline: talking-head stretches interleaved with b-roll,
    # b-roll segments limited to the actual clip duration.
    segments = []
    sorted_broll = sorted(broll_clips, key=lambda x: x["start"]) if broll_clips else []
    if sorted_broll:
        prev_end = 0.0
        for i, clip in enumerate(sorted_broll):
            actual_dur = _get_media_duration(clip["path"])
            print(f"[SaaSShorts] B-roll {i} actual duration: {actual_dur:.1f}s")
            bstart = clip["start"]
            bend = min(clip["end"], bstart + actual_dur)
            if prev_end < bstart:
                segments.append({"type": "th", "start": prev_end, "end": bstart})
            segments.append({"type": "broll", "index": i, "start": bstart, "end": bend})
            prev_end = bend
        if prev_end < th_duration:
            segments.append({"type": "th", "start": prev_end, "end": th_duration})
    else:
        segments.append({"type": "th", "start": 0.0, "end": th_duration})

    # Expand talking-head segments into jump-cut shots
    shots = []
    for seg in segments:
        if seg["type"] == "th":
            for s, e in _punch_in_subsegments(seg["start"], seg["end"], cuts):
                shots.append({"type": "th", "start": s, "end": e})
        else:
            shots.append(seg)

    if len(shots) == 1 and shots[0]["type"] == "th":
        # Single continuous take: video chain is trivial, audio still gets the mix
        music_idx = "1" if music_path else None
        music_gain_db = _music_bed_gain_db(music_path) if music_path else 0.0
        simple_inputs = [
            "-i", talking_head_path,
            *(["-stream_loop", "-1", "-i", music_path] if music_path else []),
        ]
        measured = _measure_final_loudness(
            simple_inputs, "0", music_idx, music_volume, music_gain_db=music_gain_db,
        )
        audio_parts = _final_audio_filter_parts(
            "0", music_idx, music_volume, measured, music_gain_db=music_gain_db,
        )
        filter_parts = [f"[0:v]{norm},{sub_filter}[finalv]"] + audio_parts
        cmd = [
            "ffmpeg", "-y",
            *simple_inputs,
            "-filter_complex", ";".join(filter_parts),
            "-map", "[finalv]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            output_path,
        ]
        subprocess.run(cmd, check=True)
        print(f"[SaaSShorts] ✅ Final video (simple): {output_path}")
        return output_path

    inputs = ["-i", talking_head_path]
    for clip in sorted_broll:
        inputs.extend(["-i", clip["path"]])
    music_idx = None
    if music_path:
        music_idx = str(1 + len(sorted_broll))
        inputs.extend(["-stream_loop", "-1", "-i", music_path])

    filter_parts = []
    concat_parts = []
    for j, shot in enumerate(shots):
        if shot["type"] == "th":
            vf = norm if j % 2 == 0 else f"{norm},{punch_zoom}"
            filter_parts.append(
                f"[0:v]trim=start={shot['start']:.3f}:end={shot['end']:.3f},setpts=PTS-STARTPTS,{vf}[v{j}]"
            )
        else:
            idx = shot["index"] + 1
            dur = shot["end"] - shot["start"]
            filter_parts.append(
                f"[{idx}:v]trim=start=0:end={dur:.3f},setpts=PTS-STARTPTS,{norm}[v{j}]"
            )
        concat_parts.append(f"[v{j}]")

    filter_parts.append(f"{''.join(concat_parts)}concat=n={len(shots)}:v=1:a=0[outv]")
    filter_parts.append(f"[outv]{sub_filter}[finalv]")
    music_gain_db = _music_bed_gain_db(music_path) if music_path else 0.0
    filter_parts.extend(_final_audio_filter_parts(
        "0", music_idx, music_volume,
        _measure_final_loudness(inputs, "0", music_idx, music_volume, music_gain_db=music_gain_db),
        music_gain_db=music_gain_db,
    ))

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "[finalv]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]

    subprocess.run(cmd, check=True)
    print(f"[SaaSShorts] ✅ Final video ({len(shots)} shots): {output_path}")
    return output_path


# ═══════════════════════════════════════════════════════════════════════
# Orchestrator: Full Pipeline
# ═══════════════════════════════════════════════════════════════════════

def _video_url_from_fal_result(result: dict) -> str:
    video = result.get("video")
    if isinstance(video, dict) and video.get("url"):
        return video["url"]
    if isinstance(video, str):
        return video
    videos = result.get("videos")
    if isinstance(videos, list) and videos:
        first = videos[0]
        if isinstance(first, dict) and first.get("url"):
            return first["url"]
        if isinstance(first, str):
            return first
    for key in ("video_url", "output"):
        value = result.get(key)
        if isinstance(value, dict) and value.get("url"):
            return value["url"]
        if isinstance(value, str):
            return value
    raise Exception(f"No video URL in fal result: {result}")


def _shot_request_prompt(shot: dict) -> str:
    """The prompt a single-shot fal request would carry (mirrors build_kling_v3_storyboard_request)."""
    normalized = normalize_storyboard_shots({"shots": [shot]})
    source = normalized[0] if normalized else shot
    return source.get("generation_prompt") or source.get("scene") or source.get("speech") or "vertical social video shot"


def _cached_clip_prompt(output_path: str) -> Optional[str]:
    try:
        with open(f"{output_path}.meta.json", encoding="utf-8") as f:
            payload = (json.load(f).get("payload") or {})
    except (OSError, json.JSONDecodeError):
        return None
    if "prompt" in payload:
        return payload["prompt"]
    return None


def _storyboard_clip_cache_valid(shot: dict, output_path: str) -> bool:
    """True while a cached Kling V3 clip still matches the shot's current prompt.

    Every caller must go through this (not a bare os.path.exists check), or
    edited prompts get silently ignored on retry. Clips without meta.json
    (legacy jobs) stay valid: regenerating them is a paid call the user did
    not ask for.
    """
    if not (os.path.exists(output_path) and os.path.getsize(output_path) > 0):
        return False
    cached_prompt = _cached_clip_prompt(output_path)
    return cached_prompt is None or cached_prompt == _shot_request_prompt(shot)


def _chunk_request_prompts(shots: list) -> list:
    """Prompts a multi-shot fal request would carry (mirrors build_kling_v3_storyboard_request)."""
    normalized = normalize_storyboard_shots({"shots": shots})
    return [
        shot.get("generation_prompt") or shot.get("scene") or shot.get("speech") or "vertical social video shot"
        for shot in normalized
    ]


def _cached_chunk_prompts(output_path: str) -> Optional[list]:
    try:
        with open(f"{output_path}.meta.json", encoding="utf-8") as f:
            payload = (json.load(f).get("payload") or {})
    except (OSError, json.JSONDecodeError):
        return None
    multi = payload.get("multi_prompt")
    if isinstance(multi, list):
        return [entry.get("prompt") for entry in multi if isinstance(entry, dict)]
    if "prompt" in payload:
        return [payload["prompt"]]
    return None


def _storyboard_chunk_cache_valid(shots: list, output_path: str) -> bool:
    if not (os.path.exists(output_path) and os.path.getsize(output_path) > 0):
        return False
    cached = _cached_chunk_prompts(output_path)
    return cached is None or cached == _chunk_request_prompts(shots)


def generate_storyboard_shot_clip(
    shot: dict,
    fal_key: str,
    output_path: str,
    tier: str = "standard",
    aspect_ratio: str = "9:16",
) -> str:
    """Generate one storyboard shot with Kling V3 and no native audio."""
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        # The UI lets the user edit a shot's Kling prompt and retry the job:
        # the cached clip is only valid while the prompt still matches.
        if _storyboard_clip_cache_valid(shot, output_path):
            return output_path
        print(f"[SaaSShorts] Prompt changed for {os.path.basename(output_path)} — regenerating clip.")
        for stale in (
            output_path,
            f"{output_path}.fal_url.txt",
            f"{output_path}.meta.json",
            f"{output_path}.review.json",
            f"{output_path}.review.jpg",
        ):
            try:
                if os.path.exists(stale):
                    os.remove(stale)
            except OSError:
                pass

    start_image_url = _resolve_storyboard_start_image_url(shot, fal_key)
    model_id, payload = build_kling_v3_storyboard_request(
        [shot],
        tier=tier,
        generation_mode="single_shot",
        aspect_ratio=aspect_ratio,
        start_image_url=start_image_url,
    )
    result = _fal_run(model_id, payload, fal_key, timeout=1800)
    video_url = _video_url_from_fal_result(result)
    with httpx.Client(timeout=300.0) as client:
        vid_resp = client.get(video_url)
        vid_resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(vid_resp.content)

    _write_json_file(f"{output_path}.meta.json", {
        "shot": shot,
        "tier": tier,
        "model_id": model_id,
        "payload": payload,
        "fal_request": result.get("_fal_request", {}),
        "video_url": video_url,
    })
    return output_path


def generate_storyboard_chunk_clip(
    shots: list,
    fal_key: str,
    output_path: str,
    tier: str = "standard",
) -> str:
    """Generate a <=15s multi-shot Kling V3 storyboard chunk."""
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        if _storyboard_chunk_cache_valid(shots, output_path):
            return output_path
        print(f"[SaaSShorts] Prompts changed for {os.path.basename(output_path)} — regenerating chunk.")
        for stale in (output_path, f"{output_path}.fal_url.txt", f"{output_path}.meta.json"):
            try:
                if os.path.exists(stale):
                    os.remove(stale)
            except OSError:
                pass

    model_id, payload = build_kling_v3_storyboard_request(
        shots,
        tier=tier,
        generation_mode="multi_shot",
        aspect_ratio="9:16",
    )
    result = _fal_run(model_id, payload, fal_key, timeout=1800)
    video_url = _video_url_from_fal_result(result)
    with httpx.Client(timeout=300.0) as client:
        vid_resp = client.get(video_url)
        vid_resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(vid_resp.content)

    _write_json_file(f"{output_path}.meta.json", {
        "shots": shots,
        "tier": tier,
        "model_id": model_id,
        "payload": payload,
        "fal_request": result.get("_fal_request", {}),
        "video_url": video_url,
    })
    return output_path


def _parse_review_issues(text: str) -> list:
    """Extract {"issues": [...]} from a Gemini reply that may have prose around it."""
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return []
    issues = data.get("issues")
    if not isinstance(issues, list):
        return []
    return [str(issue).strip() for issue in issues if str(issue).strip()][:5]


def review_clip_quality(
    clip_path: str,
    shot: dict,
    gemini_key: str,
    log: Callable[[str], None] = print,
) -> list:
    """Gemini-vision QC of one generated clip (deferred audit item #13).

    Flags defects a duration check can't see: strangers in b-roll, garbled
    on-screen glyphs, deformed hands. Advisory only — warnings go to the job
    log and quality_warnings; the user decides whether to regenerate (a retry
    is a paid fal call). Result is cached next to the clip.
    """
    review_path = f"{clip_path}.review.json"
    if os.path.exists(review_path):
        try:
            with open(review_path, encoding="utf-8") as f:
                return json.load(f).get("issues", [])
        except (OSError, json.JSONDecodeError):
            pass

    grid_path = f"{clip_path}.review.jpg"
    duration = _get_media_duration(clip_path)
    fps = 4.0 / max(duration, 0.5)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", clip_path,
            # 540px per tile — a 1080x1920 grid, i.e. one full vertical frame
            # worth of pixels. The old 360px halved a 720px Kling clip and made
            # Gemini judge fingers and cutlery on mush; sending the clip's full
            # resolution instead would roughly quadruple the image tokens
            # (Gemini bills them in ~768px tiles) for detail nobody reads.
            "-vf", f"fps={fps:.4f},scale='min(iw,540)':-2,tile=2x2",
            "-frames:v", "1", "-q:v", "4", grid_path,
        ],
        check=True, capture_output=True,
    )

    broll = _is_broll_shot(shot)
    person_rule = (
        "- no people or identifiable generated faces in a b-roll shot unless the requested action "
        "needs a faceless back view, cropped body/hands, silhouette or non-identifiable profile"
        if broll
        else "- a second person appearing, or the actor's identity visibly changing between frames"
    )
    prompt = (
        "You are a QC reviewer for AI-generated vertical video ads. The image is a 2x2 grid of "
        "frames from ONE clip, in time order. These are freeze-frames of moving footage that "
        "plays for a few seconds on a phone: motion blur, soft focus, half-visible props and "
        "awkward mid-motion poses are normal and are NOT defects.\n"
        "Report ONLY defects severe enough that the ad cannot be published — a casual viewer "
        "would notice within a second, at normal playback speed, without pausing:\n"
        f"{person_rule}\n"
        "- garbled glyph-like pseudo-text on screens, labels or documents\n"
        "- badly deformed hands or limbs: extra, missing or fused fingers, an impossible arm\n"
        "Do NOT report the shape of small props, cutlery, utensils, food or other objects — "
        "uneven fork tines or a slightly odd grip do not matter. Do NOT report clothing "
        "wrinkles, lighting, blur, styling or other cosmetic nitpicks. If you had to zoom in "
        "or study the frame to find it, it is not a defect.\n"
        'Reply with JSON only: {"issues": ["короткое описание проблемы по-русски", ...]}. '
        'If the clip is publishable, reply {"issues": []}.'
    )

    from google import genai
    from google.genai import types

    with open(grid_path, "rb") as f:
        image_bytes = f.read()
    client = genai.Client(api_key=gemini_key)
    last_error = None
    for model in _gemini_model_chain():
        try:
            response = client.models.generate_content(
                model=model,
                contents=[types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"), prompt],
            )
            issues = _parse_review_issues(response.text or "")
            _write_json_file(review_path, {"issues": issues, "model": model, "broll": broll})
            return issues
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Gemini vision review failed: {last_error}")


_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_MUSIC_DIR = os.path.join(_ASSETS_DIR, "music")
_FONTS_DIR = os.path.join(_ASSETS_DIR, "fonts")
_MUSIC_EXTENSIONS = (".mp3", ".m4a", ".wav", ".ogg", ".aac", ".flac")


def _subtitle_filter(srt_path: str) -> str:
    """ffmpeg subtitle filter wired to our bundled fonts (the container has no Arial Black)."""
    safe_sub = srt_path.replace("\\", "/").replace(":", "\\:")
    fontsdir = ""
    if os.path.isdir(_FONTS_DIR):
        safe_fonts = _FONTS_DIR.replace("\\", "/").replace(":", "\\:")
        fontsdir = f":fontsdir='{safe_fonts}'"
    if srt_path.endswith(".ass"):
        return f"ass='{safe_sub}'{fontsdir}"
    sub_style = (
        "Alignment=2,Fontname=Montserrat ExtraBold,Fontsize=24,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=4,Shadow=0,MarginV=120,Bold=0"
    )
    return f"subtitles='{safe_sub}':force_style='{sub_style}'{fontsdir}"


def _pick_background_music(seed: str) -> Optional[str]:
    """Deterministically pick a bed track from assets/music (same job — same track)."""
    try:
        tracks = sorted(
            name for name in os.listdir(_MUSIC_DIR)
            if name.lower().endswith(_MUSIC_EXTENSIONS)
        )
    except OSError:
        return None
    if not tracks:
        return None
    digest = int(hashlib.sha1((seed or "").encode("utf-8")).hexdigest(), 16)
    return os.path.join(_MUSIC_DIR, tracks[digest % len(tracks)])


_LOUDNORM_TARGET = "loudnorm=I=-14:TP=-1.5:LRA=11"
_LOUDNORM_MEASURED_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")

# Куда ставим музыкальную подложку по громкости (RMS, dBFS). Голос в финальном
# миксе живёт около -15 dBFS, так что -32 держит бед примерно на 17 dB ниже —
# слышно в паузах, не мешает речи.
_MUSIC_BED_DBFS = -32.0
_music_gain_cache: dict = {}


def _music_bed_gain_db(music_path: str, target_dbfs: float = _MUSIC_BED_DBFS) -> float:
    """Gain that puts ANY bed track at a predictable level under the voiceover.

    A flat `volume=0.16` assumed a normally mastered bed. Our generated track
    sits at -23.7 dBFS, so it got attenuated twice and landed ~25 dB below the
    voice — mixed in, but inaudible on a phone (the user never heard it).
    Measuring the track and normalizing to a target fixes the whole class of
    bug: swap the track and the bed still sits where it should.
    """
    if music_path in _music_gain_cache:
        return _music_gain_cache[music_path]
    gain = 0.0
    try:
        proc = subprocess.run(
            ["ffmpeg", "-v", "info", "-i", music_path, "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, errors="replace", timeout=120,
        )
        match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", proc.stderr or "")
        if match:
            gain = target_dbfs - float(match.group(1))
    except Exception:
        gain = 0.0
    _music_gain_cache[music_path] = gain
    return gain


def _loudnorm_filter(measured: Optional[dict] = None, print_json: bool = False) -> str:
    """The final loudness stage, in one-pass or two-pass form.

    One-pass loudnorm normalizes frame by frame: it rides the gain inside the
    take, squeezes what little dynamic range a TTS voice has left (a real job
    went LRA 3.2 -> 2.3) and overshoots the true-peak ceiling. That flat,
    uniformly loud delivery is a chunk of what reads as "AI voice". Given the
    measurements from a first pass, loudnorm instead applies ONE linear gain to
    the whole track — same -14 LUFS, prosody intact.
    """
    parts = [_LOUDNORM_TARGET]
    if measured:
        parts.append(
            f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
            f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
            f"offset={measured['target_offset']}:linear=true"
        )
    if print_json:
        parts.append("print_format=json")
    return ":".join(parts)


def _final_audio_filter_parts(
    voice_input: str,
    music_input: Optional[str],
    music_volume: float,
    measured: Optional[dict] = None,
    print_json: bool = False,
    music_gain_db: float = 0.0,
) -> list:
    """
    Build the final-mix audio chain: voiceover (+ optional ducked music bed),
    normalized to -14 LUFS — what TikTok/Reels normalize to anyway, so the
    platform doesn't re-compress our mix unpredictably.

    `music_gain_db` comes from `_music_bed_gain_db` and puts the bed at a known
    level whatever the track; `music_volume` is a plain trim on top of that.
    """
    # Either an input index ("3") or a label already built in the graph
    # ("[voicecat]"), which is what the sliced-avatar edit hands over: its voice
    # is stitched from the takes' own audio, not read from one file.
    voice_src = voice_input if voice_input.startswith("[") else f"[{voice_input}:a]"
    parts = []
    if music_input:
        parts.append(f"{voice_src}aresample=48000,asplit=2[vo][vosc]")
        # Normalize the bed to a known level first, then apply the (optional) trim.
        parts.append(
            f"[{music_input}:a]aresample=48000,volume={music_gain_db:.2f}dB,volume={music_volume}[mus]"
        )
        # Music is the main input, voice the sidechain: the bed dips whenever she
        # speaks. Ratio 12 with a 500ms release buried the bed for the whole clip —
        # a reel is nearly wall-to-wall speech, so the bed never came back up.
        parts.append("[mus][vosc]sidechaincompress=threshold=0.05:ratio=6:attack=20:release=300[duck]")
        parts.append("[vo][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix]")
        mix_src = "[mix]"
    else:
        mix_src = voice_src
    parts.append(f"{mix_src}{_loudnorm_filter(measured, print_json)},aresample=48000[aout]")
    return parts


def _measure_final_loudness(
    inputs: list,
    voice_input: str,
    music_input: Optional[str],
    music_volume: float,
    log: Callable[[str], None] = print,
    music_gain_db: float = 0.0,
    voice_parts: Optional[list] = None,
) -> Optional[dict]:
    """Pass 1 of the two-pass loudnorm: measure the finished mix, decode only.

    Runs the exact audio graph of the real render against `-f null`, so the
    numbers describe the mix that will actually be encoded (music bed and
    ducking included). `voice_parts` builds the voice stream when it is not a
    plain input — the sliced-avatar edit stitches it from the takes. Returns
    None on any trouble — the caller then falls back to one-pass, which is worse
    for dynamics but never fails the render.
    """
    parts = list(voice_parts or [])
    parts += _final_audio_filter_parts(
        voice_input, music_input, music_volume, print_json=True, music_gain_db=music_gain_db,
    )
    cmd = [
        "ffmpeg", "-y", *inputs,
        "-filter_complex", ";".join(parts),
        "-map", "[aout]", "-vn", "-f", "null", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=600)
        stderr = proc.stderr or ""
        measured = json.loads(stderr[stderr.rindex("{"):stderr.rindex("}") + 1])
        # A silent or unmeasurable track reports -inf/nan; feeding that back to
        # loudnorm makes it bail out mid-render.
        for key in _LOUDNORM_MEASURED_KEYS:
            if not math.isfinite(float(measured[key])):
                raise ValueError(f"{key}={measured[key]}")
        return {key: measured[key] for key in _LOUDNORM_MEASURED_KEYS}
    except Exception as error:
        log(f"  ⚠️ Loudness measurement failed, falling back to one-pass: {error}")
        return None


# Насколько «дышит» говорящий кадр за свою длину. 6% глаз читает как движение и
# не читает как приём; больше — аттракцион, меньше — незаметно.
_TALKING_PUSH_ZOOM = 0.06
# Короче этого наезд не успевает прочитаться, а на джамп-катах только мельтешит.
_TALKING_PUSH_MIN_SECONDS = 2.4
# Наезд достаётся каждому третьему говорящему кадру. Пока его давали всем, кадр
# ехал всегда, и ролик читался как непрерывная смена крупности вместо смены
# камер. Приём работает, только пока он редкий: крупность — движение по ходу
# реплики, а между кадрами меняется ракурс (см. `_AVATAR_FRAMINGS`).
_TALKING_PUSH_EVERY = 3
# Запас разрешения под зум: zoompan округляет смещение окна до целых пикселей
# входа, и без запаса медленный наезд идёт заметными ступеньками.
_TALKING_PUSH_OVERSAMPLE = "scale=1620:2880"


def _talking_push_in(index: int, duration: float) -> str:
    """Медленный наезд внутри одного говорящего клипа. "" — если он не нужен.

    Kling оживляет неподвижное фото: мимика есть, камера стоит намертво. Две-три
    секунды такого кадра читаются как фотография с говорящим ртом — отсюда
    ощущение, что ролик тянется. Наезд эти секунды держит и ничего не стоит:
    он трогает только картинку, не PTS и не звук, поэтому липсинк не уезжает.

    Достаётся он каждому третьему говорящему кадру и всегда идёт внутрь.
    Чередование «туда-сюда» было нужно, пока наезд стоял на каждом кадре и
    соседи иначе склеивались в один длинный; у редкого соседей нет.
    """
    frames = int(round(max(0.0, duration) * 30))
    if index % _TALKING_PUSH_EVERY or duration < _TALKING_PUSH_MIN_SECONDS or frames < 2:
        return ""
    span = frames - 1
    zoom = f"1+{_TALKING_PUSH_ZOOM}*on/{span}"
    # Центр наезда чуть выше середины: на вертикальном портрете лицо живёт в
    # верхней части кадра, и наезд «в центр» уводит камеру в грудь.
    return (
        f"{_TALKING_PUSH_OVERSAMPLE},"
        f"zoompan=z='{zoom}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)*0.35':"
        "d=1:s=1080x1920:fps=30,setsar=1"
    )


# Шёпот подходит ближе остальных кадров — это его смысл. Но приходит он туда
# сам, за время реплики: статичный кроп на весь клип давал ступеньку крупности
# ровно на склейке, а между кадрами меняется ракурс, не крупность.
_WHISPER_PUSH_ZOOM = 0.18


def _whisper_push_in(duration: float) -> str:
    """Наезд на шёпот — движением внутри кадра, а не ступенькой на склейке."""
    frames = int(round(max(0.0, duration) * 30))
    if frames < 2:
        return ""
    span = frames - 1
    return (
        f"{_TALKING_PUSH_OVERSAMPLE},"
        f"zoompan=z='1+{_WHISPER_PUSH_ZOOM}*on/{span}':x='(iw-iw/zoom)/2':"
        "y='(ih-ih/zoom)*0.42':d=1:s=1080x1920:fps=30,setsar=1"
    )


def _self_voiced_clip(clip: dict) -> bool:
    """A take the avatar model returned with its own lip-synced audio.

    Such a take is used exactly as delivered — whole, sound included. Cutting it
    to the slot and playing the master track under it is arithmetically the same
    picture against the same waveform, but it chops the mouth mid-word at every
    cut: the model always returns a little more picture than audio, and that tail
    is where the lips finish the phrase and close. B-roll has no audio of its own
    and keeps taking the master track.
    """
    if _is_broll_shot(clip.get("shot") or {}):
        return False
    if not clip.get("audio_slice"):
        return False
    try:
        return _get_media_stream_duration(clip["path"], "audio") > 0
    except Exception:
        return False


_REEL_FPS = 30


def _trim_end(seconds: float) -> str:
    """Конец trim'а, попадающий внутрь последнего нужного кадра.

    `trim` пропускает кадры с PTS < end, а запись времени с тремя знаками легко
    перепрыгивает границу кадра: замер на реальном клипе — `end=1.867` отдаёт 57
    кадров (1.900 с) вместо 56 (1.867 с). Лишний кадр на каждой склейке и есть
    тот дрейф, из-за которого монтаж уползал от озвучки. Полкадра назад — и
    попадаем ровно в тот кадр, который просили.
    """
    return f"{max(0.0, seconds - 0.5 / _REEL_FPS):.3f}"


# Скругление на самой склейке. Дубль и мастер несут одни и те же слова, но
# разный кодек и разный шум, и стык двух волн в середине фразы щёлкает.
# Десять миллисекунд снимают щелчок и не читаются как пауза.
_TAKE_SPLICE_FADE_SECONDS = 0.01


def _take_level_match_db(clip: dict, master_path: str, master_start: float,
                         window: float, head: float) -> float:
    """Gain that puts a take's own audio at the level of the master voiceover.

    The model re-encodes the audio we sent and hands it back 2-3 dB quieter
    (measured on job saas_d6b674c6: takes peak at -9.0 dB against the master's
    -6.7). Cutting between the two is heard as the voice stepping up and down at
    every edit — «выраженные окончания и начала». Both sides carry the same
    words, so one measured gain per take lines them up.
    """
    def mean_volume(path: str, start: float, length: float) -> Optional[float]:
        try:
            proc = subprocess.run(
                ["ffmpeg", "-v", "info", "-ss", f"{start:.3f}", "-i", path,
                 "-t", f"{length:.3f}", "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, errors="replace", timeout=120,
            )
            match = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", proc.stderr or "")
            return float(match.group(1)) if match else None
        except Exception:
            return None

    theirs = mean_volume(clip["path"], head, window)
    ours = mean_volume(master_path, master_start, window)
    if theirs is None or ours is None:
        return 0.0
    # A big correction means the two are not the same words after all — trust
    # the take rather than shout it into place.
    return max(-6.0, min(6.0, ours - theirs))


def _reel_layout(clips: list, master_path: str = "") -> list:
    """Where every clip sits in the edit, and where its words sit in the master.

    One timeline, snapped to the frame grid: shot boundaries are rounded to a
    whole frame once, off the running master time, so a segment is always a
    whole number of frames and nothing accumulates. Reel time and master time
    stay the same time, which is what lets a take's own audio and the master
    take turns without a gap or a repeat at the seam.

    A self-voiced take gives up exactly the picture the model drew around its
    words: the head of silence its driving mp3 carried (`speech_offset`) and
    everything past the last word. Both ends are cut from picture and sound
    together, so the model's own lip sync is untouched — but the sentence runs
    on without the hole that padding used to punch into it.
    """
    layout = []
    master_cursor = 0.0
    frame_cursor = 0
    for index, clip in enumerate(clips):
        actual = _get_media_duration(clip["path"])
        window = max(0.1, float(clip.get("duration") or actual))
        self_voiced = _self_voiced_clip(clip)
        try:
            offset = float(clip.get("speech_offset") or 0.0)
        except (TypeError, ValueError):
            offset = 0.0
        master_start = master_cursor
        master_cursor += window
        reel_start = frame_cursor / _REEL_FPS
        frame_cursor = int(round(master_cursor * _REEL_FPS))
        duration = frame_cursor / _REEL_FPS - reel_start
        own_audio = 0.0
        gain_db = 0.0
        head = 0.0
        if self_voiced:
            own_audio = _get_media_stream_duration(clip["path"], "audio")
            head = max(0.0, min(reel_start - master_start + offset,
                                max(0.0, actual - duration)))
            if master_path:
                gain_db = _take_level_match_db(
                    clip, master_path, master_start, window, offset,
                )
        layout.append({
            "index": index,
            "clip": clip,
            "actual": actual,
            "window": window,
            "self_voiced": self_voiced,
            "own_audio": own_audio,
            "gain_db": gain_db,
            "duration": duration,
            "head": head,
            "master_start": master_start,
            "master_end": master_cursor,
            "reel_start": reel_start,
        })
    return layout


_VOICE_STITCH_FORMAT = "aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo"

# Ровный фон под всей дорожкой. Каждый источник несёт свой шум (astats на job
# saas_d6b674c6: дубли -72.9...-83.4 dB, мастер -78.4), а дописанная тишина и
# паузы самой озвучки — ровный ноль, -240 dB. Обрыв шума в ноль слышно не как
# паузу, а как пропавшую связь: «как будто наушники отключились на доли
# секунды». Фон чуть ниже самого шумного источника убирает и провалы, и
# ступеньки шума на склейках.
_ROOM_TONE_HEADROOM_DB = 3.0
_ROOM_TONE_FLOOR_DB = -80.0
_ROOM_TONE_CEILING_DB = -66.0
# Уровень самого генератора: замер astats на
# `anoisesrc=color=pink:amplitude=1,lowpass=f=6000` даёт RMS -14.5 dB.
_ROOM_TONE_SOURCE_RMS_DB = -14.5


def _noise_floor_db(path: str) -> Optional[float]:
    """Уровень самого тихого места дорожки (astats)."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-v", "info", "-i", path, "-vn",
             "-af", "astats=metadata=1:reset=0", "-f", "null", "-"],
            capture_output=True, text=True, errors="replace", timeout=180,
        )
        floors = re.findall(r"Noise floor dB:\s*(-?\d+(?:\.\d+)?)", proc.stderr or "")
    except Exception:
        return None
    return max(float(value) for value in floors) if floors else None


def _room_tone_db(paths: list) -> float:
    """Уровень фона, который не выдаёт себя, но не даёт дорожке замолчать."""
    floors = [floor for floor in (_noise_floor_db(path) for path in paths if path)
              if floor is not None]
    if not floors:
        return _ROOM_TONE_FLOOR_DB
    return max(_ROOM_TONE_FLOOR_DB,
               min(_ROOM_TONE_CEILING_DB, max(floors) - _ROOM_TONE_HEADROOM_DB))


def _room_tone_filter_parts(seconds: float, room_tone_db: float) -> list:
    """Фон нужной длины и нужного уровня, подмешанный под голос."""
    return [
        f"anoisesrc=color=pink:sample_rate=48000:amplitude=1:seed=1:"
        f"duration={seconds:.3f},lowpass=f=6000,"
        f"volume={room_tone_db - _ROOM_TONE_SOURCE_RMS_DB:.1f}dB,"
        f"{_VOICE_STITCH_FORMAT}[roomtone]",
        "[voicedry][roomtone]amix=inputs=2:duration=first:normalize=0[voicecat]",
    ]


def _stitched_voice_filter_parts(layout: list, master_input: str,
                                 room_tone_db: Optional[float] = None) -> list:
    """Voice track for an edit whose talking takes carry their own audio.

    A self-voiced take contributes its own sound for exactly the stretch of the
    sentence its picture covers. Every other shot takes the same stretch of the
    master voiceover, which is what keeps the sentence running over b-roll —
    the two sources hand the sentence over at the frame boundary, with nothing
    inserted between them. The whole result rides on a room tone bed, so no
    seam ever falls into a silence deeper than the material around it.
    """
    parts = []
    from_master = [segment for segment in layout if not segment["self_voiced"]]
    if len(from_master) == 1:
        parts.append(f"[{master_input}:a]{_VOICE_STITCH_FORMAT}[m{from_master[0]['index']}]")
    elif from_master:
        parts.append(
            f"[{master_input}:a]{_VOICE_STITCH_FORMAT},asplit={len(from_master)}"
            + "".join(f"[m{segment['index']}]" for segment in from_master)
        )
    for segment in layout:
        index, duration = segment["index"], segment["duration"]
        if segment["self_voiced"]:
            fade = _TAKE_SPLICE_FADE_SECONDS
            source = (
                f"[{index}:a]{_VOICE_STITCH_FORMAT},"
                f"volume={segment['gain_db']:.2f}dB,"
                f"atrim=start={segment['head']:.3f}:"
                f"end={segment['head'] + duration:.3f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:st=0:d={fade},"
                f"afade=t=out:st={max(0.0, duration - fade):.3f}:d={fade},"
            )
        else:
            source = (
                f"[m{index}]atrim=start={segment['reel_start']:.3f}:"
                f"end={segment['reel_start'] + duration:.3f},asetpts=PTS-STARTPTS,"
            )
        parts.append(
            f"{source}apad,atrim=end={duration:.3f},"
            f"asetpts=PTS-STARTPTS[a{index}]"
        )
    parts.append(
        "".join(f"[a{segment['index']}]" for segment in layout)
        + f"concat=n={len(layout)}:v=0:a=1"
        + ("[voicedry]" if room_tone_db is not None else "[voicecat]")
    )
    if room_tone_db is not None:
        parts.extend(_room_tone_filter_parts(
            sum(segment["duration"] for segment in layout), room_tone_db,
        ))
    return parts


def composite_storyboard_video(
    clips: list,
    audio_path: str,
    srt_path: str,
    output_path: str,
    music_path: Optional[str] = None,
    # Бед нормализуется к _MUSIC_BED_DBFS, так что это просто подстройка сверху.
    music_volume: float = 1.0,
) -> str:
    """Concatenate storyboard clips and lay the voiceover/subtitles on top.

    A take that came back from the avatar model with its own audio keeps that
    audio under its own picture (see `_self_voiced_clip`); the master voiceover
    fills the shots that were generated mute. Both are cut on the same frame
    grid as the master the captions were timed on, so the sentence runs through
    the seams and the captions still land on it.
    """
    if not clips:
        raise ValueError("Storyboard composite requires at least one clip")

    layout = _reel_layout(clips, audio_path)
    stitched_voice = any(segment["self_voiced"] for segment in layout)
    sub_filter = _subtitle_filter(srt_path)
    inputs = []
    for clip in clips:
        inputs.extend(["-i", clip["path"]])
    inputs.extend(["-i", audio_path])
    if music_path:
        # Loop the bed for the whole edit; amix duration=first ends it with the voice.
        inputs.extend(["-stream_loop", "-1", "-i", music_path])

    norm = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920:(iw-ow)/2:(ih-oh)/2,"
        "fps=30,setsar=1"
    )
    whisper_punch = (
        "crop=iw/1.18:ih/1.18:(iw-ow)/2:(ih-oh)*0.42,"
        "scale=1080:1920,setsar=1"
    )
    filter_parts = []
    # Наезд считается по номеру говорящего кадра, а не по индексу клипа: вставки
    # между ними живут своей жизнью и сбивать чередование не должны.
    talking_index = 0
    concat_parts = []
    for segment in layout:
        index, clip = segment["index"], segment["clip"]
        actual = segment["actual"]
        # A self-voiced take owns its whole length: the slot only says where its
        # words sit in the master, not how much picture the model returned.
        duration = segment["duration"]
        shot = clip.get("shot") or {}
        whisper = _shot_performance(shot) == "whisper"
        try:
            whisper_start = float(shot.get("_whisper_start") or 0.0)
        except (TypeError, ValueError):
            whisper_start = 0.0
        if not (whisper and 0.05 < whisper_start < duration - 0.05):
            whisper_start = 0.0
        clip_norm = norm
        if whisper and not whisper_start:
            # Free pattern interrupt for the hush shot. This changes only the
            # crop: slowing a lip-synced clip would move its mouth off the
            # untouched master voiceover. Кадр приезжает ближе за свою длину, а
            # не оказывается ближе с первого кадра: ступенька крупности на
            # склейке — это то самое «приближение между кадрами», которого быть
            # не должно.
            push = _whisper_push_in(duration)
            if push:
                clip_norm += f",{push}"
        elif not whisper and not _is_broll_shot(shot):
            # Медленный наезд внутри говорящего кадра. Kling оживляет неподвижное
            # фото: мимика есть, камера стоит намертво — и кадр на две-три секунды
            # читается как фотография с говорящим ртом. Наезд эти секунды держит,
            # и он бесплатный: трогает только картинку, PTS и звук не касается,
            # так что липсинк не уезжает.
            push = _talking_push_in(talking_index, duration)
            talking_index += 1
            if push:
                clip_norm += f",{push}"
        # A lip-synced clip can open with the head of silence its driving audio
        # carried (see _mp3_encoder_delay). When the take keeps its own sound
        # that head is harmless — picture and audio carry it together — so only
        # a clip played against the master track gets it skipped.
        head = segment["head"] if segment["self_voiced"] else min(
            max(0.0, float(clip.get("speech_offset") or 0.0)), max(0.0, actual - 0.1),
        )
        head_arg = f"{head:.3f}" if head else "0"
        usable = max(0.1, actual - head)
        deficit = duration - usable
        stretchable = _is_broll_shot(clip.get("shot") or {})
        if segment["self_voiced"]:
            # Never re-synced: picture and sound are cut at the same two points,
            # so the model's own lip sync survives whole. What goes is only the
            # picture around the words — the head of silence the driving mp3
            # carried, and the tail past the last word, which has nothing to
            # sound and would open a hole in the middle of the sentence.
            chain = (f"[{index}:v]trim=start={head_arg}:"
                     f"end={_trim_end(head + duration)},"
                     f"setpts=PTS-STARTPTS,{clip_norm}")
        elif usable > 0 and 0.05 < deficit <= usable * 0.15 and stretchable:
            # Short b-roll: slow the whole clip a touch instead of a visible
            # end-freeze — motion carries through and the seam disappears.
            # Talking shots keep the freeze: stretching them would drag the
            # lips out of sync with the master voiceover.
            ratio = duration / usable
            head_chain = f"trim=start={head_arg},setpts=PTS-STARTPTS," if head else ""
            chain = (
                f"[{index}:v]{head_chain}setpts={ratio:.6f}*PTS,{clip_norm},"
                f"trim=start=0:end={_trim_end(duration)},setpts=PTS-STARTPTS"
            )
        else:
            chain = (
                f"[{index}:v]trim=start={head_arg}:end={_trim_end(head + duration)},"
                f"setpts=PTS-STARTPTS,{clip_norm}"
            )
            # Clip came back shorter than its slot: freeze the last frame
            # instead of silently shifting every later shot off-sync.
            if usable > 0 and deficit > 0.05:
                chain += f",tpad=stop_mode=clone:stop_duration={deficit:.3f}"
        output_label = f"v{index}base" if whisper_start else f"v{index}"
        filter_parts.append(chain + f"[{output_label}]")
        if whisper_start:
            # Short inline whisper: use one paid lip-sync take, then create the
            # edit locally. The cut lands inside the existing pause and only
            # the post-marker picture is punched; audio and PTS stay untouched.
            filter_parts.append(
                f"[{output_label}]split=2[v{index}pre][v{index}whisper]"
            )
            filter_parts.append(
                f"[v{index}pre]trim=start=0:end={_trim_end(whisper_start)},"
                f"setpts=PTS-STARTPTS[v{index}pretrim]"
            )
            filter_parts.append(
                f"[v{index}whisper]trim=start={whisper_start:.3f}:end={_trim_end(duration)},"
                f"setpts=PTS-STARTPTS,{whisper_punch}[v{index}whisperzoom]"
            )
            filter_parts.append(
                f"[v{index}pretrim][v{index}whisperzoom]"
                f"concat=n=2:v=1:a=0[v{index}]"
            )
        concat_parts.append(f"[v{index}]")
    filter_parts.append(
        f"{''.join(concat_parts)}concat=n={len(clips)}:v=1:a=0,"
        "fps=30,settb=expr=1/30,setpts=N/(30*TB),setsar=1[vout]"
    )
    filter_parts.append(f"[vout]{sub_filter}[finalv]")
    master_input = str(len(clips))
    music_input = str(len(clips) + 1) if music_path else None
    music_gain_db = _music_bed_gain_db(music_path) if music_path else 0.0
    voice_parts = _stitched_voice_filter_parts(
        layout, master_input,
        _room_tone_db([audio_path] + [segment["clip"]["path"] for segment in layout
                                      if segment["self_voiced"]]),
    ) if stitched_voice else []
    voice_input = "[voicecat]" if stitched_voice else master_input
    filter_parts.extend(voice_parts)
    filter_parts.extend(_final_audio_filter_parts(
        voice_input,
        music_input,
        music_volume,
        _measure_final_loudness(
            inputs, voice_input, music_input, music_volume,
            music_gain_db=music_gain_db, voice_parts=voice_parts,
        ),
        music_gain_db=music_gain_db,
    ))

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filter_parts),
        "-map", "[finalv]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True)
    return output_path


def _normalize_align_token(token: str) -> str:
    return re.sub(r"[\W_]+", "", (token or "").lower(), flags=re.UNICODE)


# A slice that opens with dead air is what makes a cut read as "the picture is
# ahead of the voice": the avatar model starts its clip from the reference pose
# and the mouth moves while nothing is being said yet. Measured on job
# saas_b13f0229 — 130-590 ms of silence at the head of every shot but the first,
# and the lips visibly settling through it. So a cut lands just before the next
# phrase and the pause stays with the shot that has just finished talking.
_SLICE_LEAD_IN = 0.08
# ASR word starts are approximate, so leave one video frame plus a little
# safety before the first audible consonant. This is short enough to avoid the
# "mouth moving over silence" failure while not cutting into the word.
_AVATAR_SPEECH_PREROLL = 0.04
_AVATAR_ONSET_SEARCH_SECONDS = 1.5


def _phrase_boundary(prev_end: float, next_start: float) -> float:
    """Cut point inside an inter-word pause: right before the next word."""
    return max(prev_end, next_start - _SLICE_LEAD_IN)


def _align_shots_to_voiceover(shots: list, words: list, audio_duration: float) -> tuple:
    """
    Assign each speech shot a contiguous [start, end] slice of one master voiceover.

    Boundaries are placed proportionally to each shot's word count, then snapped
    to an inter-word pause: a pause right after the shot's last scripted word
    wins outright; otherwise the pause score is penalized by distance from the
    proportional target, so a marginally longer pause one phrase away cannot
    steal the boundary. Returns (slices, skipped_shots) where slices tile
    [0, audio_duration] exactly.
    """
    speech_shots = [s for s in shots if (s.get("speech") or "").strip()]
    skipped = [s for s in shots if not (s.get("speech") or "").strip()]
    if not speech_shots:
        return [], skipped

    # Audio tags ([sighs]...) are acting directions, not spoken words —
    # exclude them from proportional weights and boundary word matching.
    spoken_texts = [_strip_audio_tags(s.get("speech") or "") for s in speech_shots]
    weights = [max(1, len(t.split())) for t in spoken_texts]
    total_weight = sum(weights)

    boundaries = [0.0]
    n = len(words or [])
    cum = 0
    for shot_index, w_count in enumerate(weights[:-1]):
        cum += w_count
        if n > 1:
            target_idx = min(max(round(n * cum / total_weight), 1), n - 1)
            lo = max(1, target_idx - 4)
            hi = min(n - 1, target_idx + 4)
            shot_tokens = spoken_texts[shot_index].split()
            last_token = _normalize_align_token(shot_tokens[-1]) if shot_tokens else ""
            text_matches = [
                k for k in range(lo, hi + 1)
                if last_token and _normalize_align_token(words[k - 1].get("word", "")) == last_token
            ]
            if text_matches:
                best = min(text_matches, key=lambda k: abs(k - target_idx))
            else:
                best = max(
                    range(lo, hi + 1),
                    key=lambda k: (
                        float(words[k]["start"]) - float(words[k - 1]["end"])
                        - 0.06 * abs(k - target_idx)
                    ),
                )
            boundary = _phrase_boundary(float(words[best - 1]["end"]), float(words[best]["start"]))
        else:
            boundary = audio_duration * cum / total_weight
        boundaries.append(boundary)
    boundaries.append(audio_duration)

    # Enforce monotonic boundaries with a minimum slice length
    min_len = 0.4
    for i in range(1, len(boundaries)):
        boundaries[i] = min(max(boundaries[i], boundaries[i - 1] + min_len), audio_duration)
    boundaries[-1] = audio_duration

    slices = []
    for i, shot in enumerate(speech_shots):
        start, end = boundaries[i], boundaries[i + 1]
        if end - start < 0.2:
            raise ValueError(
                f"Voiceover too short to fit shot {shot.get('shot_number', i + 1)}: "
                f"slice {start:.2f}-{end:.2f}s"
            )
        slices.append({"shot": shot, "start": round(start, 3), "end": round(end, 3)})
    return slices, skipped


def _retime_talking_slices_to_speech(
    slices: list,
    words: list,
    audio_path: str,
) -> int:
    """Move a talking shot's leading dead air into the previous visual.

    Incremental voice manifests deliberately preserve per-shot audio pieces,
    including the pause between separately recorded takes. Those exact bounds
    are right for the master voiceover cache but wrong for an avatar request:
    Kling starts animating its reference pose during the pause. This pass keeps
    the master untouched and only moves the shared render boundary.
    """
    if len(slices) < 2:
        return 0

    hop = 0.01
    voiced = _speech_onset_mask(audio_path) or []
    moved = 0
    for index in range(1, len(slices)):
        current = slices[index]
        if _is_broll_shot(current.get("shot") or {}):
            continue
        start = float(current["start"])
        end = float(current["end"])
        if end - start <= 0.5:
            continue

        candidates = []
        if voiced:
            first = max(0, int(start / hop))
            limit = min(
                len(voiced),
                int(min(end - 0.4, start + _AVATAR_ONSET_SEARCH_SECONDS) / hop) + 1,
            )
            onset_index = next((i for i in range(first, limit) if voiced[i]), None)
            if onset_index is not None:
                candidates.append(onset_index * hop)

        first_word = next(
            (
                float(word["start"])
                for word in (words or [])
                if float(word.get("end", 0.0)) > start
                and float(word.get("start", end)) < end
            ),
            None,
        )
        if first_word is not None:
            # A word already in progress at the manifest boundary means there is
            # no leading pause to hand away.
            candidates.append(max(start, first_word))
        if not candidates:
            continue

        target = max(start, min(candidates) - _AVATAR_SPEECH_PREROLL)
        if target - start <= 0.02 or end - target < 0.4:
            continue

        previous = slices[index - 1]
        previous["end"] = round(target, 3)
        current["start"] = round(target, 3)
        previous["_speech_onset_shifted"] = True
        current["_speech_onset_shifted"] = True
        moved += 1
    return moved


# libmp3lame writes 576 samples of encoder lookahead plus 529 samples of
# decoder delay ahead of the first real sample and declares them in the LAME
# info tag.
_LAME_ENCODER_DELAY_SAMPLES = 1105


def _mp3_encoder_delay(path: str) -> float:
    """Leading silence an mp3 slice carries that a naive decoder keeps.

    ffmpeg honours the LAME info tag and drops this head, the avatar service
    does not: the speech it lip-syncs against starts one encoder delay into our
    slice, so its clip comes back with the mouth exactly that late. Measured on
    job saas_b13f0229: every talking clip's audio sat +25 ms behind its slice
    (44.1 kHz → 1105/44100 s), and the same +20…+27 ms showed up in the pixels
    when the clip was compared with Kling's own render. Non-mp3 slices (plain
    PCM) have no such head, so this returns 0 and the compensation disappears
    on its own.
    """
    if not path or os.path.splitext(path)[1].lower() != ".mp3":
        return 0.0
    rate = 0.0
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        output = result.stdout.strip().splitlines()
        if output and output[0].strip().isdigit():
            rate = float(output[0].strip())
    except Exception as e:
        print(f"[SaaSShorts] ffprobe sample rate failed for {path}: {e}")
    return _LAME_ENCODER_DELAY_SAMPLES / (rate or 44100.0)


def _slice_voiceover_segment(audio_path: str, start: float, end: float, output_path: str) -> str:
    """Extract [start, end] of the master voiceover with decode-accurate seeking."""
    if _nonempty(output_path):
        return output_path
    cmd = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-c:a", "libmp3lame", "-b:a", "192k",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def _ensure_slice_audio(
    audio_path: str,
    start: float,
    end: float,
    output_path: str,
    clip_path: str,
    log: Callable[[str], None] = print,
    identity: str = "",
    invalidate_video: bool = True,
) -> str:
    """Cut the voiceover slice, invalidating stale audio when it no longer fits.

    Slice files are cached by name, and the name is an ordinal — so deleting a
    shot and rendering again hands slice 3 to what used to be shot 4. Two things
    have to match before a cached slice is trusted: its length, which catches
    moved bounds, and its identity, which catches a file that now belongs to a
    different shot or to different words. Neither alone is enough — a reordered
    script full of similar-length lines passes the duration check happily, and
    the clip lip-synced to that audio would then play against someone else's
    sentence.
    """
    expected = max(0.0, end - start)
    identity_path = f"{output_path}.id.txt"
    if _nonempty(output_path):
        stored = ""
        try:
            with open(identity_path, encoding="utf-8") as f:
                stored = f.read().strip()
        except OSError:
            # Legacy slice with no identity recorded: length is all we have, and
            # re-cutting it would throw away a paid clip on a guess.
            stored = identity
        actual = _get_media_duration(output_path)
        if abs(actual - expected) <= 0.08 and stored == identity:
            return output_path
        reason = (
            f"границы сместились ({actual:.2f}s -> {expected:.2f}s)"
            if abs(actual - expected) > 0.08 else "звук кадра изменился"
        )
        action = (
            "пересечка звука и перегенерация lip-sync клипа"
            if invalidate_video
            else "пересечка служебного аудио; готовое B-roll видео сохраняю"
        )
        log(f"  Слайс {os.path.basename(output_path)}: {reason} — {action}.")
        stale_audio = (
            identity_path,
            output_path,
            f"{output_path}.fal_url.txt",
        )
        stale_video = (
            clip_path,
            clip_path.replace(".mp4", "_base.mp4"),
            clip_path.replace(".mp4", "_base_fal.json"),
            f"{clip_path}.meta.json",
            f"{clip_path}.review.json",
            f"{clip_path}.review.jpg",
            f"{clip_path}.fal_url.txt",
        )
        for stale in stale_audio + (stale_video if invalidate_video else ()):
            try:
                if os.path.exists(stale):
                    os.remove(stale)
            except OSError:
                pass
    _slice_voiceover_segment(audio_path, start, end, output_path)
    if identity:
        with open(identity_path, "w", encoding="utf-8") as f:
            f.write(identity)
    return output_path


_MIN_TALKING_SLICE_SECONDS = 2.0
_MAX_TALKING_SLICE_SECONDS = 8.0


def _stored_slice_cuts(shot: dict, duration: float, cuts_by_shot: Optional[dict]) -> list:
    """Jump cuts this shot was split at last time, if they still fit its audio.

    Reused rather than recomputed because the cuts are found in a transcript of
    the whole reel: re-voicing a neighbour shifts that transcript, the cuts move
    a few milliseconds, and every sub-slice of an untouched shot looks changed —
    which costs an avatar clip per sub-slice, for nothing.
    """
    stored = (cuts_by_shot or {}).get(str(shot.get("shot_number")))
    if not isinstance(stored, list) or not stored:
        return []
    cuts = [float(c) for c in stored]
    if any(b - a < _MIN_TALKING_SLICE_SECONDS for a, b in zip([0.0] + cuts, cuts + [duration])):
        return []
    return cuts


def _billed_avatar_seconds(window: float) -> float:
    """Сколько секунд говорящего клипа попадёт в счёт при таком куске речи.

    Не длина речи: Avatar не отдаёт клип короче своего пола и не отдаёт длину
    произвольную — она округляется вверх до блока в 8 кадров. Проверено на
    прошлом ролике: пять кусков речи 1.72 / 1.64 / 2.58 / 1.66 / 2.26 с по этой
    формуле дают 11.466 с, и ровно столько лежит на диске.
    """
    block = _KLING_AVATAR_BLOCK_FRAMES / _KLING_AVATAR_FPS
    return max(_KLING_AVATAR_MIN_CLIP_SECONDS,
               math.ceil(max(0.0, float(window)) / block) * block)


def _billed_broll_seconds(window: float) -> float:
    """Сколько секунд перебивки попадёт в счёт при таком окне в монтаже.

    Ровно то, что уедет в запрос: `_broll_slice_shot` округляет окно вверх до
    секунды, а `_shot_duration` поднимает результат до пола Kling. Считать смету
    по самому окну — значит обещать полсекунды там, где будут оплачены три.
    """
    return float(_shot_duration({"start": 0, "end": math.ceil(max(1.0, window))}))


def _billed_clip_seconds(clip: dict) -> float:
    """Сколько секунд снятого клипа попадёт в счёт.

    Не длина окна: сборка обрежет клип до окна, но модель уже сняла и посчитала
    своё — она никогда не отдаёт меньше своего пола и округляет длину вверх.
    Поэтому меряем файл; окно остаётся запасным ответом, если файла нет.
    """
    path = clip.get("path") or ""
    # Мерить можно только то, что есть: ffprobe на пустом пути читает не тот
    # поток и возвращает правдоподобное число, которое молча уедет в счёт.
    if path and os.path.exists(path):
        actual = _get_media_duration(path)
        if actual and actual > 0:
            return actual
    window = float(clip.get("duration") or 0.0)
    if _is_broll_shot(clip.get("shot") or {}):
        return _billed_broll_seconds(window)
    return _billed_avatar_seconds(window)


def _slice_silence_at_edges(sl: dict, words: list) -> tuple:
    """Сколько немого времени у куска в начале и в конце.

    Речь здесь единственная неприкосновенная величина: слова кадра сняты вместе
    с его губами. Тишина по краям — нет, её можно отдать соседу.
    """
    inside = [
        w for w in words
        if float(w.get("start", 0.0)) < sl["end"] and float(w.get("end", 0.0)) > sl["start"]
    ]
    if not inside:
        return sl["end"] - sl["start"], sl["end"] - sl["start"]
    first = min(float(w.get("start", 0.0)) for w in inside)
    last = max(float(w.get("end", 0.0)) for w in inside)
    # Разгон оставляем говорящему: губы должны тронуться чуть раньше слова, а не
    # ровно по нему, иначе первый слог выходит уже открытым ртом.
    head = first - _AVATAR_SPEECH_PREROLL - sl["start"]
    return max(0.0, head), max(0.0, sl["end"] - last)


def _clip_floor_of(sl: dict) -> float:
    """Пол клипа, которым снимут этот кусок, — короче модель не отдаст и не сочтёт."""
    return (float(_KLING_MIN_CLIP_SECONDS) if _is_broll_shot(sl["shot"])
            else _KLING_AVATAR_MIN_CLIP_SECONDS)


def _fill_slices_to_clip_floor(slices: list, words: list) -> tuple:
    """Отдать кадру всё время, за которое всё равно заплачено.

    Клипов короче своего пола ни одна из моделей не отдаёт: под перебивку с
    полусекундой речи Kling V3 снимет три секунды и три возьмёт в счёт, под
    полуторасекундную реплику Avatar отдаст свои 2.14. Сборка обрежет клип до
    окна — зритель видит вспышку, касса видит полный клип.

    Поэтому короткий кадр добирает недостающее у соседей: его окно растёт,
    соседнее на столько же сжимается, общая длина дорожки не меняется. Липсинк
    это не задевает — говорящий клип снимается по своему куску озвучки, а кусок
    режется уже по новым границам, так что губы и звук по-прежнему одно целое.

    Но берётся только тишина по краям соседа, не его слова. Иначе кадр съедал бы
    первый слог следующего — ровно ту паузу перед речью, ради которой существует
    `_retime_talking_slices_to_speech`, — и лечение вышло бы хуже болезни. Когда
    тишины не хватает, кадр остаётся коротким: склеивать соседние кадры или
    менять их тип значило бы молча переписать раскадровку, а это решение автора —
    ему об этом и скажут.

    Возвращает (сколько добрали, сколько так и осталось короткими).
    """
    floor_of = _clip_floor_of

    # Меньше этого не двигаем: пара кадров на экране ничего не меняет, а границы
    # кусков озвучки от такого шевеления поедут.
    epsilon = 0.05
    filled = short = 0
    for index, sl in enumerate(slices):
        need = floor_of(sl) - (sl["end"] - sl["start"])
        if need <= epsilon:
            continue
        # Сначала вперёд: тишина перед следующей мыслью принадлежит ей меньше,
        # чем хвост уже сказанной — предыдущей.
        for neighbour_index, forward in ((index + 1, True), (index - 1, False)):
            if need <= epsilon or not 0 <= neighbour_index < len(slices):
                continue
            neighbour = slices[neighbour_index]
            head, tail = _slice_silence_at_edges(neighbour, words)
            room = (neighbour["end"] - neighbour["start"]) - floor_of(neighbour)
            take = min(need, max(0.0, room), head if forward else tail)
            if take <= epsilon:
                continue
            if forward:
                sl["end"] += take
                neighbour["start"] += take
            else:
                sl["start"] -= take
                neighbour["end"] -= take
            need -= take
        if need > epsilon:
            short += 1
        else:
            filled += 1
    return filled, short


def _split_performance_slices(slices: list, words: list) -> list:
    """Give an inline ``[whispers]`` direction its own visual performance.

    TTS already understands the tag. This maps the same point onto the video
    timeline, so the whispered phrase starts on a deliberate edit instead of
    continuing in the ordinary camera setup. Each side stays at least as long
    as Kling's reliable clip floor; when the source shot is too short to split,
    the whole shot uses the whisper performance rather than creating flashes.
    """
    result = []
    for sl in slices:
        shot = sl["shot"]
        speech = shot.get("speech") or ""
        match = _WHISPER_TAG_RE.search(speech)
        if _is_broll_shot(shot) or not match:
            result.append(sl)
            continue

        before = _strip_audio_tags(speech[:match.start()])
        after = _strip_audio_tags(speech[match.end():])
        if not after:
            result.append(sl)
            continue
        if not before:
            whispered = dict(shot)
            whispered["_performance"] = "whisper"
            whispered["speech"] = after
            result.append({**sl, "shot": whispered})
            continue

        start, end = float(sl["start"]), float(sl["end"])
        duration = end - start
        before_count = len(before.split())
        local_words = [
            word for word in (words or [])
            if start <= (float(word["start"]) + float(word["end"])) / 2 <= end
        ]
        if 0 < before_count < len(local_words):
            target = _phrase_boundary(
                float(local_words[before_count - 1]["end"]),
                float(local_words[before_count]["start"]),
            )
        else:
            spoken_count = max(1, before_count + len(after.split()))
            target = start + duration * before_count / spoken_count

        if duration < 2 * _MIN_TALKING_SLICE_SECONDS:
            whispered = dict(shot)
            whispered["_performance"] = "whisper"
            # One short Kling take is more reliable (and cheaper) than two tiny
            # paid takes. Keep the natural pause in the master voiceover and
            # tell the local compositor where to punch in inside this clip.
            if duration > 0.2:
                whispered["_whisper_start"] = round(min(
                    max(target - start, 0.1),
                    duration - 0.1,
                ), 3)
            result.append({**sl, "shot": whispered})
            continue

        cut = round(min(
            max(target, start + _MIN_TALKING_SLICE_SECONDS),
            end - _MIN_TALKING_SLICE_SECONDS,
        ), 3)

        normal = dict(shot)
        normal["_performance"] = "normal"
        normal["speech"] = before
        whispered = dict(shot)
        whispered["_performance"] = "whisper"
        whispered["speech"] = after
        result.extend([
            {"shot": normal, "start": start, "end": cut},
            {"shot": whispered, "start": cut, "end": end},
        ])
    return result


def _split_long_slices(
    slices: list,
    words: list,
    max_len: Optional[float] = None,
    cuts_by_shot: Optional[dict] = None,
) -> list:
    """Split only talking takes that exceed Kling Avatar's practical limit.

    An authored shot at or below the limit stays one paid generation. Splitting
    a short take creates another minimum-billed Kling request and a visible
    pose/framing reset at the seam. Pass max_len to use a stricter explicit
    limit. Stored cuts are replayed only while a take still exceeds that limit.
    B-roll slices pass through because the master voiceover plays over them.
    """
    result = []
    for sl in slices:
        duration = sl["end"] - sl["start"]
        limit = float(max_len) if max_len is not None else _MAX_TALKING_SLICE_SECONDS
        if _is_broll_shot(sl["shot"]) or duration <= limit + 0.01:
            result.append(sl)
            continue
        replay = _stored_slice_cuts(sl["shot"], duration, cuts_by_shot)
        if replay:
            bounds = [sl["start"]] + [round(sl["start"] + c, 3) for c in replay] + [sl["end"]]
            for i in range(len(bounds) - 1):
                result.append({"shot": dict(sl["shot"]), "start": bounds[i], "end": bounds[i + 1]})
            continue
        parts = int(math.ceil(duration / limit))
        # Never slice below the floor: Kling wants real audio in every clip and
        # sub-second flashes read as a glitch, not as an edit.
        parts = max(1, min(parts, int(duration // _MIN_TALKING_SLICE_SECONDS)))
        if parts < 2:
            result.append(sl)
            continue
        floor = _MIN_TALKING_SLICE_SECONDS
        gaps = []
        for prev, nxt in zip(words or [], (words or [])[1:]):
            boundary = _phrase_boundary(float(prev["end"]), float(nxt["start"]))
            if sl["start"] + floor < boundary < sl["end"] - floor:
                gaps.append((boundary, max(0.0, float(nxt["start"]) - float(prev["end"]))))
        bounds = [sl["start"]]
        for i in range(1, parts):
            # Keep the floor on both sides: reserve room for every remaining part,
            # otherwise the last cut gets dragged back and leaves a flash frame.
            low = bounds[-1] + floor
            high = sl["end"] - floor * (parts - i)
            if high < low:
                break
            target = min(max(sl["start"] + duration * i / parts, low), high)
            usable = [g for g in gaps if low <= g[0] <= high]
            if usable:
                cut = max(usable, key=lambda g: g[1] - 0.15 * abs(g[0] - target))[0]
            else:
                cut = target
            bounds.append(round(cut, 3))
        bounds.append(sl["end"])
        for i in range(len(bounds) - 1):
            result.append({"shot": dict(sl["shot"]), "start": bounds[i], "end": bounds[i + 1]})
    return result


def _job_output_root(output_dir: str) -> str:
    """The directory jobs live in, so a `/videos/<job>/...` url can be resolved.

    Frames approved in a preview job sit in that job's folder, and the render
    runs in its own — without the root there is no way back to a picture the
    user already paid for.
    """
    return os.path.dirname(output_dir.rstrip("/\\")) or "output"


def _storyboard_avatar_reference_image(shot: dict, output_dir: str, index: int) -> str:
    """Return a local path to the shot's reference frame, downloading remote URLs."""
    local_ref = (shot.get("image_path") or shot.get("local_path") or "").strip()
    if not local_ref:
        local_url = (shot.get("local_url") or "").strip()
        if local_url.startswith("/videos/"):
            local_ref = os.path.join("output", local_url.replace("/videos/", "", 1))
    if local_ref and os.path.exists(local_ref):
        return local_ref

    for key in ("image_url", "start_image_url"):
        url = (shot.get(key) or "").strip()
        if url.startswith(("http://", "https://")):
            ext = os.path.splitext(url.split("?")[0])[1] or ".png"
            ref_path = os.path.join(output_dir, f"avatar_ref_{index:02d}{ext}")
            if _nonempty(ref_path):
                return ref_path
            with httpx.Client(timeout=120.0) as client:
                resp = client.get(url)
                resp.raise_for_status()
                with open(ref_path, "wb") as f:
                    f.write(resp.content)
            return ref_path
    return ""


def _avatar_clip_cache_valid(
    clip_path: str,
    reference_path: str,
    motion_prompt: str = _AVATAR_MOTION_PROMPT,
) -> bool:
    """True while a cached Kling Avatar clip still matches its reference frame.

    An avatar clip is defined by two things: the frame it was staged from and
    the audio slice it was lip-synced to. The audio side is handled by
    `_ensure_slice_audio`, which drops the clip when the slice bounds move, so
    the check here is the picture: the shot's own scene edits land in the
    reference frame (`_avatar_reference_image`), and a new frame means the clip
    has to be shot again.

    Clips shot with any other prompt came from the old recipe that made Kling
    paint garbled captions into the frame — those are never reusable. Clips
    without meta (legacy jobs) stay valid: an avatar clip is the most expensive
    artifact in the pipeline, so an unknown history is not enough to spend
    money again.
    """
    if not _nonempty(clip_path):
        return False
    meta_path = clip_path.replace(".mp4", "_base_fal.json")
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError):
        return True
    stored_prompt = ((meta.get("payload") or {}).get("prompt") or "").strip()
    if stored_prompt and stored_prompt != motion_prompt:
        return False
    stored = meta.get("reference_fingerprint")
    if not isinstance(stored, str) or not stored:
        return True
    return stored == _file_fingerprint(reference_path)


def _is_broll_shot(shot: dict) -> bool:
    return (shot.get("visual_type") or "").strip().lower() in ("broll", "b-roll", "b_roll")


def _shot_wants_actor(shot: dict) -> bool:
    """True when a b-roll insert shows OUR presenter, not a stranger.

    Half the inserts are objects and hands with nobody in them; the other half
    is the same character seen from behind or cropped ("вид сзади: женский
    силуэт закрывает холодильник"). Only the storyboard knows which, so it says
    so per shot — guessing from the Russian scene text at render time is how a
    different woman ends up in the middle of the reel. Missing means false: we
    never claim a continuity we are not staging.
    """
    value = shot.get("actor_in_frame")
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "да")
    return bool(value)


def _broll_slice_shot(shot: dict, slice_duration: float) -> dict:
    """Prepare a shot copy for a Kling V3 clip that plays under the master voiceover.

    The clip must cover its voiceover slice, so the duration is rounded UP —
    the composite trims the surplus, while a short clip would end in a freeze.
    Lips must stay shut: there is no lipsync pass on this footage.
    """
    v3_shot = dict(shot)
    v3_shot["start"] = 0
    v3_shot["end"] = int(math.ceil(max(1.0, slice_duration)))
    base = (v3_shot.get("generation_prompt") or "").strip() or _build_storyboard_generation_prompt(v3_shot)
    v3_shot["generation_prompt"] = (
        f"{base}, anyone in frame keeps their mouth closed and still, "
        "plain surfaces with nothing written on them, "
        "any device screens turned away from camera or out of focus, "
        "voiceover plays over the scene"
    )
    return v3_shot


# Image-conditioned Flux edit: keeps the reference person's identity while
# staging a new scene. Swap here if a better identity model becomes available.
AVATAR_REFERENCE_MODEL = "fal-ai/flux-pro/kontext"

# Каталог редакторов «поставь этого человека в эту сцену» — витрина для
# пользователя, а не цепочка фолбэков.
#
# Kontext на фото ведущего может отдать чёрный кадр: у Flux так выглядит
# сработавшая модерация входного изображения — картинка валидная, просто пустая
# (см. `_looks_blank`), денег это не отменяет. Раньше код в таком случае молча
# брал следующего кандидата, и человек узнавал о подмене только по счёту. Теперь
# выбор его: пайплайн зовёт ровно ту модель, которую попросили, а отказ отдаёт
# наверх вместе с дословным ответом fal (см. `_FAL_MODERATION_FIELDS`).
#
# Порядок — по убыванию качества переноса личности и по убыванию строгости
# фильтров, и это одна и та же ось: у закрытых API (BFL, Google, ByteDance)
# модерация стоит и на входе, и на выходе — оттуда и берутся чёрные квадраты.
# Замыкает список Qwen-Image-Edit: открытые веса, которые fal крутит на своих
# GPU, то есть чужого модератора над ними нет вообще. Он рисует хуже соседей,
# но именно он должен нарисовать хоть что-то, когда остальные отказали.
#
# `field` — имя поля под картинку: у разных эндпоинтов оно своё, поэтому лежит в
# таблице, а не в коде. Неизвестный или переименованный эндпоинт ответит 404/422
# — это бесплатно, платим только за реальную генерацию.
AVATAR_EDIT_MODELS = (
    {
        "id": AVATAR_REFERENCE_MODEL,
        "title": "FLUX Kontext",
        "vendor": "Black Forest Labs",
        "note": "Лучший перенос лица и самые строгие фильтры.",
        "field": "image_url",
        "args": {"aspect_ratio": "9:16", "safety_tolerance": "5"},
    },
    {
        "id": "fal-ai/nano-banana/edit",
        "title": "Nano Banana",
        "vendor": "Google",
        "note": "Держит личность почти как Kontext, модерация — гугловская.",
        "field": "image_urls",
        "args": {},
    },
    {
        "id": "fal-ai/bytedance/seedream/v4/edit",
        "title": "Seedream 4",
        "vendor": "ByteDance",
        "note": "Третий независимый стек модерации при похожем качестве.",
        "field": "image_urls",
        "args": {},
    },
    {
        "id": "fal-ai/qwen-image-edit",
        "title": "Qwen Image Edit",
        "vendor": "Alibaba (открытые веса)",
        "note": "Рисует слабее остальных, зато чужого модератора над ним нет.",
        "field": "image_url",
        "args": {},
    },
)

DEFAULT_AVATAR_EDIT_MODEL = AVATAR_EDIT_MODELS[0]["id"]

# Поля ответа, по которым видно, что кадр зарубила модерация, а не сбой сети.
_FAL_MODERATION_FIELDS = ("has_nsfw_concepts", "nsfw_content_detected", "error", "message", "detail")
_FAL_BOOLEAN_MODERATION_FIELDS = ("has_nsfw_concepts", "nsfw_content_detected")
_MODERATION_WORDS = ("moderation", "nsfw", "safety policy", "content policy")


def _moderation_value_is_true(value) -> bool:
    if isinstance(value, (list, tuple, set)):
        return any(_moderation_value_is_true(item) for item in value)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return False


def _explicit_moderation_flags(result: dict) -> dict:
    """Return only evidence that explicitly confirms provider moderation."""
    flags = {
        key: result[key] for key in _FAL_BOOLEAN_MODERATION_FIELDS
        if key in result and _moderation_value_is_true(result[key])
    }
    for key in ("error", "message", "detail"):
        value = result.get(key)
        if isinstance(value, str) and any(word in value.lower() for word in _MODERATION_WORDS):
            flags[key] = value
    return flags


def _avatar_edit_model(model_id: str = "") -> dict:
    """Каталожная запись выбранного редактора; по умолчанию — первый.

    Незнакомый id значит, что фронт отстал от каталога, — берём дефолт, а не
    падаем: неизвестная модель уехала бы в fal и вернула 422.
    """
    for entry in AVATAR_EDIT_MODELS:
        if entry["id"] == (model_id or "").strip():
            return entry
    return AVATAR_EDIT_MODELS[0]


def _blank_model_memo(photo_path: str) -> str:
    return f"{photo_path}.blank_models.json"


_BLANK_MEMO_LOCK = threading.Lock()
# Столько же, сколько у съёмки клипов: fal держит очередь на аккаунт, и гнать
# шире значит только дольше стоять в ней.
_FRAME_WORKERS = 3


def _photo_fingerprint(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prompt_fingerprint(prompt: str) -> str:
    return hashlib.sha256((prompt or "").encode("utf-8")).hexdigest()


def _read_moderation_memo(photo_path: str) -> dict:
    """Read only verified, versioned moderation records.

    Legacy model-only arrays did not preserve fal's verdict or the prompt that
    caused it. They therefore cannot safely block a future paid request.
    """
    try:
        with open(_blank_model_memo(photo_path), encoding="utf-8") as source:
            data = json.load(source)
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(data, dict) or data.get("version") != 2:
        return {}
    if not isinstance(data.get("records"), list):
        return {}
    return data


def _models_that_blanked(photo_path: str, prompt: str) -> set:
    """Models with confirmed moderation for this exact photo and prompt."""
    data = _read_moderation_memo(photo_path)
    if data.get("version") != 2:
        return set()
    try:
        photo_sha = _photo_fingerprint(photo_path)
    except OSError:
        return set()
    prompt_sha = _prompt_fingerprint(prompt)
    return {
        record["model"] for record in data.get("records", [])
        if isinstance(record, dict)
        if record.get("photo_sha256") == photo_sha
        and record.get("prompt_sha256") == prompt_sha
        and record.get("model")
    }


def _remember_confirmed_moderation(
    photo_path: str,
    model: str,
    prompt: str,
    flags: dict,
) -> None:
    """Persist one vendor-confirmed verdict without exposing partial JSON."""
    memo_path = _blank_model_memo(photo_path)
    with _BLANK_MEMO_LOCK:
        try:
            data = _read_moderation_memo(photo_path)
            records = list(data.get("records", []))
            photo_sha = _photo_fingerprint(photo_path)
            prompt_sha = _prompt_fingerprint(prompt)
            records = [record for record in records if not (
                isinstance(record, dict)
                and record.get("model") == model
                and record.get("photo_sha256") == photo_sha
                and record.get("prompt_sha256") == prompt_sha
            )]
            records.append({
                "model": model,
                "photo_sha256": photo_sha,
                "prompt_sha256": prompt_sha,
                "flags": flags,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            temporary = f"{memo_path}.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                with open(temporary, "w", encoding="utf-8") as target:
                    json.dump({"version": 2, "records": records}, target, ensure_ascii=False)
                os.replace(temporary, memo_path)
            finally:
                if os.path.exists(temporary):
                    os.remove(temporary)
        except OSError:
            # Memo persistence is an optimization and must not fail generation.
            pass


def _drop_frame_files(output_path: str) -> None:
    for stale in (output_path, f"{output_path}.fal_url.txt"):
        try:
            if os.path.exists(stale):
                os.remove(stale)
        except OSError:
            pass


def _report_blocked_editor(
    billing: Optional[dict],
    entry: dict,
    reason: str,
    flags: dict,
    charged: bool,
    photo_path: str,
    prompt: str,
) -> None:
    """Записать отказ редактора так, чтобы интерфейс мог о нём рассказать.

    Лог читают не все, а деньги списываются со всех. Отчёт несёт дословный ответ
    fal (`has_nsfw_concepts` и соседи) и список моделей, которые на этом фото ещё
    не пробовали, — из него интерфейс собирает предложение сменить модель.
    """
    if billing is None:
        return
    tried = _models_that_blanked(photo_path, prompt) if photo_path else set()
    billing.setdefault("blocked", []).append({
        "model": entry["id"],
        "title": entry["title"],
        "vendor": entry["vendor"],
        # "moderation" — модель зарубила кадр, "known" — уже рубила его раньше,
        # "unavailable" — эндпоинт ответил ошибкой (404/422), это не про
        # модерацию, "unreachable" — запрос до fal вообще не дошёл, и тогда
        # смена модели не поможет: чинить надо сеть.
        "reason": reason,
        "flags": flags,
        "charged": charged,
        "alternatives": [
            {
                "id": m["id"],
                "title": m["title"],
                "vendor": m["vendor"],
                "note": m["note"],
                "blocked": m["id"] in tried,
            }
            for m in AVATAR_EDIT_MODELS
            if m["id"] != entry["id"]
        ],
    })


def _flux_reference_frame(
    prompt: str,
    fal_key: str,
    output_path: str,
    log: Callable[[str], None] = print,
    actor_photo_path: str = "",
    label: str = "Reference frame",
    on_failure: str = "",
    billing: Optional[dict] = None,
    edit_model: str = "",
    extra_photo_paths: Optional[List[str]] = None,
) -> str:
    """Draw one Flux still for a shot, cached by prompt. "" on any failure.

    Two models behind one door: given an actor photo this is an image-conditioned
    edit that keeps that person's identity, without one it is plain
    text-to-image. The cache keys on the prompt, so an edited shot is redrawn and
    an untouched one never pays twice.

    `edit_model` — какой редактор из `AVATAR_EDIT_MODELS` позвать (пусто = дефолт).
    Отказ никогда не переходит на другую модель сам: он попадает в `billing`
    отчётом, а выбор остаётся за пользователем.

    `actor_photo_path` — главный референс: он уходит первым и по нему же ведётся
    память об отказах модерации. `extra_photo_paths` — остальные, и доходят они
    не до всех: поле под картинку у половины каталога одиночное (см. `field` в
    `AVATAR_EDIT_MODELS`). Обещать модели картинку там, где мы её не отправляем,
    — значит просить выдумать её содержимое, поэтому решение «идут лишние
    референсы или нет» принимает вызывающий, а не текст промпта.
    """
    prompt_sidecar = f"{output_path}.prompt.txt"
    if _nonempty(output_path):
        try:
            with open(prompt_sidecar, encoding="utf-8") as f:
                cached_prompt = f.read()
        except OSError:
            cached_prompt = None
        # Референс валиден, пока совпадает промпт кадра (юзер мог его отредактировать).
        if cached_prompt is None or cached_prompt == prompt:
            return output_path
        _drop_frame_files(output_path)
    # Один клик — максимум один платный запрос, и ровно к той модели, которую
    # выбрал пользователь. Молчаливого перехода к следующей нет: чёрный кадр
    # стоит столько же, сколько нормальный, и подменять модель за спиной значит
    # тратить чужие деньги на догадку. Отказ уходит наверх, решение — за юзером.
    entry = _avatar_edit_model(edit_model)
    if actor_photo_path:
        blanked = _models_that_blanked(actor_photo_path, prompt)
        if entry["id"] in blanked:
            # Бесплатный отказ: модерация детерминированна, тот же редактор с тем
            # же фото купит тот же чёрный квадрат.
            log(f"  ⚠️ {label}: {entry['title']} на это фото уже вернул пустой кадр. "
                "Повторный запрос не делаю — он платный и вернёт то же самое. "
                "Нужна другая модель или другое фото ведущего.")
            _report_blocked_editor(
                billing, entry, "known", {}, False, actor_photo_path, prompt,
            )
            return ""
        model, image_field, extra = entry["id"], entry["field"], entry["args"]
        photos = [actor_photo_path]
        if image_field == "image_urls":
            photos.extend(p for p in (extra_photo_paths or []) if p)
        image_urls = [_fal_upload_file(_flux_condition_photo(p), fal_key) for p in photos]
    else:
        model, image_field, extra = "fal-ai/flux-2-pro", "", {"image_size": "portrait_16_9", "safety_tolerance": 5}
        image_urls = []

    args = {"prompt": prompt, **extra}
    if image_field == "image_urls":
        args["image_urls"] = image_urls
    elif image_field:
        args[image_field] = image_urls[0]

    # Граница, за которой картинка уже нарисована и уже оплачена. Всё, что
    # ломается после неё, цену не отменяет.
    generated = False
    try:
        if billing is not None:
            billing["calls"] = billing.get("calls", 0) + 1
        result = _fal_run(model, args, fal_key, timeout=600)
        generated = True
        images = result.get("images") or result.get("output", [])
        if not images:
            raise RuntimeError(f"no images in Flux result: {list(result.keys())}")
        img_url = images[0]["url"] if isinstance(images[0], dict) else images[0]
        for attempt in range(3):
            try:
                with httpx.Client(timeout=120.0) as client:
                    resp = client.get(img_url)
                    resp.raise_for_status()
                    with open(output_path, "wb") as f:
                        f.write(resp.content)
                break
            except httpx.RequestError as download_error:
                if attempt == 2:
                    raise
                wait = 3 * (attempt + 1)
                log(
                    f"  ⚠️ {label}: готовый кадр не скачался "
                    f"({download_error}); повторяю через {wait} с."
                )
                time.sleep(wait)
        if _looks_blank(output_path):
            # Ответ модели — единственное место, где видно «зарубила модерация»
            # вместо «что-то пошло не так». Без него причина остаётся догадкой.
            flags = _explicit_moderation_flags(result)
            reason = "moderation" if flags else "blank"
            log(f"  ⚠️ {label}: {model} вернул пустой кадр"
                + (f" — ответ модели: {flags}" if flags else " (модель не назвала причину)"))
            _drop_frame_files(output_path)
            if actor_photo_path:
                if flags:
                    _remember_confirmed_moderation(
                        actor_photo_path, model, prompt, flags,
                    )
                _report_blocked_editor(
                    billing, entry, reason, flags, True, actor_photo_path, prompt,
                )
                left = [m["title"] for m in AVATAR_EDIT_MODELS
                        if m["id"] not in _models_that_blanked(actor_photo_path, prompt)]
                log(f"  {label}: не пробовали на этом фото: {', '.join(left)} — выбор за тобой."
                    if left else f"  {label}: редакторы кончились — нужно другое фото ведущего.")
            return ""
        if model != DEFAULT_AVATAR_EDIT_MODEL and actor_photo_path:
            log(f"  ✅ {label}: кадр нарисовала {model}")
        with open(prompt_sidecar, "w", encoding="utf-8") as f:
            f.write(prompt)
        return output_path
    except Exception as e:
        # Три разных случая, и путать их дорого.
        #
        # Запрос не дошёл до fal — модель фотографию не видела, платить не за
        # что, и повторять надо ту же самую модель. Именно этот случай раньше
        # записывался в вердикты модерации: 2026-08-05 резолвер в контейнере
        # перестал разрешать queue.fal.run, и два редактора из четырёх оказались
        # вычеркнуты навсегда, ни разу не увидев фото (см. `FalUnreachable`).
        #
        # Эндпоинт ответил ошибкой — модель переехала или её сняли; запоминаем,
        # чтобы не платить за тот же 404 второй раз.
        #
        # Сломалось после генерации (не скачалась готовая картинка) — fal своё
        # уже посчитал. Вычесть вызов здесь значит соврать в отчёте о тратах.
        unreachable = isinstance(e, FalUnreachable)
        download_failed = generated and isinstance(e, httpx.RequestError)
        log(f"  ⚠️ {label}: {model} не отработал ({e}){on_failure}")
        if billing is not None and not generated:
            billing["calls"] = max(0, billing.get("calls", 1) - 1)
        if actor_photo_path:
            reason = "unreachable" if unreachable else "download" if download_failed else "unavailable"
            _report_blocked_editor(billing, entry, reason,
                                   {"error": str(e)}, generated, actor_photo_path, prompt)
        return ""


# Длинная сторона фото-условия, которое уходит в Flux Kontext. Фото ведущего
# приходит как есть из галереи или загрузки — попадаются 4802×3584 на 30 МБ.
# Kontext на таких молча возвращает чёрный кадр (см. `_looks_blank`), а дальше
# пайплайн оживляет исходное фото. Ужимаем — на качество кадра это не влияет,
# модель всё равно рисует свой.
_FLUX_CONDITION_MAX_PX = 2048


def _flux_condition_photo(path: str) -> str:
    """Уменьшенная копия фото для Flux; сам путь — если ужимать нечего."""
    try:
        from PIL import Image

        with Image.open(path) as im:
            if max(im.size) <= _FLUX_CONDITION_MAX_PX:
                return path
            small = f"{os.path.splitext(path)[0]}_cond.png"
            if _nonempty(small):
                return small
            copy = im.convert("RGB")
            copy.thumbnail((_FLUX_CONDITION_MAX_PX, _FLUX_CONDITION_MAX_PX))
            copy.save(small)
            return small
    except Exception:
        # Не смогли прочитать — отдаём оригинал: пусть решает fal, а не мы.
        return path


def _broll_reference_image(
    shot: dict,
    fal_key: str,
    output_path: str,
    log: Callable[[str], None] = print,
    actor_photo_path: str = "",
    billing: Optional[dict] = None,
    edit_model: str = "",
) -> str:
    """Flux still of the b-roll scene, so Kling animates it via image-to-video.

    Text-only Kling controls composition poorly (it invented strangers before
    the no-people rules); a cheap Flux frame pins the exact composition and a
    consistent aesthetic. Returns "" on any failure — the caller falls back to
    plain text-to-video, a worse shot beats a failed job.

    When the storyboard marks the insert as showing our own presenter
    (`actor_in_frame`), the frame is staged from the actor photo instead: same
    hair, build and outfit, face turned away. Otherwise a stranger walks into
    the middle of the reel, and the viewer reads that as a different story —
    they don't know the shot is "b-roll".
    """
    base_prompt = (shot.get("generation_prompt") or shot.get("scene") or "").strip()
    if _shot_wants_actor(shot) and actor_photo_path and os.path.exists(actor_photo_path):
        # Композицию задаёт описание кадра, и только оно. Раньше здесь стояло
        # «этого человека видно со спины, через плечо», и на просьбе «крупно руки»
        # модель слушалась хвоста, а не описания: получался средний план со спины
        # вместо кистей. Лицо за кадром — это требование (иначе вставка читается
        # как новый герой), а не указание, откуда снимать.
        actor_prompt = (
            "The reference image is the only source of identity and appearance: keep the "
            "exact same person, same hairstyle, build and clothing. Single photographic "
            "frame, vertical 9:16, one person only, natural light, shallow depth of field, "
            "smartphone realism, plain unbranded surfaces. This person's face stays out of "
            "frame — a back view, an over-the-shoulder angle or a tight crop on the hands "
            "and forearms are all fine, whichever the description asks for. "
            f"Recompose the shot as described{': ' + base_prompt if base_prompt else ''}."
        )
        made = _flux_reference_frame(
            actor_prompt, fal_key, output_path, log=log,
            actor_photo_path=actor_photo_path,
            label="B-roll frame with our presenter",
            billing=billing,
            edit_model=edit_model,
            on_failure="; drawing the insert without them instead",
        )
        if made:
            return made
    prompt = (
        f"{base_prompt}. Single photographic frame, vertical 9:16, first frame of a short "
        "product b-roll: keep the requested subject and action, natural light, shallow depth "
        "of field, smartphone realism. no people unless the requested action needs a faceless "
        "back view, cropped body/hands, silhouette or non-identifiable profile; faces stay out "
        "of frame, plain unbranded surfaces"
    )
    return _flux_reference_frame(
        prompt, fal_key, output_path, log=log,
        label="B-roll reference frame",
        on_failure="; falling back to text-to-video",
        billing=billing,
    )


# Лицо на плите — это не портрет, а стартовая поза для Kling: он держит найденное
# на кадре выражение всю реплику и возвращается к нему после каждого слога.
# Широкая улыбка с зубами, растянутая на две секунды говорения, читается как
# оскал — поэтому улыбка запрещена прямо («mouth closed, no smile»), а не
# «спокойное лицо» намёком: мягкое «calm expression, lips gently closed» уже
# проигрывало улыбающемуся исходнику.
#
# Просили об этом целым абзацем — «override the expression of the reference
# photo», «no teeth are visible anywhere», «any warmth lives in the eyes alone».
# Абзац съеден вместе с личностью, светом и фотореализмом: четыре слова в хвосте
# делают ту же работу, а всё остальное только глушило строку камеры.

# Комната приезжает картинкой, а не словами. На фото ведущего место уже снято —
# со своим светом, мебелью и временем суток, — а текст сета пишется вслепую: та
# модель фото не видела. Пока описание подставлялось всегда, оно эту комнату
# перекрашивало. 2026-08-04, джоб 244d4ef0: на фото светлая дневная кухня, сет
# просил «soft evening ambient lighting, warm glow» — и кадр вышел в чужой
# вечерней кухне с тёмными фасадами. Текст поэтому вступает в дело только когда
# место выбрал человек: тогда он и правда хочет другую комнату.
#
# Сохранять надо место, а не фон, и сказать это надо одним словом. Первая
# редакция просила «ту же мебель и поверхности за человеком» — и камера
# перестала двигаться вовсе: модель развернула человека на месте, оставив кадр
# за ним нетронутым (2026-08-04, джоб 6c5e990d). Вторая объясняла разницу между
# местом и фоном тремя предложениями и одним «не копируй» — сработало, но это
# были сто восемнадцать слов там, где хватает двух: «the same photo». Фраза сама
# несёт и комнату, и свет, и время суток, и то, что снимок другой.
_AVATAR_PLATE_TAIL = "Chest up, mouth closed, no smile, vertical 9:16."


def _avatar_plate_prompt(framing: str, set_text: str = "", face_first: bool = False,
                         room_last: bool = False) -> str:
    """Плита одной фразой: что снимаем, откуда — и хвост из трёх требований.

    В хвосте только то, за что уже платили ошибкой. «Chest up» — дистанция,
    общая для всех камер: разная крупность на стыке читается наездом, а не
    второй камерой (2026-08-02, джоб saas_bd4a6584). «Mouth closed, no smile» —
    плита становится первым кадром клипа, и улыбка на ней улыбается всю реплику.
    «Vertical 9:16» — формат ролика. Личность, свет, фотореализм и «один человек
    в кадре» не названы намеренно: всё это приезжает картинкой, и слова о ней
    только мешают (2026-08-05, проверка руками — фраза в двенадцать слов дала
    ракурс с первого раза).
    """
    # Ракурс может и не приехать: этой же функцией рисуют кадр, где камеру никто
    # не заказывал. Тогда фраза просто короче — но не «..., . Chest up».
    where = f", {framing}" if framing else ""
    if face_first:
        opening = "The first photo is this person's face. " + (
            f"Photograph them in {set_text}{where}. " if set_text else
            f"The second photo again{where}. ")
    else:
        opening = (f"The same person, in {set_text}{where}. " if set_text else
                   f"The same photo{where}. ")
    # Про картинку говорим, только если она едет. Обещанная и неотправленная —
    # это просьба её выдумать.
    if room_last:
        opening += "The last photo is the room. "
    return opening + _AVATAR_PLATE_TAIL


def _avatar_reference_image(
    shot: dict,
    actor_photo_path: str,
    fal_key: str,
    output_path: str,
    log: Callable[[str], None] = print,
    scene_override: str = "",
    framing: str = "",
    billing: Optional[dict] = None,
    edit_model: str = "",
    face_photo_path: str = "",
    set_photo_path: str = "",
) -> str:
    """Avatar frame from the actor photo + a scene description.

    Keeps the saved avatar's identity (face, hair, outfit) via an image-conditioned
    Flux edit, but stages the described scene so each cut is its own composition
    instead of a crop of one static photo — which made Kling clone the person
    toward the frame edges. Returns "" on any failure so the caller falls back to
    a punch-in crop of the shared photo: a plainer frame beats a failed job.

    scene_override pins one set for every talking shot of a reel, и попадает в
    промпт только когда место выбрал человек: иначе комната приезжает картинкой,
    а не словами. framing — точка съёмки, одна короткая фраза (`_AVATAR_FRAMINGS`).

    Весь промпт собирает `_avatar_plate_prompt`, и он короткий. Длинный —
    объяснения, запреты и перечисление того, что и так есть на фото, — камеру
    глушит: 0.060 против 0.633 по повороту головы.
    """
    face = face_photo_path if (face_photo_path and os.path.exists(face_photo_path)) else ""
    if not face and not (actor_photo_path and os.path.exists(actor_photo_path)):
        return ""
    # Личность держит портрет, поэтому он идёт первым — и первым же его получат
    # редакторы с одиночным входом. Общий план едет вторым и только туда, где для
    # него есть место: иначе промпт рассказывал бы про картинку, которой нет.
    primary = face or actor_photo_path
    # Второй и третий референсы доходят не до всех редакторов: поле под картинку
    # у половины каталога одиночное. Что не отправляем — о том и не рассказываем.
    multi = _avatar_edit_model(edit_model)["field"] == "image_urls"
    body = ""
    if multi and face and actor_photo_path and os.path.exists(actor_photo_path):
        if os.path.normpath(actor_photo_path) != os.path.normpath(face):
            body = actor_photo_path
    room = ""
    if multi and set_photo_path and os.path.exists(set_photo_path):
        if os.path.normpath(set_photo_path) not in (os.path.normpath(primary),
                                                    os.path.normpath(body) if body else ""):
            room = set_photo_path
    scene = (scene_override or shot.get("generation_prompt") or shot.get("scene") or "")
    scene = scene.strip().rstrip(".")
    framing = (framing or "").strip().rstrip(".")
    prompt = _avatar_plate_prompt(framing, set_text=scene,
                                  face_first=bool(body), room_last=bool(room))
    return _flux_reference_frame(
        prompt, fal_key, output_path, log=log,
        actor_photo_path=primary,
        extra_photo_paths=[p for p in (body, room) if p],
        label="Avatar reference frame",
        on_failure="; using cropped photo instead",
        billing=billing,
        edit_model=edit_model,
    )


# Камеры одного сета, по кругу — весь фокус роликов, которые читаются как снятое
# интервью: фон не меняется, меняется точка съёмки, и сброс позы в начале каждого
# клипа попадает между двумя разными ракурсами и перестаёт читаться как рывок.
#
# Камеры разводит угол, а не крупность, и это правило, а не вкус. Разная
# крупность у соседних кадров читается не как вторая камера, а как наезд на
# склейке: тот же человек в той же позе, просто ближе. Дистанция поэтому у всех
# камер одна и сказана одними и теми же словами (`_AVATAR_PLATE_TAIL`), а
# крупность остаётся приёмом внутри кадра (`_talking_push_in`) — редко и по ходу
# реплики, никогда на монтажном стыке.
#
# Каждая камера — своя постановка с фото ведущего, как две камеры на подкасте.
# Выводить вторую кропом первой пробовали (2026-08-02, джоб saas_9440becb) — так
# нельзя: кроп между двумя кадрами это не вторая камера, а наезд, и вдобавок
# следующая за ним правка «смени только момент» отъезжала назад (лицо 37.5% ->
# 28.3% кадра) и переодевала человека — в одном ролике кадр 5 в рубашке с
# длинным рукавом, кадр 7 в футболке. Разводить камеры словами про план
# («medium shot» против «tight close-up») пробовали там же (джоб saas_bd4a6584):
# редактор дал 18.0% и 21.4% высоты лица — на смену плана не хватило, а то, что
# вышло, читалось наездом.
_AvatarCamera = namedtuple("_AvatarCamera", "key direction")

# Камера называется одной фразой. Прежние постановки росли по предложению за
# каждый сорванный кадр и доросли до трёхсот тридцати слов — а редактор слышит
# короткое. Замерено по повороту головы: длинная постановка развела камеры на
# 0.060, та же камера в восемь слов — на 0.633. Человек проверил это руками
# 2026-08-05: одно фото и «This is the same photo, but from a different angle,
# to the right» дали ракурс с первого раза. Всё, что длиннее, — это объяснение
# модели, зачем ей делать то, что она и так умеет.
_AVATAR_FRAMINGS = (
    _AvatarCamera("front", "taken straight on at eye level"),
    _AvatarCamera("side", "taken from a different angle, forty degrees to the right"),
)
_AVATAR_HUSH_FRAMING = _AvatarCamera(
    "hush", "taken from just below eye level, with the person leaning in")
_AVATAR_CAMERAS = {c.key: c for c in (*_AVATAR_FRAMINGS, _AVATAR_HUSH_FRAMING)}

# Номер локации живёт в ключе камеры, а не рядом с ним: ключ — это и имя файла
# плиты, и половина её подписи, так что комната, попавшая в ключ, сама разводит
# кадры по разным файлам и не даёт усыновить чужую плиту из другой комнаты.
_PLATE_LOCATION_SEP = "_l"


def _camera_at_location(camera: _AvatarCamera, index: int) -> _AvatarCamera:
    """Та же камера, но в другой комнате. Нулевая — без суффикса: имена плит
    роликов с одним местом остаются прежними, и уже утверждённые кадры не
    перерисовываются из-за одной опции, которую никто не включал."""
    if index <= 0:
        return camera
    return _AvatarCamera(f"{camera.key}{_PLATE_LOCATION_SEP}{index}", camera.direction)


def _camera_location(key: str) -> int:
    head, sep, tail = (key or "").rpartition(_PLATE_LOCATION_SEP)
    return int(tail) if head and sep and tail.isdigit() else 0


def _camera_base_key(key: str) -> str:
    return (key or "").rpartition(_PLATE_LOCATION_SEP)[0] or key or ""


def _avatar_framing_for_shot(shot: dict, framing_index: int) -> _AvatarCamera:
    if _shot_performance(shot) == "whisper":
        camera = _AVATAR_HUSH_FRAMING
    else:
        camera = _AVATAR_FRAMINGS[framing_index % len(_AVATAR_FRAMINGS)]
    try:
        return _camera_at_location(camera, int(shot.get("_set_index") or 0))
    except (TypeError, ValueError):
        return camera


def _avatar_motion_prompt_for_shot(shot: dict) -> str:
    if _shot_performance(shot) == "whisper":
        return _AVATAR_WHISPER_MOTION_PROMPT
    return _AVATAR_MOTION_PROMPT


def _framing_plate_path(output_dir: str, title_slug: str, key: str) -> str:
    """Where one camera's staged frame lives — same name for preview and render."""
    return os.path.join(output_dir, f"{title_slug}_actor_set_{key}.png")


def _is_framing_plate(path: str, title_slug: str) -> bool:
    return os.path.basename(path or "").startswith(f"{title_slug}_actor_set_")

# Gentle alternating punch-ins (zoom, center-x, center-y as fractions). Variant 0
# keeps the original so the first shot matches the approved actor photo. Used only
# when the staged framing plates are unavailable.
_AVATAR_REFERENCE_VARIANTS = [
    None,
    (1.10, 0.50, 0.42),
    (1.16, 0.46, 0.50),
    (1.10, 0.54, 0.55),
    (1.16, 0.50, 0.60),
]


def _refuse_unusable_start_frame(photo_path: str) -> None:
    """Стоп до платного Kling, если оживлять собираемся заведомо не тот кадр.

    Когда постановочный кадр не получился, говорящий клип уходит от фото
    ведущего как есть. Для одиночного вертикального портрета это честная
    деградация — ради неё запасной путь и написан. Но фото ведущего бывает
    «раскладкой»: несколько ракурсов одного человека рядом на одном листе,
    почти всегда горизонтальной. Kling оживляет её целиком — три фигуры в
    кадре, — и это уже оплаченный брак. Горизонтальная картинка в вертикальном
    ролике всё равно не стартовый кадр, так что режем по ориентации.
    """
    try:
        from PIL import Image

        with Image.open(photo_path) as im:
            width, height = im.size
    except Exception:
        return  # не прочитали — не мешаем генерации
    if width <= height:
        return
    raise RuntimeError(
        f"Не удалось поставить кадр ведущего, а его фото — горизонтальное "
        f"({width}×{height}); в вертикальном ролике оно попадёт в кадр целиком "
        f"(так бывает с раскладками «несколько ракурсов на одном листе»). "
        f"Остановился до платной генерации видео. Что сделать: нажать «Сгенерить недостающие» "
        f"на шаге раскадровки и проверить кадры глазами, либо выбрать ведущего "
        f"одиночным вертикальным портретом."
    )


def _crop_zoom_image(image_path: str, output_path: str, zoom: float, cx: float, cy: float) -> str:
    """Кадр крупнее: кроп на `zoom` вокруг точки (`cx`, `cy`) и обратно в размер.

    Разводит стартовые кадры, которые иначе совпали бы буквально (одна камера у
    двух соседних клипов, одно фото у нескольких кадров). Не заменяет камеру:
    крупность здесь — способ не повторить кадр, а не способ его получить.
    Не получилось — отдаём исходник: одинаковый кадр лучше упавшей генерации.
    """
    if _nonempty(output_path):
        return output_path
    vf = (
        f"crop=iw/{zoom}:ih/{zoom}:(iw-iw/{zoom})*{cx}:(ih-ih/{zoom})*{cy},"
        f"scale=ceil(iw*{zoom}/2)*2:ceil(ih*{zoom}/2)*2"
    )
    cmd = ["ffmpeg", "-y", "-i", image_path, "-vf", vf, output_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except Exception as e:
        print(f"[SaaSShorts] ⚠️ Crop failed, using the frame as it is: {e}")
        return image_path


def _avatar_reference_variant(image_path: str, output_path: str, index: int) -> str:
    """Crop a slightly different framing of one actor photo per shot.

    When several shots share one reference image, identical first frames make
    every cut look like a glitchy reset. A small alternating punch-in keeps the
    same person but gives each clip its own starting composition.
    """
    variant = _AVATAR_REFERENCE_VARIANTS[(index - 1) % len(_AVATAR_REFERENCE_VARIANTS)]
    if variant is None:
        return image_path
    return _crop_zoom_image(image_path, output_path, *variant)


_PLATE_IDENTITY_SUFFIX = ".set.txt"


def _reference_fingerprint(path: str) -> str:
    """Короткая подпись референса — по содержимому, а не по пути.

    Один и тот же портрет приезжает под разными именами: загрузка кладёт его в
    `actor_uploads/custom_<uuid>.png`, а джоб копирует к себе. По имени такие
    копии — разные файлы, и плита перерисовывалась бы за деньги на каждой из них.
    """
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:12]
    except OSError:
        return os.path.basename(path or "")


class _AvatarPlates:
    """Постановочные кадры камер — по одному на камеру, общие на весь ролик.

    Один источник правды для двух путей, которые раньше собирали плиты каждый
    сам: предпросмотра кадров и платного рендера. Расхождение здесь означало бы,
    что человек утвердил один кадр, а оживили другой.

    Одна плита на камеру и на весь ролик: кадр на каждый шот — это и счёт за
    каждый шот, и новая комната за каждой склейкой.

    «На весь ролик», а не «на папку джоба». Каждое нажатие «сгенерить» заводит
    новую папку, и раньше плита рисовалась в ней заново: три прогона давали три
    разных `medium` — три комнаты на одной камере, оплаченные трижды, — а рендер
    вдобавок рисовал четвёртую и оживлял её вместо утверждённой. Поэтому рядом с
    плитой лежит `.set.txt`: чем этот кадр является (камера, её постановка,
    закреплённый сет), а не как его попросили. Совпало — берём готовый файл из
    любой папки, не платим и не расходимся с предпросмотром.
    """

    def __init__(self, output_dir: str, title_slug: str, pinned_set: str,
                 actor_photo: Callable[[], str], fal_key: str,
                 edit_model: str = "", billing: Optional[dict] = None,
                 known_frames: Optional[List[str]] = None,
                 face_photo: Optional[Callable[[], str]] = None,
                 set_chosen: bool = False,
                 sets: Optional[List[str]] = None,
                 pinned_plates: Optional[dict] = None,
                 log: Callable[[str], None] = print):
        self._output_dir = output_dir
        self._slug = title_slug
        # Место действия словами берём только когда его выбрал человек: иначе
        # комнату держит фото ведущего, на котором она уже снята.
        self._set = pinned_set if set_chosen else ""
        # Мест может быть несколько — опция «менять локации». Нулевое обязано
        # совпасть с одиночным: иначе включение опции перерисовало бы и те плиты,
        # что уже утверждены для первой комнаты.
        self._sets = [s for s in (sets or []) if s] if set_chosen else []
        if self._sets:
            self._set = self._sets[0]
        # Готовые плиты, загруженные руками: картинка, а не задание её нарисовать.
        self._pinned_plates = {k: v for k, v in (pinned_plates or {}).items() if v}
        self._actor_photo = actor_photo
        self._face_photo = face_photo or (lambda: "")
        self._fal_key = fal_key
        self._edit_model = edit_model
        self._billing = billing
        self._log = log
        self._made: dict = {}
        # Кадры, которые шоты уже носят, — в том числе из прошлых папок.
        self._known: List[str] = [p for p in (known_frames or []) if p]
        self._forgotten: set = set()
        # Камера, снятая первой: её плита становится опорой комнаты для всех
        # остальных. Не «front» жёстко — ролик может целиком уйти в шёпот, и
        # тогда фронтальная плита рисовалась бы только ради опоры, деньгами за
        # кадр, которого в ролике нет. Первая камера при этом определяется
        # порядком говорящих шотов, то есть для одной раскадровки постоянна.
        self._anchor_key = ""

    def path(self, camera: _AvatarCamera) -> str:
        return _framing_plate_path(self._output_dir, self._slug, camera.key)

    def _set_for(self, camera: _AvatarCamera) -> str:
        """Комната этой камеры: номер локации зашит в её ключ."""
        if not self._sets:
            return self._set
        return self._sets[_camera_location(camera.key) % len(self._sets)]

    def _pinned_plate(self, camera: _AvatarCamera) -> str:
        """Кадр, загруженный руками. Шёпот берёт фронтальный: своего слота у него
        нет, а рисовать его за деньги там, где остальные ракурсы отданы готовыми,
        значило бы платить за единственный кадр, который человек не выбирал."""
        base = _camera_base_key(camera.key) or camera.key
        path = self._pinned_plates.get(base) or (
            self._pinned_plates.get("front") if base == "hush" else "")
        return path if (path and _nonempty(path)) else ""

    def identity(self, camera: _AvatarCamera, set_photo: str = "") -> str:
        """Чем эта плита является — по этой строке её узнают в чужой папке.

        Подпись — сам промпт, слово в слово. Раньше здесь лежала выжимка (ключ
        камеры, постановка, сет, лицо), и правка формулировки картинку меняла, а
        подпись — нет: 2026-08-04 «сохрани фон» сменилось на «камера видит другой
        угол», плиты на диске об этом не узнали и усыновились как свои. Пока
        промпт был на триста слов, выжимка имела смысл — в нём и правда хватало
        слов, ничего не решающих. В промпте на двенадцать слов лишних нет.

        Референс лица — по содержимому файла, а не по имени: сменил портрет, а
        плита осталась прежней — это ровно тот случай, когда человек видит на
        экране не того, кого выбрал. Строка появляется только когда портрет есть:
        без него подпись обязана совпасть слово в слово с той, под которой
        рисовались уже утверждённые кадры, иначе первый же прогон перерисует их
        за деньги без всякой причины.
        """
        # Промпт берём в одноимённой форме — без «первое фото это лицо». Ту
        # оговорку добавляет наличие портрета, а портрет и так входит в подпись
        # отпечатком файла строкой ниже; считать его дважды значило бы гонять
        # плиты на перерисовку при смене редактора картинок.
        parts = [camera.key, _avatar_plate_prompt(camera.direction, set_text=self._set_for(camera))]
        face = self._face_photo()
        if face:
            parts.append(f"face:{_reference_fingerprint(face)}")
        if set_photo:
            parts.append(f"set:{_reference_fingerprint(set_photo)}")
        return "\n".join(parts)

    def forget(self, camera: _AvatarCamera) -> None:
        """Убрать плиту, чтобы «перерисовать» действительно перерисовало."""
        self._made.pop(camera.key, None)
        # Иначе тот же кадр вернётся из прошлой папки: он ведь всё ещё та камера
        # того же сета, и «перерисовать» стало бы «показать то же самое».
        self._forgotten.add(camera.key)
        path = self.path(camera)
        _drop_frame_files(path)
        for extra in (".prompt.txt", _PLATE_IDENTITY_SUFFIX):
            try:
                os.remove(f"{path}{extra}")
            except OSError:
                pass

    def plate(self, camera: _AvatarCamera) -> str:
        if camera.key not in self._made:
            self._made[camera.key] = self._take(camera) or self._draw_plate(camera)
        if not self._anchor_key and self._made.get(camera.key):
            self._anchor_key = camera.key
        return self._made[camera.key]

    def _take(self, camera: _AvatarCamera) -> str:
        """Готовый кадр этой камеры: загруженный руками или уже утверждённый."""
        pinned = self._pinned_plate(camera)
        if not pinned:
            return self._adopt(camera, self._set_photo(camera))
        target = self.path(camera)
        if os.path.normpath(pinned) != os.path.normpath(target):
            try:
                shutil.copyfile(pinned, target)
            except OSError:
                return ""
            # Подпись — отпечаток самого файла: перезалил другую картинку в тот
            # же слот, и плита обязана обновиться, а не остаться прежней.
            try:
                with open(f"{target}{_PLATE_IDENTITY_SUFFIX}", "w", encoding="utf-8") as f:
                    f.write(f"{camera.key}\nuploaded:{_reference_fingerprint(pinned)}")
            except OSError:
                pass
        self._log(f"  Ракурс «{camera.key}»: беру загруженный кадр, не рисую.")
        return target

    def _draw_plate(self, camera: _AvatarCamera) -> str:
        return self._build(camera, self._set_photo(camera))

    def _set_photo(self, camera: _AvatarCamera) -> str:
        """Опоры больше нет: готовый кадр в референсах убивает вторую камеру.

        Замерено 2026-08-04 по повороту головы (`voice_test/plate_yaw_2026_08_03.py`),
        разница между камерами относительно фронтальной плиты:

            промпт 332 слова, опора есть   0.035
            промпт  80 слов,  опора есть   0.003   ← возврат входной картинки
            промпт 332 слова, опоры нет    0.060
            промпт  80 слов,  опоры нет    0.633

        С опорой ракурс мёртв при любой формулировке: модели дают готовую
        фотографию человека и просят сдвинуть камеру — она отдаёт фотографию
        обратно. Словами это не переспорить, пробовали дважды.

        Держать комнату опора была нужна, пока место сочинялось текстом. Теперь
        оно приезжает с фото ведущего («the same photo»), и опора стала
        лишней. Параметр `set_photo_path` при этом жив: в него ляжет плита
        пустой комнаты, если место всё-таки придётся строить словами. Копировать
        с неё позу будет не с кого — там нет человека.
        """
        return ""

    def _adopt(self, camera: _AvatarCamera, set_photo: str = "") -> str:
        """Готовый кадр этой камеры — из этой папки или из той, где его утвердили."""
        if camera.key in self._forgotten:
            return ""
        want = self.identity(camera, set_photo)
        target = self.path(camera)
        for path in [target, *self._known]:
            if not _nonempty(path):
                continue
            try:
                with open(f"{path}{_PLATE_IDENTITY_SUFFIX}", encoding="utf-8") as f:
                    if f.read() != want:
                        continue
            except OSError:
                continue
            if os.path.normpath(path) == os.path.normpath(target):
                return target
            shutil.copyfile(path, target)
            # Вместе с картинкой переезжает и ссылка на её загруженную копию:
            # файл побайтово тот же, значит и залитый файл тот же. Без этого
            # каждый новый джоб заново отправляет на fal полтора мегабайта уже
            # лежащей там плиты — и падает, если по дороге оборвётся сеть
            # (2026-08-04: три попытки подряд, SSL EOF, кадр так и не нарисован).
            for extra in (_PLATE_IDENTITY_SUFFIX, ".prompt.txt", ".fal_url.txt"):
                try:
                    shutil.copyfile(f"{path}{extra}", f"{target}{extra}")
                except OSError:
                    pass
            self._log(f"  Ракурс «{camera.key}»: беру уже утверждённый кадр, не рисую заново.")
            return target
        return ""

    def _build(self, camera: _AvatarCamera, set_photo: str = "") -> str:
        made = self._draw(camera, set_photo)
        if made and _nonempty(made):
            try:
                with open(f"{made}{_PLATE_IDENTITY_SUFFIX}", "w", encoding="utf-8") as f:
                    f.write(self.identity(camera, set_photo))
            except OSError:
                pass
        return made

    def _draw(self, camera: _AvatarCamera, set_photo: str = "") -> str:
        if set_photo:
            self._log(f"  Ракурс «{camera.key}»: ставлю в ту же комнату, что и "
                      f"«{self._anchor_key}» — её плита идёт референсом.")
        return _avatar_reference_image(
            {}, self._actor_photo(), self._fal_key, self.path(camera), log=self._log,
            scene_override=self._set_for(camera),
            framing=camera.direction,
            billing=self._billing, edit_model=self._edit_model,
            face_photo_path=self._face_photo(),
            set_photo_path=set_photo,
        )


def _point_shot_at_frame(shot: dict, frame_path: str, job_dir: str) -> None:
    """Прицепить кадр к шоту всеми именами, под которыми его ищут интерфейс и рендер."""
    url = f"/videos/{job_dir}/{os.path.basename(frame_path)}"
    shot["image_path"] = frame_path
    shot["local_url"] = url
    shot["image_url"] = url
    shot["preview_frame_url"] = url


# Слова, по которым оборот в тексте сета опознаётся как разговор о съёмке:
# сама камера, направление взгляда и замершая поза. Границы слов обязательны —
# без них `pose` съедает `composed`, а `pan` — `pantry`.
_SET_CAMERA_WORDS = (
    r"cameras?", r"lens", r"selfies?", r"webcam", r"tripod", r"handheld",
    r"shots?", r"close-?ups?", r"framing", r"framed?", r"angles?",
    r"zoom(?:s|ing)?", r"panning", r"dolly", r"pov", r"vertical", r"9:16",
    r"gaz(?:e|es|ing)", r"look(?:s|ing)", r"facing", r"eye contact",
    r"pos(?:e|es|ed|ing)", r"static", r"steady", r"motionless",
)
_SET_CAMERA_RE = re.compile(r"\b(?:" + "|".join(_SET_CAMERA_WORDS) + r")\b", re.I)

# Внешность приезжает в сет двумя способами, и лечатся они по-разному.
#
# «a beautiful woman» (джоб f14d08b1) — это прилагательное при человеке, и
# вырезать надо именно его: оборот целиком выбрасывать нельзя, потому что в
# старых сценариях ровно в этой запятой лежит и комната («same woman from the
# reference image sitting on a cozy sofa in a modern living room»). Вдобавок
# «beautiful» бывает и про кухню — тогда клауза обязана уцелеть.
_SET_LOOKS_PHRASE_RE = re.compile(
    r"\b(?:a|an|the)\s+"
    r"(?:beautiful|pretty|gorgeous|attractive|stunning|handsome|lovely|elegant|"
    r"young|middle-aged|older|slim|slender|curvy|athletic|fit)\s+"
    r"(?:wom[ae]n|m[ae]n|girls?|guys?|lad(?:y|ies)|persons?|people|"
    r"females?|males?|models?|presenters?|actors?|actress(?:es)?)\b",
    re.I,
)
# А это слова, которые в описании места не значат ничего, кроме внешности,
# — такую оговорку выбрасываем целиком.
_SET_LOOKS_WORDS = (
    r"blonde", r"brunette", r"redhead", r"freckles?", r"makeup", r"make-up",
    r"hair", r"hairstyles?", r"haircuts?", r"skin", r"complexions?",
    r"wearing", r"dressed", r"outfits?", r"years old",
)
_SET_LOOKS_RE = re.compile(r"\b(?:" + "|".join(_SET_LOOKS_WORDS) + r")\b", re.I)


def _clean_pinned_set(scene: str) -> str:
    """Оставить в тексте сета место, свет и предметы; убрать съёмку и внешность.

    Закреплённый сет — это первый говорящий кадр раскадровки целиком, и он
    уезжает во все плиты. Если сценарист написал там «holding a steady selfie
    pose, looking directly at the camera», эта фраза стоит в промпте рядом со
    строкой ракурса и побеждает её. Замер 03.08 по тринадцати плитам: сеты со
    словами про момент («subtle head movement») дали разницу поворота головы
    между камерами 0.30 и 0.23, сеты со словами про камеру — 0.005 и 0.02, то
    есть вторая камера выходила тем же анфасом.

    Просьбой это не лечится: в обёртке плиты уже написано «ignore any camera
    wording», и не помогло — редактор слушает текст, а не оговорку про текст.

    Режем по предложениям, потом по запятым: «sitting on a cozy sofa in a modern
    living room» остаётся, «looking directly at the camera with a sigh» уходит
    целиком. Пустой результат отдаём как есть, без отката к оригиналу: если весь
    сет оказался разговором про съёмку, места в нём и не было — тогда плиты
    возьмут фон из обёртки и из опорной камеры, и это лучше, чем текст, который
    заведомо ломает ракурс.

    С появлением `set_prompt` это страховка, а не механизм: место теперь пишет
    отдельный запрос, у которого других обязанностей нет. Но выделенный запрос
    тоже иногда пишет лишнее, а старые сценарии приходят вообще без поля.
    """
    scene = _SET_LOOKS_PHRASE_RE.sub(" ", scene)
    kept = []
    for sentence in re.split(r"(?<=[.;!?])\s+", scene):
        clauses = [c.strip().strip(".;!?").strip() for c in sentence.split(",")]
        clauses = [c for c in clauses if c
                   and not _SET_CAMERA_RE.search(c)
                   and not _SET_LOOKS_RE.search(c)]
        if clauses:
            kept.append(", ".join(clauses))
    return re.sub(r"\s{2,}", " ", ". ".join(kept)).strip()


def _pinned_avatar_set(shots: list) -> str:
    """Место действия ролика — на нём стоят все говорящие кадры.

    Сначала ищем `set_prompt`: поле, которое пишет отдельный запрос и у которого
    одна работа. Если его нет (сценарий снят до разделения запросов), работает
    прежняя схема — промпт первого говорящего кадра, вычищенный от всего, что
    местом не является.
    """
    for shot in shots:
        pinned = (shot.get("_set_prompt") or "").strip()
        if pinned:
            return _clean_pinned_set(pinned)
    for shot in shots:
        if not _is_broll_shot(shot):
            scene = (shot.get("generation_prompt") or shot.get("scene") or "").strip()
            if scene:
                return _clean_pinned_set(scene)
    return ""


def _pinned_avatar_sets(shots: list) -> List[str]:
    """Все места ролика по порядку — пусто, если оно одно."""
    for shot in shots:
        places = [s.strip() for s in (shot.get("_set_prompts") or [])
                  if isinstance(s, str) and s.strip()]
        if len(places) > 1:
            return [_clean_pinned_set(place) for place in places]
    return []


def _pinned_set_is_chosen(shots: list) -> bool:
    """Место выбрал человек, а не досочинила модель.

    Только в этом случае текст перебивает комнату с фото ведущего: сочинённое
    вслепую описание её перекрашивает, а заказанное — на то и заказано. Опция
    «менять локации» — тоже заказ: там человек просит именно выдумку.
    """
    return any(shot.get("_set_chosen") for shot in shots)


def generate_sliced_avatar_clips(
    shots: list,
    audio_path: str,
    words: list,
    fal_key: str,
    output_dir: str,
    title_slug: str,
    tier: str = "standard",
    actor_description: str = "",
    selected_actor_path: str = "",
    selected_face_path: str = "",
    broll_tier: str = "standard",
    broll_image_first: bool = True,
    avatar_image_first: bool = True,
    voice_manifest: Optional[dict] = None,
    edit_model: str = "",
    billing: Optional[dict] = None,
    pinned_plates: Optional[dict] = None,
    log: Callable[[str], None] = print,
) -> list:
    """
    Slice one master voiceover at phrase boundaries and generate a Kling Avatar
    clip per shot from its own reference frame. The slices tile the voiceover,
    so at assembly the master track plays uncut while video changes per shot.

    Shots marked visual_type "broll" render with Kling V3 instead: the master
    voiceover keeps playing over them, so no lipsync is needed — the actor just
    must not visibly talk in those clips.
    """
    audio_duration = _get_media_duration(audio_path)
    # The manifest wins when it covers the reel: it records where each shot's own
    # audio was laid down, so an untouched shot keeps its exact bounds while a
    # neighbour is re-voiced. Re-deriving them from a transcript would move them
    # by a few milliseconds and cost that shot's paid clip for nothing.
    voice_manifest = voice_manifest or {}
    slices, skipped = _slices_from_voice_bounds(shots, voice_manifest)
    if len(slices) != len(_speech_shots_numbered(shots)):
        slices, skipped = _align_shots_to_voiceover(shots, words, audio_duration)
    for shot in skipped:
        log(
            f"  ⚠️ Shot {shot.get('shot_number', '?')} has no speech — skipped: "
            "the sliced-avatar timeline is driven by the voiceover."
        )
    if not slices:
        raise ValueError("Sliced-avatar mode requires at least one shot with speech")
    onset_adjustments = _retime_talking_slices_to_speech(slices, words, audio_path)
    if onset_adjustments:
        log(
            f"  Липсинк: {onset_adjustments} говорящих кадр(а) начинаются у речи; "
            "ведущая пауза осталась предыдущему визуалу."
        )
    filled, short = _fill_slices_to_clip_floor(slices, words)
    if filled:
        log(f"  Кадры: {filled} шт. добрали время до полного клипа — "
            "платим за него в любом случае.")
    if short:
        log(f"  Кадры: {short} шт. короче того, что модель вообще снимает "
            f"(перебивка {_KLING_MIN_CLIP_SECONDS} с, говорящий "
            f"{_KLING_AVATAR_MIN_CLIP_SECONDS} с), и занять время не у кого. "
            "Клип оплачен целиком, а на экране мелькнёт: кадров в ролике больше, "
            "чем эта длительность может оплатить — их стоит укрупнить.")
    pre_split = len(slices)
    slices = _split_performance_slices(slices, words)
    slices = _split_long_slices(
        slices, words,
        cuts_by_shot={k: v.get("cuts") for k, v in voice_manifest.items() if v.get("cuts")},
    )
    update_voice_cuts(output_dir, title_slug, _cuts_from_slices(slices))
    shot_parts: dict = {}
    if len(slices) != pre_split:
        log(
            f"  Ритм: {pre_split} кадров -> {len(slices)} клипов "
            f"(говорящий кадр длиннее {_MAX_TALKING_SLICE_SECONDS:.0f}s разделён по паузам; "
            "короткие авторские кадры остаются одним дублем без двойной оплаты)."
        )

    fallback_actor_img = ""
    # One set for the whole reel, taken from the first talking shot: every talking
    # clip is staged on it, only the framing alternates.
    pinned_set = _pinned_avatar_set([sl["shot"] for sl in slices])

    def _shared_actor_photo():
        nonlocal fallback_actor_img
        if selected_actor_path and os.path.exists(selected_actor_path):
            return selected_actor_path
        if not fallback_actor_img:
            fallback_actor_img = os.path.join(output_dir, f"{title_slug}_actor.png")
            if not _nonempty(fallback_actor_img):
                desc = actor_description or (
                    "a young professional in their late 20s, wearing a casual modern outfit, clean background"
                )
                generate_actor_image(desc, fal_key, fallback_actor_img)
        return fallback_actor_img

    def _shared_face_photo():
        return selected_face_path if (selected_face_path and os.path.exists(selected_face_path)) else ""

    plates = _AvatarPlates(
        output_dir, title_slug, pinned_set, _shared_actor_photo, fal_key,
        edit_model=edit_model, billing=billing, log=log,
        face_photo=_shared_face_photo,
        set_chosen=_pinned_set_is_chosen([sl["shot"] for sl in slices]),
        sets=_pinned_avatar_sets([sl["shot"] for sl in slices]),
        pinned_plates=pinned_plates or {},
        # Рендер идёт в своей папке, а утверждали кадры в папке предпросмотра.
        # Без этого списка он нарисовал бы плиты заново — и оживил бы не то,
        # что человек посмотрел и принял.
        known_frames=_talking_frames_on_hand([sl["shot"] for sl in slices], _job_output_root(output_dir)),
    )
    reported_cameras: set = set()

    def _framing_plate(camera):
        """Staged frame for one camera of the pinned set, generated once per reel."""
        made = plates.plate(camera)
        if made and camera.key not in reported_cameras:
            reported_cameras.add(camera.key)
            log(f"  Ракурс «{camera.key}» готов — он держится на всех говорящих кадрах.")
        return made

    def _resolve_image(sl, index, camera, framing_index):
        whisper = _shot_performance(sl["shot"]) == "whisper"
        if whisper and avatar_image_first:
            plate = _framing_plate(camera)
            if plate:
                return plate
        # A frame the user picked or generated for this shot always wins, as it
        # is. Раньше каждый второй такой кадр отдавался кропом самого себя, чтобы
        # разбитый джамп-катом кадр не сыграл дважды одну картинку, — но кроп
        # между двумя кадрами это наезд на склейке. Повтор разводится сменой
        # камеры ниже, а не крупностью.
        ref = _storyboard_avatar_reference_image(sl["shot"], output_dir, index)
        # A frame the storyboard already staged as one of our cameras is not a
        # per-shot choice — the cursor owns which camera plays, so that a shot
        # split in two never plays the same angle twice in a row.
        if ref and _is_framing_plate(ref, title_slug):
            ref = ""
        if ref:
            return ref
        if avatar_image_first:
            plate = _framing_plate(camera)
            if plate:
                return plate
        # Fallback: vary the crop of the shared photo so cuts read as camera changes.
        photo = _shared_actor_photo()
        _refuse_unusable_start_frame(photo)
        variant_path = os.path.join(output_dir, f"{title_slug}_actor_ref_{index:02d}.png")
        return _avatar_reference_variant(photo, variant_path, framing_index + 1)

    jobs = []
    framing_cursor = 0
    previous_talking_image = ""
    for index, sl in enumerate(slices, start=1):
        slice_audio = os.path.join(output_dir, f"{title_slug}_slice_{index:02d}.mp3")
        broll = _is_broll_shot(sl["shot"])
        # Distinct names so a shot flipping talking<->broll never reuses a stale clip
        clip_name = f"{title_slug}_avatar_broll_{index:02d}.mp4" if broll else f"{title_slug}_avatar_{index:02d}.mp4"
        clip_path = os.path.join(output_dir, clip_name)
        # Jump cuts carry a copy of the shot, so they are counted by shot number:
        # part 2 of shot 3 must not be mistaken for part 1 on the next render.
        key = str(sl["shot"].get("shot_number"))
        part = shot_parts[key] = shot_parts.get(key, 0) + 1
        _ensure_slice_audio(
            audio_path, sl["start"], sl["end"], slice_audio, clip_path, log,
            identity=_slice_identity(sl, voice_manifest or {}, part),
            invalidate_video=not broll,
        )
        actor_ref = ""
        if broll:
            image = ""
            # Resolved here, not inside the parallel render: `_shared_actor_photo`
            # may draw the fallback actor, and two threads would draw it twice.
            if broll_image_first and _shot_wants_actor(sl["shot"]):
                actor_ref = _shared_actor_photo()
        else:
            # Two talking shots may sit back to back, but never on the same camera.
            camera = _avatar_framing_for_shot(sl["shot"], framing_cursor)
            image = _resolve_image(sl, index, camera, framing_cursor)
            # Ротация камер сама разводит соседние кадры, но не всегда: два шёпота
            # подряд оба уходят на «hush», а кадр, разбитый джамп-катом, оба раза
            # приносит свой собственный стартовый кадр. Один и тот же кадр подряд
            # читается как сбой генерации, а не как монтаж, — но лечится он второй
            # камерой, а не наездом: наезд на склейке это ровно то, чего между
            # кадрами быть не должно. Кроп остаётся только там, где камер нет.
            if image and image == previous_talking_image:
                spare = _AVATAR_FRAMINGS[(framing_cursor + 1) % len(_AVATAR_FRAMINGS)]
                other = _framing_plate(spare) if avatar_image_first else ""
                shot_label = sl["shot"].get("shot_number", index)
                if other and other != image:
                    image = other
                    log(f"  Кадр {shot_label}: та же камера, что у предыдущего — "
                        f"беру ракурс «{spare.key}», чтобы склейка не читалась как сбой.")
                else:
                    punch_path = os.path.join(
                        output_dir, f"{title_slug}_actor_punch_{index:02d}.png")
                    image = _avatar_reference_variant(image, punch_path, 2)
                    log(f"  Кадр {shot_label}: та же камера, что у предыдущего, "
                        "а второго ракурса нет — развожу кропом.")
            previous_talking_image = image
            framing_cursor += 1
        jobs.append({
            "index": index,
            "shot_number": sl["shot"].get("shot_number") or index,
            "part": part,
            "slice": sl,
            "audio": slice_audio,
            "image": image,
            "clip_path": clip_path,
            "broll": broll,
            "actor_ref": actor_ref,
            "motion_prompt": _avatar_motion_prompt_for_shot(sl["shot"]),
        })
        # Keep overlay/subtitle timing aligned with the real audio timeline
        sl["shot"]["start"] = sl["start"]
        sl["shot"]["end"] = sl["end"]

    def _job_label(job):
        label = f"Кадр {job['shot_number']}"
        if job["part"] > 1:
            label += f", фрагмент {job['part']}"
        return label

    def _gen_clip(job):
        # Cache checks are prompt-aware (a bare exists() would silently ignore
        # edited Kling prompts on retry), so the request prompt is built first.
        job_label = _job_label(job)
        if job["broll"]:
            slice_duration = job["slice"]["end"] - job["slice"]["start"]
            v3_shot = _broll_slice_shot(job["slice"]["shot"], slice_duration)
            if _storyboard_clip_cache_valid(v3_shot, job["clip_path"]):
                log(f"[{job_label} | B-roll] Видео уже готово — беру из кэша.")
                return job["clip_path"]
            frame_source = "Стартовый PNG не используется"
            if broll_image_first:
                # Кадр, одобренный в предпросмотре, уже оплачен. Рисовать его
                # заново — это второй счёт за ту же картинку и другой сэмпл
                # вместо того, что человек посмотрел и утвердил.
                approved = _existing_shot_frame(v3_shot, _job_output_root(output_dir))
                if approved:
                    v3_shot["image_path"] = approved
                    frame_source = "Стартовый PNG взят из предпросмотра"
                else:
                    ref = _broll_reference_image(
                        v3_shot, fal_key,
                        job["clip_path"].replace(".mp4", "_ref.png"),
                        log=log,
                        actor_photo_path=job["actor_ref"],
                        billing=billing, edit_model=edit_model,
                    )
                    if ref:
                        v3_shot["image_path"] = ref
                        frame_source = "Стартовый PNG подготовлен"
            log(
                f"[{job_label} | B-roll] {frame_source}; создаю новое видео Kling V3 "
                f"({job['slice']['start']:.1f}-{job['slice']['end']:.1f} с)."
            )
            return generate_storyboard_shot_clip(
                v3_shot,
                fal_key,
                job["clip_path"],
                tier=broll_tier,
            )
        if _avatar_clip_cache_valid(
            job["clip_path"],
            job["image"],
            motion_prompt=job["motion_prompt"],
        ):
            log(f"[{job_label} | ведущий] Lip-sync видео уже готово — беру из кэша.")
            return job["clip_path"]
        if _nonempty(job["clip_path"]):
            log(f"[{job_label} | ведущий] Референсный кадр изменился — старый клип не подходит.")
            for stale in (
                job["clip_path"],
                f"{job['clip_path']}.review.json",
                f"{job['clip_path']}.review.jpg",
            ):
                try:
                    if os.path.exists(stale):
                        os.remove(stale)
                except OSError:
                    pass
        log(
            f"[{job_label} | ведущий] создаю новое lip-sync видео Kling Avatar "
            f"({job['slice']['start']:.1f}-{job['slice']['end']:.1f} с)."
        )
        return generate_talking_head(
            job["image"],
            job["audio"],
            fal_key,
            job["clip_path"],
            tier=tier,
            motion_prompt=job["motion_prompt"],
        )

    errors = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_gen_clip, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            try:
                future.result()
            except Exception as e:
                errors.append(f"shot {job['index']}: {e}")
    if errors:
        raise Exception("Sliced-avatar generation failed for " + "; ".join(errors))

    return [
        {
            "path": job["clip_path"],
            "duration": job["slice"]["end"] - job["slice"]["start"],
            "shot": job["slice"]["shot"],
            "audio_slice": job["audio"],
            "reference_image": job["image"],
            "start": job["slice"]["start"],
            "end": job["slice"]["end"],
            # B-roll carries no audio, so only lip-synced clips inherit the
            # slice's encoder delay — and only they need it skipped.
            "speech_offset": 0.0 if job["broll"] else _mp3_encoder_delay(job["audio"]),
        }
        for job in jobs
    ]


# --------------------------------------------------------------------------
# Incremental voiceover
#
# Regenerating one take for the whole reel is what used to kill the paid avatar
# clips: a fresh take differs from the old one *everywhere* (eleven_v3 in
# Creative mode is never twice the same), so every clip lip-synced against the
# old one had to be shot again — including the shots the user never touched. So
# the take is not the unit of caching; the shot is. Each shot keeps its own
# audio file, and only runs of consecutive shots whose text actually changed get
# voiced again.
#
# The numbers below are measured, not guessed — tools/tts_seam_test.py on a real
# 5-shot Russian reel. That voice leaves ~410 ms between sentences, and a join
# padded to that length measured *quieter* than an average sentence boundary
# inside one continuous take (0.74 dB of level step against a natural 0.68 dB
# median, 0.49 semitones against 1.93). Voicing shot by shot instead of run by
# run measured three times worse (up to 3.77 dB, 4.45 st), which is why runs
# exist: the fewer joins, the longer each take, the more natural the delivery.
#
# eleven_v3 rejects previous_text/next_text/previous_request_ids outright, so
# there is no API-side stitching to lean on. The join is an edit, not a prompt.
_VOICE_JOIN_PAUSE_MS = 410.0
_VOICE_PIECE_EDGE_MS = 120.0
_VOICE_TARGET_LUFS = -16.0
_VOICE_SAMPLE_RATE = 44100


def _voice_manifest_path(output_dir: str, title_slug: str) -> str:
    return os.path.join(output_dir, f"{title_slug}_voice_manifest.json")


def _speech_shots_numbered(shots: list) -> list:
    """Every shot with speech, paired with the number its voiceover files use.

    One rule in one place: the manifest, the piece filenames and the slicer all
    have to agree on what "shot 3" means, or a cached piece ends up under
    somebody else's line.
    """
    speaking = [s for s in shots if (s.get("speech") or "").strip()]
    return [(shot, shot.get("shot_number") or (index + 1)) for index, shot in enumerate(speaking)]


def read_voice_manifest(output_dir: str, title_slug: str) -> dict:
    """Active shot audio inside the master track, keyed by the current number."""
    return {
        str(entry.get("shot_number")): entry
        for entry in read_voice_manifest_entries(output_dir, title_slug)
        if not entry.get("retired") and not entry.get("invalidated")
    }


def read_voice_manifest_entries(output_dir: str, title_slug: str) -> list:
    """All known voice pieces, including shots temporarily removed in the editor."""
    manifest = _read_json_file(_voice_manifest_path(output_dir, title_slug)) or {}
    return [entry for entry in (manifest.get("shots") or []) if isinstance(entry, dict)]


def _manifest_voice_piece_path(output_dir: str, entry: dict) -> str:
    """Resolve a manifest-owned piece without allowing it to escape the job dir."""
    name = os.path.basename(str((entry or {}).get("piece") or "").strip())
    return os.path.join(output_dir, name) if name else ""


def update_voice_cuts(output_dir: str, title_slug: str, cuts_by_shot: dict) -> None:
    """Remember where a shot's audio was cut into jump cuts, so it can be replayed."""
    path = _voice_manifest_path(output_dir, title_slug)
    manifest = _read_json_file(path)
    if not manifest.get("shots"):
        return
    for entry in manifest["shots"]:
        if entry.get("retired") or entry.get("invalidated"):
            continue
        cuts = cuts_by_shot.get(str(entry.get("shot_number")))
        if cuts:
            entry["cuts"] = [round(float(c), 3) for c in cuts]
        else:
            entry.pop("cuts", None)
    _write_json_file(path, manifest)


def _slices_from_voice_bounds(shots: list, manifest: dict) -> tuple:
    """Turn the voiceover manifest's exact per-shot bounds into avatar slices.

    Preferred over re-deriving boundaries from a transcript of the master track:
    the manifest already knows where each shot's own audio was laid down, so a
    shot nobody edited keeps the very same bounds when its neighbours are
    re-voiced — and keeps the paid clip lip-synced to them.
    """
    slices, skipped = [], []
    numbered = dict((id(shot), number) for shot, number in _speech_shots_numbered(shots))
    for shot in shots:
        bound = manifest.get(str(numbered.get(id(shot))))
        if not bound:
            skipped.append(shot)
            continue
        slices.append({"shot": shot, "start": float(bound["start"]), "end": float(bound["end"])})
    return slices, skipped


def _cuts_from_slices(slices: list) -> dict:
    """Where each shot ended up being cut, relative to its own start."""
    starts, cuts = {}, {}
    for sl in slices:
        number = sl["shot"].get("shot_number")
        if number is None:
            continue
        number = str(number)
        if number not in starts:
            starts[number] = sl["start"]
            continue
        cuts.setdefault(number, []).append(round(sl["start"] - starts[number], 3))
    return cuts


def _slice_identity(sl: dict, manifest: dict, part: int) -> str:
    """What a cached slice file has to still be, to be reused.

    The shot it belongs to, the words in it, and which jump cut of that shot it
    is. Without this a slice is trusted on its filename and length alone, and
    both survive a shot being deleted from the middle of the reel.
    """
    number = sl["shot"].get("shot_number")
    entry = manifest.get(str(number)) or {}
    signature = entry.get("signature") or (sl["shot"].get("speech") or "").strip()
    return f"{number}|{part}|{hashlib.sha1(signature.encode('utf-8')).hexdigest()[:16]}"


def _voice_piece_path(output_dir: str, title_slug: str, shot_number) -> str:
    # WAV, not mp3: pieces are concatenated back together, and every mp3 would
    # contribute its own encoder delay as a gap inside what used to be one
    # continuous take.
    return os.path.join(output_dir, f"{title_slug}_speech_{int(shot_number):02d}.wav")


def _voice_piece_for_shot(
    output_dir: str,
    title_slug: str,
    manifest: dict,
    shot_number,
) -> str:
    """The piece currently mapped to a shot, with a legacy filename fallback."""
    entry = (manifest or {}).get(str(shot_number)) or {}
    mapped = _manifest_voice_piece_path(output_dir, entry)
    if mapped:
        return mapped
    return _voice_piece_path(output_dir, title_slug, shot_number)


def _new_voice_piece_path(
    output_dir: str,
    title_slug: str,
    shot_number,
    signature: str,
    take_seq: int,
    take_index: int,
) -> str:
    """Allocate a piece without overwriting audio retained for another script state.

    The readable numbered name remains the first choice for a brand-new shot.
    Once that name is occupied, a signature-derived name is used instead and
    the manifest owns the number -> file mapping. This is what lets an inserted
    or reordered shot reuse its old take even though its display number changed.
    """
    numbered = _voice_piece_path(output_dir, title_slug, shot_number)
    if not _nonempty(numbered):
        return numbered
    fingerprint = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:16]
    return os.path.join(
        output_dir,
        f"{title_slug}_speech_{fingerprint}_t{int(take_seq):02d}_{int(take_index):02d}.wav",
    )


def _read_wav_samples(path: str):
    import wave

    with wave.open(path, "rb") as f:
        data = f.readframes(f.getnframes())
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


def _write_wav_samples(path: str, samples, rate: int = _VOICE_SAMPLE_RATE) -> str:
    import wave

    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return path


def _decode_audio_samples(path: str):
    """Any audio file as mono float samples at the pipeline's rate."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", path,
         "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", str(_VOICE_SAMPLE_RATE), "-"],
        check=True, capture_output=True,
    )
    return np.frombuffer(proc.stdout, dtype="<i2").astype(np.float32) / 32768.0


def _encode_audio_samples(samples, output_path: str) -> str:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(_VOICE_SAMPLE_RATE),
         "-ac", "1", "-i", "-", "-c:a", "libmp3lame", "-b:a", "192k", output_path],
        input=(np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes(),
        check=True, capture_output=True,
    )
    return output_path


def _measured_lufs(path: str) -> float:
    """Integrated loudness of a file, or NaN when ffmpeg will not say."""
    proc = subprocess.run(
        ["ffmpeg", "-nostdin", "-i", path, "-af",
         f"loudnorm=I={_VOICE_TARGET_LUFS}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    marker = proc.stderr.rfind('"input_i"')
    if marker < 0:
        return float("nan")
    start, end = proc.stderr.rfind("{", 0, marker), proc.stderr.find("}", marker)
    try:
        return float(json.loads(proc.stderr[start:end + 1])["input_i"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return float("nan")


def _take_gain(path: str) -> float:
    """One scalar that puts a whole take at the reel's loudness target.

    Per take, never per shot: a single gain leaves the take's own dynamics
    untouched and only matches its overall level to its neighbours, which is the
    artifact the ear catches first at a join.
    """
    measured = _measured_lufs(path)
    if measured != measured:  # NaN
        return 1.0
    return float(10 ** ((_VOICE_TARGET_LUFS - measured) / 20))


def _speech_bounds(samples, edge_ms: float = _VOICE_PIECE_EDGE_MS) -> tuple:
    """Where speech sits in a take, with a fixed strip of silence left on it.

    TTS hands back takes with whatever silence it felt like at the edges — in
    practice near zero, which is why two takes butted together sounded like the
    speaker gasping through a full stop. Normalising the edges here means the
    join can be a constant, decided once, instead of a measurement repeated on
    every render.
    """
    if not len(samples):
        return 0, 0
    win = _VOICE_SAMPLE_RATE // 100
    usable = len(samples) - len(samples) % win
    if usable < win:
        return 0, len(samples)
    frames = np.abs(samples[:usable].reshape(-1, win)).max(axis=1)
    floor = max(float(np.percentile(frames, 15)) * 3, float(frames.max()) * 0.02)
    loud = np.flatnonzero(frames > floor)
    if not len(loud):
        return 0, len(samples)
    edge = int(_VOICE_SAMPLE_RATE * edge_ms / 1000)
    return (max(0, int(loud[0]) * win - edge),
            min(len(samples), (int(loud[-1]) + 1) * win + edge))


def _shot_speech_signature(shot: dict, **tts_settings) -> str:
    return _tts_signature((shot.get("speech") or "").strip(), **tts_settings)


def _voice_runs(entries: list) -> list:
    """Group the shots that need voicing into runs of consecutive ones.

    One request per run rather than per shot: a run is read as continuous
    speech, so the delivery inside it stays natural and the reel gains exactly
    one join per edit boundary instead of one per shot.
    """
    runs, current = [], []
    for entry in entries:
        if entry["reusable"]:
            if current:
                runs.append(current)
                current = []
            continue
        current.append(entry)
    if current:
        runs.append(current)
    return runs


def _split_take_into_pieces(
    samples,
    take_shots: list,
    take_path: str,
    language: str,
    log: Callable[[str], None],
) -> list:
    """Cut one take into one piece per shot, so each shot can be cached alone.

    Boundaries come from the same word-proportional tiling the avatar slicer
    uses, so a piece ends where the shot's last scripted word ends rather than
    at an arbitrary proportional guess.
    """
    if len(take_shots) == 1:
        return [samples]
    duration = len(samples) / _VOICE_SAMPLE_RATE
    words = []
    try:
        words = transcribe_audio_for_subs(take_path, language=language)
        if words:
            words = _align_asr_words_to_script(
                words, " ".join((s.get("speech") or "").strip() for s in take_shots), log=log
            )
    except Exception as e:
        log(f"  ⚠️ Не удалось распознать дубль для нарезки по кадрам ({e}) — режу пропорционально.")
    slices, _ = _align_shots_to_voiceover(take_shots, words, duration)
    pieces = []
    for index, sl in enumerate(slices):
        start = int(sl["start"] * _VOICE_SAMPLE_RATE)
        # The last piece takes the remainder so the pieces rebuild the take exactly.
        end = len(samples) if index == len(slices) - 1 else int(sl["end"] * _VOICE_SAMPLE_RATE)
        pieces.append(samples[start:end])
    return pieces


def build_incremental_voiceover(
    shots: list,
    output_dir: str,
    title_slug: str,
    *,
    provider: str,
    fal_key: str,
    elevenlabs_key: str,
    voice_id: str,
    minimax_voice_id: str,
    language: str,
    actor_gender: str,
    revoice_all: bool = False,
    log: Callable[[str], None] = print,
) -> dict:
    """Voice only what changed, and hand back a master track plus its map.

    Returns the master voiceover path, each shot's exact [start, end] inside it,
    and which shots were re-voiced — the callers use the last one to work out
    which paid clips are still valid.
    """
    numbered = _speech_shots_numbered(shots)
    if not numbered:
        raise ValueError("Voiceover needs at least one shot with speech")

    tts_settings = {
        "provider": provider,
        "elevenlabs_voice_id": voice_id,
        "minimax_voice_id": minimax_voice_id,
        "language": language,
        "actor_gender": actor_gender,
    }
    stored = _read_json_file(_voice_manifest_path(output_dir, title_slug)) or {}
    stored_entries = read_voice_manifest_entries(output_dir, title_slug)
    known = read_voice_manifest(output_dir, title_slug)
    master_path = os.path.join(output_dir, f"{title_slug}_voice.mp3")
    narration = " ".join((shot.get("speech") or "").strip() for shot, _ in numbered)
    whole_signature = _tts_signature(
        narration, provider, voice_id, minimax_voice_id, language, actor_gender
    )

    def whole_take(reason: str = "", salvage: str = "", used: Optional[dict] = None) -> dict:
        """One take for the whole reel — the old behaviour, kept as the floor.

        Reached by a job recorded before per-shot pieces existed, and by any
        provider whose audio we cannot take apart. Losing incremental caching is
        a cost; losing the render would be a bug. `salvage` is a take that
        already holds the whole narration: paying for it a second time because
        we could not slice it would be absurd.
        """
        if reason:
            log(f"[1/5] {reason}")
        # A manifest describes a master built from pieces. Falling back to one
        # take replaces that master, so its map now points into audio that no
        # longer exists — and a later render must not slice by it.
        try:
            os.remove(_voice_manifest_path(output_dir, title_slug))
        except OSError:
            pass
        if salvage and _nonempty(salvage):
            shutil.move(salvage, master_path)
            return {"path": master_path, "bounds": [],
                    "changed_shots": [number for _, number in numbered],
                    "provider": (used or {}).get("provider") or provider,
                    "model": (used or {}).get("model") or ""}
        if not (_nonempty(master_path) and _read_tts_metadata(master_path).get("signature") == whole_signature):
            outcome = generate_voiceover_with_fallback(
                narration, master_path,
                provider=provider, fal_key=fal_key, elevenlabs_key=elevenlabs_key,
                elevenlabs_voice_id=voice_id, minimax_voice_id=minimax_voice_id,
                language=language, actor_gender=actor_gender, log=log,
            )
            return {"path": master_path, "bounds": [],
                    "changed_shots": [number for _, number in numbered],
                    "provider": outcome["provider"], "model": outcome.get("model") or ""}
        log("[1/5] Voiceover cached, skipping.")
        cached = _read_tts_metadata(master_path)
        return {"path": master_path, "bounds": [], "changed_shots": [],
                "provider": cached.get("provider") or provider, "model": cached.get("model") or ""}

    if not known and _nonempty(master_path) and not revoice_all:
        # A job from before this existed: its master still matches the script, so
        # reuse it rather than re-voicing (and re-paying for) every clip. The
        # first real edit moves the job onto per-shot pieces.
        if _read_tts_metadata(master_path).get("signature") == whole_signature:
            return whole_take()

    candidates_by_signature: dict = {}
    for stored_index, stored_entry in enumerate(stored_entries):
        signature = stored_entry.get("signature")
        piece_path = _manifest_voice_piece_path(output_dir, stored_entry)
        if (
            signature
            and not stored_entry.get("invalidated")
            and _nonempty(piece_path)
        ):
            candidates_by_signature.setdefault(signature, []).append(
                (stored_index, stored_entry, piece_path)
            )

    used_candidates = set()
    forced_numbers = {
        str(entry.get("shot_number"))
        for entry in stored_entries
        if not entry.get("retired") and entry.get("force_revoice")
    }
    entries = []
    for shot, number in numbered:
        signature = _shot_speech_signature(shot, **tts_settings)
        previous = known.get(str(number)) or {}
        candidate = None
        if not revoice_all and str(number) not in forced_numbers:
            matching = candidates_by_signature.get(signature) or []
            # Prefer the current number's exact entry, then any retired/moved
            # entry with the same full TTS recipe.
            matching = sorted(
                matching,
                key=lambda item: 0
                if item[1] is previous or str(item[1].get("shot_number")) == str(number)
                else 1,
            )
            candidate = next(
                (item for item in matching if item[0] not in used_candidates),
                None,
            )
        reusable = candidate is not None
        if candidate:
            source_index, source_entry, piece_path = candidate
            used_candidates.add(source_index)
        else:
            source_index, source_entry, piece_path = None, {}, ""
        entries.append({
            "shot": shot, "shot_number": number, "piece": piece_path,
            "signature": signature, "reusable": reusable,
            "take_seq": source_entry.get("take_seq", 0) if reusable else 0,
            # A re-voiced shot's jump cuts belong to audio that no longer exists.
            "cuts": source_entry.get("cuts") if reusable else None,
            "source_index": source_index,
        })

    runs = _voice_runs(entries)
    next_seq = max(
        [int(entry.get("take_seq") or 0) for entry in stored_entries]
        + [e["take_seq"] for e in entries]
        + [0]
    ) + 1
    provider_used = stored.get("provider") or provider
    model_used = stored.get("model") or ""

    if not runs:
        log("[1/5] Озвучка не менялась — беру целиком из кэша.")
    for run in runs:
        numbers = ", ".join(str(e["shot_number"]) for e in run)
        log(f"[1/5] Озвучиваю кадры {numbers} одним дублем ({len(run)} шт.)...")
        take_path = os.path.join(output_dir, f"{title_slug}_take_{next_seq:02d}.mp3")
        result = generate_voiceover_with_fallback(
            " ".join((e["shot"].get("speech") or "").strip() for e in run),
            take_path,
            provider=provider,
            fal_key=fal_key,
            elevenlabs_key=elevenlabs_key,
            elevenlabs_voice_id=voice_id,
            minimax_voice_id=minimax_voice_id,
            language=language,
            actor_gender=actor_gender,
            log=log,
        )
        provider_used, model_used = result["provider"], result.get("model") or ""

        try:
            samples = _decode_audio_samples(take_path) * _take_gain(take_path)
            head, tail = _speech_bounds(samples)
            pieces = _split_take_into_pieces(
                samples[head:tail], [e["shot"] for e in run], take_path, language, log
            )
        except Exception as e:
            covers_reel = len(runs) == 1 and len(run) == len(entries)
            return whole_take(
                f"Дубль не читается как аудио ({e}) — озвучиваю ролик одним куском.",
                salvage=take_path if covers_reel else "",
                used=result,
            )
        for take_index, (entry, piece) in enumerate(zip(run, pieces), start=1):
            entry["piece"] = _new_voice_piece_path(
                output_dir,
                title_slug,
                entry["shot_number"],
                entry["signature"],
                next_seq,
                take_index,
            )
            _write_wav_samples(entry["piece"], piece)
            entry["take_seq"] = next_seq
        next_seq += 1

    # A join between two takes gets the pause this voice takes between sentences
    # anyway. It is charged to whichever side was voiced later: that shot is
    # being re-rendered regardless, so the untouched neighbour keeps its bounds —
    # and with them its clip.
    pad = np.zeros(
        int(_VOICE_SAMPLE_RATE * max(0.0, _VOICE_JOIN_PAUSE_MS - 2 * _VOICE_PIECE_EDGE_MS) / 1000),
        dtype=np.float32,
    )
    timeline, bounds, cursor = [], [], 0
    for index, entry in enumerate(entries):
        piece = _read_wav_samples(entry["piece"])
        previous = entries[index - 1] if index else None
        start = cursor
        if previous is not None and previous["take_seq"] != entry["take_seq"]:
            timeline.append(pad)
            cursor += len(pad)
            if entry["take_seq"] < previous["take_seq"]:
                # The older take is on the right, so the pause is charged to the
                # newer one on the left — its bound grows, the untouched shot's
                # does not. Otherwise `start` stays put and the pause opens this
                # shot's slice instead.
                bounds[-1]["end"] = round(cursor / _VOICE_SAMPLE_RATE, 3)
                start = cursor
        timeline.append(piece)
        cursor += len(piece)
        bounds.append({
            "shot_number": entry["shot_number"],
            "start": round(start / _VOICE_SAMPLE_RATE, 3),
            "end": round(cursor / _VOICE_SAMPLE_RATE, 3),
        })

    master_path = os.path.join(output_dir, f"{title_slug}_voice.mp3")
    _encode_audio_samples(np.concatenate(timeline), master_path)

    changed = [e["shot_number"] for e in entries if not e["reusable"]]
    seams = sum(
        1 for i in range(1, len(entries))
        if entries[i]["take_seq"] != entries[i - 1]["take_seq"]
    )
    active_records = [
        {
            "signature": entry["signature"],
            "take_seq": entry["take_seq"],
            "piece": os.path.basename(entry["piece"]),
            **({"cuts": entry["cuts"]} if entry["cuts"] else {}),
            **bound,
        }
        for entry, bound in zip(entries, bounds)
    ]
    retired_records = []
    retained = {
        (record.get("signature"), record.get("piece"))
        for record in active_records
    }
    for stored_index, stored_entry in enumerate(stored_entries):
        if stored_index in used_candidates:
            continue
        piece_path = _manifest_voice_piece_path(output_dir, stored_entry)
        identity = (stored_entry.get("signature"), os.path.basename(piece_path))
        if not stored_entry.get("signature") or not _nonempty(piece_path) or identity in retained:
            continue
        retired = dict(stored_entry)
        retired["piece"] = os.path.basename(piece_path)
        retired["retired"] = True
        retired.pop("force_revoice", None)
        retired_records.append(retired)
        retained.add(identity)

    _write_json_file(_voice_manifest_path(output_dir, title_slug), {
        "provider": provider_used,
        "model": model_used,
        "shots": active_records + retired_records,
    })
    if runs and changed != [e["shot_number"] for e in entries]:
        log(f"[1/5] Перезаписано кадров: {len(changed)} из {len(entries)}, швов в дорожке: {seams}.")
    return {
        "path": master_path,
        "bounds": bounds,
        "changed_shots": changed,
        "provider": provider_used,
        "model": model_used,
    }


def already_prepared_voiceover(audio_path: str) -> dict:
    """Preparation report for a master track the builder already normalised.

    `prepare_voiceover_for_video_generation` strips silence off both edges, and
    the head is the problem: cutting it slides every bound in the voice manifest
    out of place, and each avatar clip would then be lip-synced against audio
    that starts a beat early. The incremental builder normalises the edges as it
    assembles, so the track is already what the avatar service wants. What stays
    is the refusal to hand Kling something unusable.
    """
    usable = _decodable_audio_duration(audio_path)
    if usable is None or usable < _MIN_VOICEOVER_SECONDS:
        raise ValueError(
            "Voiceover audio is empty or too short to animate "
            f"({'unreadable' if usable is None else f'{usable:.2f}s'}) — "
            "add spoken lines to the script before generating video."
        )
    return {
        "path": audio_path,
        "original_path": audio_path,
        "original_duration": round(usable, 3),
        "duration": round(usable, 3),
        "leading_silence": 0.0,
        "trailing_silence": 0.0,
        "silence_events": 0,
        "trimmed": False,
        "status": "normalized",
    }


def _purge_voiceover_derived_assets(output_dir: str, title_slug: str) -> None:
    """Remove assets baked from a stale master voiceover (slices, avatar clips).

    Called before regenerating the voiceover so retry caching can't stitch new
    audio to clips that were lip-synced against the old one.
    """
    patterns = [
        f"{title_slug}_slice_*.mp3",
        f"{title_slug}_avatar_*.mp4",
        f"{title_slug}_avatar_*.json",
        f"{title_slug}_voice_clean*",
        f"{title_slug}_voice.mp3.meta.json",
    ]
    for pattern in patterns:
        for path in glob.glob(os.path.join(output_dir, pattern)):
            for stale in (path, f"{path}.fal_url.txt"):
                try:
                    if os.path.exists(stale):
                        os.remove(stale)
                except OSError:
                    pass


def storyboard_title_slug(title: str) -> str:
    """Filename prefix every artifact of a storyboard job shares."""
    return re.sub(r"[^a-z0-9]+", "_", (title or "storyboard").lower())[:30] or "storyboard"


# The finished cut and the gallery record belong to the job that produced them:
# carrying them into a new job would overwrite one version with another.
_ADOPT_SKIP_NAMES = ("gallery_metadata.json",)


def _is_finished_cut(name: str) -> bool:
    """True for a job's rendered video, including its lip-synced versions."""
    return name.endswith(".mp4") and "_final" in name


def adopt_job_artifacts(
    source_dir: str,
    output_dir: str,
    source_slug: str = "",
    target_slug: str = "",
    source_label: str = "прошлого рендера",
    log: Callable[[str], None] = print,
) -> int:
    """Carry a finished job's paid artifacts into a fresh job dir.

    Re-opening a storyboard to change one shot used to re-render — and re-charge
    for — every shot, because the caches (clips, reference frames, voiceover)
    live next to the job's output. Copying them over lets the normal
    prompt-aware cache checks hit, so only the shots the user actually edited
    are generated again. The previous cut stays where it is, so both versions
    remain playable.
    """
    if not (source_dir and os.path.isdir(source_dir)):
        return 0
    source_dir = os.path.abspath(source_dir)
    output_dir = os.path.abspath(output_dir)
    if source_dir == output_dir:
        return 0
    os.makedirs(output_dir, exist_ok=True)

    copied = 0
    for name in sorted(os.listdir(source_dir)):
        src = os.path.join(source_dir, name)
        if not os.path.isfile(src):
            continue
        if name in _ADOPT_SKIP_NAMES or _is_finished_cut(name):
            continue
        target_name = name
        if source_slug and target_slug and source_slug != target_slug and name.startswith(source_slug):
            # The title (and with it every filename) may have been edited since.
            target_name = target_slug + name[len(source_slug):]
        dst = os.path.join(output_dir, target_name)
        if os.path.exists(dst):
            continue
        try:
            shutil.copy2(src, dst)
            if (
                source_slug
                and target_slug
                and source_slug != target_slug
                and target_name.endswith("_voice_manifest.json")
            ):
                manifest = _read_json_file(dst) or {}
                changed = False
                for entry in manifest.get("shots") or []:
                    piece = os.path.basename(str(entry.get("piece") or ""))
                    if piece.startswith(source_slug):
                        entry["piece"] = target_slug + piece[len(source_slug):]
                        changed = True
                if changed:
                    _write_json_file(dst, manifest)
            copied += 1
        except OSError as e:
            log(f"  ⚠️ Файл {name} из {source_label} не скопирован: {e}")
    if copied:
        source_lower = source_label.lower()
        if "озвуч" in source_lower:
            scope = "озвучка"
        elif "кадр" in source_lower:
            scope = "кадры"
        else:
            scope = "кэш"
        log(
            f"[{scope}] Перенёс {copied} файл(ов) из {source_label}; "
            "совместимые артефакты будут использованы повторно."
        )
    return copied


_SHOT_ARTIFACT_URL_KEYS = ("clip_url", "preview_frame_url", "local_url", "image_url")


def _shot_artifact_basenames(shot: dict) -> list:
    """Files this shot's rendered clip/frame is made of, by basename."""
    names = []
    for name in shot.get("_render_files") or []:
        if isinstance(name, str) and name.strip():
            names.append(os.path.basename(name.strip()))
    for key in (*_SHOT_ARTIFACT_URL_KEYS, "image_path"):
        value = (shot.get(key) or "").strip()
        if value:
            names.append(os.path.basename(value.split("?")[0]))
    return [name for name in dict.fromkeys(names) if name]


def forget_shot_artifacts(
    output_dir: str,
    shots: list,
    shot_numbers,
    log: Callable[[str], None] = print,
) -> list:
    """Drop the cached clip and frame of the shots the user wants re-rendered.

    A shot whose text did not change is served from cache, so per-shot
    «перегенерить» is the only way to ask for another take. Besides the files it
    clears the URLs the shot carries, otherwise the copies still sitting in the
    previous job's directory would be picked up as an existing frame.
    """
    wanted = set()
    for number in shot_numbers or []:
        try:
            wanted.add(int(number))
        except (TypeError, ValueError):
            continue
    if not wanted:
        return []

    removed = []
    for index, shot in enumerate(shots or [], start=1):
        if not isinstance(shot, dict):
            continue
        try:
            number = int(shot.get("shot_number") or index)
        except (TypeError, ValueError):
            number = index
        if number not in wanted:
            continue
        for base in _shot_artifact_basenames(shot):
            stem = os.path.splitext(base)[0]
            candidates = (
                base,
                f"{base}.meta.json",
                f"{base}.fal_url.txt",
                f"{base}.prompt.txt",
                f"{base}.review.json",
                f"{base}.review.jpg",
                f"{stem}_base.mp4",
                f"{stem}_base_fal.json",
                f"{stem}_ref.png",
            )
            for name in candidates:
                path = os.path.join(output_dir, name)
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                        removed.append(name)
                except OSError:
                    pass
        for key in (*_SHOT_ARTIFACT_URL_KEYS, "image_path", "_render_files"):
            shot.pop(key, None)
        log(f"[кадры] Кадр {number}: перерисовываю заново.")
    return removed


def forget_shot_voice(
    output_dir: str,
    title_slug: str,
    shot_numbers,
    log: Callable[[str], None] = print,
) -> list:
    """Drop the cached voice piece of the lines the user wants read again.

    A line whose text did not change is served from its cached take, so
    «перезаписать» is the only way to ask this voice for another reading. Only
    the piece is deleted: the builder then re-records that line, its bounds move,
    and the slice check drops the clip that was lip-synced to the old take.
    """
    removed = []
    wanted = set()
    for number in shot_numbers or []:
        try:
            wanted.add(str(int(number)))
        except (TypeError, ValueError):
            continue
    if not wanted:
        return removed

    manifest_path = _voice_manifest_path(output_dir, title_slug)
    manifest = _read_json_file(manifest_path) or {}
    entries = [entry for entry in (manifest.get("shots") or []) if isinstance(entry, dict)]
    matched = set()
    for entry in entries:
        number = str(entry.get("shot_number"))
        if number not in wanted or entry.get("retired"):
            continue
        matched.add(number)
        entry["force_revoice"] = True
        entry["invalidated"] = True
        piece = _manifest_voice_piece_path(output_dir, entry)
        if not piece:
            continue
        basename = os.path.basename(piece)
        # A duplicate line may legitimately share a piece in an imported
        # manifest. Keep the file while another valid entry points at it; the
        # force flag still prevents this shot from borrowing that take again.
        shared = any(
            other is not entry
            and not other.get("invalidated")
            and os.path.basename(str(other.get("piece") or "")) == basename
            for other in entries
        )
        try:
            if os.path.isfile(piece) and not shared:
                os.remove(piece)
            removed.append(basename)
            log(f"[озвучка] Кадр {number}: перезаписываю реплику заново.")
        except OSError:
            pass

    # Legacy jobs have no usable manifest; retain the old numbered fallback.
    for number in sorted(wanted - matched):
        piece = _voice_piece_path(output_dir, title_slug, int(number))
        try:
            if os.path.isfile(piece):
                os.remove(piece)
                removed.append(os.path.basename(piece))
                log(f"[озвучка] Кадр {number}: перезаписываю реплику заново.")
        except OSError:
            pass
    if entries:
        manifest["shots"] = entries
        _write_json_file(manifest_path, manifest)
    return removed


def _attach_shot_previews(
    shots: list,
    clips: list,
    output_dir: str,
    title_slug: str,
    log: Callable[[str], None] = print,
) -> None:
    """Attach `preview_frame_url` / `clip_url` to each shot from generated files.

    Lets the UI show the actual rendered frame of every shot after a video
    render, with no extra generation. Maps by `shot_number` (jump-cut splits copy
    the shot dict, so identity can't be trusted) and extracts one thumbnail per
    shot from its clip. Best-effort: any failure just leaves the shot without a
    preview.
    """
    job_dir = os.path.basename(output_dir.rstrip("/\\"))

    def _url(path: str) -> str:
        return f"/videos/{job_dir}/{os.path.basename(path)}"

    clips_for_number: dict = {}
    for clip in clips:
        members = list(clip.get("shots") or [])
        if clip.get("shot"):
            members.append(clip["shot"])
        for member in members:
            num = member.get("shot_number")
            if num is not None:
                clips_for_number.setdefault(num, []).append(clip)

    for i, shot in enumerate(shots):
        shot_clips = clips_for_number.get(shot.get("shot_number")) or []
        clip = shot_clips[0] if shot_clips else None
        clip_path = (clip or {}).get("path")
        if not (clip_path and os.path.exists(clip_path)):
            continue
        shot["clip_url"] = _url(clip_path)
        # Every file this shot's footage was built from, so a later
        # «перегенерить» knows exactly what to throw away — a long shot split
        # into jump cuts owns several clips, and each has its own reference
        # frame and voiceover slice.
        rendered = []
        for member in shot_clips:
            for key in ("path", "reference_image", "audio_slice"):
                value = member.get(key)
                if value:
                    rendered.append(os.path.basename(value))
        shot["_render_files"] = list(dict.fromkeys(rendered))
        thumb = os.path.join(output_dir, f"{title_slug}_thumb_{shot.get('shot_number', i + 1):02d}.jpg")
        try:
            if not _nonempty(thumb):
                subprocess.run(
                    ["ffmpeg", "-y", "-i", clip_path, "-frames:v", "1", "-q:v", "3", thumb],
                    check=True, capture_output=True,
                )
            if _nonempty(thumb):
                shot["preview_frame_url"] = _url(thumb)
        except Exception as e:
            log(f"  ⚠️ Кадр {shot.get('shot_number', i + 1)}: превью не извлечено ({e}).")


def _existing_shot_frame(shot: dict, output_root: str) -> str:
    """Path of a start frame this shot already has (possibly from an earlier job).

    A storyboard reopened from the gallery carries frames that were paid for in
    the job that rendered the video; their files live on under `output/<job>/`.
    """
    candidates = []
    stored = (shot.get("image_path") or "").strip()
    if stored:
        candidates.append(stored)
    for key in ("local_url", "image_url", "preview_frame_url"):
        url = (shot.get(key) or "").strip()
        if url.startswith("/videos/"):
            candidates.append(os.path.join(output_root, url[len("/videos/"):]))
    for path in candidates:
        if _nonempty(path) and not _looks_blank(path):
            return os.path.normpath(path)
    return ""


def _talking_frames_on_hand(shots: list, output_root: str) -> List[str]:
    """Кадры, которые говорящие шоты уже носят, — в том числе из прошлых папок.

    Из них `_AvatarPlates` узнаёт свои плиты: раскадровку, утверждённую в одном
    прогоне, рендер запускает в своей папке и иначе рисовал бы всё заново.
    """
    seen: List[str] = []
    for shot in shots:
        if _is_broll_shot(shot):
            continue
        frame = _existing_shot_frame(shot, output_root)
        if frame and frame not in seen:
            seen.append(frame)
    return seen


def _generate_storyboard_frames_only(shots, config, output_dir, title_slug, log=print):
    """Generate just the per-shot Flux start frames — no paid Kling video.

    Lets the user preview and approve each shot's composition before committing
    to a render. Frames land in the job dir and are attached to each shot as
    image_path/local_url, so a later video render reuses them as start frames
    (both `_storyboard_avatar_reference_image` and the b-roll path pick them up).
    Set `frames_only_shot` to a shot_number to (re)generate a single shot.
    """
    fal_key = config["fal_key"]
    selected_actor_path = config.get("selected_actor_path") or ""
    selected_face_path = config.get("selected_face_path") or ""
    actor_description = config.get("actor_description") or ""
    only = config.get("frames_only_shot")
    edit_model = _avatar_edit_model(config.get("avatar_edit_model") or "")["id"]
    job_dir = os.path.basename(output_dir.rstrip("/\\"))
    fallback_actor = {"path": ""}

    def _actor_photo():
        if selected_actor_path and os.path.exists(selected_actor_path):
            return selected_actor_path
        if not fallback_actor["path"]:
            path = os.path.join(output_dir, f"{title_slug}_actor.png")
            if not _nonempty(path):
                desc = actor_description or (
                    "a young professional in their late 20s, casual modern outfit, clean background"
                )
                generate_actor_image(desc, fal_key, path)
            fallback_actor["path"] = path
        return fallback_actor["path"]

    def _face_photo():
        return selected_face_path if (selected_face_path and os.path.exists(selected_face_path)) else ""

    output_root = _job_output_root(output_dir)

    # Talking shots share the staged cameras of one set. A frame per shot is both
    # a Flux charge per shot and a new room behind every cut — which is exactly
    # what makes the avatar jump between scenes.
    pinned_set = _pinned_avatar_set(shots)
    talking_order = {}
    for shot in shots:
        if not _is_broll_shot(shot):
            talking_order[id(shot)] = len(talking_order)

    made = 0
    reused = 0
    failed = 0
    # Считаем не нарисованные кадры, а обращения к модели: пустой кадр fal
    # тарифицирует наравне с картинкой, и смета обязана совпадать со счётом.
    # Сюда же складываются отказы редакторов (`blocked`) — из них интерфейс
    # собирает предупреждение с дословным ответом модели.
    billing = {"calls": 0, "blocked": []}
    plates = _AvatarPlates(
        output_dir, title_slug, pinned_set, _actor_photo, fal_key,
        edit_model=edit_model, billing=billing, log=log,
        face_photo=_face_photo,
        set_chosen=_pinned_set_is_chosen(shots),
        sets=_pinned_avatar_sets(shots),
        pinned_plates=config.get("pinned_plates") or {},
        known_frames=_talking_frames_on_hand(shots, output_root),
    )
    # Постановочные кадры ставим по очереди и до вставок: их на весь ролик один-два,
    # они делят и файлы, и фото ведущего, и крупный план дорезается из среднего —
    # то есть один из них ждёт другого по существу, а не из-за кода.
    broll_jobs: list = []
    for shot in shots:
        num = shot.get("shot_number")
        broll = _is_broll_shot(shot)
        # Кадр вставки принадлежит своему шоту: не он — не трогаем. Говорящие
        # проходят всегда, даже когда перерисовывают чужой кадр: их картинка —
        # общая плита, и после «перерисовать» на первом кадре второй обязан
        # показать плиту с нового дубля, а не файл, который только что удалили.
        # Готовая плита при этом ничего не стоит.
        if only is not None and broll and num != only:
            continue
        camera = None
        if broll:
            frame_path = os.path.join(output_dir, f"{title_slug}_frame_{int(num or 0):02d}.png")
        else:
            camera = _avatar_framing_for_shot(shot, talking_order.get(id(shot), 0))
            frame_path = plates.path(camera)
        if only is None:
            # Reopened storyboard: this shot already carries a frame (or a
            # rendered clip) from an earlier job. Drawing it again is a fresh
            # Flux charge for a picture the user already paid for — skip it.
            # Per-shot "перегенерить" still forces a redraw.
            #
            # Говорящие кадры сюда не попадают: их картинка — общая плита камеры,
            # и «уже есть» у них означало «оставить плиту прошлого прогона». Так
            # три кадра на одной камере расходились по трём комнатам. Плита сама
            # знает, что она уже нарисована (и находит себя в чужой папке), так
            # что пройти по ним заново ничего не стоит.
            existing = _existing_shot_frame(shot, output_root)
            if shot.get("clip_url") or (broll and existing):
                if existing:
                    shot.setdefault("preview_frame_url", shot.get("local_url") or "")
                log(f"[кадры] Кадр {num}: уже есть — пропускаю.")
                reused += 1
                continue
        if only is not None and num == only:
            # Explicit per-shot regenerate: drop the cached frame so a new one is drawn.
            if broll:
                for stale in (frame_path, f"{frame_path}.prompt.txt", f"{frame_path}.fal_url.txt"):
                    try:
                        if os.path.exists(stale):
                            os.remove(stale)
                    except OSError:
                        pass
            else:
                plates.forget(camera)
                log(f"[кадры] Кадр {num}: перерисовываю ракурс «{camera.key}» — "
                    "он общий для всех кадров на этой камере.")
        drawn_before = _nonempty(frame_path)
        if drawn_before and not broll:
            log(f"[кадры] Кадр {num}: ракурс «{camera.key}» уже отрисован — переиспользую.")
        if broll:
            # Вставки не делят между собой ни файлов, ни ленивого фото ведущего —
            # значит, их незачем ждать по очереди. Фото резолвим здесь, до пула:
            # `_actor_photo` при первом вызове может дорисовать запасного ведущего,
            # и два потока нарисовали бы (и оплатили) его дважды.
            broll_jobs.append({
                "shot": shot,
                "num": num,
                "frame_path": frame_path,
                "actor_photo": _actor_photo() if _shot_wants_actor(shot) else "",
            })
            continue
        if not drawn_before:
            log(f"[кадры] Генерирую кадр {num} — ракурс «{camera.key}».")
        # Платили или нет — по кассе, а не по тому, лежал ли файл в этой папке:
        # плиту могли принести из папки, где её утвердили, и это бесплатно.
        paid_before = billing["calls"]
        made_path = plates.plate(camera)
        if made_path and _nonempty(made_path):
            _point_shot_at_frame(shot, made_path, job_dir)
            if billing["calls"] == paid_before:
                reused += 1
            else:
                made += 1
        else:
            failed += 1
            log(f"  ⚠️ Кадр {num}: не удалось сгенерировать.")

    if broll_jobs:
        log(f"[кадры] Рисую {len(broll_jobs)} кадр(ов) вставок "
            f"параллельно (до {_FRAME_WORKERS} за раз).")

    def _draw_broll(job: dict) -> dict:
        # Своя касса на кадр: `billing["calls"] += 1` из нескольких потоков теряет
        # обращения, а смета обязана совпадать со счётом. Сливаем после пула.
        own = {"calls": 0, "blocked": []}
        log(f"[кадры] Генерирую кадр {job['num']} — вставка.")
        made_path = _broll_reference_image(
            job["shot"], fal_key, job["frame_path"],
            log=lambda message: log(f"[Кадр {job['num']}] {message.strip()}"),
            actor_photo_path=job["actor_photo"],
            billing=own,
            edit_model=edit_model,
        )
        return {**job, "made_path": made_path, "billing": own}

    if broll_jobs:
        with ThreadPoolExecutor(max_workers=_FRAME_WORKERS) as pool:
            drawn_broll = list(pool.map(_draw_broll, broll_jobs))
        for done in drawn_broll:
            billing["calls"] += done["billing"]["calls"]
            billing["blocked"].extend(done["billing"]["blocked"])
            if done["made_path"] and _nonempty(done["made_path"]):
                _point_shot_at_frame(done["shot"], done["made_path"], job_dir)
                made += 1
            else:
                failed += 1
                log(f"  ⚠️ Кадр {done['num']}: не удалось сгенерировать.")

    log(f"[кадры] Готово: {made} кадр(ов)." + (f" Пропущено готовых: {reused}." if reused else "")
        + (f" Платных обращений к модели: {billing['calls']}." if billing["calls"] != made else ""))
    cost = round(billing["calls"] * 0.05, 2)
    # Один отказ на модель: первый — настоящий (с ответом fal), остальные кадры
    # той же пачки упираются в тот же вердикт по памяти и ничего нового не несут.
    blocked_by_model = {}
    for item in billing.get("blocked", []):
        blocked_by_model.setdefault(item["model"], item)
    return {
        "video_path": "",
        "video_filename": "",
        "frames_only": True,
        # Счётчики, а не только лог: без них джоб завершается «успешно» с нулём
        # кадров, интерфейс молча показывает старую картинку, и пользователь
        # видит «генерация прошла, но ничего не изменилось».
        "frames_made": made,
        "frames_reused": reused,
        "frames_failed": failed,
        # Сколько раз реально заплатили: пустой кадр стоит столько же, сколько картинка.
        "frames_charged": billing["calls"],
        # Кто и почему отказался рисовать — с дословным ответом fal. Интерфейс
        # показывает это модалкой: тихая подмена модели за спиной у юзера была бы
        # тратой его денег на нашу догадку.
        "frames_blocked": list(blocked_by_model.values()),
        "avatar_edit_model": edit_model,
        "avatar_edit_models": [
            {k: m[k] for k in ("id", "title", "vendor", "note")}
            for m in AVATAR_EDIT_MODELS
        ],
        "duration": 0,
        "storyboard_shots": shots,
        "storyboard_generation_mode": (config.get("storyboard_generation_mode") or "sliced_avatar"),
        "cost_estimate": {"reference_frames_flux": cost, "total": cost},
        "quality_warnings": [],
    }


def _storyboard_voice_only_result(
    shots: list,
    output_dir: str,
    title_slug: str,
    audio_path: str,
    voice_manifest: dict,
    generation_mode: str,
    tier: str,
    language: str,
    full_narration: str,
    voiced_text: str,
    tts_provider_used: str,
    tts_model_used: str,
    voice_provenance: dict,
    log: Callable[[str], None] = print,
) -> dict:
    """Hand back the finished voiceover and the shoot it implies — no paid video.

    The voiceover decides everything after it: its length is the video's length,
    its per-shot bounds are where the cuts fall, and a long line is split into
    several avatar clips — each one paid for. Recording it costs cents, so it is
    worth hearing (and re-recording) before that, which is what this returns —
    the master track, each shot's own piece of it, and the clip plan it buys.
    """
    job_dir = os.path.basename(output_dir.rstrip("/\\"))

    def _url(path: str) -> str:
        return f"/videos/{job_dir}/{os.path.basename(path)}" if path and _nonempty(path) else ""

    audio_duration = _get_media_duration(audio_path)

    slices, _skipped = _slices_from_voice_bounds(shots, voice_manifest)
    covered = len(slices) == len(_speech_shots_numbered(shots))

    words = []
    # Расшифровка нужна только там, где по ней ищут границы: длинные реплики
    # режутся по паузам между словами, а без манифеста по ним же раскладываются
    # и сами кадры. В остальных случаях это минуты CPU впустую.
    if not covered or generation_mode == "sliced_avatar":
        try:
            words = transcribe_audio_for_subs(audio_path, language=language)
            if words:
                # Сверяем со всем текстом ролика, а не с перезаписанным куском:
                # расшифровка снята со всей дорожки, и по половине сценария
                # слова легли бы не на свои места, а с ними и разрезы.
                words = _align_asr_words_to_script(words, full_narration or "", log=log)
        except Exception as e:
            log(f"[озвучка] Дорожку не удалось разобрать по словам ({e}) — план съёмки посчитан по долям текста.")

    if not covered:
        slices, _skipped = _align_shots_to_voiceover(shots, words, audio_duration)
    if generation_mode == "sliced_avatar":
        _retime_talking_slices_to_speech(slices, words, audio_path)
        # Тот же добор, что сделает рендер: иначе смета считала бы перебивки по
        # исходным границам, а платили бы по раздвинутым.
        _fill_slices_to_clip_floor(slices, words)
    slices = _split_performance_slices(slices, words)
    # Тот же раскрой, что сделает рендер, но в манифест он не пишется: манифест
    # описывает снятое, а это ещё прогноз — иначе рендер повторил бы разрезы,
    # посчитанные по расшифровке, которая здесь могла и не получиться.
    if generation_mode == "sliced_avatar":
        slices = _split_long_slices(
            slices, words,
            cuts_by_shot={k: v.get("cuts") for k, v in (voice_manifest or {}).items() if v.get("cuts")},
        )

    spans: dict = {}
    for sl in slices:
        key = str(sl["shot"].get("shot_number"))
        span = spans.setdefault(key, {"start": sl["start"], "end": sl["end"], "clips": 0})
        span["start"] = min(span["start"], sl["start"])
        span["end"] = max(span["end"], sl["end"])
        span["clips"] += 1

    numbered = dict((id(shot), number) for shot, number in _speech_shots_numbered(shots))
    voice_shots = []
    for shot in shots:
        number = numbered.get(id(shot))
        span = spans.get(str(shot.get("shot_number"))) or {}
        piece = (
            _voice_piece_for_shot(output_dir, title_slug, voice_manifest, number)
            if number is not None
            else ""
        )
        seconds = round(max(0.0, span.get("end", 0.0) - span.get("start", 0.0)), 2)
        # Кладём на сам кадр: редактор раскадровки читает шоты, и без этого
        # длительность реплики некуда показать рядом с самой репликой.
        shot["voice_url"] = _url(piece)
        # Текст, который реально прочитан: правку реплики после записи иначе
        # видно только по звуку, а редактор молча показывал бы старую длину.
        shot["voice_speech"] = (shot.get("speech") or "").strip()
        shot["voice_start"] = round(span.get("start", 0.0), 3)
        shot["voice_end"] = round(span.get("end", 0.0), 3)
        shot["voice_seconds"] = seconds
        shot["voice_clips"] = span.get("clips", 0)
        voice_shots.append({
            "shot_number": shot.get("shot_number"),
            "speech": (shot.get("speech") or "").strip(),
            "voice_url": shot["voice_url"],
            "start": shot["voice_start"],
            "end": shot["voice_end"],
            "seconds": seconds,
            "clips": shot["voice_clips"],
        })

    talking = [sl for sl in slices if not _is_broll_shot(sl["shot"])]
    broll = [sl for sl in slices if _is_broll_shot(sl["shot"])]
    # И то и другое тарифицируют по снятому клипу, а он не короче пола своей
    # модели — иначе смета обещает полсекунды там, где счёт придёт за три.
    talking_seconds = sum(_billed_avatar_seconds(sl["end"] - sl["start"]) for sl in talking)
    broll_seconds = sum(_billed_broll_seconds(sl["end"] - sl["start"]) for sl in broll)
    forecast: dict = {}
    if generation_mode == "sliced_avatar":
        avatar_tier = tier if tier in KLING_AVATAR_TIERS else "pro"
        forecast[f"sliced_avatar_kling_{avatar_tier}"] = round(
            talking_seconds * kling_avatar_cost_per_second(avatar_tier), 2
        )
        if broll_seconds:
            broll_tier = tier if tier in KLING_V3_STORYBOARD_TIERS else "standard"
            forecast[f"sliced_broll_kling_v3_{broll_tier}"] = round(
                broll_seconds * storyboard_video_cost_per_second(broll_tier), 2
            )
    else:
        forecast[f"storyboard_{storyboard_video_family(tier)}_{tier}"] = round(
            (talking_seconds + broll_seconds) * storyboard_video_cost_per_second(tier), 2
        )
    forecast["total"] = round(sum(forecast.values()), 2)

    # Заплачено ровно за перезаписанные реплики: остальные куски дорожки взяты
    # из кэша и второй раз не тарифицируются.
    tts_cost_key = "voiceover_fal_minimax" if tts_provider_used == "fal_minimax" else "voiceover_elevenlabs"
    tts_cost = round(len(voiced_text or "") * (0.0001 if tts_provider_used == "fal_minimax" else 0.00003), 3)

    warnings = []
    if tts_provider_used == "elevenlabs" and tts_model_used and tts_model_used != "eleven_v3":
        # Ровно та подмена, из-за которой голос звучит «по-дикторски»: v3 не
        # ответил, а v2 читает ровно и не понимает [excited]/[sighs].
        warnings.append(
            f"Озвучка записана резервной моделью {tts_model_used}: eleven_v3 не ответил, "
            "поэтому подача ровнее и звучит более «дикторски»."
        )
    if tts_provider_used == "fal_minimax":
        warnings.append("Озвучка записана резервным движком MiniMax: ElevenLabs не ответил, голос другой.")
    silent = [
        shot.get("shot_number") for shot in shots
        if (shot.get("speech") or "").strip() and not shot.get("voice_seconds")
    ]
    if silent:
        warnings.append(
            "Не попали в дорожку кадры: " + ", ".join(str(n) for n in silent) + "."
        )

    log(
        f"[озвучка] Готово: {audio_duration:.1f} с, кадров с речью {len(spans)}, "
        f"клипов в съёмке {len(slices)} (~{forecast['total']:.2f}$)."
    )
    return {
        "video_path": "",
        "video_filename": "",
        "voice_only": True,
        "duration": round(audio_duration, 2),
        "audio_url": _url(audio_path),
        "voice_shots": voice_shots,
        "voice_clips_planned": len(slices),
        "voice_provider": tts_provider_used,
        **voice_provenance,
        # Что уже потрачено на дубли — и отдельно во что обойдётся съёмка по этой
        # дорожке: смешивать их в одну сумму значит показать счёт за то, чего ещё
        # не было.
        "cost_estimate": {tts_cost_key: tts_cost, "total": tts_cost},
        "video_cost_estimate": forecast,
        "storyboard_shots": shots,
        "storyboard_generation_mode": generation_mode,
        "quality_warnings": warnings,
    }


def generate_storyboard_video(
    script: dict,
    config: dict,
    output_dir: str,
    log: Callable[[str], None] = print,
) -> dict:
    """Generate a storyboard-first short: Kling V3 shots + external voiceover."""
    os.makedirs(output_dir, exist_ok=True)

    fal_key = config["fal_key"]
    video_mode = (config.get("video_mode") or "storyboard_v3_standard").lower()
    tier = storyboard_tier_from_video_mode(video_mode)
    storyboard_label = storyboard_video_label(tier)
    storyboard_family = storyboard_video_family(tier)
    language = config.get("language") or script.get("language", "ru")
    actor_gender = config.get("actor_gender", "female")
    tts_provider = config.get("tts_provider", "auto")
    elevenlabs_key = config.get("elevenlabs_key")
    voice_id = _elevenlabs_voice_for(language, config.get("voice_id"))
    minimax_voice_id = _minimax_voice_for(
        language,
        actor_gender,
        config.get("minimax_voice_id"),
    )

    title_slug = storyboard_title_slug(script.get("title", "storyboard"))
    shots = normalize_storyboard_shots({**script, "language": language})
    if not shots:
        raise ValueError("Storyboard script has no shots")

    # «Что в кадре» is the source of truth for the picture: rebuild the English
    # Kling prompt from the (possibly user-edited) scene before generating, unless
    # the shot's prompt was hand-pinned. No-op on first run / for pinned prompts.
    _rebuild_prompts_from_scene(
        shots,
        config.get("gemini_key"),
        actor_description=config.get("actor_description") or script.get("actor_description") or "",
        log=log,
    )

    # Frames-only: generate the Flux start frames for review, no paid Kling video.
    if config.get("frames_only"):
        return _generate_storyboard_frames_only(shots, config, output_dir, title_slug, log=log)

    # Shots are the source of truth for a storyboard: rebuild the narration from
    # the CURRENT shots so trimming/editing the shot list actually shortens the
    # voiceover (and therefore the video length and cost). A stale script-level
    # `full_narration` from the original AI draft must never override a user who
    # deleted shots — otherwise 3 kept shots still get voiced as the original 7.
    full_narration = " ".join(
        (shot.get("speech") or "").strip() for shot in shots if (shot.get("speech") or "").strip()
    ).strip()
    if not full_narration:
        full_narration = (script.get("full_narration") or "").strip()
    if not full_narration:
        full_narration = " ".join((shot.get("overlay_text") or shot.get("scene") or "").strip() for shot in shots)

    audio_path = os.path.join(output_dir, f"{title_slug}_voice.mp3")
    srt_path = os.path.join(output_dir, f"{title_slug}_subs.ass")
    final_path = os.path.join(output_dir, f"{title_slug}_storyboard_final.mp4")

    log("[1/5] Generating voiceover for storyboard...")
    expected_signature = _tts_signature(full_narration, tts_provider, voice_id, minimax_voice_id, language, actor_gender)
    voice_manifest: dict = {}
    # Текст, за который в этом прогоне реально заплатили: остальное взято из
    # кэша, и показывать его в счёте — врать о списании.
    voiced_text = ""
    if any((shot.get("speech") or "").strip() for shot in shots):
        # Shot by shot, so that editing one line does not throw away the paid
        # clips of the lines around it. Consecutive changed shots still share a
        # single take — the fewer joins, the more natural the delivery.
        voice_result = build_incremental_voiceover(
            shots, output_dir, title_slug,
            provider=tts_provider,
            fal_key=fal_key,
            elevenlabs_key=elevenlabs_key,
            voice_id=voice_id,
            minimax_voice_id=minimax_voice_id,
            language=language,
            actor_gender=actor_gender,
            revoice_all=bool(config.get("revoice_all")),
            log=log,
        )
        audio_path = voice_result["path"]
        # No bounds means the builder fell back to one take for the whole reel;
        # slicing then goes back to deriving boundaries from the transcript.
        if voice_result["bounds"]:
            voice_manifest = read_voice_manifest(output_dir, title_slug)
        tts_provider_used = voice_result["provider"]
        tts_model_used = voice_result.get("model") or ""
        revoiced = set(voice_result.get("changed_shots") or [])
        voiced_text = " ".join(
            (shot.get("speech") or "").strip()
            for shot, number in _speech_shots_numbered(shots) if number in revoiced
        ).strip()
    else:
        # Narration that lives outside the shots (legacy scripts, overlay-only
        # boards) has nothing to cache per shot — one take, as before.
        cached_meta = _read_tts_metadata(audio_path) if _nonempty(audio_path) else {}
        if _nonempty(audio_path) and cached_meta.get("signature") == expected_signature:
            tts_provider_used = cached_meta.get("provider") or tts_provider
            tts_model_used = cached_meta.get("model") or ""
            log("[1/5] Voiceover cached, skipping.")
        else:
            if _nonempty(audio_path):
                log("[1/5] Script or voice changed — regenerating voiceover and audio-derived clips.")
                _purge_voiceover_derived_assets(output_dir, title_slug)
            result = generate_voiceover_with_fallback(
                full_narration,
                audio_path,
                provider=tts_provider,
                fal_key=fal_key,
                elevenlabs_key=elevenlabs_key,
                elevenlabs_voice_id=voice_id,
                minimax_voice_id=minimax_voice_id,
                language=language,
                actor_gender=actor_gender,
                log=log,
            )
            tts_provider_used = result["provider"]
            tts_model_used = result.get("model") or ""
            voiced_text = full_narration
    _write_tts_metadata(audio_path, {
        "signature": expected_signature,
        "provider": tts_provider_used,
        "voice_id": voice_id,
        "model": tts_model_used,
    })
    voice_provenance = _voice_provenance(
        config,
        provider_used=tts_provider_used,
        model_used=tts_model_used,
        elevenlabs_voice_id=voice_id,
        minimax_voice_id=minimax_voice_id,
    )

    voiceover_preparation = (
        already_prepared_voiceover(audio_path) if voice_manifest
        else prepare_voiceover_for_video_generation(audio_path, log=log)
    )
    audio_path = voiceover_preparation["path"]

    generation_mode = (config.get("storyboard_generation_mode") or "per_shot").lower()
    if generation_mode not in ("per_shot", "multi_shot", "sliced_avatar"):
        generation_mode = "per_shot"
    if generation_mode == "multi_shot" and any(
        shot.get("image_url") or shot.get("start_image_url") or shot.get("image_path") or shot.get("local_url")
        for shot in shots
    ):
        generation_mode = "per_shot"
        log("[2/5] Reference frames detected, using per-shot generation for frame control.")
    if generation_mode == "multi_shot" and storyboard_family != "kling_v3":
        generation_mode = "per_shot"
        log(f"[2/5] {storyboard_label} does not support multi-shot payloads here, using per-shot generation.")

    # Length is the voiceover's, always: the final mux is `-shortest` against the
    # master track, so a manual per-shot seconds field never really sets the
    # runtime. Derive each shot's duration from its share of the voiceover (the
    # same word-proportional tiling sliced_avatar uses) so per_shot/multi_shot
    # clips match the audio, cost scales with speech, and no seconds UI is needed.
    if generation_mode in ("per_shot", "multi_shot"):
        try:
            derived_duration = _get_media_duration(audio_path)
            derived_slices, derived_skipped = (
                _slices_from_voice_bounds(shots, voice_manifest) if voice_manifest
                else _align_shots_to_voiceover(shots, [], derived_duration)
            )
            for sl in derived_slices:
                sl["shot"]["start"] = round(sl["start"], 3)
                sl["shot"]["end"] = round(sl["end"], 3)
            for silent_shot in derived_skipped:
                # No speech = no audio share; give it a short default beat.
                silent_shot["start"] = 0
                silent_shot["end"] = 3
        except Exception as e:
            log(f"[2/5] Could not derive shot durations from voiceover ({e}); keeping script timings.")

    # Дальше начинается платное. Озвучка уже готова — отдаём её на прослушивание
    # и останавливаемся: голос выбирается под ролик один раз, и менять его после
    # съёмки — значит переснимать всё, что уже оплачено.
    if config.get("voice_only"):
        return _storyboard_voice_only_result(
            shots,
            output_dir,
            title_slug,
            audio_path,
            voice_manifest,
            generation_mode,
            tier,
            language,
            full_narration,
            voiced_text,
            tts_provider_used,
            tts_model_used,
            voice_provenance,
            log=log,
        )

    spoken_words = []
    clips = []
    # Отказы редакторов кадра во время платного рендера: без них ролик просто
    # выходит с обрезанным фото вместо поставленного кадра, и понять почему —
    # неоткуда. Уходят в quality_warnings, которые интерфейс уже показывает.
    frame_report: dict = {"calls": 0, "blocked": []}
    if generation_mode == "sliced_avatar":
        avatar_tier = tier if tier in KLING_AVATAR_TIERS else "pro"
        broll_tier = tier if tier in KLING_V3_STORYBOARD_TIERS else "standard"
        if avatar_tier != tier:
            log(f"[2/5] Sliced-avatar uses Kling Avatar, switching {storyboard_label} to Kling Avatar v2 Pro.")
        log(
            f"[2/5] Generating sliced-avatar shots (Kling Avatar v2 {avatar_tier} for talking, "
            f"Kling V3 {broll_tier} for b-roll, one master voiceover)..."
        )
        try:
            spoken_words = transcribe_audio_for_subs(audio_path, language=language)
        except Exception as e:
            log(f"  ⚠️ Transcription failed, slicing voiceover proportionally: {e}")
        if spoken_words:
            # Script-text words with ASR timings: exact subtitles, and slice
            # boundaries snap to scripted phrase ends instead of ASR guesses.
            spoken_words = _align_asr_words_to_script(spoken_words, full_narration, log=log)
        clips = generate_sliced_avatar_clips(
            shots,
            audio_path,
            spoken_words,
            fal_key,
            output_dir,
            title_slug,
            tier=avatar_tier,
            actor_description=config.get("actor_description") or script.get("actor_description") or "",
            selected_actor_path=config.get("selected_actor_path") or "",
            selected_face_path=config.get("selected_face_path") or "",
            pinned_plates=config.get("pinned_plates") or {},
            broll_tier=broll_tier,
            broll_image_first=bool(config.get("broll_image_first", True)),
            avatar_image_first=bool(config.get("avatar_image_first", True)),
            voice_manifest=voice_manifest,
            edit_model=_avatar_edit_model(config.get("avatar_edit_model") or "")["id"],
            billing=frame_report,
            log=log,
        )
    elif generation_mode == "multi_shot":
        log(f"[2/5] Generating storyboard with {storyboard_label} ({generation_mode})...")
        shot_chunks = split_storyboard_shots(shots, max_duration=15)
        for index, chunk in enumerate(shot_chunks, start=1):
            clip_path = os.path.join(output_dir, f"{title_slug}_chunk_{index:02d}.mp4")
            # Cache validity is prompt-aware: a bare exists() check here would
            # silently ignore edited prompts on retry.
            if _storyboard_chunk_cache_valid(chunk, clip_path):
                log(f"  Chunk {index} cached.")
            else:
                log(f"  Generating chunk {index}/{len(shot_chunks)} ({len(chunk)} shots)...")
                generate_storyboard_chunk_clip(chunk, fal_key, clip_path, tier=tier)
            clips.append({
                "path": clip_path,
                "duration": sum(_shot_duration(shot) for shot in chunk),
                "shots": chunk,
            })
    else:
        log(f"[2/5] Generating storyboard with {storyboard_label} ({generation_mode})...")
        for index, shot in enumerate(shots, start=1):
            clip_path = os.path.join(output_dir, f"{title_slug}_shot_{index:02d}.mp4")
            # Cache validity is prompt-aware: a bare exists() check here would
            # silently ignore edited prompts on retry.
            if _storyboard_clip_cache_valid(shot, clip_path):
                log(f"  Shot {index} cached.")
            else:
                log(f"  Generating shot {index}/{len(shots)}...")
                generate_storyboard_shot_clip(shot, fal_key, clip_path, tier=tier)
            clips.append({"path": clip_path, "duration": _shot_duration(shot), "shot": shot})

    vision_warnings = []
    reported_editors = set()
    for item in frame_report.get("blocked", []):
        if item["model"] in reported_editors:
            continue
        reported_editors.add(item["model"])
        warning = (
            f"{item['title']} не нарисовал кадр ведущего"
            + (f" — ответ модели: {item['flags']}" if item["flags"] else "")
            + ". Кадры сняты обрезкой исходного фото; выбери другую модель редактора "
              "или другое фото ведущего."
        )
        vision_warnings.append(warning)
        log(f"  ⚠️ {warning}")

    gemini_key = config.get("gemini_key")
    if gemini_key and config.get("clip_vision_qc", True):
        log("[3/5] Vision-проверка клипов (Gemini)...")
        vision_issues = 0
        for clip_index, clip in enumerate(clips, start=1):
            clip_shot = clip.get("shot")
            if not clip_shot:
                continue
            try:
                issues = review_clip_quality(clip["path"], clip_shot, gemini_key, log=log)
            except Exception as e:
                log(f"  ⚠️ Клип {clip_index}: vision-проверка не удалась: {e}")
                continue
            for issue in issues:
                warning = f"Клип {clip_index}: {issue}"
                vision_warnings.append(warning)
                vision_issues += 1
                log(f"  ⚠️ {warning}")
        if not vision_issues:
            log("  ✅ Vision-проверка: дефектов не найдено.")

    log("[3/5] Transcribing voiceover and generating subtitles...")
    if not spoken_words:
        try:
            spoken_words = _align_asr_words_to_script(
                transcribe_audio_for_subs(audio_path, language=language),
                full_narration,
                log=log,
            )
        except Exception as e:
            log(f"  ⚠️ Transcription failed, subtitles limited to overlays: {e}")
    generate_storyboard_ass_subtitles(
        audio_path, shots, srt_path, max_words=1, words=spoken_words or None,
        caption_keywords=script.get("caption_keywords"),
    )

    music_path = None
    if config.get("background_music", True):
        music_path = _pick_background_music(title_slug)
    if music_path:
        log(f"[4/5] Assembling storyboard edit (музыка: {os.path.basename(music_path)})...")
    else:
        log("[4/5] Assembling storyboard edit...")
    composite_storyboard_video(clips, audio_path, srt_path, final_path, music_path=music_path)

    # Surface each shot's rendered frame/clip so the editor can show generated
    # results after a run (no extra generation — pulled from the job's files).
    _attach_shot_previews(shots, clips, output_dir, title_slug, log=log)

    log("[5/5] Storyboard video complete.")

    audio_duration = _get_media_duration(audio_path)
    tts_cost_key = "voiceover_fal_minimax" if tts_provider_used == "fal_minimax" else "voiceover_elevenlabs"
    tts_cost = round(len(full_narration) * (0.0001 if tts_provider_used == "fal_minimax" else 0.00003), 3)
    extra_costs = {}
    if generation_mode == "sliced_avatar":
        avatar_tier = tier if tier in KLING_AVATAR_TIERS else "pro"
        avatar_clips = [c for c in clips if not _is_broll_shot(c.get("shot") or {})]
        broll_clips = [c for c in clips if _is_broll_shot(c.get("shot") or {})]
        # По снятому, а не по задуманному. `clip["duration"]` — это окно в
        # монтаже, куда клип обрежут; модель же считает по тому, что отдала, а
        # отдаёт она всегда не меньше своего пола и округляет вверх. Разница
        # выходила заметная: 16-секундный ролик показывал $2.30 при 9.8 с речи,
        # тогда как на диске лежало 11.5 с говорящих клипов и 12.2 с перебивок.
        avatar_seconds = sum(_billed_clip_seconds(c) for c in avatar_clips)
        broll_seconds = sum(_billed_clip_seconds(c) for c in broll_clips)
        video_cost_key = f"sliced_avatar_kling_{avatar_tier}"
        video_cost = round(avatar_seconds * kling_avatar_cost_per_second(avatar_tier), 2)
        if broll_seconds:
            broll_tier = tier if tier in KLING_V3_STORYBOARD_TIERS else "standard"
            extra_costs[f"sliced_broll_kling_v3_{broll_tier}"] = round(
                broll_seconds * storyboard_video_cost_per_second(broll_tier), 2
            )
        # Кадры считаем по кассе, а не по числу клипов: плита, принесённая из
        # предпросмотра, ничего не стоит, и строка «reference frames» за неё
        # выставляла деньги, которых этот прогон не тратил.
        if frame_report.get("calls"):
            extra_costs["reference_frames_flux"] = round(frame_report["calls"] * 0.05, 2)
    else:
        video_seconds = sum(_shot_duration(shot) for shot in shots)
        video_cost_key = f"storyboard_{storyboard_family}_{tier}"
        video_cost = round(video_seconds * storyboard_video_cost_per_second(tier), 2)
    cost = {
        tts_cost_key: tts_cost,
        video_cost_key: video_cost,
        **extra_costs,
        "ffmpeg_compositing": 0.00,
    }
    cost["total"] = round(sum(cost.values()), 2)

    return {
        "video_path": final_path,
        "video_filename": os.path.basename(final_path),
        "srt_path": srt_path,
        "actor_image": "",
        # Длина ролика, а не озвучки: говорящие дубли идут так, как их вернула
        # модель, а картинки она отдаёт немного больше, чем звука.
        "duration": round(_get_media_duration(final_path) or audio_duration, 2),
        "cost_estimate": cost,
        "tts_provider": tts_provider_used,
        "tts_model": tts_model_used,
        **voice_provenance,
        "broll_mode": "storyboard",
        "head_source": "storyboard",
        "head_template_id": None,
        "lipsync_model": None,
        "quality_status": "storyboard",
        "quality_warnings": vision_warnings,
        "talking_head_quality": {},
        "storyboard_shots": shots,
        "storyboard_generation_mode": generation_mode,
        "voiceover_preparation": voiceover_preparation,
    }


def generate_full_video(
    script: dict,
    config: dict,
    output_dir: str,
    log: Callable[[str], None] = print,
) -> dict:
    """
    Full AI Shorts video generation pipeline.

    Args:
        script: A single script object from generate_scripts()
        config: {
            "fal_key": str,
            "elevenlabs_key": str (optional when tts_provider is fal_minimax),
            "voice_id": str (optional ElevenLabs voice),
            "tts_provider": str (optional: auto, elevenlabs, fal_minimax),
            "minimax_voice_id": str (optional),
            "language": str (optional),
            "actor_gender": str (optional),
            "actor_description": str (optional, overrides script),
        }
        output_dir: Directory to write output files
        log: Callback for progress logging

    Returns:
        {"video_path": str, "srt_path": str, "actor_image": str, "cost_estimate": dict}
    """
    os.makedirs(output_dir, exist_ok=True)

    if is_storyboard_script(script) or (config.get("video_mode") or "").lower() in STORYBOARD_VIDEO_MODES:
        return generate_storyboard_video(script, config, output_dir, log)

    # Прослушивание озвучки останавливает именно раскадровочный пайплайн. Здесь
    # такой остановки нет, а дальше по коду — платная генерация: молча снять
    # ролик вместо запрошенного дубля значит выставить счёт за то, чего не просили.
    if config.get("voice_only"):
        raise ValueError("Предварительная озвучка доступна только для раскадровки (storyboard).")

    fal_key = config["fal_key"]
    elevenlabs_key = config.get("elevenlabs_key")
    tts_provider = config.get("tts_provider", "auto")
    language = config.get("language") or script.get("language", "en")
    voice_id = _elevenlabs_voice_for(language, config.get("voice_id"))
    actor_gender = config.get("actor_gender", "female")
    minimax_voice_id = _minimax_voice_for(
        language,
        actor_gender,
        config.get("minimax_voice_id"),
    )
    actor_desc = config.get("actor_description") or script.get("actor_description", "a young professional in their late 20s, wearing a casual modern outfit, clean background")
    reusable_head_path = config.get("reusable_head_path")
    reusable_head_poster_path = config.get("reusable_head_poster_path")
    reusable_head_template_id = config.get("reusable_head_template_id")
    reusable_lipsync_model = config.get("reusable_lipsync_model") or "sync-3"
    use_reusable_head = bool(reusable_head_path)

    title_slug = re.sub(r"[^a-z0-9]+", "_", script.get("title", "video").lower())[:30]

    # Paths
    actor_img = os.path.join(output_dir, f"{title_slug}_actor.png")
    audio_path = os.path.join(output_dir, f"{title_slug}_voice.mp3")
    talking_head = os.path.join(output_dir, f"{title_slug}_head.mp4")
    srt_path = os.path.join(output_dir, f"{title_slug}_subs.ass")
    final_path = os.path.join(output_dir, f"{title_slug}_final.mp4")

    full_narration = script.get("full_narration", "")
    if not full_narration:
        full_narration = " ".join(
            seg.get("narration", "") for seg in script.get("segments", [])
        )

    def _exists(path):
        return os.path.exists(path) and os.path.getsize(path) > 0

    def _remove_if_exists(path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    tts_cache_signature = _tts_signature(
        full_narration,
        tts_provider,
        voice_id,
        minimax_voice_id,
        language,
        actor_gender,
    )
    tts_metadata = _read_tts_metadata(audio_path)
    if _exists(audio_path) and tts_metadata.get("signature") != tts_cache_signature:
        log("[1/6] TTS settings changed; regenerating voice-dependent assets.")
        for stale_path in (
            audio_path,
            f"{audio_path}.meta.json",
            f"{audio_path}.fal_url.txt",
            prepared_voiceover_path(audio_path),
            f"{prepared_voiceover_path(audio_path)}.meta.json",
            f"{prepared_voiceover_path(audio_path)}.fal_url.txt",
            talking_head,
            f"{talking_head}.fal_url.txt",
            talking_head_quality_path(talking_head),
            srt_path,
            final_path,
        ):
            _remove_if_exists(stale_path)
        tts_metadata = {}

    tts_provider_used = tts_metadata.get("provider") or tts_provider
    tts_model_used = tts_metadata.get("model") or ""

    if use_reusable_head and reusable_head_poster_path and os.path.exists(reusable_head_poster_path) and not _exists(actor_img):
        import shutil
        shutil.copy2(reusable_head_poster_path, actor_img)
        log("[1/6] Using poster from saved talking-head template.")

    # ── Step 1 & 2: Generate actor image + voiceover in parallel ──
    # If user pre-selected an actor image, copy it
    selected_actor = config.get("selected_actor_path")
    if not use_reusable_head and selected_actor and os.path.exists(selected_actor) and not _exists(actor_img):
        import shutil
        shutil.copy2(selected_actor, actor_img)
        log("[1/6] Using pre-selected actor image.")

    need_img = not _exists(actor_img)
    need_voice = not _exists(audio_path)

    if need_img or need_voice:
        tasks = []
        if need_img:
            tasks.append("actor image")
        if need_voice:
            tasks.append("voiceover")
        log(f"[1/6] Generating {' + '.join(tasks)} (parallel)...")

        with ThreadPoolExecutor(max_workers=2) as executor:
            future_img = executor.submit(generate_actor_image, actor_desc, fal_key, actor_img) if need_img else None
            future_voice = executor.submit(
                generate_voiceover_with_fallback,
                full_narration,
                audio_path,
                provider=tts_provider,
                fal_key=fal_key,
                elevenlabs_key=elevenlabs_key,
                elevenlabs_voice_id=voice_id,
                minimax_voice_id=minimax_voice_id,
                language=language,
                actor_gender=actor_gender,
                log=log,
            ) if need_voice else None

            if future_img:
                actor_img = future_img.result()
            if future_voice:
                voice_result = future_voice.result()
                audio_path = voice_result["path"]
                tts_provider_used = voice_result["provider"]
                tts_model_used = voice_result.get("model") or ""
                _write_tts_metadata(audio_path, {
                    "signature": tts_cache_signature,
                    "provider": voice_result["provider"],
                    "voice_id": voice_result["voice_id"],
                    "model": tts_model_used,
                })

        log("[2/6] Actor image and voiceover ready.")
    else:
        log("[1/6] Actor image and voiceover cached, skipping.")
        log("[2/6] ✅ Using cached assets.")

    # ── Step 3: Generate talking head ──
    voiceover_preparation = prepare_voiceover_for_video_generation(audio_path, log=log)
    source_audio_path = audio_path
    audio_path = voiceover_preparation["path"]

    video_mode = (config.get("video_mode") or "standard").lower()
    if video_mode not in ("lowcost", "standard", "premium"):
        video_mode = "standard"

    talking_head_meta_path = f"{talking_head}.meta.json"

    def _read_talking_head_meta():
        try:
            with open(talking_head_meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            hailuo_cache = talking_head.replace(".mp4", "_hailuo_cache.mp4")
            if _exists(hailuo_cache):
                return {"video_mode": "lowcost", "head_source": "generated"}
            return {"video_mode": "standard", "head_source": "generated"}

    def _write_talking_head_meta(meta: dict = None):
        payload = {"video_mode": video_mode, "head_source": "generated"}
        if not use_reusable_head and video_mode in ("standard", "premium"):
            payload["kling_input"] = "vertical_9x16_v1"
        payload["voiceover_audio_path"] = audio_path
        payload["source_audio_path"] = source_audio_path
        payload["voiceover_preparation_status"] = voiceover_preparation.get("status", "")
        if meta:
            payload.update(meta)
        with open(talking_head_meta_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    expected_head_meta = {
        "video_mode": "reused_head" if use_reusable_head else video_mode,
        "head_source": "template" if use_reusable_head else "generated",
        "reusable_head_path": reusable_head_path or "",
        "reusable_lipsync_model": reusable_lipsync_model if use_reusable_head else "",
        "kling_input": "vertical_9x16_v1" if (not use_reusable_head and video_mode in ("standard", "premium")) else "",
        "voiceover_audio_path": audio_path,
        "source_audio_path": source_audio_path,
        "voiceover_preparation_status": voiceover_preparation.get("status", ""),
    }
    current_head_meta = _read_talking_head_meta()
    if _exists(talking_head) and (
        current_head_meta.get("video_mode") != expected_head_meta["video_mode"]
        or current_head_meta.get("head_source") != expected_head_meta["head_source"]
        or current_head_meta.get("reusable_head_path", "") != expected_head_meta["reusable_head_path"]
        or current_head_meta.get("reusable_lipsync_model", "") != expected_head_meta["reusable_lipsync_model"]
        or current_head_meta.get("kling_input", "") != expected_head_meta["kling_input"]
        or current_head_meta.get("voiceover_audio_path", "") != expected_head_meta["voiceover_audio_path"]
        or current_head_meta.get("source_audio_path", "") != expected_head_meta["source_audio_path"]
        or current_head_meta.get("voiceover_preparation_status", "") != expected_head_meta["voiceover_preparation_status"]
    ):
        log("[3/6] Talking-head source changed; regenerating voice-driven talking head.")
        for stale_path in (
            talking_head,
            f"{talking_head}.fal_url.txt",
            talking_head_meta_path,
            talking_head_quality_path(talking_head),
            srt_path,
            final_path,
        ):
            _remove_if_exists(stale_path)
    if not _exists(talking_head):
        if use_reusable_head:
            if not os.path.exists(reusable_head_path):
                raise FileNotFoundError(f"Reusable talking-head template not found: {reusable_head_path}")
            log(f"[3/6] Reusing saved talking-head template via {reusable_lipsync_model} lipsync...")
            talking_head = generate_sync_lipsync_video(
                reusable_head_path,
                audio_path,
                fal_key,
                talking_head,
                model=reusable_lipsync_model,
                sync_mode="cut_off",
            )
            _write_talking_head_meta(expected_head_meta)
        elif video_mode == "lowcost":
            log("[3/6] Generating talking head (Low Cost: Hailuo + VEED Lipsync)... This can take 2-20 minutes.")
            talking_head = generate_talking_head_lowcost(actor_img, audio_path, fal_key, talking_head)
            _write_talking_head_meta()
        elif video_mode == "premium":
            log("[3/6] Generating talking head video (Kling Avatar v2 Pro)... This can take 2-20 minutes.")
            talking_head = generate_talking_head(actor_img, audio_path, fal_key, talking_head, tier="pro")
            _write_talking_head_meta()
        else:
            video_mode = "standard"
            log("[3/6] Generating talking head video (Kling Avatar v2 Standard)... This can take 2-15 minutes.")
            talking_head = generate_talking_head(actor_img, audio_path, fal_key, talking_head, tier="standard")
            _write_talking_head_meta()
        log("[3/6] Talking head ready.")
    else:
        log("[3/6] ✅ Talking head cached, skipping.")

    # ── Step 4: Generate b-roll clips ──
    talking_head_quality = _read_json_file(talking_head_quality_path(talking_head))
    if not talking_head_quality:
        talking_head_quality = inspect_talking_head_quality(talking_head, audio_path)
        _write_json_file(talking_head_quality_path(talking_head), talking_head_quality)

    quality_warnings = talking_head_quality.get("warnings") or []
    if talking_head_quality.get("status") != "ok":
        if not quality_warnings:
            quality_warnings = ["Talking-head stream durations need manual review before publishing."]
        for warning in quality_warnings:
            log(f"[3/6] Quality warning: {warning}")

    broll_mode = (config.get("broll_mode") or "mockup").lower()
    if broll_mode not in ("off", "mockup", "ai"):
        broll_mode = "mockup"

    broll_segments = []
    if broll_mode != "off":
        broll_segments = [
            seg for seg in script.get("segments", [])
            if seg.get("broll_prompt") and seg.get("visual") == "broll"
        ]

    broll_clips = []
    if broll_segments:
        # Check which b-roll clips need generating
        broll_to_generate = []
        broll_suffix = "mockup" if broll_mode == "mockup" else "ai"
        for i, seg in enumerate(broll_segments):
            broll_path = os.path.join(output_dir, f"{title_slug}_broll_{broll_suffix}_{i}.mp4")
            if _exists(broll_path):
                broll_clips.append({
                    "path": broll_path,
                    "start": seg["start"],
                    "end": seg["end"],
                })
                log(f"  ✅ B-roll {i} cached, skipping.")
            else:
                broll_to_generate.append((i, seg, broll_path))

        if broll_to_generate:
            mode_label = "product mockup" if broll_mode == "mockup" else "AI image"
            log(f"[4/6] Generating {len(broll_to_generate)} {mode_label} b-roll clips...")
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = {}
                for i, seg, broll_path in broll_to_generate:
                    if broll_mode == "mockup":
                        future = executor.submit(
                            generate_product_broll, seg, {**script, "language": language}, broll_path
                        )
                    else:
                        future = executor.submit(
                            generate_broll, seg["broll_prompt"], fal_key, broll_path
                        )
                    futures[future] = {"seg": seg, "path": broll_path}

                for future in as_completed(futures):
                    info = futures[future]
                    try:
                        path = future.result()
                        broll_clips.append({
                            "path": path,
                            "start": info["seg"]["start"],
                            "end": info["seg"]["end"],
                        })
                        log(f"  ✅ B-roll clip ready: {os.path.basename(path)}")
                    except Exception as e:
                        log(f"  ⚠️ B-roll failed (skipping): {e}")
        else:
            log("[4/6] ✅ All b-roll cached, skipping.")
    elif broll_mode == "off":
        log("[4/6] B-roll disabled, using talking head only.")
    else:
        log("[4/6] No b-roll segments in script, skipping.")

    # ── Step 5: Generate subtitles (script text on ASR timings) ──
    log("[5/6] Transcribing audio and generating TikTok-style subtitles...")
    try:
        spoken_words = transcribe_audio_for_subs(audio_path, language=language)
    except Exception as e:
        log(f"  ⚠️ Transcription failed, subtitles empty and jump-cuts fall back to fixed grid: {e}")
        spoken_words = []
    if spoken_words:
        spoken_words = _align_asr_words_to_script(spoken_words, full_narration, log=log)
    generate_tiktok_subs(audio_path, srt_path, max_words=1, words=spoken_words)

    # ── Step 6: Composite final video ──
    log("[6/6] Compositing final video with FFmpeg...")
    hook_text = script.get("hook_text", "")
    punch_in_cuts = bool(config.get("punch_in_cuts", True))
    music_path = _pick_background_music(title_slug) if config.get("background_music", True) else None
    if music_path:
        log(f"  Фоновая музыка: {os.path.basename(music_path)}")
    composite_video(
        talking_head,
        broll_clips,
        srt_path,
        hook_text,
        final_path,
        jump_cut_words=spoken_words,
        punch_in=punch_in_cuts,
        music_path=music_path,
    )

    log("🎉 Video generation complete!")

    # Cost estimate
    audio_duration = _get_media_duration(audio_path)
    tts_cost_key = "voiceover_fal_minimax" if tts_provider_used == "fal_minimax" else "voiceover_elevenlabs"
    tts_cost = round(len(full_narration) * (0.0001 if tts_provider_used == "fal_minimax" else 0.00003), 3)

    actor_cost_key = "actor_image_reused" if (selected_actor or use_reusable_head) else "actor_image_flux"
    actor_cost = 0.00 if (selected_actor or use_reusable_head) else 0.05

    if use_reusable_head:
        cost = {
            actor_cost_key: actor_cost,
            tts_cost_key: tts_cost,
            "talking_head_reuse_lipsync": estimate_sync_lipsync_cost(reusable_lipsync_model, audio_duration) or 0.00,
            "ffmpeg_compositing": 0.00,
        }
    elif video_mode == "lowcost":
        cost = {
            actor_cost_key: actor_cost,
            tts_cost_key: tts_cost,
            "hailuo_img2video": 0.19,
            "veed_lipsync": 0.20,
            "ffmpeg_compositing": 0.00,
        }
    else:
        kling_tier = "pro" if video_mode == "premium" else "standard"
        kling_attempts = max(1, int(talking_head_quality.get("paid_attempts") or 1))
        cost = {
            actor_cost_key: actor_cost,
            tts_cost_key: tts_cost,
            f"talking_head_kling_{kling_tier}": round(
                audio_duration * kling_avatar_cost_per_second(kling_tier) * kling_attempts,
                2,
            ),
            "ffmpeg_compositing": 0.00,
        }
    if broll_mode == "ai":
        cost["broll_flux"] = round(len(broll_clips) * 0.05, 2)
    elif broll_mode == "mockup":
        cost["broll_mockups"] = 0.00
    else:
        cost["broll_disabled"] = 0.00
    cost["total"] = round(sum(cost.values()), 2)
    voice_provenance = _voice_provenance(
        config,
        provider_used=tts_provider_used,
        model_used=tts_model_used,
        elevenlabs_voice_id=voice_id,
        minimax_voice_id=minimax_voice_id,
    )

    return {
        "video_path": final_path,
        "video_filename": os.path.basename(final_path),
        "srt_path": srt_path,
        "actor_image": actor_img,
        "duration": audio_duration,
        "cost_estimate": cost,
        "tts_provider": tts_provider_used,
        "tts_model": tts_model_used,
        **voice_provenance,
        "broll_mode": broll_mode,
        "head_source": "template" if use_reusable_head else "generated",
        "head_template_id": reusable_head_template_id,
        "lipsync_model": reusable_lipsync_model if use_reusable_head else None,
        "quality_status": talking_head_quality.get("status", "unknown"),
        "quality_warnings": quality_warnings,
        "talking_head_quality": talking_head_quality,
        "voiceover_preparation": voiceover_preparation,
    }
