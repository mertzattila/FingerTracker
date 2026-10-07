"""
AirControl — önálló virtuális billentyűzet KÜLÖN OpenCV-ablakban.

Miért nem tkinter? macOS-en (különösen M-chipen) a tkinter és az OpenCV
`imshow` egy folyamatban ütközik (mindkettő NSApplication/Cocoa-alapú), és a
Tk 8.6 egy új macOS-en nem létező szelektort hív -> azonnali összeomlás
("NSApplication macOSVersion unrecognized selector"). Ezért a billentyűzetet
is OpenCV-vel rajzoljuk, de EGY KÜLÖN ablakba (nem a kamera képére).

Előnyök:
  - Nincs tkinter -> nincs NSApplication-ütközés, stabil M2 Macen.
  - Külön `WINDOW_NORMAL` OpenCV-ablak: a címsoránál fogva MOZGATHATÓ, a
    sarkánál MÉRETEZHETŐ, és odahúzható a böngésző mellé.
  - Mindig felül tartjuk (topmost), ha a platform támogatja.

Célzás: a VALÓDI egérkurzor képernyő-pozíciójával mutatunk a gombokra (a kezed
az egérmódban mozgatja a kurzort). A billentyűzetablak saját képernyő-pozícióját
`cv2.getWindowImageRect`-tel kérdezzük le, így a kurzort a gombokhoz tudjuk
rendelni akkor is, ha az ablakot elhúztad/átméretezted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np
import pyautogui


WINDOW_NAME = "AirControl – Billentyuzet"

ROWS = [
    list("1234567890"),
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
    ["SPACE", "BKSP", "ENTER"],
]

KEY_COOLDOWN = 0.5  # két leütés közti minimum idő (s)

# A billentyűzet-kép logikai mérete (az ablakot ettől függetlenül átméretezheted;
# az OpenCV a WINDOW_NORMAL miatt skálázza a tartalmat az ablakmérethez).
BOARD_W = 900
BOARD_H = 340


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
    """Külön OpenCV-ablakban megjelenő virtuális billentyűzet."""

    def __init__(self) -> None:
        self.enabled = False
        self._keys: list[Key] = []
        self._last_press_time = 0.0
        self._hover_label: str | None = None
        self._pointer_screen: tuple[int, int] | None = None
        self._pinch = False
        self._build_layout()

    # --- A fő ciklus felől hívott API --------------------------------------
    def toggle(self) -> None:
        if self.enabled:
            self._close()
        else:
            self._open()

    def update(self, pointer_screen: tuple[int, int] | None, pinch: bool) -> bool:
        """Átveszi a kurzor képernyő-pozícióját és a csippentés állapotát.

        Visszatér: True, ha a kurzor a billentyűzet-ABLAK területén belül van
        (nem csak egy gombon). A hívó ebből tudja, hogy EL KELL nyomnia minden
        egérkattintást, nehogy a billentyűzet-ablakra kattintva elvegye a
        billentyűzet-fókuszt a céltól (ahova gépelni akarsz).
        """
        self._pointer_screen = pointer_screen
        self._pinch = pinch
        if not self.enabled:
            return False
        return self.is_cursor_over_window()

    def is_cursor_over_window(self) -> bool:
        """Igaz, ha a kurzor a billentyűzet-ablak téglalapján belül van."""
        if not self.enabled or self._pointer_screen is None:
            return False
        try:
            x, y, w, h = cv2.getWindowImageRect(WINDOW_NAME)
        except Exception:
            return False
        if w <= 0 or h <= 0:
            return False
        px, py = self._pointer_screen
        return x <= px <= x + w and y <= py <= y + h

    def pump(self) -> None:
        """A fő ciklus hívja minden képkockában (főszálon): kirajzol + leüt."""
        if not self.enabled:
            return

        # A billentyűzetablak képernyő-pozíciója és mérete, hogy a globális
        # kurzort a gombokhoz tudjuk rendelni.
        local = self._screen_to_board(self._pointer_screen)

        self._hover_label = None
        if local is not None:
            for key in self._keys:
                if key.contains(*local):
                    self._hover_label = key.label
                    break

        # Csippentésre leütés (ismétlésvédelemmel).
        now = time.time()
        if self._pinch and self._hover_label and \
                (now - self._last_press_time) > KEY_COOLDOWN:
            self._press(self._hover_label)
            self._last_press_time = now

        self._render()

    def shutdown(self) -> None:
        self._close()

    # --- Ablak ---------------------------------------------------------------
    def _open(self) -> None:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, BOARD_W, BOARD_H)
        try:
            cv2.moveWindow(WINDOW_NAME, 120, 460)
        except Exception:
            pass
        # Mindig felül, ha a backend támogatja.
        try:
            prop = getattr(cv2, "WND_PROP_TOPMOST", None)
            if prop is not None:
                cv2.setWindowProperty(WINDOW_NAME, prop, 1.0)
        except Exception:
            pass
        self.enabled = True
        self._render()

    def _close(self) -> None:
        self.enabled = False
        self._hover_label = None
        try:
            cv2.destroyWindow(WINDOW_NAME)
        except Exception:
            pass

    # --- Elrendezés és kirajzolás -------------------------------------------
    def _build_layout(self) -> None:
        """A gombok pozícióját a BOARD_W x BOARD_H logikai vászonra számolja."""
        self._keys = []
        pad = 8
        row_h = (BOARD_H - 2 * pad) // len(ROWS)
        for r, row in enumerate(ROWS):
            weights = []
            for label in row:
                if label == "SPACE":
                    weights.append(4.0)
                elif label in ("BKSP", "ENTER"):
                    weights.append(2.0)
                else:
                    weights.append(1.0)
            total = sum(weights)
            usable = BOARD_W - 2 * pad
            x = pad
            y = pad + r * row_h
            for label, wgt in zip(row, weights):
                kw = int(usable * (wgt / total))
                self._keys.append(
                    Key(label, x + 3, y + 3, kw - 6, row_h - 6)
                )
                x += kw

    def _render(self) -> None:
        """Kirajzolja a billentyűzetet a saját ablakba."""
        img = np.full((BOARD_H, BOARD_W, 3), 16, dtype=np.uint8)
        for key in self._keys:
            is_hover = key.label == self._hover_label
            bg = (0, 140, 255) if is_hover else (60, 60, 60)
            cv2.rectangle(img, (key.x, key.y),
                          (key.x + key.w, key.y + key.h), bg, cv2.FILLED)
            cv2.rectangle(img, (key.x, key.y),
                          (key.x + key.w, key.y + key.h), (200, 200, 200), 1)
            text = {"SPACE": "Szokoz", "BKSP": "<--", "ENTER": "Enter"}.get(
                key.label, key.label
            )
            scale = 0.8 if len(text) == 1 else 0.6
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
            tx = key.x + (key.w - tw) // 2
            ty = key.y + (key.h + th) // 2
            cv2.putText(img, text, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX,
                        scale, (255, 255, 255), 2, cv2.LINE_AA)

        cv2.putText(
            img,
            "Vidd a kurzort egy gombra, es CSIPPENTS a leuteshez. "
            "Az ablak mozgathato/merezheto.",
            (12, BOARD_H - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
            (150, 150, 150), 1, cv2.LINE_AA,
        )
        try:
            cv2.imshow(WINDOW_NAME, img)
        except Exception:
            self.enabled = False

    # --- Koordináta-leképezés ------------------------------------------------
    def _screen_to_board(self, pointer_screen):
        """A globális kurzor-képernyőpozíciót a logikai vászon koordinátáira
        képezi le, figyelembe véve az ablak aktuális helyét és méretét."""
        if pointer_screen is None:
            return None
        try:
            x, y, w, h = cv2.getWindowImageRect(WINDOW_NAME)
        except Exception:
            return None
        if w <= 0 or h <= 0:
            return None
        px, py = pointer_screen
        if not (x <= px <= x + w and y <= py <= y + h):
            return None
        # Az ablak tartalma a BOARD_W x BOARD_H vászon az ablakméretre skálázva.
        bx = int((px - x) / w * BOARD_W)
        by = int((py - y) / h * BOARD_H)
        return bx, by

    def _press(self, label: str) -> None:
        """A tényleges billentyűleütés PyAutoGUI-val (a fókuszált appba)."""
        if label == "SPACE":
            pyautogui.press("space")
        elif label == "BKSP":
            pyautogui.press("backspace")
        elif label == "ENTER":
            pyautogui.press("enter")
        else:
            pyautogui.typewrite(label.lower(), interval=0)
