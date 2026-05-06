#!/usr/bin/env python3
"""
ComfyUI MCP Server — Version Tkinter
---------------------------------------
- Fenêtre popup native Python (Tkinter + Pillow)
- Détection automatique des nœuds de workflow
- Workflow envoyé TEL QUEL, seuls prompt et seed sont modifiés
- Clic sur l'image → ouvre le dossier dans l'Explorateur Windows

Installation :
    pip install mcp Pillow

Configuration AnythingLLM (mcp.json) :
    {
      "mcpServers": {
        "comfyui": {
          "command": "python",
          "args": ["D:\\MCP\\comfyui_mcp_server.py"],
          "env": {}
        }
      }
    }
"""

import asyncio
import copy
import json
import os
import random
import re
import subprocess
import sys
import time
import tkinter as tk
import traceback
import urllib.request
import uuid
from pathlib import Path
from threading import Thread

from PIL import Image, ImageTk

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR    = Path(__file__).resolve().parent
COMFYUI_URL   = "http://127.0.0.1:8188"
OUTPUT_FOLDER = Path("D:/") / ".ComfyUI" / "output"

POLL_INTERVAL_S = 2.0
POLL_TIMEOUT_S  = 300.0


def log(msg: str):
    """Logs vers stderr uniquement — stdout est réservé au protocole MCP."""
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Popup Tkinter
# ---------------------------------------------------------------------------

# Référence globale — permet de fermer la fenêtre précédente avant d'en ouvrir une nouvelle
_popup_root = None


def close_popup():
    """Ferme la fenêtre popup active si elle existe — appelé au début d'une nouvelle génération."""
    global _popup_root
    if _popup_root is not None:
        try:
            _popup_root.after(0, _popup_root.destroy)
        except Exception:
            pass
        _popup_root = None


