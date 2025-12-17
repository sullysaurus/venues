#!/usr/bin/env python3
"""
05_generate_images.py

Generate photorealistic venue images using existing Replicate models.
No ComfyUI, no custom deployment—just API calls.
"""

import base64
import json
import os
import random
import time
import ssl
import certifi
from pathlib import Path
from typing import List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

# Fix SSL certificate issues on macOS - must be set BEFORE importing httpx/replicate
_cert_path = certifi.where()
os.environ['SSL_CERT_FILE'] = _cert_path
os.environ['REQUESTS_CA_BUNDLE'] = _cert_path
os.environ['CURL_CA_BUNDLE'] = _cert_path

# Monkey-patch ssl to use certifi certs
_original_create_default_context = ssl.create_default_context
def _patched_create_default_context(purpose=ssl.Purpose.SERVER_AUTH, *, cafile=None, capath=None, cadata=None):
    context = _original_create_default_context(purpose, cafile=cafile or _cert_path, capath=capath, cadata=cadata)
    return context
ssl.create_default_context = _patched_create_default_context

# Import httpx and patch it to use certifi
import httpx
_original_httpx_client_init = httpx.Client.__init__
def _patched_httpx_client_init(self, *args, **kwargs):
    if 'verify' not in kwargs:
        kwargs['verify'] = _cert_path
    _original_httpx_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _patched_httpx_client_init

_original_httpx_async_client_init = httpx.AsyncClient.__init__
def _patched_httpx_async_client_init(self, *args, **kwargs):
    if 'verify' not in kwargs:
        kwargs['verify'] = _cert_path
    _original_httpx_async_client_init(self, *args, **kwargs)
httpx.AsyncClient.__init__ = _patched_httpx_async_client_init

import replicate
import requests

# Patch requests to use certifi
try:
    requests.packages.urllib3.util.ssl_.DEFAULT_CERTS = _cert_path
except:
    pass


# Enhanced negative prompt to combat text hallucination
NEGATIVE_PROMPT = (
    "text, words, letters, writing, font, typography, "
    "signs, signage, banners, posters, advertisements, "
    "logos, branding, labels, captions, subtitles, "
    "numbers, digits, scoreboard text, "
    "watermark, signature, copyright, graffiti, lettering, "
    "blurry, low quality, distorted, artifacts, noise, "
    "cartoon, anime, drawing, painting, illustration, "
    "sketch, artistic, stylized, unrealistic, 3d render, cgi"
)

# Anti-text additions for positive prompts
ANTI_TEXT_POSITIVE = "no text, no words, no signs, no banners, no logos, no writing, clean image"


class RateLimitError(Exception):
    """Raised when API rate limit is hit."""
    pass


def retry_with_backoff(
    func: Callable,
    max_retries: int = 5,
    initial_delay: float = 5.0,
    max_delay: float = 60.0,
    on_retry: Optional[Callable[[int, float, str], None]] = None
):
    """Execute function with exponential backoff retry on rate limit errors."""
    last_exception = None

    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_exception = e
            error_str = str(e).lower()

            # Check if it's a rate limit error (429)
            is_rate_limit = (
                "429" in error_str or
                "rate limit" in error_str or
                "too many requests" in error_str or
                "throttled" in error_str
            )

            if not is_rate_limit:
                raise

            if attempt == max_retries:
                raise

            # Calculate delay with exponential backoff and jitter
            delay = min(initial_delay * (2 ** (attempt - 1)), max_delay)
            jitter = delay * 0.3 * random.random()
            total_delay = delay + jitter

            if on_retry:
                on_retry(attempt, total_delay, str(e))
            else:
                print(f"Rate limited (attempt {attempt}/{max_retries}). Waiting {total_delay:.1f}s...")

            time.sleep(total_delay)

    raise last_exception


def image_to_data_uri(image_path: Path) -> str:
    """Convert local image to data URI for Replicate."""
    with open(image_path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')
    
    suffix = image_path.suffix.lower()
    mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}.get(suffix, 'image/png')
    
    return f"data:{mime};base64,{data}"


