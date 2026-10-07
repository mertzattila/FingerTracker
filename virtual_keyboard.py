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

Célzás: NEM a rendszer-egérkurzorral, hanem közvetlenül a KÉZ kamerabeli
pozíciójával mozgatunk egy jelölőt a billentyűzet saját vásznán. Így a gépelés
teljesen független az egértől: NINCS kattintás, tehát NINCS fókuszvesztés.

Fókusz: a billentyűzet bekapcsolásakor (és a megnyitó ablak miatt) a célmező
elveszítheti a fókuszt. Ezt macOS-en egy AppleScript hívással adjuk vissza a
korábban aktív alkalmazásnak, hogy a leütések oda kerüljenek.
"""

from __future__ import annotations

import subprocess
import sys
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
        self._hand_norm: tuple[float, float] | None = None
        self._pinch = False
        self._build_layout()

    # --- A fő ciklus felől hívott API --------------------------------------
    def toggle(self) -> None:
        if self.enabled:
            self._close()
        else:
            self._open()

    def update(self, hand_norm: tuple[float, float] | None, pinch: bool) -> None:
        """A KÉZ normalizált (0..1) pozíciója a kameraképben + csippentés.

        FONTOS: itt NEM a rendszer-egérkurzort használjuk, hanem közvetlenül a
        kéz pozícióját képezzük a billentyűzet saját vásznára. Így a gépelés
        teljesen független az egértől: nincs kattintás, nincs fókuszvesztés.
        """
        self._hand_norm = hand_norm
        self._pinch = pinch

    def pump(self) -> None:
        """A fő ciklus hívja minden képkockában (főszálon): kirajzol + leüt."""
        if not self.enabled:
            return

        # A KÉZ normalizált pozícióját (0..1) közvetlenül a billentyűzet saját
        # vásznára képezzük. Nincs köze a rendszer-egérkurzorhoz -> nincs
        # kattintás, nincs fókuszvesztés.
        local = self._hand_to_board(self._hand_norm)

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
        # Jegyezzük meg, melyik app volt aktív (ahova gépelni akarsz), hogy a
        # billentyűzet-ablak megnyitása után visszaadhassuk neki a fókuszt.
        prev_app = _frontmost_app()

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

        # A fókuszt adjuk vissza a korábbi appnak (ahova gépelni fogsz).
        if prev_app:
            _activate_app(prev_app)

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

        # Jelölő: hol áll a KEZED a billentyűzeten (nem a rendszerkurzor).
        local = self._hand_to_board(self._hand_norm)
        if local is not None:
            cv2.circle(img, local, 10, (0, 255, 0), 2)
            cv2.circle(img, local, 2, (0, 255, 0), cv2.FILLED)

        cv2.putText(
            img,
            "Mozgasd a kezed a billentyuzeten, es CSIPPENTS a leuteshez. "
            "(Nem kell az egerrel kattintani!)",
            (12, BOARD_H - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
            (150, 150, 150), 1, cv2.LINE_AA,
        )
        try:
            cv2.imshow(WINDOW_NAME, img)
        except Exception:
            self.enabled = False

    # --- Koordináta-leképezés ------------------------------------------------
    def _hand_to_board(self, hand_norm):
        """A kéz normalizált (0..1) kamerapozícióját a logikai vászonra képezi.

        Nincs szükség a rendszer-egérkurzorra vagy az ablak képernyő-helyére:
        a kéz közvetlenül a billentyűzet-vásznon mozgat egy jelölőt. Egy kis
        holtsávval könnyebb elérni a széleket.
        """
        if hand_norm is None:
            return None
        margin = 0.08
        nx = (hand_norm[0] - margin) / (1.0 - 2 * margin)
        ny = (hand_norm[1] - margin) / (1.0 - 2 * margin)
        nx = max(0.0, min(1.0, nx))
        ny = max(0.0, min(1.0, ny))
        return int(nx * BOARD_W), int(ny * BOARD_H)

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


# --- macOS fókuszkezelés (más platformon no-op) ----------------------------
def _is_macos() -> bool:
    return sys.platform == "darwin"


def _frontmost_app() -> str | None:
    """Visszaadja az aktuálisan aktív (frontmost) alkalmazás nevét macOS-en.

    Más platformon None-t ad (ott nincs rá szükség / nincs ez a probléma).
    """
    if not _is_macos():
        return None
    try:
        out = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first '
             'application process whose frontmost is true'],
            capture_output=True, text=True, timeout=1.5,
        )
        name = out.stdout.strip()
        return name or None
    except Exception:
        return None


def _activate_app(app_name: str) -> None:
    """Visszaadja a fókuszt a megadott nevű alkalmazásnak (macOS)."""
    if not _is_macos() or not app_name:
        return
    try:
        subprocess.run(
            ["osascript", "-e", f'tell application "{app_name}" to activate'],
            capture_output=True, text=True, timeout=1.5,
        )
    except Exception:
        pass