def show_tkinter_popup(image_path: Path, prompt: str, seed, width, height, steps):
    """
    Fenêtre popup native avec navigation ◀ ▶ dans toutes les images du dossier output.
    Lancée dans un thread séparé.
    """
    global _popup_root

    def run_ui():
        global _popup_root
        try:
            root = tk.Tk()
            _popup_root = root

            def on_close():
                global _popup_root
                _popup_root = None
                root.destroy()

            root.title("ComfyUI — Image générée")
            root.protocol("WM_DELETE_WINDOW", on_close)

            win_w, win_h = 360, 490
            screen_w = root.winfo_screenwidth()
            pos_x    = screen_w - win_w - 20
            root.geometry(f"{win_w}x{win_h}+{pos_x}+20")
            root.configure(bg="#0f0f14")
            root.attributes("-topmost", True)
            root.resizable(False, False)

            # ── Liste de toutes les images du dossier (triées par date) ───
            all_images = sorted(OUTPUT_FOLDER.glob("*.png"), key=os.path.getmtime)
            if not all_images:
                all_images = [image_path]

            # Index courant = image qui vient d'être générée
            try:
                current_index = [str(p) for p in all_images].index(str(image_path))
            except ValueError:
                current_index = len(all_images) - 1

            # État mutable partagé entre les callbacks
            state = {"index": current_index}

            # ── Titre ─────────────────────────────────────────────────────
            tk.Label(
                root, text="✨ GÉNÉRATION TERMINÉE",
                bg="#0f0f14", fg="#4ecca3",
                font=("Segoe UI", 10, "bold"), pady=8
            ).pack()

            # ── Image cliquable ───────────────────────────────────────────
            img_label = tk.Label(root, bg="#000000", cursor="hand2")
            img_label.pack(padx=10, pady=4)

            hint = tk.Label(
                root, text="📂 Clic → ouvrir le dossier",
                bg="#0f0f14", fg="#64748b", font=("Segoe UI", 8)
            )
            hint.pack()

            # ── Compteur + nom fichier ─────────────────────────────────────
            counter_label = tk.Label(
                root, text="",
                bg="#0f0f14", fg="#4ecca3", font=("Consolas", 8)
            )
            counter_label.pack(pady=2)

            # ── Métadonnées ───────────────────────────────────────────────
            meta_label = tk.Label(
                root, text="",
                bg="#0f0f14", fg="#94a3b8",
                font=("Consolas", 8), pady=4
            )
            meta_label.pack()

            # ── Navigation ◀ ▶ ───────────────────────────────────────────
            nav_frame = tk.Frame(root, bg="#0f0f14")
            nav_frame.pack(pady=4)

            def load_image(idx):
                """Charge et affiche l'image à l'index donné."""
                path = all_images[idx]
                img  = Image.open(path)
                img.thumbnail((320, 320), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                img_label.config(image=photo)
                img_label.image = photo  # évite le garbage collection

                # Met à jour le clic → ouvrir le bon fichier
                def open_folder(event=None, p=path):
                    win_path = str(p).replace("/", "\\")
                    subprocess.Popen(f'explorer /select,"{win_path}"')
                img_label.bind("<Button-1>", open_folder)

                # Met à jour les labels
                counter_label.config(text=f"{path.name}  ({idx+1}/{len(all_images)})")
                # Métadonnées : si c'est l'image fraîche, affiche seed/dim/steps
                if str(path) == str(image_path):
                    meta_label.config(text=f"Seed: {seed}   {width}×{height}px   Steps: {steps}")
                else:
                    try:
                        from PIL import Image as _Img
                        with _Img.open(path) as _i:
                            w, h = _i.size
                        meta_label.config(text=f"{w}×{h}px")
                    except Exception:
                        meta_label.config(text="")

                # Active/désactive les flèches selon la position
                btn_prev.config(state="normal" if idx > 0 else "disabled")
                btn_next.config(state="normal" if idx < len(all_images) - 1 else "disabled")

            def go_prev():
                state["index"] -= 1
                load_image(state["index"])

            def go_next():
                state["index"] += 1
                load_image(state["index"])

            btn_prev = tk.Button(
                nav_frame, text="◀", command=go_prev,
                bg="#1e293b", fg="#e2e8f0",
                font=("Segoe UI", 11, "bold"),
                relief="flat", padx=16, pady=4,
                cursor="hand2", activebackground="#334155"
            )
            btn_prev.grid(row=0, column=0, padx=6)

            btn_next = tk.Button(
                nav_frame, text="▶", command=go_next,
                bg="#1e293b", fg="#e2e8f0",
                font=("Segoe UI", 11, "bold"),
                relief="flat", padx=16, pady=4,
                cursor="hand2", activebackground="#334155"
            )
            btn_next.grid(row=0, column=1, padx=6)

            # ── Bouton fermer ─────────────────────────────────────────────
            tk.Button(
                root, text="FERMER", command=on_close,
                bg="#1e293b", fg="#e2e8f0",
                font=("Segoe UI", 8, "bold"),
                relief="flat", padx=24, pady=6,
                cursor="hand2", activebackground="#334155"
            ).pack(pady=10)

            # Charge l'image courante (la dernière générée)
            load_image(state["index"])

            root.mainloop()

        except Exception as e:
            log(f"[ComfyUI] Erreur popup Tkinter : {e}")

    Thread(target=run_ui, daemon=True).start()


# ---------------------------------------------------------------------------
# Détection automatique des nœuds
# ---------------------------------------------------------------------------

PROMPT_NODE_CLASSES = {
    "CLIPTextEncode", "CLIPTextEncodeSDXL", "CLIPTextEncodeSD3",
    "CLIPTextEncodeFlux", "CLIPTextEncodeHunyuanDiT",
    "ImpactWildcardProcessor", "CR Text", "ShowText|pysssss",
}
NEGATIVE_KEYWORDS = {"negative", "negatif", "neg", "vide", "empty"}

SAMPLER_NODE_CLASSES = {
    "KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced",
}

LATENT_NODE_CLASSES = {
    "EmptyLatentImage", "EmptySD3LatentImage", "EmptyHunyuanLatentVideo",
    "EmptyMochiLatentVideo", "EmptyLTXVLatentVideo", "EmptyCogVideoLatentVideo",
}


def detect_nodes(workflow: dict) -> dict:
    prompt_candidates = []
    sampler_node      = None
    latent_node       = None

    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        meta_title = node.get("_meta", {}).get("title", "").lower()
        inputs     = node.get("inputs", {})

        # Latent
        if class_type in LATENT_NODE_CLASSES and latent_node is None:
            latent_node = node_id

        # Sampler — supporte seed et noise_seed
        if sampler_node is None:
            if class_type in SAMPLER_NODE_CLASSES:
                if "seed" in inputs or "noise_seed" in inputs:
                    sampler_node = node_id

        # Prompt positif
        if class_type in PROMPT_NODE_CLASSES and "text" in inputs:
            is_negative = any(kw in meta_title for kw in NEGATIVE_KEYWORDS)
            if not is_negative:
                text_len = len(str(inputs.get("text", "")))
                prompt_candidates.append((text_len, node_id))

    prompt_node = None
    if prompt_candidates:
        prompt_candidates.sort(key=lambda x: -x[0])
        prompt_node = prompt_candidates[0][1]

    # Valeurs par défaut lues depuis le workflow
    defaults = {}
    if latent_node and latent_node in workflow:
        li = workflow[latent_node].get("inputs", {})
        if isinstance(li.get("width"),  int): defaults["width"]  = li["width"]
        if isinstance(li.get("height"), int): defaults["height"] = li["height"]

    if sampler_node and sampler_node in workflow:
        si = workflow[sampler_node].get("inputs", {})
        if isinstance(si.get("steps"),        int):         defaults["steps"]        = si["steps"]
        if isinstance(si.get("cfg"),          (int,float)): defaults["cfg"]          = si["cfg"]
        if isinstance(si.get("sampler_name"), str):         defaults["sampler_name"] = si["sampler_name"]
        if isinstance(si.get("scheduler"),    str):         defaults["scheduler"]    = si["scheduler"]
        if isinstance(si.get("denoise"),      (int,float)): defaults["denoise"]      = si["denoise"]

    return {
        "prompt_node":  prompt_node,
        "sampler_node": sampler_node,
        "latent_node":  latent_node,
        "defaults":     defaults,
    }


# ---------------------------------------------------------------------------
# Chargement des workflows
# ---------------------------------------------------------------------------

def load_workflows() -> dict:
    workflows  = {}
    skip_names = {"mcp", "anythingllm_mcp_servers", "plugin"}

    for json_file in sorted(SCRIPT_DIR.glob("*.json")):
        if json_file.stem.lower() in skip_names:
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                workflow = json.load(f)
            if not any(isinstance(v, dict) and "class_type" in v for v in workflow.values()):
                continue
            nodes     = detect_nodes(workflow)
            tool_name = re.sub(r"[^a-z0-9_]", "_", json_file.stem.lower())
            workflows[tool_name] = {
                "file":     json_file,
                "workflow": workflow,
                "nodes":    nodes,
            }
        except Exception as e:
            log(f"[ComfyUI] Erreur chargement {json_file.name}: {e}")

    return workflows


# ---------------------------------------------------------------------------
# ComfyUI helpers
# ---------------------------------------------------------------------------

def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read())


