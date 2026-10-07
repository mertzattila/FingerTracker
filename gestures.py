"""
Gesztusfelismerés a MediaPipe kéz-landmarkokból.

Ez a modul tisztán a kéz "állapotát" számolja ki (melyik ujj van felállítva,
mekkora a csippentési távolság, hol a mutatóujj hegye stb.), és ebből egy
magas szintű gesztust ad vissza. A tényleges egér-/billentyűakciókat a hívó
(finger_tracker.py) végzi, hogy a felismerés és a cselekvés szét legyen választva.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto


# A MediaPipe Hands 21 landmarkjának indexei, amiket használunk.
WRIST = 0
THUMB_TIP = 4
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_TIP = 8
MIDDLE_MCP = 9
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_PIP = 14
RING_TIP = 16
PINKY_PIP = 18
PINKY_TIP = 20


class Gesture(Enum):
    """Magas szintű, felismert kézgesztusok."""

    NONE = auto()           # nincs értelmezhető gesztus / nyitott tenyér
    MOVE = auto()           # kurzormozgatás (csak mutatóujj fent)
    LEFT_CLICK = auto()     # hüvelyk + mutató csippentés
    RIGHT_CLICK = auto()    # hüvelyk + középső csippentés
    SCROLL = auto()         # mutató + középső együtt fent (függőleges görgetés)
    DRAG = auto()           # ököl (minden ujj behajlítva) -> fogd és vidd
    SWIPE_LEFT = auto()     # gyors balra legyintés nyitott tenyérrel
    SWIPE_RIGHT = auto()    # gyors jobbra legyintés nyitott tenyérrel
    TOGGLE_KEYBOARD = auto()  # "shaka" (hüvelyk + kisujj) -> billentyűzet be/ki


@dataclass
class HandState:
    """A kéz egy képkockára kiszámolt, feldolgozott állapota."""

    # Ujjak felállítva-e: [hüvelyk, mutató, középső, gyűrűs, kisujj]
    fingers_up: list[bool] = field(default_factory=lambda: [False] * 5)
    # Mutatóujj hegyének normalizált (0..1) koordinátái.
    index_x: float = 0.0
    index_y: float = 0.0
    # Hüvelyk-mutató és hüvelyk-középső csippentési távolság (kézmérethez
    # normalizálva, tehát kameratávolságtól független).
    pinch_index: float = 1.0
    pinch_middle: float = 1.0
    # Kézméret referencia (csukló -> középső ujj töve) a normalizáláshoz.
    hand_size: float = 1.0

    @property
    def num_fingers_up(self) -> int:
        return sum(self.fingers_up)


def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def analyze_hand(landmarks, handed_label: str) -> HandState:
    """A nyers MediaPipe landmarkokból kiszámolja a HandState-et.

    `handed_label`: "Left" vagy "Right" (a MediaPipe tükrözött képre vett
    címkéje). A hüvelykujj fel/le állapota vízszintes irányú, ezért a kéz
    oldalától függ, melyik irányba kell néznünk.
    """
    lm = landmarks.landmark

    hand_size = _dist(lm[WRIST], lm[MIDDLE_MCP])
    if hand_size < 1e-6:
        hand_size = 1e-6

    # --- Ujjak felállítása ---------------------------------------------------
    # A négy "hosszú" ujj akkor áll, ha a hegye feljebb (kisebb y) van, mint a
    # középső íze (PIP). A kép fel-irányban kisebb y-t jelent.
    index_up = lm[INDEX_TIP].y < lm[INDEX_PIP].y
    middle_up = lm[MIDDLE_TIP].y < lm[MIDDLE_PIP].y
    ring_up = lm[RING_TIP].y < lm[RING_PIP].y
    pinky_up = lm[PINKY_TIP].y < lm[PINKY_PIP].y

    # A hüvelyk vízszintesen nyílik. Tükrözött képen a "Right" kéz hüvelykje a
    # kéztől balra (kisebb x) nyúlik, ha ki van nyitva; a "Left"-é fordítva.
    if handed_label == "Right":
        thumb_up = lm[THUMB_TIP].x < lm[INDEX_MCP].x
    else:
        thumb_up = lm[THUMB_TIP].x > lm[INDEX_MCP].x

    fingers_up = [thumb_up, index_up, middle_up, ring_up, pinky_up]

    # --- Csippentési távolságok ---------------------------------------------
    pinch_index = _dist(lm[THUMB_TIP], lm[INDEX_TIP]) / hand_size
    pinch_middle = _dist(lm[THUMB_TIP], lm[MIDDLE_TIP]) / hand_size

    return HandState(
        fingers_up=fingers_up,
        index_x=lm[INDEX_TIP].x,
        index_y=lm[INDEX_TIP].y,
        pinch_index=pinch_index,
        pinch_middle=pinch_middle,
        hand_size=hand_size,
    )


# Küszöbök a gesztusokhoz (kézmérethez normalizált távolságok).
PINCH_THRESHOLD = 0.35


def classify_gesture(state: HandState) -> Gesture:
    """A HandState alapján eldönti a magas szintű gesztust.

    A sorrend számít: a specifikusabb (csippentés) eseteket előbb vizsgáljuk.
    """
    thumb, index, middle, ring, pinky = state.fingers_up

    # "Shaka" / telefon jel: csak a HÜVELYK és a KISUJJ áll, a három középső
    # ujj behajlítva. Ritka, nem ütközik mással -> ezzel kapcsoljuk a
    # billentyűzetet (a finger_tracker él-triggerrel kezeli: egy felmutatás =
    # egy váltás). Így a billentyűzet KÉZZEL kapcsolható, nem a 'k' billentyűvel
    # (ami csak akkor menne, ha az AirControl ablaka aktív).
    if thumb and pinky and not index and not middle and not ring:
        return Gesture.TOGGLE_KEYBOARD

    # Csippentések először (ezek felülírják a mozgatást).
    # FONTOS: a bal kattintáshoz a MUTATÓUJJNAK fent kell lennie, különben egy
    # zárt ököl (ahol a hüvelyk és a behajlított mutató hegye közel kerül)
    # tévesen kattintásnak látszana. A jobb kattintásnál ugyanígy a KÖZÉPSŐ.
    if index and state.pinch_index < PINCH_THRESHOLD:
        return Gesture.LEFT_CLICK
    if middle and not index and state.pinch_middle < PINCH_THRESHOLD:
        return Gesture.RIGHT_CLICK

    # Görgetés: mutató + középső együtt fent, gyűrűs/kisujj behajlítva.
    if index and middle and not ring and not pinky:
        return Gesture.SCROLL

    # Mozgatás: csak a mutatóujj áll.
    if index and not middle and not ring and not pinky:
        return Gesture.MOVE

    # Ököl: minden ujj behajlítva -> drag.
    if not index and not middle and not ring and not pinky:
        return Gesture.DRAG

    # Nyitott tenyér (4-5 ujj fent): legyintés-jelölt (a swipe-ot a
    # finger_tracker a vízszintes sebességből dönti el).
    return Gesture.NONE
