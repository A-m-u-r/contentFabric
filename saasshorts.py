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
import httpx
import numpy as np
import textwrap
from urllib.parse import urljoin
from typing import Optional, List, Dict, Callable, Any
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

GEMINI_FAST_TEXT_MODEL_KEYS = {"fast", "flash", "default"}
GEMINI_PRO_TEXT_MODEL_KEYS = {"pro", "quality", "power"}


class GeminiTemporaryError(Exception):
    """Raised when Gemini is temporarily unavailable after retry/fallback attempts."""


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


# ═══════════════════════════════════════════════════════════════════════
# Phase 1: Website Scraping, Web Research & Analysis
# ═══════════════════════════════════════════════════════════════════════

def research_saas_online(url: str, gemini_key: str, text_model: Optional[str] = None) -> dict:
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

    response = _generate_gemini_content(
        client,
        contents=[prompt],
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
        model_chain=gemini_grounding_model_chain(text_model),
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

    response = _generate_gemini_content(
        client,
        contents=[prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
        text_model=text_model,
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


def _finalize_generated_script(script: dict) -> dict:
    """Replace unreliable generated metadata with narration-derived values."""
    narration = _script_spoken_text(script)
    script["full_narration"] = narration
    script["duration_seconds"] = _estimate_speech_duration(narration)
    script["duration_source"] = "narration_estimate"
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
        shot["generation_prompt"] = _build_storyboard_generation_prompt({
            **shot,
            "generation_prompt": generation_prompt,
        })
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
        raise Exception(
            f"Gemini returned a broken {label} answer twice in a row. Please try generating again."
        )
    if note:
        print(f"[SaaSShorts] {note} - kept {len(scripts)}/{num_scripts} {label}(s).")
    return scripts


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
) -> list:
    """Generate video scripts based on product/business analysis."""
    from google import genai
    from google.genai import types

    lang_name = {"es": "Spanish", "ru": "Russian"}.get(language, "English")
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
    "style": "{style}",
    "duration_seconds": 18,
    "target_platform": "instagram",
    "hook_text": "2-6 word overlay hook",
    "shots": [
      {{
        "shot_number": 1,
        "start": 0,
        "end": 3,
        "role": "hook",
        "scene": "Where the shot happens and what we see, written in {lang_name}",
        "camera": "shot type and camera movement, written in {lang_name}",
        "actor_action": "what the actor does, written in {lang_name}",
        "transition": "cut",
        "speech": "Exact line the actor says",
        "emotion": "excited",
        "overlay_text": "Short text on screen",
        "visual_type": "talking",
        "actor_in_frame": false,
        "generation_prompt": "English Kling V3 prompt: vertical 9:16 realistic social video, same woman, scene, action, camera, lighting"
      }}
    ],
    "full_narration": "All shot speech joined exactly",
    "caption_keywords": ["2-4 emotionally loaded words from the narration, in the script language, for subtitle color-accents"],
    "actor_description": "English physical description only",
    "hashtags": ["#reels"],
    "caption": "Suggested caption"
  }}
]

RULES:
- One shot = one short beat of about 3 seconds (5 at the absolute limit). Generate as many shots as the script needs so NO shot runs long: a ~30-second video needs about 8-10 shots, a ~20-second one about 6-7. Never compress a long script into few long shots.
- Every shot must be visually distinct from its neighbours (new scene, angle or subject) — the point of many short shots is variety, not the same framing repeated.
- Use visual variety: close-up, kitchen/lifestyle, exercise/home, product close-up, final CTA.
- Do NOT rely only on talking head. Use the actor as a consistent character across shots.
- visual_type per shot: "talking" = the actor speaks to camera, lips visible; "broll" = an insert while the voiceover keeps playing. Every B-roll scene must be tied to that shot's exact speech: literally demonstrate the claim or use one immediately understandable visual analogy. A faceless person is allowed when the concept needs human action (back view, cropped body/hands, silhouette or non-identifiable profile); never request an identifiable face without an actor reference. The first shot (hook) and the last shot (cta) MUST be "talking". Make 1-2 middle shots "broll" for visual dynamics.
- actor_in_frame per shot: true ONLY when a "broll" shot shows the SAME person who speaks in the talking shots (seen from behind, over the shoulder, her hands, her silhouette), false when the insert shows objects, food, an interior or anybody else. It is the difference between our presenter walking into her own kitchen and a random stranger appearing mid-reel — say it explicitly, we cannot guess it from the scene text. Always false for "talking" shots.
- Each shot MUST include role, actor_action, camera, overlay_text, speech, transition, and generation_prompt.
- Each shot MUST include emotion — one of: excited, warm, confident, calm, urgent, playful. Vary it across shots to follow the narrative arc.
- role must be one of: hook, problem, explanation, solution, proof, cta.
- transition should be "cut" or "smooth_0.3s".
- speech, overlay_text, scene, camera and actor_action must be in {lang_name} — the user reads them in the app UI.
- generation_prompt MUST be in English and MUST say: vertical 9:16, realistic phone video, same actor/character, natural light. It must fully describe the scene, action and camera on its own — the {lang_name} fields are NOT passed to the video model. Write it as a plain description of what IS in frame: no "no text"/"no watermark"/"never show" clauses, those are sent to the model in a separate negative field and inside the description they only make the model draw exactly that. For B-roll, pick subjects with no identifiable face and nothing written on them; a faceless human action is allowed when the exact spoken claim needs it.
- Screens and text props are forbidden in every shot: any phone/tablet/laptop screen must be off, turned away from camera, or out of focus; never show readable UI, documents, checklists or labels — video models render text as garbage glyphs.
- Never request written text of ANY kind inside a shot: no labels, markings, signs, numbers, dates, stickers or captions on objects (a scene like "photo marked '20 years'" is forbidden). Express every comparison purely visually: size, amount, color, position, before/after composition.
- In "broll" shots avoid objects with digital displays entirely (kitchen scales with screens, phones, smartwatches, monitors): the display will render as garbage glyphs. Do not use generic wellness stock filler such as avocado, salad, measuring tape, yoga mats, supplements, scales or food prep unless that exact spoken line is about it. Use one clear subject and action grounded in the claim.
- In "talking" shots the actor holds a steady selfie pose: only subtle facial expressions and small head movement. NO exercising, walking, turning away, drinking, standing up or big hand/arm gestures — motion breaks lip-sync.
- Each shot's speech is ONE short sentence of about 8-10 words (~3-4 seconds spoken), 11 words HARD max — a shot must NEVER carry more than 5 seconds of speech (spoken Russian runs ~2.3 words/sec, so 12+ words already overflows 5s). If the script has more to say, add another shot (more, shorter shots are fine); never grow one shot's speech, because any shot over 5 seconds gets chopped into jump-cut takes and the shot count stops matching the clips produced.
- A reel is ~20-25 seconds, so aim for roughly 5-7 shots and keep every shot at or under 5 seconds of speech; prefer more short shots over fewer long ones.
- Do not ask Kling to generate Russian audio. The app adds Russian voiceover later.
- Keep marketing copy punchy. If the user provided exact topic wording, preserve it.
- Actor gender: {actor_gender}. actor_description must describe a {actor_gender} person in English.
- Avoid laptops, monitors, headset, microphones, studio AI background unless the product explicitly needs them.
"""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=32768,
        )
        scripts = _request_gemini_script_batch(
            lambda: _generate_gemini_content(
                client,
                contents=[prompt],
                config=config,
                text_model=text_model,
            ),
            num_scripts=num_scripts,
            require_shots=True,  # a script without shots is nothing to storyboard
            label="storyboard script",
            batch_validator=lambda batch: _validate_script_batch_hooks(batch, supplied_hook=supplied_hook),
        )

        for script in scripts:
            script["format"] = "storyboard_v3"
            script["shots"] = normalize_storyboard_shots(script)
            # The AI writes scene and generation_prompt together, so the prompt
            # matches this scene: stamp it as the baseline. Later, if the user
            # edits «Что в кадре», the prompt is rebuilt from the new scene.
            for shot in script["shots"]:
                shot["_prompt_source_scene"] = (shot.get("scene") or "").strip()
            _finalize_generated_script(script)
        refine_storyboard_broll_alignment(
            scripts,
            gemini_key,
            text_model=text_model,
            language=language,
        )
        print(f"[SaaSShorts] Generated {len(scripts)} storyboard scripts")
        return scripts

    prompt = f"""You are a viral short-form video scriptwriter for TikTok/Instagram Reels.