def submit_workflow(workflow: dict, client_id: str) -> str:
    result = _post_json(f"{COMFYUI_URL}/prompt", {"prompt": workflow, "client_id": client_id})
    return result["prompt_id"]


def poll_until_done(prompt_id: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT_S
    while time.time() < deadline:
        try:
            history = _get_json(f"{COMFYUI_URL}/history/{prompt_id}")
        except Exception:
            time.sleep(POLL_INTERVAL_S)
            continue
        if prompt_id in history:
            entry      = history[prompt_id]
            status_str = entry.get("status", {}).get("status_str", "")
            if status_str == "success":
                return entry
            if status_str == "error":
                raise RuntimeError(f"ComfyUI error: {entry.get('status',{}).get('messages',[])}")
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"Timeout après {POLL_TIMEOUT_S}s")


def get_output_images(history_entry: dict) -> list:
    outputs = history_entry.get("outputs", {})
    paths   = []
    for _, node_output in outputs.items():
        for img in node_output.get("images", []):
            subfolder = img.get("subfolder", "")
            filename  = img["filename"]
            paths.append(
                OUTPUT_FOLDER / subfolder / filename if subfolder
                else OUTPUT_FOLDER / filename
            )
    return paths


# ---------------------------------------------------------------------------
# Génération
# ---------------------------------------------------------------------------