def generate_with_sdxl_depth(
    depth_map_path: Path,
    prompt: str,
    output_path: Path,
    strength: float = 0.8
) -> Optional[str]:
    """
    Generate using SDXL with ControlNet depth.
    Good balance of speed and quality.
    """
    depth_uri = image_to_data_uri(depth_map_path)
    enhanced_prompt = f"{prompt}, {ANTI_TEXT_POSITIVE}"

    def do_generate():
        output = replicate.run(
            "lucataco/sdxl-controlnet:06d6fae3b75ab68a28cd2900afa6033166910dd09fd9751047043a5bbb4c184b",
            input={
                "image": depth_uri,
                "prompt": enhanced_prompt,
                "negative_prompt": NEGATIVE_PROMPT,
                "num_inference_steps": 30,
                "guidance_scale": 7.5,
                "condition_scale": strength,
            }
        )

        if output:
            image_url = output[0] if isinstance(output, list) else str(output)
            response = requests.get(image_url)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.content)

            return str(output_path)

        return None

    try:
        # Verify API token is set
        token = os.environ.get("REPLICATE_API_TOKEN")
        if not token:
            raise ValueError("REPLICATE_API_TOKEN not set in environment")
        if not token.startswith("r8_"):
            raise ValueError(f"Invalid API token format (should start with r8_)")
        return retry_with_backoff(do_generate)
    except Exception as e:
        raise RuntimeError(f"SDXL generation failed: {type(e).__name__}: {e}") from e


def generate_with_flux_depth(
    depth_map_path: Path,
    prompt: str,
    output_path: Path,
    strength: float = 0.75
) -> Optional[str]:
    """
    Generate using Flux with depth conditioning.
    Higher quality, newer model.
    """
    depth_uri = image_to_data_uri(depth_map_path)
    # Flux doesn't support negative prompts, so we add anti-text to positive prompt
    enhanced_prompt = f"{prompt}, {ANTI_TEXT_POSITIVE}, photorealistic, sharp focus, professional photograph"

    def do_generate():
        output = replicate.run(
            "black-forest-labs/flux-depth-dev",
            input={
                "control_image": depth_uri,
                "prompt": enhanced_prompt,
                "guidance_scale": 3.5,
                "num_inference_steps": 28,
                "strength": strength
            }
        )

        if output:
            image_url = output[0] if isinstance(output, list) else str(output)
            response = requests.get(image_url)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.content)

            return str(output_path)

        return None

    try:
        # Verify API token is set
        token = os.environ.get("REPLICATE_API_TOKEN")
        if not token:
            raise ValueError("REPLICATE_API_TOKEN not set in environment")
        if not token.startswith("r8_"):
            raise ValueError(f"Invalid API token format (should start with r8_)")
        return retry_with_backoff(do_generate)
    except Exception as e:
        # Re-raise with more context so Streamlit can display it
        raise RuntimeError(f"Flux generation failed: {type(e).__name__}: {e}") from e


def generate_with_ip_adapter(
    depth_map_path: Path,
    reference_image_path: Path,
    prompt: str,
    output_path: Path,
    depth_strength: float = 0.75,
    style_strength: float = 0.5
) -> Optional[str]:
    """
    Generate using IP-adapter for style transfer from reference image.
    Combines depth conditioning with reference image style.

    Args:
        depth_map_path: Path to the depth map image
        reference_image_path: Path to the reference image for style
        prompt: Text prompt
        output_path: Where to save the result
        depth_strength: ControlNet depth strength (0-1)
        style_strength: IP-adapter style transfer strength (0-1)
    """
    depth_uri = image_to_data_uri(depth_map_path)
    reference_uri = image_to_data_uri(reference_image_path)
    enhanced_prompt = f"{prompt}, {ANTI_TEXT_POSITIVE}"

    def do_generate():
        # Using IP-adapter SDXL model with depth
        output = replicate.run(
            "zsxkib/ip-adapter-sdxl:f64608a08c4e2f50b90e2c7eb7d13ee6b8a3e70e75a1f4ed60d7d07f1e6d6a4a",
            input={
                "image": reference_uri,
                "prompt": enhanced_prompt,
                "negative_prompt": NEGATIVE_PROMPT,
                "num_inference_steps": 30,
                "guidance_scale": 7.5,
                "ip_adapter_scale": style_strength,
                "controlnet_conditioning_scale": depth_strength,
                "control_image": depth_uri,
            }
        )

        if output:
            image_url = output[0] if isinstance(output, list) else str(output)
            response = requests.get(image_url)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.content)

            return str(output_path)

        return None

    try:
        return retry_with_backoff(do_generate)
    except Exception as e:
        print(f"Error with IP-adapter: {e}")
        # Fallback: try simpler IP-adapter model
        try:
            return generate_with_ip_adapter_simple(
                reference_image_path, prompt, output_path, style_strength
            )
        except Exception as e2:
            print(f"Fallback also failed: {e2}")
            return None


