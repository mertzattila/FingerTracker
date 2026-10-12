"""
Egérvezérlő: egy felismert gesztusból tényleges egérakciót hajt végre.

Az osztály kapszulázza a kattintás-időzítőket, a drag állapotát és a kurzor
mozgóátlagát, hogy a fő ciklus (finger_tracker.py) tiszta maradjon.
"""

from __future__ import annotations

from collections import deque

import pyautogui

from gestures import Gesture, HandState


class MouseController:
    def __init__(self, screen_w: int, screen_h: int, *,
                 smoothing_window: int = 5,
                 click_cooldown: float = 0.4,
                 scroll_sensitivity: int = 60,
                 frame_margin: float = 0.15) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.click_cooldown = click_cooldown
        self.scroll_sensitivity = scroll_sensitivity
        self.frame_margin = frame_margin

        self._xs: deque[float] = deque(maxlen=smoothing_window)
        self._ys: deque[float] = deque(maxlen=smoothing_window)
        self._last_left = 0.0
        self._last_right = 0.0
        self._dragging = False

    def reset_smoothing(self) -> None:
        self._xs.clear()
        self._ys.clear()

    def _smoothed_target(self, state: HandState) -> tuple[float, float]:
        nx = _remap(state.index_x, self.frame_margin, 1.0 - self.frame_margin)
        ny = _remap(state.index_y, self.frame_margin, 1.0 - self.frame_margin)
        self._xs.append(nx * self.screen_w)
        self._ys.append(ny * self.screen_h)
        return sum(self._xs) / len(self._xs), sum(self._ys) / len(self._ys)

    def _release_drag(self) -> None:
        if self._dragging:
            pyautogui.mouseUp()
            self._dragging = False

    def handle(self, gesture: Gesture, state: HandState, now: float) -> None:
        """Végrehajtja a gesztushoz tartozó egérakciót."""
        sx, sy = self._smoothed_target(state)

        if gesture == Gesture.MOVE:
            self._release_drag()
            pyautogui.moveTo(sx, sy)

        elif gesture == Gesture.LEFT_CLICK:
            pyautogui.moveTo(sx, sy)
            if not self._dragging and (now - self._last_left) > self.click_cooldown:
                pyautogui.click()
                self._last_left = now

        elif gesture == Gesture.RIGHT_CLICK:
            pyautogui.moveTo(sx, sy)
            if (now - self._last_right) > self.click_cooldown:
                pyautogui.click(button="right")
                self._last_right = now

        elif gesture == Gesture.SCROLL:
            # A kéz függőleges helye a kép közepéhez képest adja a görgetést.
            offset = (0.5 - state.index_y) * 2.0  # -1..1
            amount = int(offset * self.scroll_sensitivity)
            if amount != 0:
                pyautogui.scroll(amount)

        elif gesture == Gesture.DRAG:
            if not self._dragging:
                pyautogui.mouseDown()
                self._dragging = True
            pyautogui.moveTo(sx, sy)

        else:
            # NONE / SWIPE: ha drag volt, elengedjük.
            self._release_drag()


def _remap(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return value
    scaled = (value - lo) / (hi - lo)
    return max(0.0, min(1.0, scaled))