Generate {num_scripts} video scripts to promote this product/business.
{lang_instructions}
{topic_instructions}
{hook_instructions}
PRODUCT ANALYSIS:
{json.dumps(analysis, indent=2)}

STYLE: {style_guide.get(style, style_guide['ugc'])}

Each script MUST be 18-22 seconds total. NEVER longer than 22 seconds.

YOU MUST USE EXACTLY THIS 5-SEGMENT STRUCTURE. NO EXCEPTIONS:
1. HOOK (0-4s): type="hook", visual="actor_talking", broll_prompt=null — Avatar says a punchy hook.
2. B-ROLL 1 (4-8s): type="problem", visual="broll", broll_prompt="..." (REQUIRED) — Visual of the problem.
3. BODY (8-14s): type="solution", visual="actor_talking", broll_prompt=null — Avatar presents the solution.
4. B-ROLL 2 (14-18s): type="demo", visual="broll", broll_prompt="..." (REQUIRED) — Visual of the product.
5. CTA (18-22s): type="cta", visual="actor_talking", broll_prompt=null — Avatar says CTA with link in bio.

CRITICAL — READ CAREFULLY:
- EXACTLY 5 segments. Not 3, not 4, not 6. FIVE.
- Segments 2 and 4 MUST have visual="broll" and a non-null broll_prompt string.
- Segments 1, 3, 5 MUST have visual="actor_talking" and broll_prompt=null.
- duration_seconds MUST be between 18 and 22.
- full_narration = all narration text joined together.

Return a JSON array:
[
    {{
        "title": "Short internal title",
        "hook_type": "result_first",
        "style": "{style}",
        "duration_seconds": 21,
        "target_platform": "tiktok",
        "hook_text": "Hook overlay text (2-5 words max)",
        "segments": [
            {{
                "type": "hook",
                "start": 0,
                "end": 4,
                "narration": "Punchy hook the actor says",
                "visual": "actor_talking",
                "broll_prompt": null,
                "emotion": "excited",
                "subtitle_text": "Hook phrase"
            }},
            {{
                "type": "problem",
                "start": 4,
                "end": 8,
                "narration": "Voiceover describing the pain point",
                "visual": "broll",
                "broll_prompt": "REQUIRED: visual of the problem relevant to the product, e.g. realistic everyday close-up of objects/food/hands showing the pain point. No people, no faces. No readable screens or text.",
                "emotion": "frustrated",
                "subtitle_text": "Pain phrase",
                "bullets": ["2-3 short punchy words naming the pain, in the script language"]
            }},
            {{
                "type": "solution",
                "start": 8,
                "end": 14,
                "narration": "Actor introduces the product naturally",
                "visual": "actor_talking",
                "broll_prompt": null,
                "emotion": "confident",
                "subtitle_text": "Solution phrase"
            }},
            {{
                "type": "demo",
                "start": 14,
                "end": 18,
                "narration": "Voiceover showing the product in action",
                "visual": "broll",
                "broll_prompt": "REQUIRED: visual of the product/result, e.g. real-world result or product in use, close-up of objects/hands. No people, no faces. No readable screens, UI or text.",
                "emotion": "excited",
                "subtitle_text": "Result phrase",
                "bullets": ["2-3 short benefit words, in the script language"]
            }},
            {{
                "type": "cta",
                "start": 18,
                "end": 21,
                "narration": "Short CTA mentioning link in bio",
                "visual": "actor_talking",
                "broll_prompt": null,
                "emotion": "confident",
                "subtitle_text": "Link in bio"
            }}
        ],
        "full_narration": "ALL segment narration joined in timeline order",
        "actor_description": "Specific person description: age, gender, ethnicity, hair style, clothing. Casual everyday look.",
        "hashtags": ["#reels", "#product", "#ugc"],
        "caption": "Suggested Instagram/TikTok caption"
    }}
]

