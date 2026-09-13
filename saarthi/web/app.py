"""
JARVIS Web Server — FastAPI application for Universal Device Access.
Accessible on Localhost and Local Network for Phones, Tablets, and Laptops.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import socket
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from ..agent import Agent
from ..config import Settings
from ..voice.tts import TTSEngine

log = logging.getLogger("saarthi.web")


def get_local_ip() -> str:
    """Find local network IP address for mobile connections."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class ChatRequest(BaseModel):
    prompt: str
    device: str | None = None
    voice_response: bool = True


def create_app(agent: Agent | None = None) -> FastAPI:
    app = FastAPI(title="J.A.R.V.I.S. Core", version="2.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # State
    shared_agent = agent or Agent(config=Settings.load())
    shared_agent.settings.jarvis_mode = True
    tts = TTSEngine()

    # ------------------------------------------------------------------
    #  PWA Manifest & Service Worker
    # ------------------------------------------------------------------

    @app.get("/api/download-shortcut")
    async def download_shortcut() -> Response:
        """Provide a 1-click Windows Internet Shortcut (.url) file."""
        shortcut_content = "[InternetShortcut]\nURL=http://localhost:8000\nIconIndex=0\n"
        return Response(
            content=shortcut_content,
            media_type="application/internet-shortcut",
            headers={"Content-Disposition": "attachment; filename=JARVIS.url"},
        )

    @app.get("/manifest.json")
    async def manifest() -> JSONResponse:
        return JSONResponse(
            {
                "name": "J.A.R.V.I.S. - Advanced AI Assistant",
                "short_name": "JARVIS",
                "start_url": "/",
                "display": "standalone",
                "background_color": "#070b14",
                "theme_color": "#00e5ff",
                "description": "Just A Rather Very Intelligent System - Universal Multimodal AI Agent",
                "icons": [
                    {
                        "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='45' fill='%23070b14' stroke='%2300e5ff' stroke-width='4'/%3E%3Ccircle cx='50' cy='50' r='25' fill='%2300e5ff' opacity='0.7'/%3E%3Cpath d='M50 15 L50 85 M15 50 L85 50' stroke='%2300e5ff' stroke-width='3'/%3E%3C/svg%3E",
                        "sizes": "192x192 512x512",
                        "type": "image/svg+xml",
                    }
                ],
            }
        )

    @app.get("/service-worker.js")
    async def service_worker() -> Response:
        js = """
        self.addEventListener('install', (e) => self.skipWaiting());
        self.addEventListener('activate', (e) => clients.claim());
        self.addEventListener('fetch', (e) => {
            // Network first with fallback
            e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
        });
        """
        return Response(content=js, media_type="application/javascript")

    # ------------------------------------------------------------------
    #  Hardware & Status API
    # ------------------------------------------------------------------

    @app.get("/api/status")
    async def get_status() -> dict[str, Any]:
        import psutil

        cpu = psutil.cpu_percent(interval=0.05)
        mem = psutil.virtual_memory()
        battery = psutil.sensors_battery()

        batt_info = {"percent": 100, "plugged": True}
        if battery:
            batt_info = {"percent": battery.percent, "plugged": battery.power_plugged}

        active_provider = "None"
        if shared_agent.brain.providers:
            active_provider = shared_agent.brain.providers[0].name.upper()

        devices = [d.kind for d in shared_agent.devices.all()]

        return {
            "status": "online",
            "name": "J.A.R.V.I.S.",
            "version": "2.0.0",
            "local_ip": get_local_ip(),
            "cpu_percent": cpu,
            "ram_percent": mem.percent,
            "ram_used_gb": round(mem.used / (1024**3), 2),
            "ram_total_gb": round(mem.total / (1024**3), 2),
            "battery": batt_info,
            "active_provider": active_provider,
            "active_devices": devices,
            "voice_backend": tts.backend.name,
        }

    # ------------------------------------------------------------------
    #  Desktop Screen Snapshot
    # ------------------------------------------------------------------

    @app.get("/api/screenshot")
    async def get_screenshot() -> dict[str, Any]:
        desktop = shared_agent.devices.get("desktop")
        if desktop:
            res = await desktop.screenshot()
            if res.ok and res.data and "image_b64" in res.data:
                return {"ok": True, "image_b64": res.data["image_b64"]}
            return {"ok": False, "error": res.error or "Failed to grab screenshot"}
        return {"ok": False, "error": "No desktop device available"}

    # ------------------------------------------------------------------
    #  Text Command / Chat API
    # ------------------------------------------------------------------

    @app.post("/api/chat")
    async def chat(req: ChatRequest) -> dict[str, Any]:
        if not req.prompt.strip():
            raise HTTPException(status_code=400, detail="Empty prompt")

        start = time.monotonic()
        turn = await shared_agent.run_turn(req.prompt.strip())
        elapsed = time.monotonic() - start

        audio_b64 = None
        if req.voice_response and turn.reply:
            try:
                # Generate audio with edge-tts in memory / temp
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
                    tpath = Path(tf.name)
                saved = tts.synthesize_to_file(turn.reply, tpath)
                if saved and saved.exists() and saved.stat().st_size > 0:
                    audio_b64 = base64.b64encode(saved.read_bytes()).decode("ascii")
                    saved.unlink(missing_ok=True)
            except Exception as exc:
                log.warning("Speech synth error: %s", exc)

        return {
            "ok": turn.ok,
            "reply": turn.reply,
            "steps": turn.steps_used,
            "tools": turn.tool_calls,
            "error": turn.error,
            "elapsed_seconds": round(elapsed, 2),
            "audio_b64": audio_b64,
        }

    # ------------------------------------------------------------------
    #  VS Code OpenAI-compatible API (/v1/chat/completions)
    # ------------------------------------------------------------------

    @app.get("/v1/models")
    async def list_v1_models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [
                {
                    "id": "jarvis",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "jarvis",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def v1_chat_completions(raw_req: dict[str, Any]) -> dict[str, Any]:
        import uuid
        messages = raw_req.get("messages", [])
        user_prompt = "Hello"
        for m in reversed(messages):
            if m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    user_prompt = c
                elif isinstance(c, list):
                    parts = [p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text"]
                    user_prompt = " ".join(parts)
                break

        turn = await shared_agent.run_turn(user_prompt)
        reply = turn.reply or "Action completed, Sir."

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "jarvis",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": reply,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(user_prompt.split()),
                "completion_tokens": len(reply.split()),
                "total_tokens": len(user_prompt.split()) + len(reply.split()),
            },
        }

    # ------------------------------------------------------------------
    #  Voice Audio Upload API (for recording from Phone/Browser)
    # ------------------------------------------------------------------

    @app.post("/api/voice")
    async def voice_upload(file: UploadFile = File(...)) -> dict[str, Any]:
        from ..voice import WhisperConfig, WhisperSTT, is_stt_available

        if not is_stt_available():
            raise HTTPException(status_code=500, detail="faster-whisper is not installed")

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            tpath = Path(tf.name)
            tpath.write_bytes(await file.read())

        try:
            config = WhisperConfig.from_env()
            stt = WhisperSTT(config)
            await asyncio.to_thread(stt.load)

            # Load audio bytes and transcribe
            transcribed = await asyncio.to_thread(stt.transcribe, str(tpath))
            text = transcribed.text.strip() if transcribed else ""
            if not text:
                return {"ok": False, "reply": "I could not understand the audio, Sir.", "user_text": ""}

            # Execute turn
            turn = await shared_agent.run_turn(text)

            audio_b64 = None
            if turn.reply:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as out_tf:
                    out_path = Path(out_tf.name)
                saved = tts.synthesize_to_file(turn.reply, out_path)
                if saved and saved.exists():
                    audio_b64 = base64.b64encode(saved.read_bytes()).decode("ascii")
                    saved.unlink(missing_ok=True)

            return {
                "ok": turn.ok,
                "user_text": text,
                "reply": turn.reply,
                "steps": turn.steps_used,
                "tools": turn.tool_calls,
                "error": turn.error,
                "audio_b64": audio_b64,
            }
        finally:
            tpath.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    #  Interactive Futuristic Web UI
    # ------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        local_ip = get_local_ip()
        return HTMLResponse(get_jarvis_html(local_ip))

    return app


def get_jarvis_html(local_ip: str) -> str:
    """Return the ultra-futuristic Iron-Man Jarvis Single Page Web App."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>J.A.R.V.I.S. — Universal AI Assistant</title>
    <link rel="manifest" href="/manifest.json">
    <meta name="theme-color" content="#00e5ff">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;800;900&family=Rajdhani:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #050811;
            --panel: rgba(10, 18, 36, 0.75);
            --border: rgba(0, 229, 255, 0.25);
            --cyan: #00e5ff;
            --cyan-glow: rgba(0, 229, 255, 0.45);
            --orange: #ff9100;
            --green: #00e676;
            --red: #ff1744;
            --text: #e0f7fa;
            --muted: #546e7a;
            --font-display: 'Orbitron', monospace;
            --font-body: 'Rajdhani', sans-serif;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
        }}

        body {{
            background: radial-gradient(circle at 50% 10%, #0a1733 0%, var(--bg) 80%);
            color: var(--text);
            font-family: var(--font-body);
            height: 100vh;
            width: 100vw;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}

        /* Scanning grid effect */
        body::before {{
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(rgba(0, 229, 255, 0.03) 1px, transparent 1px),
                        linear-gradient(90deg, rgba(0, 229, 255, 0.03) 1px, transparent 1px);
            background-size: 30px 30px;
            pointer-events: none;
            z-index: 0;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 20px;
            background: rgba(5, 10, 20, 0.85);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--border);
            z-index: 10;
        }}

        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .brand-logo {{
            width: 32px;
            height: 32px;
            border: 2px solid var(--cyan);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 15px var(--cyan-glow);
            animation: pulse-border 2s infinite ease-in-out;
        }}

        .brand-logo-inner {{
            width: 12px;
            height: 12px;
            background: var(--cyan);
            border-radius: 50%;
        }}

        .brand-title {{
            font-family: var(--font-display);
            font-size: 1.25rem;
            font-weight: 800;
            letter-spacing: 3px;
            color: #ffffff;
            text-shadow: 0 0 10px var(--cyan-glow);
        }}

        .brand-subtitle {{
            font-size: 0.75rem;
            color: var(--cyan);
            letter-spacing: 2px;
            font-weight: 600;
        }}

        .hud-pills {{
            display: flex;
            gap: 8px;
            align-items: center;
        }}

        .pill {{
            padding: 4px 10px;
            background: rgba(0, 229, 255, 0.08);
            border: 1px solid var(--border);
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--cyan);
            display: flex;
            align-items: center;
            gap: 6px;
        }}

        .pill-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--green);
            box-shadow: 0 0 6px var(--green);
        }}

        /* Main Workspace */
        main {{
            flex: 1;
            display: flex;
            position: relative;
            z-index: 1;
            overflow: hidden;
        }}

        /* Left Side: Arc Reactor & Diagnostics */
        .telemetry-pane {{
            width: 380px;
            background: var(--panel);
            backdrop-filter: blur(16px);
            border-right: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            padding: 20px;
            gap: 16px;
        }}

        @media (max-width: 900px) {{
            .telemetry-pane {{
                display: none;
            }}
        }}

        /* Reactor Core Visualizer */
        .core-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 20px 0;
            position: relative;
        }}

        .arc-reactor {{
            width: 140px;
            height: 140px;
            border-radius: 50%;
            border: 3px dashed var(--cyan);
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            box-shadow: 0 0 30px var(--cyan-glow), inset 0 0 30px var(--cyan-glow);
            transition: all 0.3s ease;
            cursor: pointer;
        }}

        .arc-reactor.active {{
            animation: spin 8s linear infinite;
            border-color: #ffffff;
            box-shadow: 0 0 50px var(--cyan), inset 0 0 40px var(--cyan);
        }}

        .arc-core {{
            width: 70px;
            height: 70px;
            background: radial-gradient(circle, #ffffff 10%, var(--cyan) 70%, transparent 100%);
            border-radius: 50%;
            box-shadow: 0 0 25px var(--cyan);
        }}

        .reactor-status {{
            margin-top: 15px;
            font-family: var(--font-display);
            font-size: 0.9rem;
            color: var(--cyan);
            letter-spacing: 2px;
            text-align: center;
        }}

        /* Gauge Cards */
        .metrics-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }}

        .metric-card {{
            background: rgba(0, 229, 255, 0.04);
            border: 1px solid rgba(0, 229, 255, 0.15);
            border-radius: 8px;
            padding: 10px 14px;
        }}

        .metric-label {{
            font-size: 0.75rem;
            color: var(--muted);
            letter-spacing: 1px;
            text-transform: uppercase;
        }}

        .metric-value {{
            font-family: var(--font-display);
            font-size: 1.1rem;
            font-weight: 700;
            color: #ffffff;
            margin-top: 4px;
        }}

        .metric-bar {{
            height: 4px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 2px;
            margin-top: 8px;
            overflow: hidden;
        }}

        .metric-bar-fill {{
            height: 100%;
            background: var(--cyan);
            width: 0%;
            transition: width 0.5s ease;
        }}

        /* Right Side: Chat & Interactive Console */
        .chat-pane {{
            flex: 1;
            display: flex;
            flex-direction: column;
            background: rgba(7, 12, 24, 0.5);
            position: relative;
        }}

        .messages-container {{
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}

        .message {{
            display: flex;
            gap: 12px;
            max-width: 85%;
            animation: fadeIn 0.25s ease-out;
        }}

        .message.user {{
            align-self: flex-end;
            flex-direction: row-reverse;
        }}

        .msg-avatar {{
            width: 36px;
            height: 36px;
            border-radius: 50%;
            border: 1px solid var(--cyan);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
            font-family: var(--font-display);
            flex-shrink: 0;
            background: rgba(0, 229, 255, 0.1);
        }}

        .message.user .msg-avatar {{
            border-color: var(--orange);
            background: rgba(255, 145, 0, 0.1);
            color: var(--orange);
        }}

        .msg-bubble {{
            background: var(--panel);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 12px 18px;
            line-height: 1.5;
            font-size: 1rem;
            user-select: text;
        }}

        .message.user .msg-bubble {{
            background: rgba(255, 145, 0, 0.08);
            border-color: rgba(255, 145, 0, 0.3);
        }}

        .tool-chip {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            background: rgba(0, 229, 255, 0.12);
            border: 1px solid var(--cyan);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            margin: 4px 4px 4px 0;
            color: var(--cyan);
            font-family: monospace;
        }}

        /* Suggested Chips */
        .quick-actions {{
            display: flex;
            gap: 8px;
            padding: 8px 20px;
            overflow-x: auto;
            border-top: 1px solid rgba(0, 229, 255, 0.1);
        }}

        .chip-btn {{
            background: rgba(0, 229, 255, 0.05);
            border: 1px solid rgba(0, 229, 255, 0.2);
            color: var(--cyan);
            padding: 6px 14px;
            border-radius: 16px;
            font-size: 0.85rem;
            font-family: var(--font-body);
            font-weight: 600;
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.2s ease;
        }}

        .chip-btn:hover {{
            background: rgba(0, 229, 255, 0.15);
            border-color: var(--cyan);
            transform: translateY(-1px);
        }}

        /* Input Controls */
        .input-bar {{
            padding: 14px 20px;
            background: rgba(5, 10, 20, 0.9);
            border-top: 1px solid var(--border);
            display: flex;
            gap: 12px;
            align-items: center;
        }}

        .cmd-input {{
            flex: 1;
            background: rgba(0, 229, 255, 0.05);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 12px 20px;
            color: #ffffff;
            font-family: var(--font-body);
            font-size: 1.05rem;
            outline: none;
            transition: all 0.2s ease;
            user-select: text;
        }}

        .cmd-input:focus {{
            border-color: var(--cyan);
            box-shadow: 0 0 15px var(--cyan-glow);
        }}

        .action-btn {{
            width: 46px;
            height: 46px;
            border-radius: 50%;
            border: 1px solid var(--cyan);
            background: rgba(0, 229, 255, 0.1);
            color: var(--cyan);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            font-size: 1.2rem;
            transition: all 0.2s ease;
            flex-shrink: 0;
        }}

        .action-btn:hover {{
            background: var(--cyan);
            color: #000000;
            box-shadow: 0 0 15px var(--cyan);
        }}

        .action-btn.mic.listening {{
            background: var(--red);
            border-color: var(--red);
            color: #ffffff;
            box-shadow: 0 0 20px var(--red);
            animation: pulse-red 1s infinite alternate;
        }}

        /* Animations */
        @keyframes pulse-border {{
            0%, 100% {{ box-shadow: 0 0 10px var(--cyan-glow); }}
            50% {{ box-shadow: 0 0 20px var(--cyan); }}
        }}

        @keyframes pulse-red {{
            0% {{ transform: scale(1); }}
            100% {{ transform: scale(1.1); }}
        }}

        @keyframes spin {{
            100% {{ transform: rotate(360deg); }}
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        /* Mobile full-width adjustments */
        @media (max-width: 600px) {{
            header {{ padding: 10px 14px; }}
            .brand-title {{ font-size: 1.1rem; }}
            .brand-subtitle {{ display: none; }}
            .input-bar {{ padding: 10px 12px; }}
            .cmd-input {{ font-size: 0.95rem; padding: 10px 16px; }}
            .action-btn {{ width: 40px; height: 40px; font-size: 1.1rem; }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="brand">
            <div class="brand-logo"><div class="brand-logo-inner"></div></div>
            <div>
                <div class="brand-title">J.A.R.V.I.S.</div>
                <div class="brand-subtitle">UNIVERSAL MULTIMODAL CORE</div>
            </div>
        </div>
        <div class="hud-pills">
            <div class="pill"><div class="pill-dot"></div> <span id="brainBadge">AI BRAIN</span></div>
            <a href="http://localhost:8000" id="secureSwitch" class="pill" style="text-decoration: none; color: var(--cyan); display: none;" title="Click to remove 'Not secure'">🔒 SECURE MODE</a>
            <div class="pill" id="ipBadge" title="Open on Mobile / Tablet">🌐 {local_ip}:8000</div>
            <button class="pill" id="muteToggle" onclick="toggleAudio()" style="cursor: pointer;">🔊 VOICE</button>
            <button class="pill" id="installAppBtn" onclick="triggerInstall()" style="cursor: pointer; background: linear-gradient(90deg, #00e5ff 0%, #00b0ff 100%); color: #000000; font-weight: 800; border: none; box-shadow: 0 0 15px rgba(0,229,255,0.4);">📲 INSTALL APP</button>
        </div>
    </header>

    <main>
        <section class="telemetry-pane">
            <div class="core-container">
                <div class="arc-reactor" id="reactorCore" onclick="startVoiceRecognition()">
                    <div class="arc-core"></div>
                </div>
                <div class="reactor-status" id="reactorLabel">SYSTEM READY</div>
            </div>

            <div class="metrics-grid">
                <div class="metric-card">
                    <div class="metric-label">CPU LOAD</div>
                    <div class="metric-value" id="cpuVal">0%</div>
                    <div class="metric-bar"><div class="metric-bar-fill" id="cpuBar"></div></div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">MEMORY</div>
                    <div class="metric-value" id="memVal">0 GB</div>
                    <div class="metric-bar"><div class="metric-bar-fill" id="memBar"></div></div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">POWER</div>
                    <div class="metric-value" id="battVal">100%</div>
                    <div class="metric-bar"><div class="metric-bar-fill" id="battBar"></div></div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">DEVICES</div>
                    <div class="metric-value" id="devVal">ONLINE</div>
                    <div class="metric-bar"><div class="metric-bar-fill" style="width: 100%;"></div></div>
                </div>
            </div>

            <div style="margin-top: auto; padding: 12px; background: rgba(0, 229, 255, 0.03); border: 1px dashed var(--border); border-radius: 8px;">
                <div style="font-size: 0.75rem; color: var(--cyan); letter-spacing: 1px; font-weight: 600;">📱 CONNECT FROM ANY PHONE / LAPTOP:</div>
                <div style="font-size: 0.9rem; color: #ffffff; margin-top: 4px; font-family: monospace;">http://{local_ip}:8000</div>
                <div style="font-size: 0.75rem; color: var(--muted); margin-top: 4px;">Open this in your phone's browser to control PC/Laptop & talk to Jarvis!</div>
            </div>
        </section>

        <section class="chat-pane">
            <div class="messages-container" id="chatList">
                <div class="message">
                    <div class="msg-avatar">J</div>
                    <div class="msg-bubble">
                        Good day, Sir. J.A.R.V.I.S. is fully online and standing by across all systems. How may I assist you today?
                    </div>
                </div>
            </div>

            <div class="quick-actions">
                <button class="chip-btn" onclick="sendQuick('System Status check karo')">⚡ Status</button>
                <button class="chip-btn" onclick="sendQuick('Screen dekh kar bata kya hai')">👁️ Screen View</button>
                <button class="chip-btn" onclick="sendQuick('YouTube pe Trending videos kholo')">▶️ YouTube</button>
                <button class="chip-btn" onclick="sendQuick('Battery aur storage check kar')">🔋 Battery</button>
                <button class="chip-btn" onclick="sendQuick('Chrome kholo')">🌐 Chrome</button>
                <button class="chip-btn" onclick="sendQuick('Python se ek matrix multiplication karke dikhao')">🐍 Python Code</button>
            </div>

            <div class="input-bar">
                <button class="action-btn mic" id="micBtn" onclick="toggleMic()" title="Voice Input (Mic)">🎙️</button>
                <input type="text" class="cmd-input" id="promptInput" placeholder="Command JARVIS with voice or text..." autocomplete="off">
                <button class="action-btn" onclick="submitPrompt()" title="Send Command">➤</button>
            </div>
        </section>
    </main>

    <audio id="ttsAudio" style="display: none;"></audio>

    <!-- High Tech Install & Secure Modal -->
    <div id="installModal" style="display: none; position: fixed; inset: 0; background: rgba(5,8,17,0.85); backdrop-filter: blur(12px); z-index: 1000; align-items: center; justify-content: center; padding: 20px;">
        <div style="background: rgba(10,18,36,0.95); border: 2px solid var(--cyan); border-radius: 16px; width: 100%; max-width: 500px; padding: 24px; box-shadow: 0 0 40px var(--cyan-glow); position: relative;">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 12px; margin-bottom: 16px;">
                <div style="font-family: var(--font-display); font-size: 1.1rem; color: #ffffff; font-weight: 800; letter-spacing: 2px;">📲 INSTALL J.A.R.V.I.S. APP</div>
                <button onclick="document.getElementById('installModal').style.display='none'" style="background: none; border: none; color: var(--cyan); font-size: 1.5rem; cursor: pointer;">✕</button>
            </div>

            <div style="display: flex; flex-direction: column; gap: 16px;">
                <div style="padding: 12px 16px; background: rgba(0, 229, 255, 0.05); border: 1px solid var(--border); border-radius: 8px;">
                    <div style="font-weight: 700; color: var(--cyan); font-size: 0.95rem; margin-bottom: 4px;">1. Chrome Desktop App (1-Click)</div>
                    <div style="font-size: 0.85rem; color: var(--text); line-height: 1.4;">
                        Chrome ke URL bar ke andar right side mein <b>[🖥️ Install]</b> icon par click karein ya niche <b>Download Shortcut</b> karein.
                    </div>
                </div>

                <div style="padding: 12px 16px; background: rgba(0, 230, 118, 0.05); border: 1px solid rgba(0, 230, 118, 0.3); border-radius: 8px;">
                    <div style="font-weight: 700; color: var(--green); font-size: 0.95rem; margin-bottom: 4px;">2. 'Not Secure' Hatane Ke Liye:</div>
                    <div style="font-size: 0.85rem; color: var(--text); line-height: 1.4; margin-bottom: 8px;">
                        Local IP (192.168.x.x) par Chrome 'Not secure' likhta hai. <b>localhost</b> par open karne se 'Not secure' turant gayab ho jayega!
                    </div>
                    <a href="http://localhost:8000" style="display: inline-block; padding: 6px 14px; background: var(--green); color: #000000; font-weight: 700; border-radius: 6px; text-decoration: none; font-size: 0.85rem;">🔒 Switch to http://localhost:8000</a>
                </div>

                <div style="padding: 12px 16px; background: rgba(255, 145, 0, 0.05); border: 1px solid rgba(255, 145, 0, 0.3); border-radius: 8px;">
                    <div style="font-weight: 700; color: var(--orange); font-size: 0.95rem; margin-bottom: 4px;">3. Direct Desktop Shortcut (.URL File):</div>
                    <div style="font-size: 0.85rem; color: var(--text); line-height: 1.4; margin-bottom: 8px;">
                        Ek click mein Windows Desktop shortcut download karein aur direct click se JARVIS open karein:
                    </div>
                    <a href="/api/download-shortcut" download="JARVIS.url" style="display: inline-block; padding: 6px 14px; background: var(--orange); color: #000000; font-weight: 700; border-radius: 6px; text-decoration: none; font-size: 0.85rem;">💾 Download Desktop App Shortcut</a>
                </div>
            </div>

            <div style="margin-top: 18px; text-align: right;">
                <button onclick="document.getElementById('installModal').style.display='none'" style="padding: 8px 18px; background: rgba(0,229,255,0.1); border: 1px solid var(--cyan); color: var(--cyan); border-radius: 8px; font-weight: 600; cursor: pointer;">Close</button>
            </div>
        </div>
    </div>

    <script>
        let voiceMuted = false;
        let isListening = false;
        let recognition = null;

        // Register Service Worker for PWA
        let deferredPrompt = null;

        // Check if currently on IP address and show 'Secure Mode' switch
        if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {{
            const secBtn = document.getElementById('secureSwitch');
            if (secBtn) secBtn.style.display = 'inline-flex';
        }}

        window.addEventListener('beforeinstallprompt', (e) => {{
            e.preventDefault();
            deferredPrompt = e;
            const btn = document.getElementById('installAppBtn');
            if (btn) btn.style.display = 'inline-flex';
        }});

        function triggerInstall() {{
            if (deferredPrompt) {{
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then((choice) => {{
                    if (choice.outcome === 'accepted') {{
                        document.getElementById('installAppBtn').textContent = '✅ INSTALLED';
                    }}
                    deferredPrompt = null;
                }});
            }} else {{
                document.getElementById('installModal').style.display = 'flex';
            }}
        }}

        if ('serviceWorker' in navigator) {{
            navigator.serviceWorker.register('/service-worker.js').catch(e => console.log('SW reg fail', e));
        }}

        let isProcessing = false;
        let speechAccumulator = '';

        // Initialize Web Speech API with debounce and full sentence wait
        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {{
            const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
            recognition = new SpeechRec();
            recognition.continuous = false;
            recognition.interimResults = true;
            recognition.lang = 'en-IN'; // Highly tuned for Hinglish & Indian English

            recognition.onstart = () => {{
                isListening = true;
                speechAccumulator = '';
                document.getElementById('micBtn').classList.add('listening');
                document.getElementById('reactorCore').classList.add('active');
                document.getElementById('reactorLabel').textContent = 'LISTENING...';
            }};

            recognition.onresult = (event) => {{
                let fullText = '';
                for (let i = 0; i < event.results.length; ++i) {{
                    fullText += event.results[i][0].transcript;
                }}
                speechAccumulator = fullText.trim();
                document.getElementById('promptInput').value = speechAccumulator;
            }};

            recognition.onerror = (event) => {{
                console.warn('Speech recognition error:', event.error);
                stopListening();
            }};

            recognition.onend = () => {{
                stopListening();
                // Submit only once after full sentence is completed and silence is reached
                if (speechAccumulator && !isProcessing) {{
                    submitPrompt();
                }}
            }};
        }}

        function toggleMic() {{
            if (isListening) {{
                stopListening();
            }} else {{
                startVoiceRecognition();
            }}
        }}

        function startVoiceRecognition() {{
            if (recognition) {{
                try {{
                    speechAccumulator = '';
                    recognition.start();
                }} catch (e) {{
                    console.log('Recognition restart:', e);
                }}
            }} else {{
                alert('Speech recognition is not supported in this browser. You can type directly!');
            }}
        }}

        function stopListening() {{
            isListening = false;
            document.getElementById('micBtn').classList.remove('listening');
            document.getElementById('reactorCore').classList.remove('active');
            if (!isProcessing) {{
                document.getElementById('reactorLabel').textContent = 'SYSTEM READY';
            }}
        }}

        function toggleAudio() {{
            voiceMuted = !voiceMuted;
            const btn = document.getElementById('muteToggle');
            btn.textContent = voiceMuted ? '🔇 MUTED' : '🔊 VOICE';
            btn.style.borderColor = voiceMuted ? 'var(--orange)' : 'var(--cyan)';
        }}

        function sendQuick(text) {{
            document.getElementById('promptInput').value = text;
            submitPrompt();
        }}

        async function submitPrompt() {{
            if (isProcessing) return;

            const input = document.getElementById('promptInput');
            const text = input.value.trim();
            if (!text) return;

            isProcessing = true;
            speechAccumulator = '';
            input.value = '';
            input.disabled = true;

            appendMessage('user', text);

            const core = document.getElementById('reactorCore');
            const label = document.getElementById('reactorLabel');
            core.classList.add('active');
            label.textContent = 'PROCESSING...';

            try {{
                const res = await fetch('/api/chat', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ prompt: text, voice_response: !voiceMuted }})
                }});

                const data = await res.json();
                if (data.reply) {{
                    appendMessage('jarvis', data.reply, data.tools);
                    if (data.audio_b64 && !voiceMuted) {{
                        playAudioB64(data.audio_b64);
                    }} else if (!voiceMuted && 'speechSynthesis' in window) {{
                        const utter = new SpeechSynthesisUtterance(data.reply);
                        window.speechSynthesis.speak(utter);
                    }}
                }} else if (data.error) {{
                    appendMessage('jarvis', '⚠️ ' + data.error);
                }}
            }} catch (e) {{
                appendMessage('jarvis', 'Connection error: ' + e.message);
            }} finally {{
                isProcessing = false;
                input.disabled = false;
                input.focus();
                if (!isListening) {{
                    core.classList.remove('active');
                    label.textContent = 'SYSTEM READY';
                }}
            }}
        }}

        function playAudioB64(base64Data) {{
            const audio = document.getElementById('ttsAudio');
            audio.src = 'data:audio/mp3;base64,' + base64Data;
            audio.play().catch(e => console.log('Audio autoplay blocked:', e));
        }}

        function appendMessage(sender, text, tools) {{
            const list = document.getElementById('chatList');
            const msg = document.createElement('div');
            msg.className = 'message ' + sender;

            const avatar = document.createElement('div');
            avatar.className = 'msg-avatar';
            avatar.textContent = sender === 'user' ? 'U' : 'J';

            const bubble = document.createElement('div');
            bubble.className = 'msg-bubble';

            let toolsHtml = '';
            if (tools && tools.length) {{
                toolsHtml = '<div>' + tools.map(t => `<span class="tool-chip">⚡ ${{t}}</span>`).join('') + '</div>';
            }}

            bubble.innerHTML = text.replace(/\\n/g, '<br>') + toolsHtml;

            msg.appendChild(avatar);
            msg.appendChild(bubble);
            list.appendChild(msg);
            list.scrollTop = list.scrollHeight;
        }}

        // Enter key to submit
        document.getElementById('promptInput').addEventListener('keydown', (e) => {{
            if (e.key === 'Enter') {{
                submitPrompt();
            }}
        }});

        // Live telemetry polling every 3 seconds
        async function updateTelemetry() {{
            try {{
                const res = await fetch('/api/status');
                const data = await res.json();

                document.getElementById('cpuVal').textContent = data.cpu_percent + '%';
                document.getElementById('cpuBar').style.width = data.cpu_percent + '%';

                document.getElementById('memVal').textContent = data.ram_used_gb + ' GB';
                document.getElementById('memBar').style.width = data.ram_percent + '%';

                const plug = data.battery.plugged ? '⚡ ' : '🔋 ';
                document.getElementById('battVal').textContent = plug + data.battery.percent + '%';
                document.getElementById('battBar').style.width = data.battery.percent + '%';

                document.getElementById('brainBadge').textContent = data.active_provider || 'AI BRAIN';
                document.getElementById('devVal').textContent = data.active_devices.join(', ').toUpperCase() || 'ONLINE';
            }} catch (e) {{}}
        }}

        setInterval(updateTelemetry, 3000);
        updateTelemetry();
    </script>
</body>
</html>
"""