def generate_image(wf_entry: dict, prompt: str, seed=None,
                   width=None, height=None, steps=None) -> dict:
    # Ferme l'ancienne popup dès le début — avant même que ComfyUI génère
    close_popup()

    workflow = copy.deepcopy(wf_entry["workflow"])
    nodes    = wf_entry["nodes"]
    defaults = nodes["defaults"]

    resolved_seed = seed if seed is not None else random.randint(0, 2**32 - 1)

    # ── Prompt ────────────────────────────────────────────────────────────
    if nodes["prompt_node"]:
        workflow[nodes["prompt_node"]]["inputs"]["text"] = prompt

    # ── Seed (supporte seed et noise_seed) ────────────────────────────────
    if nodes["sampler_node"]:
        si = workflow[nodes["sampler_node"]]["inputs"]
        if "seed" in si:
            si["seed"] = resolved_seed
        elif "noise_seed" in si:
            si["noise_seed"] = resolved_seed
        if steps is not None:
            si["steps"] = steps

    # ── Dimensions (seulement si demandées) ───────────────────────────────
    if nodes["latent_node"]:
        li = workflow[nodes["latent_node"]]["inputs"]
        if width  is not None: li["width"]  = width
        if height is not None: li["height"] = height

    # ── Envoi à ComfyUI ───────────────────────────────────────────────────
    client_id     = str(uuid.uuid4())
    prompt_id     = submit_workflow(workflow, client_id)
    history_entry = poll_until_done(prompt_id)
    images        = get_output_images(history_entry)

    if not images:
        candidates = sorted(OUTPUT_FOLDER.glob("*.png"), key=os.path.getmtime)
        if not candidates:
            raise RuntimeError("ComfyUI finished but returned no output images.")
        image_path = candidates[-1]
    else:
        image_path = images[0]

    actual_width  = width  if width  is not None else defaults.get("width",  "?")
    actual_height = height if height is not None else defaults.get("height", "?")
    actual_steps  = steps  if steps  is not None else defaults.get("steps",  "?")

    # ── Popup Tkinter (ouverte après génération) ──────────────────────────
    try:
        show_tkinter_popup(image_path, prompt, resolved_seed,
                           actual_width, actual_height, actual_steps)
    except Exception as e:
        log(f"[ComfyUI] Popup error: {e}")

    return {
        "path":   image_path,
        "seed":   resolved_seed,
        "width":  actual_width,
        "height": actual_height,
        "steps":  actual_steps,
    }


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

WORKFLOWS = load_workflows()
server    = Server("comfyui-universal")


