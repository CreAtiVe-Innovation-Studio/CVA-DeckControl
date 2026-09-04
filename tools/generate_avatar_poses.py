#!/usr/bin/env python3
"""Generiert reaktive Mii/VTuber-Posen fuer den geplanten Radar-Charakter,
per lokalem ComfyUI (Z-Image-Turbo + valent1n_Lora_v1-Checkpoint bei Step 500,
ueber den pc42-Netzwerk-Share unter models/loras/ kopiert). Pro Event-
Kategorie mehrere zufaellig gewaehlte Posen statt einer starren Sequenz.

Die valent1n-LoRA wurde mit exakt diesem Beschreibungs-Vokabular gecaptioned
("Comic-style boy with medium-length brown hair, wearing a pink T-shirt, blue
jeans, and gray sneakers") - ohne diese Ankerworte im Prompt driftet das
Ergebnis zu einem generischen Anime-Girl ab, weil die schwache LoRA-Signatur
(nur 500/1600 Trainingsschritte) von den Basismodell-Priors ueberstimmt wird.
Ausserdem: nur Close-up/Bust-Shots (kein Full-Body - bei 100x100px auf der
Taste sonst unlesbar), damit spaeter per Hintergrund-Freistellung (siehe
remove_backgrounds.py) sauber ausgeschnitten werden kann.

Ausfuehren: python3 tools/generate_avatar_poses.py
Ergebnis landet in assets/generated-avatars/<kategorie>/<slug>.png
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import requests

COMFYUI_URL = "http://127.0.0.1:8188"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "generated-avatars"

UNET_NAME = "z_image_turbo_nvfp4.safetensors"
CLIP_NAME = "qwen_3_4b_fp4_mixed.safetensors"
VAE_NAME = "ae.safetensors"
LORA = "valent1n_zimage_v1_step500.safetensors"
LORA_STRENGTH = 1.0

BASE = (
    "valent1n, Comic-style boy with medium-length brown hair, wearing a pink "
    "T-shirt, blue jeans, and gray sneakers"
)
NEGATIVE = (
    "text, watermark, signature, blurry, extra limbs, bad anatomy, deformed, "
    "low quality, jpeg artifacts, multiple people, cropped head, full body, nsfw"
)

# Jede Kategorie entspricht einem Radar-Event; pro Kategorie mehrere Posen,
# die zur Laufzeit ZUFAELLIG (nicht der Reihe nach) durchgewechselt werden.
# Alles bewusst als "close-up" formuliert (Trainings-Caption-Vokabular) statt
# full-body, da die Taste nur 100x100px hat.
POSES: dict[str, list[str]] = {
    "idle": [
        f"{BASE}, close-up, neutral face, relaxed, soft smile, looking at viewer",
        f"{BASE}, close-up, big smile, looking at viewer",
        f"{BASE}, close-up, smirk, looking to the side",
        f"{BASE}, close-up, half-closed eyes, sleepy, yawning",
        f"{BASE}, close-up, big smile, thumbs up near face, looking at viewer",
    ],
    "camera_lowfly": [
        f"{BASE}, close-up, holding a camera up near face, excited, looking up",
        f"{BASE}, close-up, pointing up, wide excited eyes, looking up",
        f"{BASE}, close-up, holding binoculars up to eyes, amazed",
        f"{BASE}, close-up, camera raised near face, focused expression, looking up",
        f"{BASE}, close-up, mouth open in awe, looking up, camera visible near face",
    ],
    "gewitter": [
        f"{BASE}, close-up, worried expression, looking up, holding umbrella handle",
        f"{BASE}, close-up, nervous expression, gripping umbrella tightly, looking up",
        f"{BASE}, close-up, peeking out from under umbrella, cautious expression",
        f"{BASE}, close-up, uneasy expression, hugging umbrella close to chest",
        f"{BASE}, close-up, worried, glancing to the side, holding umbrella",
    ],
    "gewitter_massive": [
        f"{BASE}, close-up, screaming in fear, covering ears, dramatic lightning in background",
        f"{BASE}, close-up, terrified expression, hiding under umbrella",
        f"{BASE}, close-up, covering eyes with both hands, panicked expression",
        f"{BASE}, close-up, eyes squeezed shut, scared expression, curled shoulders",
        f"{BASE}, close-up, flinching back, wide terrified eyes, hands raised defensively",
    ],
    "regierungsflugzeug": [
        f"{BASE}, close-up, serious formal expression, saluting",
        f"{BASE}, close-up, curious raised eyebrow, pointing upward",
        f"{BASE}, close-up, cool confident expression, looking up",
        f"{BASE}, close-up, alert formal expression, straightened posture",
        f"{BASE}, close-up, surprised curious look, hand shielding eyes, looking up",
    ],
    "wind": [
        f"{BASE}, close-up, holding onto hair, hair blowing sideways in strong wind",
        f"{BASE}, close-up, squinting against strong wind, hair whipping sideways",
        f"{BASE}, close-up, shielding face with one arm, hair flying in wind",
        f"{BASE}, close-up, bracing against gusty wind, hair blown back",
        f"{BASE}, close-up, surprised, chasing after a flying hat, wind blowing",
    ],
    "heli_tief": [
        f"{BASE}, close-up, curious tilted head, hand shielding eyes, looking up",
        f"{BASE}, close-up, covering ears from loud noise, squinting, looking up",
        f"{BASE}, close-up, pointing excitedly upward, wide eyes, hair blown by wind",
        f"{BASE}, close-up, startled, ducking slightly, hands near head",
        f"{BASE}, close-up, delighted expression, waving up at the sky",
    ],
    "klarer_himmel": [
        f"{BASE}, close-up, content smile, eyes closed, peaceful expression",
        f"{BASE}, close-up, cheerful bright smile, stretching",
        f"{BASE}, close-up, eyes closed, serene relaxed expression",
        f"{BASE}, close-up, happy squinting smile, shielding eyes from sun",
        f"{BASE}, close-up, joyful carefree big smile, looking at viewer",
    ],
    "viel_verkehr": [
        f"{BASE}, close-up, overwhelmed excited expression, pointing to the side",
        f"{BASE}, close-up, dizzy excited expression, looking around",
        f"{BASE}, close-up, wide eyes, overwhelmed delighted expression, hands near face",
        f"{BASE}, close-up, amazed expression, eyes wide, looking side to side",
        f"{BASE}, close-up, thrilled excited expression, mouth open",
    ],
}


def build_workflow(prompt: str, seed: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": UNET_NAME, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": CLIP_NAME, "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}},
        "12": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {"model": ["1", 0], "lora_name": LORA, "strength_model": LORA_STRENGTH},
        },
        "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "7": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["12", 0], "shift": 3}},
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["7", 0], "positive": ["5", 0], "negative": ["11", 0], "latent_image": ["4", 0],
                "seed": seed, "steps": 8, "cfg": 1.0, "sampler_name": "res_multistep",
                "scheduler": "simple", "denoise": 1.0,
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "valent1n_pose"}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["2", 0]}},
    }


def generate_one(slug: str, prompt: str, seed_offset: int) -> Path | None:
    seed = (int(time.time()) + seed_offset) % (2**32)
    workflow = build_workflow(prompt, seed)
    client_id = str(uuid.uuid4())
    resp = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=30)
    resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]
    print(f"[{slug}] eingereiht: {prompt_id}")

    # Grosszuegiges Zeitfenster - der erste Job nach einem Modell-Wechsel laedt
    # den ~7GB-Checkpoint vom Netzwerk-Share, das kann auf der langsamen HDD
    # mehrere Minuten dauern (danach bleibt das Modell im VRAM gecacht).
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        time.sleep(2)
        r = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10)
        if r.status_code != 200:
            continue
        history = r.json()
        if prompt_id not in history:
            continue
        outputs = history[prompt_id].get("outputs", {})
        for node_out in outputs.values():
            images = node_out.get("images", [])
            if images:
                info = images[0]
                img_resp = requests.get(
                    f"{COMFYUI_URL}/view",
                    params={"filename": info["filename"], "subfolder": info.get("subfolder", ""), "type": info.get("type", "output")},
                    timeout=30,
                )
                img_resp.raise_for_status()
                out_path = OUT_DIR / f"{slug}.png"
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(img_resp.content)
                print(f"[{slug}] gespeichert: {out_path}")
                return out_path
    print(f"[{slug}] TIMEOUT")
    return None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    i = 0
    for category, prompts in POSES.items():
        for idx, prompt in enumerate(prompts, start=1):
            slug = f"{category}/{category}_{idx}"
            try:
                generate_one(slug, prompt, seed_offset=i)
            except Exception as exc:
                print(f"[{slug}] FEHLER: {exc}")
            i += 1


if __name__ == "__main__":
    main()
