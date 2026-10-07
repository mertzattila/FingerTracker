"""
AirControl — önálló, mozgatható/méretezhető virtuális billentyűzet (tkinter).

A korábbi megoldás a billentyűzetet a kameraablakra rajzolta, ezért böngészés
közben használhatatlan volt. Ez a verzió egy KÜLÖN, natív ablakot nyit, amit a
képernyőn bárhova húzhatsz és átméretezhetsz (pl. a böngésző mellé).

FONTOS (macOS): a tkinter és a PyAutoGUI hívásokat a FŐSZÁLON kell futtatni,
különben M-chipes Macen összeomlik ("TIS/TSM in non-main thread"). Ezért ez az
osztály NEM indít saját szálat: a fő program (aircontrol.py) a főszálon tartja
életben a tkinter ablakot, és minden képkockában meghívja a `pump()`-ot, ami
egyszer pörgeti a tkinter eseményhurkot. A tényleges billentyűleütés is a
főszálról, a `pump()`-ban történik.

Célzás: a VALÓDI egérkurzor képernyő-pozíciójával mutatunk a gombokra (a kezed
az egérmódban mozgatja a kurzort), és csippentésre üt le a gomb.
"""

from __future__ import annotations

import time
import tkinter as tk

import pyautogui


ROWS = [
    list("1234567890"),
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    list("ZXCVBNM"),
    ["SPACE", "BKSP", "ENTER"],
]

KEY_COOLDOWN = 0.5  # két leütés közti minimum idő (s), ismétlésvédelem


class VirtualKeyboard:
    """Főszálon élő tkinter billentyűzet-ablak. Nem indít saját szálat.

    Életciklus:
      - toggle(): megnyitja/bezárja az ablakot (a főszálon).
      - update(pointer_screen, pinch): a fő ciklus adja át a kurzor képernyő-
        pozícióját és a csippentés állapotát (nem blokkol).
      - pump(): a fő ciklus hívja minden képkockában; egyszer pörgeti a tkinter
        eseményhurkot, frissíti a kiemelést, és csippentésre leüt.
    """

    def __init__(self) -> None:
        self.enabled = False
        self._root: tk.Tk | None = None
        self._buttons: dict[str, tk.Button] = {}
        self._pointer_screen: tuple[int, int] | None = None
        self._pinch = False
        self._last_press_time = 0.0

    # --- A fő ciklus felől hívott API --------------------------------------
    def toggle(self) -> None:
        if self.enabled:
            self._close()
        else:
            self._open()

    def update(self, pointer_screen: tuple[int, int] | None, pinch: bool) -> bool:
        """Átveszi a kurzor képernyő-pozícióját és a csippentés állapotát.

        Visszatér: True, ha a kurzor épp egy gomb fölött van (a hívó ebből
        tudja, hogy "a billentyűzeten vagyunk").
        """
        self._pointer_screen = pointer_screen
        self._pinch = pinch
        if not self.enabled:
            return False
        return self._button_at(pointer_screen) is not None if pointer_screen else False

    def pump(self) -> None:
        """Egyszer pörgeti a tkinter eseményhurkot + kiemelés + leütés.

        A FŐSZÁLON kell hívni (minden képkockában). Ha az ablakot a felhasználó
        az X-szel bezárta, ezt észleljük és letiltjuk magunkat.
        """
        root = self._root
        if root is None or not self.enabled:
            return

        try:
            # Kurzor fölötti gomb kiemelése.
            hovered = (self._button_at(self._pointer_screen)
                       if self._pointer_screen else None)
            for label, btn in self._buttons.items():
                btn.configure(bg="#ff8c00" if label == hovered else "#3c3c3c")

            # Csippentésre leütés (ismétlésvédelemmel) — főszálon, macOS-barát.
            now = time.time()
            if self._pinch and hovered and \
                    (now - self._last_press_time) > KEY_COOLDOWN:
                self._press(hovered)
                self._last_press_time = now

            # A tkinter eseményhurok egyszeri pörgetése (nem blokkol).
            root.update_idletasks()
            root.update()
        except tk.TclError:
            # Az ablakot bezárták (X). Takarítás.
            self._root = None
            self._buttons = {}
            self.enabled = False

    def shutdown(self) -> None:
        self._close()

    # --- Ablak ---------------------------------------------------------------
    def _open(self) -> None:
        root = tk.Tk()
        self._root = root
        root.title("AirControl – Billentyuzet")
        root.configure(bg="#101010")
        root.attributes("-topmost", True)   # mindig felül (a böngésző fölött)
        root.geometry("860x320+120+460")    # kezdő méret+pozíció; húzható/méretezhető
        root.minsize(420, 180)

        for row in ROWS:
            frame = tk.Frame(root, bg="#101010")
            frame.pack(fill="both", expand=True, padx=4, pady=3)
            for label in row:
                text = {"SPACE": "Szokoz", "BKSP": "<--", "ENTER": "Enter"}.get(
                    label, label
                )
                btn = tk.Button(
                    frame, text=text, bg="#3c3c3c", fg="white",
                    activebackground="#ff8c00", relief="raised", bd=1,
                    font=("Helvetica", 16, "bold"),
                    command=lambda l=label: self._press(l),  # egérrel is megy
                )
                # A SPACE/BKSP/ENTER szélesebb legyen.
                expand_w = 4 if label == "SPACE" else 2 if label in ("BKSP", "ENTER") else 1
                btn.pack(side="left", fill="both", expand=True, padx=2,
                         ipadx=expand_w * 3, ipady=6)
                self._buttons[label] = btn

        tk.Label(
            root,
            text="Vidd a kurzort egy gombra (kezzel), es CSIPPENTS a leuteshez. "
                 "Az ablak szabadon mozgathato es atmerezheto.",
            bg="#101010", fg="#9a9a9a", font=("Helvetica", 10),
        ).pack(fill="x", pady=(0, 4))

        # Az X-gomb csak letiltja a billentyűzetet (nem állítja le a programot).
        root.protocol("WM_DELETE_WINDOW", self._close)
        self.enabled = True

    def _close(self) -> None:
        self.enabled = False
        root = self._root
        self._root = None
        self._buttons = {}
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass

    # --- Segédek ------------------------------------------------------------
    def _button_at(self, pointer_screen) -> str | None:
        """Melyik gomb van a megadott képernyő-pixel alatt (ha van)."""
        if self._root is None or pointer_screen is None:
            return None
        px, py = pointer_screen
        for label, btn in self._buttons.items():
            try:
                x = btn.winfo_rootx()
                y = btn.winfo_rooty()
                w = btn.winfo_width()
                h = btn.winfo_height()
            except Exception:
                continue
            if x <= px <= x + w and y <= py <= y + h:
                return label
        return None

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