def make_tool(tool_name: str, wf_entry: dict) -> Tool:
    nodes    = wf_entry["nodes"]
    defaults = nodes["defaults"]
    filename = wf_entry["file"].name

    def_width   = defaults.get("width",        "?")
    def_height  = defaults.get("height",       "?")
    def_steps   = defaults.get("steps",        "?")
    def_cfg     = defaults.get("cfg",          "?")
    def_sampler = defaults.get("sampler_name", "?")
    def_sched   = defaults.get("scheduler",    "?")
    def_denoise = defaults.get("denoise",      "?")

    detected = []
    if nodes["prompt_node"]:  detected.append(f"prompt→{nodes['prompt_node']}")
    if nodes["sampler_node"]: detected.append(f"sampler→{nodes['sampler_node']}")
    if nodes["latent_node"]:  detected.append(f"latent→{nodes['latent_node']}")

    return Tool(
        name        = tool_name,
        description = (
            f"Génère une image avec le workflow ComfyUI '{filename}'. "
            f"Paramètres : {def_width}×{def_height}px | "
            f"steps={def_steps} | cfg={def_cfg} | "
            f"sampler={def_sampler} | scheduler={def_sched} | denoise={def_denoise}. "
            f"Seul le prompt est obligatoire. "
            f"Nœuds : {', '.join(detected) if detected else 'aucun'}."
        ),
        inputSchema = {
            "type": "object",
            "properties": {
                "prompt": {"type": "string",  "description": "Description de l'image à générer."},
                "seed":   {"type": "integer", "description": "Seed (optionnel, aléatoire si omis)."},
                "width":  {"type": "integer", "description": f"Largeur px (défaut workflow : {def_width}px)."},
                "height": {"type": "integer", "description": f"Hauteur px (défaut workflow : {def_height}px)."},
                "steps":  {"type": "integer", "description": f"Steps (défaut workflow : {def_steps})."},
            },
            "required": ["prompt"],
        },
    )


@server.list_tools()
async def list_tools():
    return [make_tool(name, entry) for name, entry in WORKFLOWS.items()]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name not in WORKFLOWS:
        available = ", ".join(WORKFLOWS.keys()) or "aucun"
        raise ValueError(f"Outil inconnu : '{name}'. Disponibles : {available}")

    wf_entry = WORKFLOWS[name]
    nodes    = wf_entry["nodes"]
    prompt   = arguments["prompt"]
    seed     = arguments.get("seed")
    width    = int(arguments["width"])  if "width"  in arguments else None
    height   = int(arguments["height"]) if "height" in arguments else None
    steps    = int(arguments["steps"])  if "steps"  in arguments else None

    warnings = []
    if not nodes["prompt_node"]:  warnings.append("⚠️ Nœud prompt non détecté.")
    if not nodes["sampler_node"]: warnings.append("⚠️ Nœud sampler non détecté.")
    if not nodes["latent_node"] and (width or height):
        warnings.append("⚠️ Nœud latent non détecté — dimensions ignorées.")

    try:
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: generate_image(wf_entry, prompt, seed, width, height, steps),
        )
    except Exception as exc:
        tb = traceback.format_exc()
        return [TextContent(type="text", text=f"ERREUR :\n{exc}\n\nTraceback:\n{tb}")]

    warning_text = ("\n" + "\n".join(warnings)) if warnings else ""

    return [
        TextContent(
            type="text",
            text=(
                f"✅ Image générée !{warning_text}\n\n"
                f"📁 Fichier  : `{result['path']}`\n"
                f"🔧 Workflow : `{wf_entry['file'].name}`\n"
                f"🎨 Prompt   : {prompt}\n"
                f"🎲 Seed     : {result['seed']}\n"
                f"📐 Taille   : {result['width']}×{result['height']}px"
                f" | Steps : {result['steps']}"
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    if WORKFLOWS:
        log(f"[ComfyUI] {len(WORKFLOWS)} workflow(s) chargé(s) depuis {SCRIPT_DIR} :")
        for name, entry in WORKFLOWS.items():
            n = entry["nodes"]
            d = n["defaults"]
            log(
                f"  • {name} ({entry['file'].name})\n"
                f"    {d.get('width','?')}×{d.get('height','?')}px | "
                f"steps={d.get('steps','?')} | cfg={d.get('cfg','?')} | "
                f"sampler={d.get('sampler_name','?')} | scheduler={d.get('scheduler','?')}\n"
                f"    nœuds → prompt={n['prompt_node']} "
                f"sampler={n['sampler_node']} latent={n['latent_node']}"
            )
    else:
        log(f"[ComfyUI] ⚠️ Aucun workflow JSON trouvé dans {SCRIPT_DIR}")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream,
                         server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
