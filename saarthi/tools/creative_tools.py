"""
Creative Tools — Image & Video Generation.

SAARTHI ab create bhi kar sakta hai — sirf control nahi.

Free APIs used:
  - Pollinations.ai (image + video) — high quality, multiple models
    Flux, GPTImage, Seedream for images
    Veo, Seedance, Wan for videos

Setup:
  Optional: POLLINATIONS_API_KEY in .env (for higher limits)
  Without key: works with basic rate limits (1/hour per IP)
"""

from __future__ import annotations

import os
import time
import urllib.parse
from pathlib import Path

import httpx

from ..devices.base import ActionResult
from .base import Tool, ToolContext

# Output folder
_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "generated"

# Pollinations base
_POLLINATIONS_BASE = "https://gen.pollinations.ai"

# Default timeouts (image fast, video slow)
_IMAGE_TIMEOUT = 120.0
_VIDEO_TIMEOUT = 300.0


def _get_pollinations_key() -> str | None:
    """Pollinations API key .env se uthao (optional)."""
    return os.getenv("POLLINATIONS_API_KEY") or None


def _ensure_output_dir(subdir: str = "") -> Path:
    """Output directory bana do agar nahi hai."""
    path = _OUTPUT_DIR / subdir if subdir else _OUTPUT_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_filename(prompt: str, ext: str) -> str:
    """Prompt se safe filename banao."""
    # Pehle 50 chars, special chars hatao
    clean = "".join(c if c.isalnum() or c in " _-" else "" for c in prompt[:50])
    clean = clean.strip().replace(" ", "_") or "generated"
    timestamp = int(time.time())
    return f"{clean}_{timestamp}.{ext}"


# ======================================================================
#  IMAGE GENERATION
# ======================================================================


