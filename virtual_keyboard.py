"""
Virtuális billentyűzet, amit a kameraablakra rajzolunk ki.

A felhasználó a mutatóujja hegyével "céloz" egy gombra, és egy
hüvelyk-mutató csippentéssel "lenyomja". A tényleges billentyűleütést a
PyAutoGUI végzi, így az az éppen fókuszban lévő alkalmazásba kerül.

A billentyűzet be/ki kapcsolható (a finger_tracker 'k' billentyűvel vezérli).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import pyautogui


# A billentyűzet sorai. A speciális gombok címkéje külön kezelt (lásd _press).
ROWS = [
    list("1234567890"),
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
    ["SPACE", "BKSP", "ENTER"],
]

# A csippentés utáni "lenyomás" ismétlésvédelme (másodperc).
KEY_COOLDOWN = 0.5

# Mennyi ideig kell a gombon tartani az ujjat a kiváltáshoz (dwell, másodperc).
# A dwell egy alternatív/kiegészítő mód: ha nem csippentesz, de rajta tartod a
# gombon az ujjad, az is leüti. 0-ra állítva kikapcsol.
DWELL_TIME = 0.0


@dataclass
class Key:
    label: str
    x: int
    y: int
    w: int
    h: int

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


class VirtualKeyboard:
    """OpenCV-re rajzolt virtuális billentyűzet célzással és csippentéssel."""

    def __init__(self) -> None:
        self.enabled = False
        self._keys: list[Key] = []
        self._layout_for_size: tuple[int, int] | None = None
        self._last_press_time = 0.0
        self._last_label: str | None = None
        self._hover_label: str | None = None
        self._hover_since = 0.0

    def toggle(self) -> None:
        self.enabled = not self.enabled
        # Lenullázzuk a hover-állapotot, hogy ne üssön be gombot bekapcsoláskor.
        self._hover_label = None
        self._hover_since = 0.0

    # --- Elrendezés ---------------------------------------------------------
    def _build_layout(self, width: int, height: int) -> None:
        """A billentyűzet gombjainak pozícióját a képméretre számolja ki.

        A billentyűzet a kép alsó ~45%-át foglalja el, középre igazítva.
        """
        self._keys = []
        kb_top = int(height * 0.52)
        kb_height = height - kb_top - 10
        row_h = kb_height // len(ROWS)
        pad = 6

        for r, row in enumerate(ROWS):
            # A szóköz sort kicsit arányosítjuk, hogy a SPACE szélesebb legyen.
            weights = []
            for label in row:
                if label == "SPACE":
                    weights.append(4.0)
                elif label in ("BKSP", "ENTER"):
                    weights.append(2.0)
                else:
                    weights.append(1.0)
            total_w = sum(weights)
            usable_w = width - 2 * pad
            x = pad
            y = kb_top + r * row_h
            for label, wgt in zip(row, weights):
                kw = int(usable_w * (wgt / total_w))
                self._keys.append(
                    Key(label=label, x=x + pad // 2, y=y + pad // 2,
                        w=kw - pad, h=row_h - pad)
                )
                x += kw
        self._layout_for_size = (width, height)

    # --- Kirajzolás ---------------------------------------------------------
    def draw(self, frame, pointer_px: tuple[int, int] | None) -> None:
        """A billentyűzet kirajzolása a frame-re, a mutató gomb kiemelésével."""
        if not self.enabled:
            return
        h, w = frame.shape[:2]
        if self._layout_for_size != (w, h):
            self._build_layout(w, h)

        # Félig átlátszó háttér a billentyűzet mögé.
        if self._keys:
            top = min(k.y for k in self._keys) - 8
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, top), (w, h), (20, 20, 20), cv2.FILLED)
            cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

        hovered = None
        if pointer_px is not None:
            for key in self._keys:
                if key.contains(*pointer_px):
                    hovered = key.label
                    break

        for key in self._keys:
            is_hover = key.label == hovered
            bg = (0, 140, 255) if is_hover else (60, 60, 60)
            cv2.rectangle(frame, (key.x, key.y),
                          (key.x + key.w, key.y + key.h), bg, cv2.FILLED)
            cv2.rectangle(frame, (key.x, key.y),
                          (key.x + key.w, key.y + key.h), (200, 200, 200), 1)

            text = {"SPACE": "___", "BKSP": "<--", "ENTER": "<-'"}.get(
                key.label, key.label
            )
            font_scale = 0.6 if len(text) <= 3 else 0.5
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX,
                                          font_scale, 2)
            tx = key.x + (key.w - tw) // 2
            ty = key.y + (key.h + th) // 2
            cv2.putText(frame, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX,
                        font_scale, (255, 255, 255), 2, cv2.LINE_AA)

        # Dwell (ráidőzítés) folyamatjelző, ha használatban van.
        if DWELL_TIME > 0 and self._hover_label and pointer_px is not None:
            held = time.time() - self._hover_since
            frac = max(0.0, min(1.0, held / DWELL_TIME))
            cv2.circle(frame, pointer_px, 18, (0, 140, 255), 2)
            cv2.ellipse(frame, pointer_px, (18, 18), -90, 0,
                        int(360 * frac), (0, 255, 0), 4)

    # --- Interakció ---------------------------------------------------------
    def update(self, pointer_px: tuple[int, int] | None, pinch: bool) -> bool:
        """A célzás és csippentés feldolgozása.

        `pointer_px`: a mutatóujj hegye pixelben, vagy None, ha nincs kéz.
        `pinch`: igaz, ha épp hüvelyk-mutató csippentés van (él-trigger a hívónál
                 nem szükséges, mert itt KEY_COOLDOWN véd az ismétlés ellen).

        Visszatér: True, ha a billentyűzet "elkapta" az interakciót (azaz a
        mutató a billentyűzet területén belül van), így a hívó NEM mozgatja az
        egeret ilyenkor.
        """
        if not self.enabled or pointer_px is None:
            self._hover_label = None
            return False

        # Melyik gomb fölött van az ujj?
        target = None
        for key in self._keys:
            if key.contains(*pointer_px):
                target = key.label
                break

        inside_kb = pointer_px[1] >= (min((k.y for k in self._keys), default=10) - 8) \
            if self._keys else False

        now = time.time()

        # Dwell-mód: ha ugyanazon a gombon tartjuk az ujjat elég sokáig.
        if DWELL_TIME > 0:
            if target and target == self._hover_label:
                if (now - self._hover_since) >= DWELL_TIME and \
                        (now - self._last_press_time) > KEY_COOLDOWN:
                    self._press(target)
                    self._last_press_time = now
                    self._hover_since = now  # újraindít, hogy ne ismételjen
            else:
                self._hover_label = target
                self._hover_since = now

        # Csippentés-mód: ha célgomb fölött vagyunk és csippentünk.
        if pinch and target and (now - self._last_press_time) > KEY_COOLDOWN:
            self._press(target)
            self._last_press_time = now

        return inside_kb

    def _press(self, label: str) -> None:
        """A tényleges billentyűleütés PyAutoGUI-val."""
        if label == "SPACE":
            pyautogui.press("space")
        elif label == "BKSP":
            pyautogui.press("backspace")
        elif label == "ENTER":
            pyautogui.press("enter")
        else:
            pyautogui.typewrite(label.lower(), interval=0)
        self._last_label = label
