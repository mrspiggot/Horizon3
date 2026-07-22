"""Van Gogh header illustrations — an abstract painting that evokes THIS article's finding.

Two principles, both learned the hard way:

  1. The picture reflects the ARTICLE, not the persona. An LLM art-director reads the article's actual
     finding — the specific reading the executed model produced this run — and invents a van Gogh-style
     scene that evokes its essence. Change the data and the finding changes and so does the painting.
     There is no fixed per-persona canvas.
  2. It is an evocative PAINTING, not an infographic. The "no numbers / no diffusion" rule belongs to
     the deterministic infographic (a diffusion model cannot render exact figures). It does NOT apply
     here: this image may use any figurative or symbolic elements the art-director judges evocative.

Backends, in `auto` order: local ComfyUI (SDXL + van_gogh LoRA) if COMFYUI_URL answers; else the OpenAI
Images API (gpt-image-1) — the working backend on this machine (ComfyUI is not installed here); else a
PIL placeholder (last-resort offline stand-in, never a deliverable). Results are cached (png + the scene
metadata) so a re-run never re-bills. No import from Horizon2; this module never touches a NumberObject.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import random
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_WORKFLOW = _HERE / "comfyui_workflow.json"
CACHE_DIR = _HERE / ".cache"
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")


# A rotating well of van Gogh VISUAL REGISTERS — palette, light, brushwork and mood only, NEVER the
# subjects. Each run draws one at random so successive articles differ in colour and feeling, but the
# SUBJECTS are always invented fresh from the article's finding. The named canvas is a shorthand for a
# look, not a scene to reproduce — the prompt forbids depicting the painting's own subjects/composition.
_PALETTE: dict[str, str] = {
    "The Starry Night": "a churning nocturne — deep cobalt and indigo swept with swirling turbulence, "
        "luminous yellow-white points of light, restless spiralling brushwork, ominous yet transcendent",
    "Café Terrace at Night": "warm lamplight against deep-blue night — pools of amber and gold set "
        "against cool dark, an intimate human warmth held against the surrounding shadow",
    "The Night Café": "a feverish, oppressive palette — clashing blood-red and acid-green under a harsh "
        "yellow glare, airless tension and unease, garish claustrophobic heat",
    "Wheat Stack in Provence": "high-noon Provençal heat — saturated amber, ochre and gold under a wide "
        "bleached sky, heavy stillness and thick sun-baked impasto",
    "The Red Vineyard": "a blazing low sun — molten red, orange and violet flooding everything, fiery "
        "reflected light, collective warmth and toil at day's end",
    "Cypresses": "restless wind-swept greens and blues — twisting flame-like verticals, a rolling "
        "churning sky, coiled kinetic energy and disquiet",
    "The Bedroom in Arles": "an enclosed interior calm — flat planes of ochre, lilac and sky-blue, a "
        "skewed intimate perspective, quiet refuge and repose",
    "The Yellow House": "brilliant sun-struck daylight — vivid chrome-yellow against intense cobalt, "
        "clear hard-edged shadows, bright optimism edged with exposure",
    "Daubigny's Garden": "lush verdant abundance — dense greens dappled with flower-colour, soft diffuse "
        "summer light, tranquil fertility and ease",
}


# ── the art-director: article finding → a van Gogh scene that evokes it ─────────────────────────────
def art_director(title: str, decision: str, finding: str) -> dict:
    """Turn THIS article's finding into a vivid van Gogh-style scene. Returns {scene, caption, source}.
    A visual register (palette/light/mood) is drawn at random from _PALETTE for variety, but the SUBJECTS
    are always invented from the finding — never the source painting. Falls back if the LLM is down."""
    painting, register = random.choice(list(_PALETTE.items()))
    try:
        from pydantic import BaseModel, Field

        from ..studio.llm import get_llm

        class Scene(BaseModel):
            scene: str = Field(description="2-4 sentences describing ONE vivid van Gogh-style oil "
                               "painting that evokes the essence of the finding — subjects, "
                               "composition, palette, light, brushwork, mood. Anchor it in ONE "
                               "concrete, specific subject drawn from the finding's own particulars "
                               "(the actual mechanism, actors, place, object or tension it names), not "
                               "a generic emblem. Figurative/symbolic elements welcome; do NOT depict "
                               "charts or graphs, and do NOT default to a lone figure walking a "
                               "road/path/furrow toward a post, signpost, gate or marker, a rising or "
                               "setting sun, or a fork in the road.")
            caption: str = Field(description="a short metaphor title, <= 8 words")

        llm = get_llm().with_structured_output(Scene)
        prompt = (
            "You are the art director for a serious financial publication. Every article ships with ONE "
            "header illustration: an abstract oil painting in the unmistakable style of Vincent van Gogh "
            "that evokes the ESSENCE of the article's specific finding — its mood, tension and message — "
            "so a reader who merely glances at the picture already senses what the piece is about and how "
            "it feels. It is an evocative PAINTING, not an infographic: invent figurative or symbolic "
            "imagery freely. The SUBJECTS of the painting must come ENTIRELY from THIS article's finding "
            "— the objects, figures, landscape or event you choose must stand for what the finding says. "
            "\n\nRender it in ONE fixed visual register — the palette, light, brushwork and mood of van "
            f"Gogh's «{painting}»: {register}. Use that register ONLY for how the picture LOOKS and FEELS. "
            f"Do NOT depict «{painting}» itself or any of its subjects — no reuse of that painting's "
            "scene, objects or composition. Two articles handed the same register must still yield "
            "completely different pictures, because their subjects come from different findings. Do not "
            "depict charts or graphs.\n\n"
            "AVOID THE HOUSE CLICHÉ. Do not reach for the stock 'economic destiny' emblem — a lone "
            "hatted figure trudging along a winding road or furrow toward a distant post, signpost, "
            "gate or marker; a sun rising or setting on the horizon; a crossroads or a fork in the "
            "road. Those are exhausted and say nothing specific — a reader could paste them onto any "
            "article. Instead SEIZE ONE CONCRETE PARTICULAR from THIS finding — the specific force, "
            "object, actor, threshold or reversal it describes — and build the whole picture around "
            "that one thing, so this image could not be swapped onto a different piece.\n\n"
            f"Article headline: {title}\n"
            f"The decision it informs: {decision}\n"
            f"The article's actual finding (this is what the painting must evoke): {finding}\n\n"
            "Invent the single scene that best captures the essence of THAT finding.")
        r = llm.invoke(prompt)
        return {"scene": r.scene.strip(), "caption": r.caption.strip(), "source": painting}
    except Exception:
        head = " ".join((finding or title).split())[:240]
        return {"scene": f"A van Gogh-style landscape evoking: {head}", "caption": (title or "")[:60],
                "source": painting}


def _build_prompt(scene: str) -> str:
    """The scene carries the meaning; here we only pin the van Gogh idiom. No content restrictions — it
    is an abstract painting, not a numeric surface."""
    return ("Oil painting in the unmistakable style of Vincent van Gogh — thick impasto, bold visible "
            "brushstrokes, vivid expressive post-impressionist colour, emotionally charged composition. "
            + scene)


# ── backends ─────────────────────────────────────────────────────────────────────────────────────
def _comfyui_up() -> bool:
    try:
        import requests
        requests.get(f"{COMFYUI_URL}/system_stats", timeout=2).raise_for_status()
        return True
    except Exception:
        return False


def _comfyui(prompt: str, seed: int, *, timeout: float = 180.0) -> bytes:
    import requests

    wf = json.loads(_WORKFLOW.read_text())
    wf["6"]["inputs"]["text"] = prompt
    wf["3"]["inputs"]["seed"] = seed
    r = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": wf}, timeout=10)
    r.raise_for_status()
    prompt_id = r.json()["prompt_id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        h = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
        h.raise_for_status()
        hist = h.json()
        if prompt_id in hist:
            for node in hist[prompt_id]["outputs"].values():
                for img in node.get("images", []):
                    v = requests.get(f"{COMFYUI_URL}/view", params={
                        "filename": img["filename"], "subfolder": img.get("subfolder", ""),
                        "type": img.get("type", "output")}, timeout=30)
                    v.raise_for_status()
                    return v.content
            raise RuntimeError("ComfyUI history had no image output")
        time.sleep(1.5)
    raise TimeoutError("ComfyUI render timed out")


def _load_openai_key() -> str | None:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None
    for p in (Path.home() / "PycharmProjects/Horizon3/.env",
              Path.home() / "PycharmProjects/kalshi/.env"):
        if p.exists():
            load_dotenv(p, override=False)
    return os.environ.get("OPENAI_API_KEY")


def _openai_image(prompt: str) -> bytes:
    from openai import OpenAI

    key = _load_openai_key()
    if not key:
        raise RuntimeError("no OPENAI_API_KEY available")
    client = OpenAI(api_key=key)
    # gpt-image-1 only — dall-e-3 returns 400 "model does not exist" on this account (H2's finding).
    r = client.images.generate(model="gpt-image-1", prompt=prompt, size="1536x1024", n=1)
    d = r.data[0]
    if getattr(d, "b64_json", None):
        return base64.b64decode(d.b64_json)
    if getattr(d, "url", None):
        import requests
        return requests.get(d.url, timeout=60).content
    raise RuntimeError("OpenAI returned no image data")


def _pil_painterly(key: str, *, width: int = 1344, height: int = 768) -> bytes:
    """Last-resort offline stand-in — an abstract impasto field seeded by `key`, in a warm van Gogh
    palette. NOT a deliverable; only so the pipeline runs with no ComfyUI and no OpenAI key."""
    import math
    import random

    from PIL import Image, ImageDraw, ImageFilter

    rng = random.Random(int(hashlib.sha1(key.encode()).hexdigest()[:8], 16))
    base = [(int(40 + rng.random() * 60), int(40 + rng.random() * 70), int(70 + rng.random() * 80))]
    pal = base + [(230, 180, 40), (210, 110, 40), (60, 120, 150), (235, 225, 190)]
    img = Image.new("RGB", (width, height), pal[0])
    draw = ImageDraw.Draw(img, "RGBA")
    flow = rng.uniform(-1, 1)
    for _ in range(5000):
        x, y = rng.randint(0, width), rng.randint(0, height)
        ang = flow + rng.uniform(-0.5, 0.5)
        length, w = rng.randint(14, 44), rng.randint(3, 9)
        c = pal[rng.randint(0, len(pal) - 1)]
        c = tuple(max(0, min(255, v + rng.randint(-22, 22))) for v in c)
        draw.line([(x, y), (x + int(length * math.cos(ang)), y + int(length * math.sin(ang)))],
                  fill=c + (rng.randint(150, 235),), width=w)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── public API ───────────────────────────────────────────────────────────────────────────────────
def _cache_paths(key: str, backend: str) -> tuple[Path, Path]:
    tag = hashlib.sha1(f"{key}|{backend}".encode()).hexdigest()[:12]
    return CACHE_DIR / f"{tag}.png", CACHE_DIR / f"{tag}.json"


def illustration_png(finding: str, *, title: str = "", decision: str = "", cache_key: str | None = None,
                     backend: str = "auto", force: bool = False) -> tuple[str, dict]:
    """Return (base64 PNG, meta) for a van Gogh header that evokes THIS article's `finding`. `meta` =
    {scene, caption, prompt}. `backend`: 'comfyui' | 'openai' | 'pil' | 'auto'. Cached (png + meta) by
    `cache_key` (defaults to the finding) so a re-run never re-bills."""
    key = cache_key or finding
    use = backend
    if use == "auto":
        use = "comfyui" if _comfyui_up() else ("openai" if _load_openai_key() else "pil")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    png_p, meta_p = _cache_paths(key, use)
    if png_p.exists() and meta_p.exists() and not force:
        return base64.b64encode(png_p.read_bytes()).decode(), json.loads(meta_p.read_text())

    art = art_director(title, decision, finding)
    prompt = _build_prompt(art["scene"])
    if use == "comfyui":
        try:
            data = _comfyui(prompt, int(hashlib.sha1(key.encode()).hexdigest()[:8], 16))
        except Exception:
            data = _pil_painterly(key)
    elif use == "openai":
        data = _openai_image(prompt)
    else:
        data = _pil_painterly(key)

    meta = {**art, "prompt": prompt}
    png_p.write_bytes(data)
    meta_p.write_text(json.dumps(meta))
    return base64.b64encode(data).decode(), meta


def illustration_block(finding: str, *, title: str = "", decision: str = "", cache_key: str | None = None,
                       backend: str = "auto", block_id: str = "illus"):
    """A ready `illustration_slot` Block carrying the base64 image (no numbers in the DOM — the slot's
    isolation is about the page's text, not the painting's content). Returns (Block, meta)."""
    from ..infographic.schema import Block
    b64, meta = illustration_png(finding, title=title, decision=decision, cache_key=cache_key, backend=backend)
    return Block(id=block_id, type="illustration_slot", chart_png=b64), meta
