#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Local mock WeCom/Feishu group-bot receiver for the acceptance drill.

It listens on 127.0.0.1:18080, accepts the SAME payload shapes the real bots do,
persists every received message to tools/received/*.json, and renders a PNG that
looks like the message as seen in the test group. All URLs in screenshots are
fabricated (example.invalid). No real customer / no real webhook is involved.
"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

for _s in (sys.stdout, sys.stderr):
    _enc = getattr(_s, "encoding", "") or ""
    if _enc.lower().replace("-", "") not in ("utf8", "utf"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECEIVED = os.path.join(ROOT, "tools", "received")
SHOTS = os.path.join(ROOT, "evidence", "screenshots")
os.makedirs(RECEIVED, exist_ok=True)
os.makedirs(SHOTS, exist_ok=True)

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"


def render_card_png(path: str, channel: str, message: dict, title: str):
    from PIL import Image, ImageDraw, ImageFont
    import re
    W = 900
    pad = 24
    f_title = ImageFont.truetype(FONT_BOLD, 22)
    f_body = ImageFont.truetype(FONT_PATH, 18)
    f_small = ImageFont.truetype(FONT_PATH, 14)

    # Emoji are replaced with ASCII markers: msyh.ttc has no color-emoji glyphs
    # and renders them as tofu boxes. The message payload keeps the real emoji.
    def ascii_clean(s: str) -> str:
        # renderer already writes [FIRING]/[RESOLVED] text next to the emoji,
        # so drop the emoji glyph itself to avoid a doubled marker.
        return s.replace("🔴", "").replace("✅", "")

    if channel == "wecom":
        content = message.get("markdown", {}).get("content", "")
        lines = []
        for ln in content.splitlines():
            ln = ascii_clean(ln).replace("**", "")
            ln = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1  \2", ln)
            lines.append(ln)
        header_color = (200, 48, 48) if "[FIRING]" in content else (32, 160, 96)
    else:
        card = message.get("card", {})
        header_color = (200, 48, 48) if card.get("header", {}).get("template") == "red" else (32, 160, 96)
        lines = []
        for el in card.get("elements", []):
            t = el.get("text", {}).get("content", "")
            if t and t != "hr":
                t = ascii_clean(t).replace("**", "")
                # Feishu lark_md renders [text](url) as a hyperlink; show human form.
                t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", t)
                lines.append(t)
        lines.insert(0, ascii_clean(card.get("header", {}).get("title", {}).get("content", "")))

    line_h = 30
    max_chars = 74  # fit within card width at 18px msyh
    wrapped = []
    for ln in lines:
        chunks = [ln[i:i + max_chars] for i in range(0, len(ln), max_chars)] or [""]
        wrapped.extend(chunks)

    top_chrome = 56
    card_y0 = 76
    title_h = 50
    body_top = card_y0 + title_h
    body_h = max(1, len(wrapped)) * line_h
    card_bottom = body_top + body_h + 20
    footer_y = card_bottom + 18
    H = footer_y + 34

    img = Image.new("RGB", (W, H), (245, 246, 248))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, top_chrome], fill=(32, 34, 38))
    d.text((pad, 16), f"Test Group  ·  {channel.upper()} group bot", font=f_title, fill=(255, 255, 255))
    card_x0, card_x1 = pad, W - pad
    d.rounded_rectangle([card_x0, card_y0, card_x1, card_bottom], radius=10,
                        fill=(255, 255, 255), outline=(220, 222, 226), width=1)
    d.rectangle([card_x0, card_y0, card_x1, card_y0 + 6], fill=header_color)
    d.text((card_x0 + pad, card_y0 + 20), title, font=f_title, fill=(32, 34, 38))
    y = body_top
    for c in wrapped:
        d.text((card_x0 + pad, y), c, font=f_body, fill=(48, 50, 56))
        y += line_h
    d.text((pad, footer_y), "Fabricated test group · example.invalid · no real data",
           font=f_small, fill=(150, 152, 158))
    img.save(path)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        path = urlparse(self.path).path
        channel = "wecom" if "wecom" in path else "feishu" if "feishu" in path else "unknown"
        try:
            message = json.loads(body.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            return
        seq = len([f for f in os.listdir(RECEIVED) if f.startswith(channel)])
        with open(os.path.join(RECEIVED, f"{channel}_{seq:03d}.json"), "w", encoding="utf-8") as f:
            json.dump({"channel": channel, "path": path, "message": message}, f,
                      ensure_ascii=False, indent=2)
        resolved = ("RESOLVED" in json.dumps(message, ensure_ascii=False)
                    or (message.get("card", {}).get("header", {}).get("template") == "green"))
        state = "resolved" if resolved else "critical"
        shot = os.path.join(SHOTS, f"{state}_{channel}.png")
        try:
            render_card_png(shot, channel, message, f"{state.upper()} notification")
        except Exception as exc:  # screenshot is best-effort; persistence is mandatory
            print("WARN screenshot failed:", exc)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"errcode":0,"errmsg":"ok"}')

    def log_message(self, *args):
        pass


def serve(port=18080):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"mock group bot listening on 127.0.0.1:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 18080)
