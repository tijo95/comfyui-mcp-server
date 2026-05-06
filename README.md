# ComfyUI MCP Server for AnythingLLM

A universal MCP (Model Context Protocol) server that connects **AnythingLLM** to **ComfyUI** for AI image generation — directly from your chat interface.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![MCP](https://img.shields.io/badge/MCP-stdio-orange)

---

## ✨ Features

- 🔌 **Universal** — drop any ComfyUI workflow `.json` in the folder, it becomes an MCP tool automatically
- 🧠 **Smart node detection** — auto-detects prompt, sampler, and latent nodes from any workflow
- 🎛️ **Workflow-first** — the workflow is sent as-is to ComfyUI, only prompt and seed are modified
- 🖼️ **Native popup viewer** — a Tkinter window shows the generated image instantly
- 🗂️ **Image gallery** — navigate all images in the output folder with ◀ ▶ arrows
- 📂 **One-click folder** — click the image to open its folder in Windows Explorer
- 🔄 **Auto-close** — the popup closes automatically when a new generation starts

---

## 📋 Requirements

- Python 3.10+
- ComfyUI running locally on `http://127.0.0.1:8188`
- AnythingLLM (any recent version)

---

## 📦 Installation

**1. Clone the repo**
```bash
git clone https://github.com/YOUR_USERNAME/comfyui-mcp-server.git
cd comfyui-mcp-server
```

**2. Install dependencies**
```bash
pip install mcp Pillow
```

**3. Copy your ComfyUI workflow(s)**

Place your ComfyUI workflow JSON files (exported in API format) next to the script:
```
comfyui-mcp-server/
  comfyui_mcp_server.py
  my_workflow.json        ← your workflow here
  another_workflow.json   ← each one becomes a separate MCP tool
```

> ⚠️ Export your workflow from ComfyUI using **"Save (API Format)"** — not the default save.

**4. Edit the configuration** in `comfyui_mcp_server.py`

```python
COMFYUI_URL   = "http://127.0.0.1:8188"          # your ComfyUI URL
OUTPUT_FOLDER = Path("D:/") / ".ComfyUI" / "output"  # your ComfyUI output folder
```

---

## ⚙️ AnythingLLM Configuration

In AnythingLLM, go to **Settings → MCP Servers** and paste:

```json
{
  "mcpServers": {
    "comfyui": {
      "command": "python",
      "args": ["D:\\PATH\\TO\\comfyui_mcp_server.py"],
      "env": {}
    }
  }
}
```

> Replace `D:\\PATH\\TO\\` with the actual path to your script.

---

## 🚀 Usage

Once configured, just ask AnythingLLM naturally:

> *"Generate an image of a futuristic city at night using the flux_workflow"*

> *"Create a portrait of a samurai with my sd1_5 workflow, 768x1024"*

The agent will:
1. Select the right workflow tool
2. Send the prompt to ComfyUI
3. Wait for the image to be generated
4. Open a popup with the result

### Available parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| `prompt`  | ✅ Yes   | Image description |
| `seed`    | No       | Random seed (random if omitted) |
| `width`   | No       | Width in pixels (uses workflow default) |
| `height`  | No       | Height in pixels (uses workflow default) |
| `steps`   | No       | Sampling steps (uses workflow default) |

---

## 🖼️ Popup Viewer

After each generation, a compact native window appears in the top-right corner:

```
┌──────────────────────────────┐
│  ✨ GÉNÉRATION TERMINÉE      │
│  ┌────────────────────────┐  │
│  │                        │  │
│  │       [image]          │  │  ← click → open folder
│  │                        │  │
│  └────────────────────────┘  │
│  📂 Clic → ouvrir le dossier │
│  image_00003_.png  (3/12)    │
│  Seed: 123  1024×1024  8st   │
│        ◀          ▶          │  ← browse all output images
│          FERMER              │
└──────────────────────────────┘
```

- **Click image** → opens Windows Explorer with the file selected
- **◀ ▶ arrows** → browse all images in the output folder
- **Auto-closes** when a new generation starts

---

## 🔍 How Node Detection Works

The script automatically scans each workflow JSON and identifies:

| Node type | Detected classes |
|-----------|-----------------|
| **Prompt** | `CLIPTextEncode`, `CLIPTextEncodeSDXL`, `CLIPTextEncodeFlux`, `CLIPTextEncodeSD3`... |
| **Sampler** | `KSampler`, `KSamplerAdvanced`, `SamplerCustom`... |
| **Latent** | `EmptyLatentImage`, `EmptySD3LatentImage`... |

Only the **positive prompt text** and **seed** are modified. Everything else (model, LoRA, VAE, CFG, scheduler, etc.) is kept exactly as in your workflow JSON.

---

## 📁 Project Structure

```
comfyui-mcp-server/
├── comfyui_mcp_server.py   # main MCP server script
├── mcp.json                # AnythingLLM config example
├── requirements.txt        # Python dependencies
└── README.md
```

---

## 🛠️ Troubleshooting

**MCP server fails to start**
- Make sure `stdout` is not polluted — all logs go to `stderr` in this script ✅
- Check that `mcp` and `Pillow` are installed: `pip install mcp Pillow`

**Workflow nodes not detected**
- Export your workflow using **API Format** from ComfyUI
- Check the terminal output — the script logs which nodes were detected at startup

**Image not found after generation**
- Verify `OUTPUT_FOLDER` points to your actual ComfyUI output directory

---

## 📄 License

MIT — free to use, modify, and share.

---

## 🙏 Credits

Built with:
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
- [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm)