class ImageGenerateTool(Tool):
    name = "image_banao"
    description = (
        "Generate an image with AI. Give a text prompt and get a "
        "high-quality image. Can create anything — art, photos, logos, "
        "illustrations. Models: flux (best quality), gptimage (creative), "
        "seedream (photorealistic). Free, no limit."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "What to create — describe it in detail. "
                    "Write in English for best results. "
                    "Example: 'a majestic tiger in a misty forest, photorealistic, 8k'"
                ),
            },
            "model": {
                "type": "string",
                "description": (
                    "Which model to use. Options: "
                    "flux (default, best quality), "
                    "gptimage (creative, artistic), "
                    "seedream (photorealistic), "
                    "ideogram-v4-turbo (text in images)"
                ),
            },
            "width": {
                "type": "integer",
                "description": "Image width in pixels. Default 1024.",
            },
            "height": {
                "type": "integer",
                "description": "Image height in pixels. Default 1024.",
            },
            "style": {
                "type": "string",
                "description": (
                    "Style hint — added to the prompt. "
                    "Examples: photorealistic, anime, watercolor, "
                    "cinematic, minimalist, pixel art"
                ),
            },
        },
        "required": ["prompt"],
    }

    async def run(self, ctx: ToolContext, **kwargs) -> ActionResult:
        prompt: str = kwargs["prompt"]
        model: str = kwargs.get("model", "flux")
        width: int = kwargs.get("width", 1024)
        height: int = kwargs.get("height", 1024)
        style: str = kwargs.get("style", "")

        # Style ko prompt mein merge karo
        full_prompt = f"{prompt}, {style}" if style else prompt

        # Clamp dimensions
        width = max(256, min(width, 2048))
        height = max(256, min(height, 2048))

        # Build URL
        encoded_prompt = urllib.parse.quote(full_prompt)
        url = (
            f"{_POLLINATIONS_BASE}/image/{encoded_prompt}"
            f"?model={model}&width={width}&height={height}&nologo=true"
        )

        # API key add karo agar hai
        api_key = _get_pollinations_key()
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Download image
        try:
            async with httpx.AsyncClient(
                timeout=_IMAGE_TIMEOUT,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            return ActionResult.failure(
                "Image generate karte waqt timeout ho gaya. "
                "Dobara try karo ya chhota size try karo."
            )
        except httpx.RequestError as exc:
            return ActionResult.failure(f"Network error: {exc}")

        if response.status_code == 402:
            return ActionResult.failure(
                "Pollinations balance khatam. POLLINATIONS_API_KEY .env mein add karo "
                "ya enter.pollinations.ai pe top up karo."
            )

        if response.status_code >= 400:
            return ActionResult.failure(
                f"Image generation fail: HTTP {response.status_code}. "
                f"Model '{model}' ya prompt mein koi issue ho sakta hai."
            )

        # Content type se extension decide karo
        content_type = response.headers.get("content-type", "image/jpeg")
        if "png" in content_type:
            ext = "png"
        elif "svg" in content_type:
            ext = "svg"
        else:
            ext = "jpg"

        # Save file
        output_dir = _ensure_output_dir("images")
        filename = _safe_filename(prompt, ext)
        filepath = output_dir / filename

        filepath.write_bytes(response.content)

        size_kb = len(response.content) / 1024
        return ActionResult.success(
            f"Image generate ho gayi!\n"
            f"  File: {filepath}\n"
            f"  Size: {size_kb:.0f} KB\n"
            f"  Model: {model}\n"
            f"  Dimensions: {width}x{height}\n"
            f"  Prompt: {prompt[:80]}",
            file_path=str(filepath),
        )


# ======================================================================
#  VIDEO GENERATION
# ======================================================================


class VideoGenerateTool(Tool):
    name = "video_banao"
    description = (
        "Generate a video with AI. Give a text prompt and get an MP4 "
        "video. Can create short clips — 4 to 10 seconds. Models: veo "
        "(cinematic, best), wan-fast (quick), seedance-2.0 (motion). "
        "Video generation can take 1-3 minutes."
    )
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": (
                    "What should be in the video — describe it in detail. "
                    "Write in English. "
                    "Example: 'a drone flying over snowy mountains at sunset, cinematic'"
                ),
            },
            "model": {
                "type": "string",
                "description": (
                    "Which model to use. Options: "
                    "veo (default, cinematic quality), "
                    "wan-fast (quick generation), "
                    "seedance-2.0 (best motion/dance), "
                    "seedance-2.0-fast (faster seedance)"
                ),
            },
            "duration": {
                "type": "integer",
                "description": "Video length in seconds. Default 4, max 10.",
            },
            "style": {
                "type": "string",
                "description": (
                    "Style hint. Examples: cinematic, slow-motion, "
                    "timelapse, aerial, close-up, dramatic lighting"
                ),
            },
        },
        "required": ["prompt"],
    }

    async def run(self, ctx: ToolContext, **kwargs) -> ActionResult:
        prompt: str = kwargs["prompt"]
        model: str = kwargs.get("model", "wan-fast")
        duration: int = kwargs.get("duration", 4)
        style: str = kwargs.get("style", "")

        # Style merge
        full_prompt = f"{prompt}, {style}" if style else prompt

        # Clamp duration
        duration = max(2, min(duration, 10))

        # Build URL
        encoded_prompt = urllib.parse.quote(full_prompt)
        url = (
            f"{_POLLINATIONS_BASE}/video/{encoded_prompt}"
            f"?model={model}&duration={duration}"
        )

        # API key
        api_key = _get_pollinations_key()
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Download video — ye time lega
        try:
            async with httpx.AsyncClient(
                timeout=_VIDEO_TIMEOUT,
                follow_redirects=True,
            ) as client:
                response = await client.get(url, headers=headers)
        except httpx.TimeoutException:
            return ActionResult.failure(
                "Video generate karte waqt timeout (5 min). "
                "Video generation slow hai — dobara try karo ya "
                "wan-fast model try karo (sabse fast hai)."
            )
        except httpx.RequestError as exc:
            return ActionResult.failure(f"Network error: {exc}")

        if response.status_code == 402:
            return ActionResult.failure(
                "Pollinations balance khatam. POLLINATIONS_API_KEY .env mein add karo."
            )

        if response.status_code >= 400:
            return ActionResult.failure(
                f"Video generation fail: HTTP {response.status_code}. "
                f"Model '{model}' ya prompt check karo."
            )

        # Save video
        output_dir = _ensure_output_dir("videos")
        filename = _safe_filename(prompt, "mp4")
        filepath = output_dir / filename

        filepath.write_bytes(response.content)

        size_mb = len(response.content) / (1024 * 1024)
        return ActionResult.success(
            f"Video generate ho gayi!\n"
            f"  File: {filepath}\n"
            f"  Size: {size_mb:.1f} MB\n"
            f"  Model: {model}\n"
            f"  Duration: {duration}s\n"
            f"  Prompt: {prompt[:80]}",
            file_path=str(filepath),
        )


# ======================================================================
#  Factory
# ======================================================================


def creative_tools() -> list[Tool]:
    """Image + Video generation tools."""
    return [
        ImageGenerateTool(),
        VideoGenerateTool(),
    ]