def generate_with_ip_adapter_simple(
    reference_image_path: Path,
    prompt: str,
    output_path: Path,
    style_strength: float = 0.5
) -> Optional[str]:
    """
    Simplified IP-adapter without depth (fallback).
    Uses reference image for style guidance only.
    """
    reference_uri = image_to_data_uri(reference_image_path)
    enhanced_prompt = f"{prompt}, {ANTI_TEXT_POSITIVE}"

    def do_generate():
        output = replicate.run(
            "tencentarc/ip-adapter-sdxl:9e6e812ae0fe7e2bc8e8c85a35d43e3dd8c45a2bdb57e65ca2f3f63d5b5e3c8a",
            input={
                "image": reference_uri,
                "prompt": enhanced_prompt,
                "negative_prompt": NEGATIVE_PROMPT,
                "num_inference_steps": 30,
                "guidance_scale": 7.5,
                "scale": style_strength,
            }
        )

        if output:
            image_url = output[0] if isinstance(output, list) else str(output)
            response = requests.get(image_url)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.content)

            return str(output_path)

        return None

    try:
        return retry_with_backoff(do_generate)
    except Exception as e:
        print(f"Error: {e}")
        return None


def generate_with_controlnet_depth(
    depth_map_path: Path,
    prompt: str,
    output_path: Path,
    strength: float = 0.8
) -> Optional[str]:
    """
    Generate using ControlNet depth (SD 1.5 based).
    Fastest option.
    """
    depth_uri = image_to_data_uri(depth_map_path)
    enhanced_prompt = f"{prompt}, {ANTI_TEXT_POSITIVE}"

    def do_generate():
        output = replicate.run(
            "jagilley/controlnet-depth:cedd8b81a3630cb9e0a10e69438e2d369d3c0a7eb0bad7fb2365979e89e20276",
            input={
                "image": depth_uri,
                "prompt": enhanced_prompt,
                "negative_prompt": NEGATIVE_PROMPT,
                "num_inference_steps": 30,
                "guidance_scale": 7.5,
                "a_prompt": "best quality, high resolution, photorealistic, no text, clean",
                "n_prompt": NEGATIVE_PROMPT,
            }
        )

        if output:
            image_url = output[0] if isinstance(output, list) else str(output)
            response = requests.get(image_url)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.content)

            return str(output_path)

        return None

    try:
        token = os.environ.get("REPLICATE_API_TOKEN")
        if not token:
            raise ValueError("REPLICATE_API_TOKEN not set in environment")
        return retry_with_backoff(do_generate)
    except Exception as e:
        raise RuntimeError(f"ControlNet generation failed: {type(e).__name__}: {e}") from e