RULES:
- EXACTLY 5 segments in order: actor, broll, actor, broll, actor
- EXACTLY 2 broll segments with detailed broll_prompt (NOT null)
- full_narration = ALL segment narration joined in timeline order, including b-roll voiceover lines.
- Total duration MUST be 18-22 seconds, never more
- Keep narrations punchy, conversational, with contractions
- Actor descriptions: casual, real-person look (NOT model/influencer)
- B-roll prompts: cinematic, specific, detailed visual descriptions
- Each script should use a different pain point / angle
- Vary actor look (hair color/style, outfit, age within range) across scripts
- CTA MUST be natural for the selected language. For English/Spanish, mention "link in bio" / "enlace en la bio". For Russian, use a DM CTA if the product context suggests it, e.g. "Напиши НЕДЕЛЯ — пришлю чеклист", otherwise use "ссылка в профиле".
- Write ALL text in {lang_name}
- Actor gender: {actor_gender}. ALL actor_description fields MUST describe a {actor_gender} person.
- IMPORTANT: actor_description MUST ALWAYS be in ENGLISH regardless of script language. Only describe physical appearance: age, gender, ethnicity, hair, clothing. NO actions, NO background, NO scene description.
- Actors must look European, attractive but natural, trustworthy premium wellness / UGC creator vibe. Vary across: blonde, brunette, redhead. Ages 24-38.
- Avoid office/tech-worker cues in actor_description: no laptop, no monitor, no headset, no headphones, no microphone, no gaming chair, no visible screens.
- If female: minimalist premium casual look (turtleneck, simple tee, blazer, knit top). If male: clean premium casual tee, knit, blazer, or overshirt.
- Example female: "a 26 year old attractive european woman, light brown wavy hair, wearing a white tank top, natural minimal makeup, friendly face"
- Example male: "a 29 year old european man, short dark hair, light stubble, wearing a navy t-shirt, smart casual look" """

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        max_output_tokens=32768,
    )
    scripts = _request_gemini_script_batch(
        lambda: _generate_gemini_content(
            client,
            contents=[prompt],
            config=config,
            text_model=text_model,
        ),
        num_scripts=num_scripts,
        require_shots=False,
        label="script",
        batch_validator=lambda batch: _validate_script_batch_hooks(batch, supplied_hook=supplied_hook),
    )

    for script in scripts:
        _finalize_generated_script(script)

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
    seconds = len(words) / 2.2 + len(tags) * 0.8 + pauses * 0.4
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

    shots = normalize_storyboard_shots({"shots": shots})
    full_narration = " ".join(shot.get("speech", "") for shot in shots if shot.get("speech")).strip()
    actor_noun = "woman" if actor_gender == "female" else "man"
    return {
        "title": title,
        "format": "storyboard_v3",
        "style": style,
        "duration_seconds": int(max((shot.get("end", 0) for shot in shots), default=0)),
        "target_platform": "instagram",
        "hook_text": (shots[0].get("overlay_text") or shots[0].get("speech", "")[:50]) if shots else title,
        "shots": shots,
        "full_narration": full_narration or text,
        "actor_description": (
            f"a 30 year old natural looking european {actor_noun}, casual premium wellness outfit, "
            "friendly trustworthy face, minimal styling, authentic UGC look"
        ),
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

    actor_noun = "woman" if actor_gender == "female" else "man"
    actor_description = (
        f"a 30 year old natural looking european {actor_noun}, casual everyday outfit, "
        "friendly trustworthy face, minimal styling, authentic UGC look"
    )

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
        "actor_description": actor_description,
        "hashtags": ["#reels", "#shorts", "#ugc"] if language != "ru" else ["#рилс", "#привычки", "#питание"],
        "caption": topic or product_desc,
        "custom_script": True,
    }


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Asset Generation
# ═══════════════════════════════════════════════════════════════════════

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
                raise Exception(f"fal.ai submit request failed for {model_id} at {submit_url}: {e}") from e
            wait = 3 * (attempt + 1)
            print(f"[fal.ai] Submit connect failed ({e}), retrying in {wait}s...")
            time.sleep(wait)
        except httpx.RequestError as e:
            raise Exception(f"fal.ai submit request failed for {model_id} at {submit_url}: {e}") from e

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
    return max(3, min(15, int(round(duration or 5))))


def _build_storyboard_generation_prompt(shot: dict) -> str:
    existing = (shot.get("generation_prompt") or "").strip()
    if existing:
        # Уважать промпт пользователя (он редактируется в UI): гардрейлы формата
        # дописываем, а не заменяем ими весь текст. Идемпотентно — повторный
        # normalize не меняет строку, иначе кэш клипов считал бы её «новым промптом».
        additions = []
        if "9:16" not in existing:
            additions.append("vertical 9:16")
        return ", ".join([existing] + additions)

    scene = (shot.get("scene") or shot.get("visual") or "realistic social video scene").strip()
    actor_action = (shot.get("actor_action") or shot.get("action") or "natural movement").strip()
    camera = (shot.get("camera") or "vertical 9:16 steady handheld smartphone video").strip()
    bits = [
        "vertical 9:16 realistic phone video",
        "same actor/character across shots",
        scene,
        actor_action,
        camera,
        "natural light",
        "authentic smartphone footage",
    ]
    return ", ".join(bit for bit in bits if bit)


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
    scene edits are detectable. On any failure the existing prompts are kept.
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
            f"Actor: {actor_description or 'a consistent real person, same across all shots'}.\n"
            "For each shot, write ONE English prompt that fully describes the scene, action "
            "and camera on its own. Rules: vertical 9:16, same actor/character across shots, "
            "natural light, authentic smartphone footage. Describe only what IS in frame — "
            "never write 'no text', 'no watermark' or any other ban, those go to the model in "
            "a separate field and in the description they only make it draw them. "
            "For visual_type 'broll', use the exact speech as the visual source of "
            "truth: literally demonstrate the claim or use one clear visual analogy. Do not use "
            "generic wellness filler (avocado, salad, measuring tape, yoga mat, supplements, "
            "scales or food prep) unless the speech explicitly concerns it. A faceless human "
            "action is allowed when conceptually necessary (back view, cropped body/hands, "
            "silhouette, non-identifiable profile); never request an identifiable face. When "
            "actor_in_frame is true the person in that insert IS the presenter herself — write "
            "'the same woman from the reference' (or man) and keep her face away from camera; "
            "when it is false do not put any recognisable person in the shot. Never "
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
Actor: {script.get('actor_description') or f'a consistent {actor_gender} person, same in every shot'}

Full storyboard for context (already existing shots):
{json.dumps(context, ensure_ascii=False, indent=1)}

Fill in the MISSING production fields for these shots (keep any value that is
already filled in — only replace empty ones):
{json.dumps(payload, ensure_ascii=False, indent=1)}

RULES:
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
- In "talking" shots the actor holds a steady selfie pose: subtle expressions and
  small head movement only. No exercising, walking, drinking or big gestures —
  motion breaks lip-sync.
- Every shot must be visually distinct from its neighbours in the storyboard above.
- role: one of hook, problem, explanation, solution, proof, cta.
- emotion: one of excited, warm, confident, calm, urgent, playful.
- transition: "cut" or "smooth_0.3s".
- No readable text anywhere: no labels, signs, numbers, stickers, no phone/laptop
  screens facing camera — video models render text as garbage glyphs.
- generation_prompt MUST be English and fully describe scene, action and camera on
  its own: vertical 9:16, realistic phone video, same actor, natural light. Describe only
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
            merged["generation_prompt"] = _build_storyboard_generation_prompt(
                {**merged, "generation_prompt": (item.get("generation_prompt") or "").strip()
                 or merged.get("generation_prompt") or ""}
            )
            merged["_prompt_source_scene"] = (merged.get("scene") or "").strip()
        out.append(merged)
    return out


def normalize_storyboard_shots(script: dict) -> list:
    """Normalize shot dictionaries for Kling V3 generation and UI edits."""
    raw_shots = script.get("shots") or []
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
        # Only coerce when the storyboard actually stated it: an absent flag must
        # stay absent so `fill_storyboard_shot_details` can still decide, while a
        # user's explicit "no" is never re-decided for them.
        if "actor_in_frame" in shot:
            normalized["actor_in_frame"] = _shot_wants_actor(shot)
        normalized["generation_prompt"] = _build_storyboard_generation_prompt(normalized)
        shots.append(normalized)
    return shots

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
# from the reference image, so the prompt's single job is to hold the body
# still: with no prompt at all Kling invents leg-crossing and hand-shuffling
# that reads as fidgeting. Length is deliberate — fal's own schema defaults this
# field to "." and the comparable Longcat avatar endpoint defaults to a single
# plain sentence, so two sentences is already the upper end of what these models
# expect here.
_AVATAR_MOTION_PROMPT = (
    "The person stays seated in the same pose, hands resting calmly, legs still, speaking "
    "straight to the camera with a calm friendly expression. Only the face moves: the lips "
    "follow the audio, natural blinking, small head movements, one locked-off take."
)

_AVATAR_WHISPER_MOTION_PROMPT = (
    "The person leans slightly closer to the camera, chin lowered, one hand resting near the "
    "mouth, whispering confidentially with a restrained conspiratorial expression. The lips "
    "follow the audio, natural blinking, tiny head movements, one locked-off take."
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


def generate_tiktok_subs(audio_path: str, output_path: str, max_words: int = 3, words: Optional[list] = None) -> str:
    """
    Generate TikTok-style ASS subtitles from audio using Whisper transcription.

    Style: Big bold centered text, 1-3 words at a time, white with black outline.
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
        text = _strip_pictographs(" ".join(w["word"] for w in group)).upper()
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
    max_words: int = 3,
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
        text = _strip_pictographs(" ".join(w["word"] for w in group)).upper()
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
    parts = []
    if music_input:
        parts.append(f"[{voice_input}:a]aresample=48000,asplit=2[vo][vosc]")
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
        mix_src = f"[{voice_input}:a]"
    parts.append(f"{mix_src}{_loudnorm_filter(measured, print_json)},aresample=48000[aout]")
    return parts


