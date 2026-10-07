"""
Offline tesztek a gesztuslogikára. Kamera/MediaPipe NEM szükséges — hamis
landmarkokkal dolgozunk. Futtatás:  python -m pytest test_gestures.py
(vagy egyszerűen:  python test_gestures.py)
"""

import gestures
from gestures import Gesture


class _LM:
    """MediaPipe-szerű landmark. y 'up' konvencióval adjuk meg (nagyobb=feljebb),
    és a MediaPipe képi konvenciójára (fel = kisebb y) alakítjuk."""

    def __init__(self, x: float, y_up: float):
        self.x = x
        self.y = 1.0 - y_up


class _Hand:
    def __init__(self, pts):
        self.landmark = pts


def _build(index_up=False, middle_up=False, ring_up=False, pinky_up=False,
           pinch_index=False, pinch_middle=False):
    p = [_LM(0.5, 0.0) for _ in range(21)]
    p[0] = _LM(0.5, 0.0)     # wrist
    p[9] = _LM(0.5, 0.3)     # middle_mcp -> hand_size ~ 0.3
    p[5] = _LM(0.45, 0.3)    # index_mcp (hüvelyk-referencia)

    p[6] = _LM(0.45, 0.4);  p[8] = _LM(0.45, 0.6 if index_up else 0.2)
    p[10] = _LM(0.5, 0.4);  p[12] = _LM(0.5, 0.6 if middle_up else 0.2)
    p[14] = _LM(0.55, 0.4); p[16] = _LM(0.55, 0.6 if ring_up else 0.2)
    p[18] = _LM(0.6, 0.4);  p[20] = _LM(0.6, 0.6 if pinky_up else 0.2)

    # Hüvelyk alaphelyzet: behajlítva (x közel az index_mcp-hez).
    p[4] = _LM(0.47, 0.3)
    # Csippentésnél a hüvelyk tip az adott ujj hegyére kerül.
    if pinch_index:
        p[4] = _LM(p[8].x, 1.0 - p[8].y)
    if pinch_middle:
        p[4] = _LM(p[12].x, 1.0 - p[12].y)
    return _Hand(p)


def _classify(hand):
    return gestures.classify_gesture(gestures.analyze_hand(hand, "Right"))


def test_move():
    assert _classify(_build(index_up=True)) == Gesture.MOVE


def test_scroll():
    assert _classify(_build(index_up=True, middle_up=True)) == Gesture.SCROLL


def test_drag_fist():
    assert _classify(_build()) == Gesture.DRAG


def test_left_click():
    assert _classify(_build(index_up=True, pinch_index=True)) == Gesture.LEFT_CLICK


def test_right_click():
    # Hüvelyk + középső csippentés: középső fent, mutató behajlítva.
    assert _classify(
        _build(index_up=False, middle_up=True, pinch_middle=True)
    ) == Gesture.RIGHT_CLICK


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("Minden gesztusteszt sikeres.")