def batch_generate(
    depth_maps_dir: Path,
    prompt: str,
    output_dir: Path,
    model: str = "flux",
    strength: float = 0.75,
    max_workers: int = 1,  # Reduced from 3 to avoid rate limits
    min_delay: float = 8.0,  # Minimum seconds between requests
    seat_ids: Optional[List[str]] = None  # Optional: specific seats to generate
) -> List[str]:
    """
    Generate images for depth maps in a directory.

    Args:
        depth_maps_dir: Directory containing depth map PNGs
        prompt: Generation prompt
        output_dir: Where to save generated images
        model: Model to use (flux, sdxl, controlnet)
        strength: ControlNet strength
        max_workers: Parallel workers (default 1 to avoid rate limits)
        min_delay: Minimum delay between requests in seconds
        seat_ids: Optional list of specific seat IDs to generate
    """

    generators = {
        "sdxl": generate_with_sdxl_depth,
        "flux": generate_with_flux_depth,
        "controlnet": generate_with_controlnet_depth
    }
    generate_fn = generators.get(model, generate_with_flux_depth)

    # Get depth maps (filtered by seat_ids if provided)
    if seat_ids:
        depth_maps = []
        for seat_id in seat_ids:
            depth_path = depth_maps_dir / f"{seat_id}_depth.png"
            if depth_path.exists():
                depth_maps.append(depth_path)
            else:
                print(f"Warning: No depth map for {seat_id}")
    else:
        depth_maps = list(depth_maps_dir.glob("*_depth.png"))

    if not depth_maps:
        print(f"No depth maps found in {depth_maps_dir}")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    total = len(depth_maps)
    last_request_time = 0

    print(f"Generating {total} images using {model}...")
    print(f"Prompt: {prompt[:80]}...")
    print(f"Rate limit: {min_delay}s between requests, {max_workers} worker(s)")

    def process_one(depth_map: Path, index: int) -> tuple:
        nonlocal last_request_time

        seat_id = depth_map.stem.replace("_depth", "")
        output_path = output_dir / f"{seat_id}_final.jpg"

        # Enforce minimum delay between requests
        elapsed = time.time() - last_request_time
        if elapsed < min_delay and last_request_time > 0:
            wait_time = min_delay - elapsed
            print(f"  Waiting {wait_time:.1f}s before next request...")
            time.sleep(wait_time)

        last_request_time = time.time()

        result = generate_fn(
            depth_map_path=depth_map,
            prompt=prompt,
            output_path=output_path,
            strength=strength
        )

        return seat_id, result

    # Sequential processing for better rate limit handling
    if max_workers == 1:
        for i, depth_map in enumerate(depth_maps):
            seat_id, result = process_one(depth_map, i)
            if result:
                results.append(result)
                print(f"[{i+1}/{total}] ✓ {seat_id}")
            else:
                print(f"[{i+1}/{total}] ✗ {seat_id} failed")
    else:
        # Parallel processing (not recommended with rate limits)
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_one, dm, i): dm for i, dm in enumerate(depth_maps)}

            for future in as_completed(futures):
                completed += 1
                seat_id, result = future.result()

                if result:
                    results.append(result)
                    print(f"[{completed}/{total}] ✓ {seat_id}")
                else:
                    print(f"[{completed}/{total}] ✗ {seat_id} failed")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate venue images from depth maps")
    parser.add_argument("--venue", default="pnc_arena", help="Venue ID")
    parser.add_argument("--event", default="hockey", help="Event type")
    parser.add_argument("--model", default="flux", choices=["sdxl", "flux", "controlnet"],
                        help="Model to use (flux recommended)")
    parser.add_argument("--strength", type=float, default=0.75, help="ControlNet strength")
    parser.add_argument("--workers", type=int, default=1, help="Parallel API calls (default 1 for rate limits)")
    parser.add_argument("--delay", type=float, default=8.0, help="Minimum delay between requests (seconds)")
    parser.add_argument("--seats", type=str, nargs="+", help="Specific seat IDs to generate (e.g., 101_A_12)")
    args = parser.parse_args()
    
    # Paths
    script_dir = Path(__file__).parent
    venue_dir = script_dir.parent / "venues" / args.venue
    depth_maps_dir = venue_dir / "outputs" / "depth_maps"
    output_dir = venue_dir / "outputs" / "final_images"
    
    # Check for REPLICATE_API_TOKEN
    if not os.environ.get("REPLICATE_API_TOKEN"):
        print("Error: Set REPLICATE_API_TOKEN environment variable")
        print("  export REPLICATE_API_TOKEN=r8_...")
        return
    
    # Load venue config for prompt
    config_path = venue_dir / "config.json"
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        prompt_details = config.get("prompt_details", {})
        base_prompt = prompt_details.get("base", config.get("name", "Arena"))
        event_prompt = prompt_details.get(args.event, "")
        prompt = f"{base_prompt}, {event_prompt}, realistic photography, packed crowd, high detail, professional photo"
    else:
        prompt = f"{args.venue} arena seat view, {args.event}, packed crowd, realistic photography"
    
    print(f"\nVenue: {args.venue}")
    print(f"Event: {args.event}")
    print(f"Model: {args.model}")
    print(f"Depth maps: {depth_maps_dir}")
    print(f"Output: {output_dir}")
    
    results = batch_generate(
        depth_maps_dir=depth_maps_dir,
        prompt=prompt,
        output_dir=output_dir,
        model=args.model,
        strength=args.strength,
        max_workers=args.workers,
        min_delay=args.delay,
        seat_ids=args.seats
    )
    
    print(f"\n{'='*40}")
    print(f"Generated {len(results)} images")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