def _measure_final_loudness(
    inputs: list,
    voice_input: str,
    music_input: Optional[str],
    music_volume: float,
    log: Callable[[str], None] = print,
    music_gain_db: float = 0.0,
) -> Optional[dict]:
    """Pass 1 of the two-pass loudnorm: measure the finished mix, decode only.

    Runs the exact audio graph of the real render against `-f null`, so the
    numbers describe the mix that will actually be encoded (music bed and
    ducking included). Returns None on any trouble — the caller then falls back
    to one-pass, which is worse for dynamics but never fails the render.
    """
    parts = _final_audio_filter_parts(
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


def composite_storyboard_video(
    clips: list,
    audio_path: str,
    srt_path: str,
    output_path: str,
    music_path: Optional[str] = None,
    # Бед нормализуется к _MUSIC_BED_DBFS, так что это просто подстройка сверху.
    music_volume: float = 1.0,
) -> str:
    """Concatenate Kling V3 storyboard clips and lay the voiceover/subtitles on top."""
    if not clips:
        raise ValueError("Storyboard composite requires at least one clip")

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
    filter_parts = []
    concat_parts = []
    for index, clip in enumerate(clips):
        actual = _get_media_duration(clip["path"])
        duration = max(0.1, float(clip.get("duration") or actual))
        clip_norm = norm
        if _shot_performance(clip.get("shot") or {}) == "whisper":
            # Free pattern interrupt for the hush shot. This changes only the
            # crop: slowing a lip-synced clip would move its mouth off the
            # untouched master voiceover.
            clip_norm += (
                ",crop=iw/1.08:ih/1.08:(iw-ow)/2:(ih-oh)*0.42,"
                "scale=1080:1920"
            )
        # A lip-synced clip can open with the head of silence its driving audio
        # carried (see _mp3_encoder_delay): skipping it puts the lips back on
        # the master voiceover instead of that many milliseconds behind it.
        head = min(max(0.0, float(clip.get("speech_offset") or 0.0)), max(0.0, actual - 0.1))
        head_arg = f"{head:.3f}" if head else "0"
        usable = max(0.1, actual - head)
        deficit = duration - usable
        stretchable = _is_broll_shot(clip.get("shot") or {})
        if usable > 0 and 0.05 < deficit <= usable * 0.15 and stretchable:
            # Short b-roll: slow the whole clip a touch instead of a visible
            # end-freeze — motion carries through and the seam disappears.
            # Talking shots keep the freeze: stretching them would drag the
            # lips out of sync with the master voiceover.
            ratio = duration / usable
            head_chain = f"trim=start={head_arg},setpts=PTS-STARTPTS," if head else ""
            chain = (
                f"[{index}:v]{head_chain}setpts={ratio:.6f}*PTS,{clip_norm},"
                f"trim=start=0:end={duration:.3f},setpts=PTS-STARTPTS"
            )
        else:
            chain = (
                f"[{index}:v]trim=start={head_arg}:end={head + duration:.3f},"
                f"setpts=PTS-STARTPTS,{clip_norm}"
            )
            # Clip came back shorter than its slot: freeze the last frame
            # instead of silently shifting every later shot off-sync.
            if usable > 0 and deficit > 0.05:
                chain += f",tpad=stop_mode=clone:stop_duration={deficit:.3f}"
        filter_parts.append(chain + f"[v{index}]")
        concat_parts.append(f"[v{index}]")
    filter_parts.append(f"{''.join(concat_parts)}concat=n={len(clips)}:v=1:a=0[vout]")
    filter_parts.append(f"[vout]{sub_filter}[finalv]")
    voice_input = str(len(clips))
    music_input = str(len(clips) + 1) if music_path else None
    music_gain_db = _music_bed_gain_db(music_path) if music_path else 0.0
    filter_parts.extend(_final_audio_filter_parts(
        voice_input,
        music_input,
        music_volume,
        _measure_final_loudness(
            inputs, voice_input, music_input, music_volume, music_gain_db=music_gain_db,
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
        log(
            f"  Слайс {os.path.basename(output_path)}: {reason} — "
            "пересечка звука и перегенерация клипа."
        )
        for stale in (
            identity_path,
            output_path,
            f"{output_path}.fal_url.txt",
            clip_path,
            clip_path.replace(".mp4", "_base.mp4"),
            clip_path.replace(".mp4", "_base_fal.json"),
            f"{clip_path}.meta.json",
            f"{clip_path}.review.json",
            f"{clip_path}.review.jpg",
            f"{clip_path}.fal_url.txt",
        ):
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
# Cut fast on the hook, let the body breathe. Measured off the reel that broke
# through (16 shots / 72s): 2.2 2.2 2.8 on the hook, then 4.3-8.2, median 4.7.
_HOOK_WINDOW_SECONDS = 8.0
_HOOK_SLICE_SECONDS = 2.6
_BODY_WINDOW_SECONDS = 30.0
_BODY_SLICE_SECONDS = 5.0
_LATE_SLICE_SECONDS = 6.5


def _target_slice_seconds(start: float) -> float:
    """How long one talking shot may run at this point in the reel."""
    if start < _HOOK_WINDOW_SECONDS:
        return _HOOK_SLICE_SECONDS
    if start < _BODY_WINDOW_SECONDS:
        return _BODY_SLICE_SECONDS
    return _LATE_SLICE_SECONDS


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
        if duration < 2 * _MIN_TALKING_SLICE_SECONDS:
            whispered = dict(shot)
            whispered["_performance"] = "whisper"
            result.append({**sl, "shot": whispered})
            continue

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
    """Split talking slices into jump-cut sub-slices on a rhythm curve.

    Kling Avatar lip-sync drifts over long takes and a long static monologue
    reads dead, so shots stay short — shortest on the hook, where attention is
    won or lost. Pass max_len to override the curve with one flat limit, or
    cuts_by_shot to replay the cuts a shot already got. Cuts snap to inter-word
    pauses; each sub-slice carries a copy of the shot, so the alternating
    framings render the splits as natural angle changes. B-roll slices pass
    through: the master voiceover plays over them, no lip-sync involved.
    """
    result = []
    for sl in slices:
        duration = sl["end"] - sl["start"]
        limit = max_len if max_len is not None else _target_slice_seconds(sl["start"])
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


def _models_that_blanked(photo_path: str) -> set:
    """Редакторы, уже вернувшие чёрный кадр на это фото.

    Пустой кадр fal тарифицирует как обычный: платим за чёрный квадрат ровно
    столько же, сколько за картинку. Модерация срабатывает детерминированно —
    повторный запрос той же моделью с тем же фото купит тот же квадрат. Поэтому
    вердикт запоминается рядом с фотографией и переживает джобы.
    """
    try:
        with open(_blank_model_memo(photo_path), encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _remember_blank_model(photo_path: str, model: str) -> None:
    known = _models_that_blanked(photo_path) | {model}
    try:
        with open(_blank_model_memo(photo_path), "w", encoding="utf-8") as f:
            json.dump(sorted(known), f)
    except OSError:
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
) -> None:
    """Записать отказ редактора так, чтобы интерфейс мог о нём рассказать.

    Лог читают не все, а деньги списываются со всех. Отчёт несёт дословный ответ
    fal (`has_nsfw_concepts` и соседи) и список моделей, которые на этом фото ещё
    не пробовали, — из него интерфейс собирает предложение сменить модель.
    """
    if billing is None:
        return
    tried = _models_that_blanked(photo_path) if photo_path else set()
    billing.setdefault("blocked", []).append({
        "model": entry["id"],
        "title": entry["title"],
        "vendor": entry["vendor"],
        # "moderation" — модель зарубила кадр, "known" — уже рубила его раньше,
        # "unavailable" — эндпоинт не ответил (404/422), это не про модерацию.
        "reason": reason,
        "flags": flags,
        "charged": charged,
        "alternatives": [
            {"id": m["id"], "title": m["title"], "vendor": m["vendor"], "note": m["note"]}
            for m in AVATAR_EDIT_MODELS
            if m["id"] not in tried and m["id"] != entry["id"]
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
) -> str:
    """Draw one Flux still for a shot, cached by prompt. "" on any failure.

    Two models behind one door: given an actor photo this is an image-conditioned
    edit that keeps that person's identity, without one it is plain
    text-to-image. The cache keys on the prompt, so an edited shot is redrawn and
    an untouched one never pays twice.

    `edit_model` — какой редактор из `AVATAR_EDIT_MODELS` позвать (пусто = дефолт).
    Отказ никогда не переходит на другую модель сам: он попадает в `billing`
    отчётом, а выбор остаётся за пользователем.
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
        blanked = _models_that_blanked(actor_photo_path)
        if entry["id"] in blanked:
            # Бесплатный отказ: модерация детерминированна, тот же редактор с тем
            # же фото купит тот же чёрный квадрат.
            log(f"  ⚠️ {label}: {entry['title']} на это фото уже вернул пустой кадр. "
                "Повторный запрос не делаю — он платный и вернёт то же самое. "
                "Нужна другая модель или другое фото ведущего.")
            _report_blocked_editor(billing, entry, "known", {}, False, actor_photo_path)
            return ""
        model, image_field, extra = entry["id"], entry["field"], entry["args"]
        image_url = _fal_upload_file(_flux_condition_photo(actor_photo_path), fal_key)
    else:
        model, image_field, extra = "fal-ai/flux-2-pro", "", {"image_size": "portrait_16_9", "safety_tolerance": 5}
        image_url = ""

    args = {"prompt": prompt, **extra}
    if image_field == "image_urls":
        args["image_urls"] = [image_url]
    elif image_field:
        args[image_field] = image_url

    try:
        if billing is not None:
            billing["calls"] = billing.get("calls", 0) + 1
        result = _fal_run(model, args, fal_key, timeout=600)
        images = result.get("images") or result.get("output", [])
        if not images:
            raise RuntimeError(f"no images in Flux result: {list(result.keys())}")
        img_url = images[0]["url"] if isinstance(images[0], dict) else images[0]
        with httpx.Client(timeout=120.0) as client:
            resp = client.get(img_url)
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)
        if _looks_blank(output_path):
            # Ответ модели — единственное место, где видно «зарубила модерация»
            # вместо «что-то пошло не так». Без него причина остаётся догадкой.
            flags = {k: result[k] for k in _FAL_MODERATION_FIELDS if k in result}
            log(f"  ⚠️ {label}: {model} вернул пустой кадр"
                + (f" — ответ модели: {flags}" if flags else " (модель не назвала причину)"))
            _drop_frame_files(output_path)
            if actor_photo_path:
                _remember_blank_model(actor_photo_path, model)
                _report_blocked_editor(billing, entry, "moderation", flags, True, actor_photo_path)
                left = [m["title"] for m in AVATAR_EDIT_MODELS
                        if m["id"] not in _models_that_blanked(actor_photo_path)]
                log(f"  {label}: не пробовали на этом фото: {', '.join(left)} — выбор за тобой."
                    if left else f"  {label}: редакторы кончились — нужно другое фото ведущего.")
            return ""
        if model != DEFAULT_AVATAR_EDIT_MODEL and actor_photo_path:
            log(f"  ✅ {label}: кадр нарисовала {model}")
        with open(prompt_sidecar, "w", encoding="utf-8") as f:
            f.write(prompt)
        return output_path
    except Exception as e:
        # Отказ эндпоинта деньгами не пахнет (fal берёт только за генерацию), но
        # и повторять его незачем: сетевые сбои переигрывает сам `_fal_run`, а
        # 404/422 значит, что модель переехала — запоминаем и идём дальше.
        log(f"  ⚠️ {label}: {model} не отработал ({e}){on_failure}")
        if billing is not None:
            billing["calls"] = max(0, billing.get("calls", 1) - 1)
        if actor_photo_path:
            _remember_blank_model(actor_photo_path, model)
            _report_blocked_editor(billing, entry, "unavailable", {"error": str(e)}, False,
                                   actor_photo_path)
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
        actor_prompt = (
            "Keep the exact same person as in the reference image: same hairstyle, build "
            f"and clothing. {base_prompt + '. ' if base_prompt else ''}"
            "Single photographic frame, vertical 9:16, this person seen from behind, over "
            "the shoulder or cropped so the face stays out of frame. One person only, "
            "natural light, shallow depth of field, smartphone realism, plain unbranded "
            "surfaces."
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
) -> str:
    """Avatar frame from the actor photo + a scene description.

    Keeps the saved avatar's identity (face, hair, outfit) via an image-conditioned
    Flux edit, but stages the described scene so each cut is its own composition
    instead of a crop of one static photo — which made Kling clone the person
    toward the frame edges. Returns "" on any failure so the caller falls back to
    a punch-in crop of the shared photo: a plainer frame beats a failed job.

    scene_override pins one set for every talking shot of a reel; framing asks
    for a specific crop of that set, so the reel reads as two cameras on one
    take instead of a new room behind every cut.
    """
    if not (actor_photo_path and os.path.exists(actor_photo_path)):
        return ""
    scene = (scene_override or shot.get("generation_prompt") or shot.get("scene") or "")
    scene = scene.strip().rstrip(".")
    framing = (framing or "").strip().rstrip(".")
    prompt = (
        "Keep the exact same person, face, hairstyle and outfit as in the reference image. "
        f"{scene + '. ' if scene else ''}"
        f"{framing + '. ' if framing else ''}"
        "Vertical 9:16 portrait, one single person only, centered and fully inside the frame, "
        "photorealistic phone-camera look, natural light. Never duplicate the person, never add a "
        "second face, keep the frame edges free of any extra person. Plain unbranded clothing "
        "and background."
    )
    return _flux_reference_frame(
        prompt, fal_key, output_path, log=log,
        actor_photo_path=actor_photo_path,
        label="Avatar reference frame",
        on_failure="; using cropped photo instead",
        billing=billing,
        edit_model=edit_model,
    )


# Two cameras on one set, alternating — the whole trick behind reels that read as
# a filmed interview: the background never changes, only the framing does, so the
# pose reset every generated clip starts with lands between two different angles
# and stops registering as a jump.
_AVATAR_FRAMINGS = (
    ("medium",
     "Medium shot from the chest up, the person centred with the room visible behind them"),
    ("close",
     "Tight close-up, the face filling the frame, shoulders cropped, background softly "
     "out of focus"),
)
_AVATAR_HUSH_FRAMING = (
    "hush",
    "Tight intimate close-up, leaning slightly toward the camera, chin lowered, one hand "
    "resting near the mouth, restrained confidential expression",
)


def _avatar_framing_for_shot(shot: dict, framing_index: int) -> tuple:
    if _shot_performance(shot) == "whisper":
        return _AVATAR_HUSH_FRAMING
    return _AVATAR_FRAMINGS[framing_index % len(_AVATAR_FRAMINGS)]


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


def _avatar_reference_variant(image_path: str, output_path: str, index: int) -> str:
    """Crop a slightly different framing of one actor photo per shot.

    When several shots share one reference image, identical first frames make
    every cut look like a glitchy reset. A small alternating punch-in keeps the
    same person but gives each clip its own starting composition.
    """
    variant = _AVATAR_REFERENCE_VARIANTS[(index - 1) % len(_AVATAR_REFERENCE_VARIANTS)]
    if variant is None:
        return image_path
    if _nonempty(output_path):
        return output_path
    zoom, cx, cy = variant
    vf = (
        f"crop=iw/{zoom}:ih/{zoom}:(iw-iw/{zoom})*{cx}:(ih-ih/{zoom})*{cy},"
        f"scale=ceil(iw*{zoom}/2)*2:ceil(ih*{zoom}/2)*2"
    )
    cmd = ["ffmpeg", "-y", "-i", image_path, "-vf", vf, output_path]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return output_path
    except Exception as e:
        print(f"[SaaSShorts] ⚠️ Reference variant failed, using original photo: {e}")
        return image_path


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
    broll_tier: str = "standard",
    broll_image_first: bool = True,
    avatar_image_first: bool = True,
    voice_manifest: Optional[dict] = None,
    edit_model: str = "",
    billing: Optional[dict] = None,
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
            f"(хук по {_HOOK_SLICE_SECONDS:.1f}s, дальше {_BODY_SLICE_SECONDS:.0f}-{_LATE_SLICE_SECONDS:.1f}s — "
            "частая склейка держит внимание, короткий дубль держит липсинк)."
        )

    fallback_actor_img = ""
    plates: dict = {}
    # One set for the whole reel, taken from the first talking shot: every talking
    # clip is staged on it, only the framing alternates.
    pinned_set = ""
    for sl in slices:
        if not _is_broll_shot(sl["shot"]):
            pinned_set = (
                sl["shot"].get("generation_prompt") or sl["shot"].get("scene") or ""
            ).strip()
            if pinned_set:
                break

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

    def _framing_plate(framing_spec):
        """Staged frame for one camera of the pinned set, generated once per reel."""
        key, framing_line = framing_spec
        if key in plates:
            return plates[key]
        plate_path = _framing_plate_path(output_dir, title_slug, key)
        made = _avatar_reference_image(
            {}, _shared_actor_photo(), fal_key, plate_path, log=log,
            scene_override=pinned_set, framing=framing_line,
            billing=billing, edit_model=edit_model,
        )
        plates[key] = made
        if made:
            log(f"  Ракурс «{key}» готов — он держится на всех говорящих кадрах.")
        return made

    def _resolve_image(sl, index, framing_spec, framing_index):
        whisper = _shot_performance(sl["shot"]) == "whisper"
        if whisper and avatar_image_first:
            plate = _framing_plate(framing_spec)
            if plate:
                return plate
        # A frame the user picked or generated for this shot always wins — but a
        # split shot must not play the same framing twice in a row, so every other
        # talking clip gets a punch-in of it.
        ref = _storyboard_avatar_reference_image(sl["shot"], output_dir, index)
        # A frame the storyboard already staged as one of our cameras is not a
        # per-shot choice — the cursor owns which camera plays, so that a shot
        # split in two never plays the same angle twice in a row.
        if ref and _is_framing_plate(ref, title_slug):
            ref = ""
        if ref:
            if framing_index % len(_AVATAR_FRAMINGS) == 0:
                return ref
            punch_path = os.path.join(output_dir, f"{title_slug}_shot_ref_{index:02d}.png")
            return _avatar_reference_variant(ref, punch_path, 2)
        if avatar_image_first:
            plate = _framing_plate(framing_spec)
            if plate:
                return plate
        # Fallback: vary the crop of the shared photo so cuts read as camera changes.
        photo = _shared_actor_photo()
        _refuse_unusable_start_frame(photo)
        variant_path = os.path.join(output_dir, f"{title_slug}_actor_ref_{index:02d}.png")
        return _avatar_reference_variant(photo, variant_path, framing_index + 1)

    jobs = []
    framing_cursor = 0
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
            framing_spec = _avatar_framing_for_shot(sl["shot"], framing_cursor)
            image = _resolve_image(sl, index, framing_spec, framing_cursor)
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

    output_root = _job_output_root(output_dir)

    # Talking shots share two staged cameras of one set. A frame per shot is both
    # a Flux charge per shot and a new room behind every cut — which is exactly
    # what makes the avatar jump between scenes.
    pinned_set = ""
    for shot in shots:
        if not _is_broll_shot(shot):
            pinned_set = (shot.get("generation_prompt") or shot.get("scene") or "").strip()
            if pinned_set:
                break
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
    for shot in shots:
        num = shot.get("shot_number")
        if only is not None and num != only:
            continue
        broll = _is_broll_shot(shot)
        framing = ""
        if broll:
            frame_path = os.path.join(output_dir, f"{title_slug}_frame_{int(num or 0):02d}.png")
        else:
            key, framing = _avatar_framing_for_shot(
                shot,
                talking_order.get(id(shot), 0),
            )
            frame_path = _framing_plate_path(output_dir, title_slug, key)
        if only is None:
            # Reopened storyboard: this shot already carries a frame (or a
            # rendered clip) from an earlier job. Drawing it again is a fresh
            # Flux charge for a picture the user already paid for — skip it.
            # Per-shot "перегенерить" still forces a redraw.
            existing = _existing_shot_frame(shot, output_root)
            if shot.get("clip_url") or existing:
                if existing:
                    shot.setdefault("preview_frame_url", shot.get("local_url") or "")
                log(f"[кадры] Кадр {num}: уже есть — пропускаю.")
                reused += 1
                continue
        if only is not None:
            # Explicit per-shot regenerate: drop the cached frame so a new one is drawn.
            for stale in (frame_path, f"{frame_path}.prompt.txt", f"{frame_path}.fal_url.txt"):
                try:
                    if os.path.exists(stale):
                        os.remove(stale)
                except OSError:
                    pass
            if not broll:
                log(f"[кадры] Кадр {num}: перерисовываю ракурс «{key}» — он общий "
                    "для всех кадров на этой камере.")
        drawn_before = _nonempty(frame_path)
        if drawn_before and not broll:
            log(f"[кадры] Кадр {num}: ракурс «{key}» уже отрисован — переиспользую.")
        else:
            log(f"[кадры] Генерирую кадр {num}...")
        if broll:
            made_path = _broll_reference_image(
                shot, fal_key, frame_path, log=log,
                actor_photo_path=_actor_photo() if _shot_wants_actor(shot) else "",
                billing=billing,
                edit_model=edit_model,
            )
        else:
            made_path = _avatar_reference_image(
                {}, _actor_photo(), fal_key, frame_path, log=log,
                scene_override=pinned_set, framing=framing,
                billing=billing,
                edit_model=edit_model,
            )
        if made_path and _nonempty(made_path):
            url = f"/videos/{job_dir}/{os.path.basename(made_path)}"
            shot["image_path"] = made_path
            shot["local_url"] = url
            shot["image_url"] = url
            shot["preview_frame_url"] = url
            # A second shot on an already-drawn camera costs nothing.
            if drawn_before and not broll:
                reused += 1
            else:
                made += 1
        else:
            failed += 1
            log(f"  ⚠️ Кадр {num}: не удалось сгенерировать.")

    log(f"[кадры] Готово: {made} кадр(ов)." + (f" Пропущено готовых: {reused}." if reused else "")
        + (f" Платных обращений к модели: {billing['calls']}." if billing["calls"] != made else ""))
    cost = round(billing["calls"] * 0.05, 2)
    # Один отказ на модель: первый — настоящий (с ответом fal), остальные кадры
    # той же пачки упираются в тот же вердикт по памяти и ничего нового не несут.
    blocked_by_model = {}
    for item in billing.get("blocked", []):
        blocked_by_model.setdefault(item["model"], item)
    actor_photo = selected_actor_path or fallback_actor["path"]
    tried = _models_that_blanked(actor_photo) if actor_photo else set()
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
            {**{k: m[k] for k in ("id", "title", "vendor", "note")}, "blocked": m["id"] in tried}
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
    talking_seconds = sum(sl["end"] - sl["start"] for sl in talking)
    broll_seconds = sum(sl["end"] - sl["start"] for sl in broll)
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
    shots = normalize_storyboard_shots(script)
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
        audio_path, shots, srt_path, max_words=2, words=spoken_words or None,
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
        avatar_seconds = sum(c["duration"] for c in avatar_clips)
        broll_seconds = sum(c["duration"] for c in broll_clips)
        video_cost_key = f"sliced_avatar_kling_{avatar_tier}"
        video_cost = round(avatar_seconds * kling_avatar_cost_per_second(avatar_tier), 2)
        if broll_seconds:
            broll_tier = tier if tier in KLING_V3_STORYBOARD_TIERS else "standard"
            extra_costs[f"sliced_broll_kling_v3_{broll_tier}"] = round(
                broll_seconds * storyboard_video_cost_per_second(broll_tier), 2
            )
        # Per-shot Flux reference frames (avatar scene + b-roll composition).
        ref_frames = 0
        if config.get("avatar_image_first", True):
            ref_frames += len(avatar_clips)
        if broll_seconds and config.get("broll_image_first", True):
            ref_frames += len(broll_clips)
        if ref_frames:
            extra_costs["reference_frames_flux"] = round(ref_frames * 0.05, 2)
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
        "duration": audio_duration,
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
    generate_tiktok_subs(audio_path, srt_path, max_words=2, words=spoken_words)

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
