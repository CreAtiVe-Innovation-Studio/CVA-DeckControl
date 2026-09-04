#!/usr/bin/env python3
"""Generiert kleine App-Icons per ComfyUI (Z-Image-Turbo, gleiche Basis wie
ghost_trail_v1's Workflow, aber ohne den LoRA-Teil - reines Text-zu-Bild).

Ausfuehren: python3 tools/generate_app_icons.py
Ergebnis landet in assets/generated-icons/<slug>.png
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import requests

COMFYUI_URL = "http://127.0.0.1:8188"
OUT_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "generated-icons"

STYLE = (
    "flat minimalist app icon, single bold instantly-recognizable pictogram, "
    "vector icon style like Feather or Material icons, solid plain black "
    "background with no scene/texture/gradient behind it, one vivid neon "
    "color accent glow (cyan, magenta or orange), centered composition, "
    "thick clean line-art, glowing neon outline, no text, no watermark, "
    "no logo text, no realistic photo, futuristic Elgato Stream Deck icon style"
)

ICONS = {
    "firefox": "a stylized orange-red fox curled around a blue globe",
    "word": "a blue document page with folded corner and horizontal text lines",
    "powerpoint": "an orange presentation slide with a bar chart",
    "teams": "two overlapping purple people silhouettes, chat bubble",
    "geogebra": "a graph with a curved function line and coordinate axes, orange and blue",
    "whiteboard": "a rectangular whiteboard on an easel stand with a marker pen drawing a checkmark on it",
    "claude": "a soft warm orange abstract star burst symbol, friendly AI assistant",
    "anki": "a stack of flashcards with a red circular arrow, spaced repetition",
    "hotkey": "a single glowing keyboard key with a star symbol",
    "website": "a globe with latitude and longitude lines, browser window frame",
    "page_next": "a simple bold right-pointing arrow chevron",
    "page_previous": "a simple bold left-pointing arrow chevron",
    "switch_profile": "a circular refresh arrow icon, two curved arrows forming a loop",
    "screenshot": "a simple retro camera icon, rectangular body with a round lens in the middle, photo capture symbol",
    "volume_up": "a speaker cone icon with a bold thick upward-pointing arrow next to it, turn volume up symbol",
    "volume_down": "a speaker cone icon with a bold thick downward-pointing arrow next to it, turn volume down symbol",
    "mute": "a speaker cone icon with a glowing diagonal slash through it",
    "play_pause": "a rounded glowing play triangle merged with two pause bars",
    "stop": "a simple bold filled square inside a circle outline, media player stop button symbol",
    "next_track": "two bold triangles pointing right stacked side by side next to a vertical bar, skip to next track media player icon",
    "prev_track": "two bold triangles pointing left stacked side by side next to a vertical bar, skip to previous track media player icon",
    "shuffle": "two crossing arrows forming an X, shuffle symbol",
    "speaker_output": "a pair of stereo speakers icon, glowing outline",
    "headphones": "a modern over-ear headphone icon, glowing outline",
    "microphone": "a microphone icon with a glowing pop-filter ring",
    "folder": "a sleek closed folder icon with a glowing edge outline",
    "freecad": "a glowing wireframe gear merged with a cube, CAD design symbol",
    "comfyui": "connected nodes and flowing lines, generative pipeline symbol",
    "studyos": "an open book with a glowing brain circuit overlay",
    "ghost_trail": "a stealthy ghost silhouette leaving a glowing trail line",
    "cva_innovations": "abstract glowing letters C and V interlocked, tech logo style",
    "chatgpt": "a stylized swirling knot symbol, soft green glow",
    "gemini": "two overlapping four-pointed glowing stars, twin symbol",
    "huggingface": "a friendly minimal robot face, orange glow, rounded antenna",
    "undo": "a curved counter-clockwise glowing arrow",
    "redo": "a curved clockwise glowing arrow",
    "save": "a glowing floppy disk icon, minimalist",
    "discord": "a rounded glowing game controller face mascot silhouette",
    "steam": "a glowing stylized planet-and-orbit game symbol",
    "mail": "a simple minimalist closed envelope outline icon, single cyan neon glow accent, no other colors",
    "whatsapp": "a glowing chat bubble with a phone handset silhouette inside",
    "code_editor": "angle brackets forming a glowing code symbol",
    "terminal": "a glowing terminal window with a blinking cursor prompt",
    "git": "three connected glowing circles forming a branch symbol",
    "session_start": "a bold glowing rocket launching upward, start session symbol",
    "window_layout": "a single computer monitor screen with its rectangle split into a full left panel and a smaller right panel by a bold glowing line, window tiling layout symbol",
    "keepassxc": "a glowing shield with a keyhole in the center, password vault symbol",
    "system_monitor": "a glowing speedometer gauge with a needle, system performance symbol",
    "nfs_rivals": "a glowing sports car speeding sideways with motion streak lines, street racing symbol",
    "minecraft_dashboard": "a glowing blocky pixelated cube stack, server admin symbol",
    "most_wanted_game": "a glowing wanted poster with a target crosshair in the middle",
    "rc_drift": "a glowing small remote control car drifting sideways with tire smoke lines",
    "rc_hangar": "a glowing hangar building with a large open arched door",
    "grafana": "multiple glowing colorful bar-chart columns of different heights, analytics dashboard symbol",
    "prometheus": "a single glowing flame icon, metrics collector symbol",
    "garten_gewaechshaus": "a glowing greenhouse building with plant sprouts inside",
    "lernkarten": "a glowing stack of flashcards with a small lightbulb above",
    "gimp_icon": "a glowing paintbrush crossed with a magic wand selection tool, image editing symbol",
    "spotify": "a glowing circle with three curved soundwave arcs inside, music streaming symbol",
    "home_assistant": "a glowing simple house outline with a small heart pulse line inside, smart home symbol",
    "ha_light": "a glowing lightbulb icon with radiating light lines",
    "ha_blinds": "a glowing window icon with horizontal blind slats",
    "cooking_os": "a glowing chef hat above a cooking pot",
    "cover_up": "a glowing window blinds icon with a bold upward arrow above it",
    "cover_down": "a glowing window blinds icon with a bold downward arrow above it",
    "radar_icon": "a glowing radar screen with concentric range rings and a sweeping line, one small blip dot",
    "math_aufgaben_app": "a glowing calculator with a checkmark on its screen",
    "youtube": "a glowing rounded rectangle with a play triangle inside, video platform symbol",
    "mathlern": "a glowing stylized city skyline with a map pin above it, gamified learning app symbol",
    "gaming_controller": "a glowing modern game controller/gamepad icon",
    "streaming_kassengold": "a glowing treasure chest overflowing with gold coins",
    "streaming_apfelbaumarmee": "a small stylized apple tree with glowing red apples, orchard symbol",
    "streaming_busch": "a simple rounded green bush plant icon",
    "streaming_auto": "a simple side-view car icon",
    "streaming_muell": "a trash can icon with a lid",
    "streaming_abflug": "an airplane icon angled upward, taking off symbol",
    "streaming_pov_zusammen": "two overlapping glowing eye icons, shared point of view symbol",
    "streaming_pov_valentin": "a glowing eye icon with a small blue ring accent, point of view camera symbol",
    "streaming_pov_anja": "a glowing eye icon with a small pink flower accent, point of view camera symbol",
    "streaming_pov_cindy": "a glowing eye icon with a small purple star accent, point of view camera symbol",
    "streaming_pause": "two bold vertical glowing bars, pause symbol",
    "streaming_intro_song": "a musical note with a bold upward arrow beside it, song intro symbol",
    "streaming_outro_song": "a musical note with a bold downward arrow beside it, song outro symbol",
    "streaming_sieg": "a glowing golden trophy icon, victory symbol",
    "streaming_technik": "a glowing gear and wrench crossed together, technical settings symbol",
    "streaming_hai": "a simple shark fin icon cutting through a wave line",
    "streaming_eispalast": "a crystalline ice castle icon with pointed towers",
}


def build_workflow(prompt: str, seed: int) -> dict:
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_nvfp4.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b_fp4_mixed.safetensors", "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": f"{prompt}, {STYLE}", "clip": ["2", 0]}},
        "7": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3}},
        "8": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["7", 0], "positive": ["5", 0], "negative": ["11", 0], "latent_image": ["4", 0],
                "seed": seed, "steps": 8, "cfg": 1.0, "sampler_name": "res_multistep",
                "scheduler": "simple", "denoise": 1.0,
            },
        },
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "streamdeck_icon"}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": "text, watermark, blurry, photo, realistic, cluttered", "clip": ["2", 0]}},
    }


def generate_one(slug: str, prompt: str) -> Path | None:
    seed = int(time.time()) % (2**32)
    workflow = build_workflow(prompt, seed)
    client_id = str(uuid.uuid4())
    resp = requests.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=30)
    resp.raise_for_status()
    prompt_id = resp.json()["prompt_id"]
    print(f"[{slug}] eingereiht: {prompt_id}")

    deadline = time.monotonic() + 120
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
                out_path.write_bytes(img_resp.content)
                print(f"[{slug}] gespeichert: {out_path}")
                return out_path
    print(f"[{slug}] TIMEOUT")
    return None


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for slug, prompt in ICONS.items():
        try:
            generate_one(slug, prompt)
        except Exception as exc:
            print(f"[{slug}] FEHLER: {exc}")


if __name__ == "__main__":
    main()
