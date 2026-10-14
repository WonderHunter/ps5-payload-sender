"""Small simplified flags drawn on a Tk canvas (emoji flags don't render on Windows)."""

import math
import tkinter as tk


def _star(cx, cy, r, rot=-90):
    pts = []
    for i in range(10):
        a = math.radians(rot + i * 36)
        rr = r if i % 2 == 0 else r * 0.4
        pts += [cx + rr * math.cos(a), cy + rr * math.sin(a)]
    return pts


def _hstripes(cv, w, h, colors, weights=None):
    weights = weights or [1] * len(colors)
    total, y = sum(weights), 0
    for color, wt in zip(colors, weights):
        y2 = y + h * wt / total
        cv.create_rectangle(0, y, w, y2, fill=color, width=0)
        y = y2


def _vstripes(cv, w, h, colors):
    step = w / len(colors)
    for i, color in enumerate(colors):
        cv.create_rectangle(i * step, 0, (i + 1) * step, h, fill=color, width=0)


def draw(cv, code, w, h):
    s = h / 14  # line widths scale with the flag size
    if code == "fr":
        _vstripes(cv, w, h, ["#0055A4", "#FFFFFF", "#EF4135"])
    elif code == "it":
        _vstripes(cv, w, h, ["#009246", "#FFFFFF", "#CE2B37"])
    elif code == "de":
        _hstripes(cv, w, h, ["#000000", "#DD0000", "#FFCE00"])
    elif code == "ru":
        _hstripes(cv, w, h, ["#FFFFFF", "#0039A6", "#D52B1E"])
    elif code == "nl":
        _hstripes(cv, w, h, ["#AE1C28", "#FFFFFF", "#21468B"])
    elif code == "pl":
        _hstripes(cv, w, h, ["#FFFFFF", "#DC143C"])
    elif code == "uk":
        _hstripes(cv, w, h, ["#0057B7", "#FFD700"])
    elif code == "es":
        _hstripes(cv, w, h, ["#AA151B", "#F1BF00", "#AA151B"], [1, 2, 1])
    elif code == "en":
        cv.create_rectangle(0, 0, w, h, fill="#012169", width=0)
        for x0, y0, x1, y1 in ((0, 0, w, h), (0, h, w, 0)):
            cv.create_line(x0, y0, x1, y1, fill="#FFFFFF", width=3 * s)
            cv.create_line(x0, y0, x1, y1, fill="#C8102E", width=1 * s)
        cv.create_rectangle(w / 2 - 2.5 * s, 0, w / 2 + 2.5 * s, h, fill="#FFFFFF", width=0)
        cv.create_rectangle(0, h / 2 - 2.5 * s, w, h / 2 + 2.5 * s, fill="#FFFFFF", width=0)
        cv.create_rectangle(w / 2 - 1.3 * s, 0, w / 2 + 1.3 * s, h, fill="#C8102E", width=0)
        cv.create_rectangle(0, h / 2 - 1.3 * s, w, h / 2 + 1.3 * s, fill="#C8102E", width=0)
    elif code == "pt":
        cv.create_rectangle(0, 0, w * 0.4, h, fill="#006600", width=0)
        cv.create_rectangle(w * 0.4, 0, w, h, fill="#FF0000", width=0)
        r = h * 0.26
        cv.create_oval(w * 0.4 - r, h / 2 - r, w * 0.4 + r, h / 2 + r, fill="#FFCC00", width=0)
        r *= 0.55
        cv.create_oval(w * 0.4 - r, h / 2 - r, w * 0.4 + r, h / 2 + r, fill="#FFFFFF", outline="#FF0000", width=s)
    elif code == "ar":
        cv.create_rectangle(0, 0, w, h, fill="#006C35", width=0)
        cv.create_rectangle(w * 0.28, h * 0.32, w * 0.72, h * 0.32 + 1.6 * s, fill="#FFFFFF", width=0)
        cv.create_rectangle(w * 0.22, h * 0.48, w * 0.78, h * 0.48 + 1.2 * s, fill="#FFFFFF", width=0)
        cv.create_rectangle(w * 0.28, h * 0.68, w * 0.72, h * 0.68 + 1 * s, fill="#FFFFFF", width=0)
    elif code == "ja":
        cv.create_rectangle(0, 0, w, h, fill="#FFFFFF", width=0)
        r = h * 0.3
        cv.create_oval(w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r, fill="#BC002D", width=0)
    elif code == "zh":
        cv.create_rectangle(0, 0, w, h, fill="#EE1C25", width=0)
        cv.create_polygon(_star(w * 0.2, h * 0.32, h * 0.2), fill="#FFDE00", width=0)
        for x, y in ((0.36, 0.12), (0.43, 0.25), (0.43, 0.42), (0.36, 0.54)):
            cv.create_polygon(_star(w * x, h * y, h * 0.07), fill="#FFDE00", width=0)
    elif code == "ko":
        cv.create_rectangle(0, 0, w, h, fill="#FFFFFF", width=0)
        r = h * 0.26
        box = (w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r)
        cv.create_arc(*box, start=0, extent=180, fill="#CD2E3A", width=0, style="pieslice")
        cv.create_arc(*box, start=180, extent=180, fill="#0047A0", width=0, style="pieslice")
        d = h * 0.12
        for cx, cy, sx in ((w * 0.17, h * 0.2, 1), (w * 0.83, h * 0.8, 1), (w * 0.83, h * 0.2, -1), (w * 0.17, h * 0.8, -1)):
            cv.create_line(cx - d * sx, cy - d, cx + d * sx, cy + d, fill="#000000", width=1.6 * s)
    elif code == "tr":
        cv.create_rectangle(0, 0, w, h, fill="#E30A17", width=0)
        r = h * 0.27
        cv.create_oval(w * 0.36 - r, h / 2 - r, w * 0.36 + r, h / 2 + r, fill="#FFFFFF", width=0)
        r2 = r * 0.8
        cv.create_oval(w * 0.42 - r2, h / 2 - r2, w * 0.42 + r2, h / 2 + r2, fill="#E30A17", width=0)
        cv.create_polygon(_star(w * 0.62, h / 2, h * 0.14, rot=-180), fill="#FFFFFF", width=0)
    else:
        cv.create_rectangle(0, 0, w, h, fill="#888888", width=0)


def flag(parent, code, scale=1.0, bg="#000000"):
    w, h = round(21 * scale), round(14 * scale)
    cv = tk.Canvas(parent, width=w, height=h, bg=bg, highlightthickness=0, bd=0)
    draw(cv, code, w, h)
    return cv
