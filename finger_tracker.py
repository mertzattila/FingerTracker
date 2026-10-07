"""
FingerTracker — kézvezérelt egér + virtuális billentyűzet
==========================================================

A webkamera képéből MediaPipe-pal követi a kezed, és egy teljes értékű,
gesztus-alapú egérként viselkedik. Emellett egy be/ki kapcsolható virtuális
billentyűzetet is kivetít a kameraablakra, amin a kezeddel tudsz gépelni.

Gesztusok (alap: a jobb kéz vezérel; lásd --hand):
  - Csak a MUTATÓUJJ fent ............. kurzor mozgatása
  - Hüvelyk + mutató CSIPPENTÉS ....... bal kattintás
  - Hüvelyk + középső CSIPPENTÉS ...... jobb kattintás
  - MUTATÓ + KÖZÉPSŐ együtt fent ...... függőleges görgetés (a kéz fel/le)
  - ÖKÖL (minden ujj behajlítva) ...... fogd és vidd (drag): mozgasd, majd nyisd
  - Gyors LEGYINTÉS nyitott tenyérrel .. oldallapozás (balra/jobbra nyíl)

Billentyűk a kameraablakon:
  - 'k' .... virtuális billentyűzet be/ki
  - 'm' .... egérvezérlés be/ki (ha csak gépelni akarsz)
  - 'q' / ESC .... kilépés

Virtuális billentyűzet használata: kapcsold be 'k'-val, célozz a mutatóujjaddal
egy gombra, és egy hüvelyk-mutató csippentéssel "üsd le".
"""

from __future__ import annotations

import argparse
import time

import cv2
import pyautogui

import gestures
from gestures import Gesture
from mouse_controller import MouseController
from virtual_keyboard import VirtualKeyboard


def _load_mediapipe_solutions():
    """A MediaPipe `solutions` API betöltése verziótól függetlenül.

    Az újabb MediaPipe buildekben (pl. 0.10.3x, 1.x) a `mp.solutions` már NEM
    töltődik be automatikusan a `import mediapipe as mp`-vel, ezért a megszokott
    `mp.solutions.hands` AttributeError-t ad. Itt több utat is megpróbálunk:

    1. a klasszikus `mediapipe.solutions` (régebbi buildek),
    2. az explicit `mediapipe.python.solutions` almodulok (újabb buildek).

    Visszatér: (hands_module, drawing_utils_module).
    """
    try:
        import mediapipe as mp  # noqa: F401

        if hasattr(mp, "solutions"):
            return mp.solutions.hands, mp.solutions.drawing_utils
    except Exception:
        pass

    try:
        import mediapipe.python.solutions.hands as mp_hands
        import mediapipe.python.solutions.drawing_utils as mp_draw

        return mp_hands, mp_draw
    except Exception as exc:  # pragma: no cover - környezetfüggő
        raise ImportError(
            "Nem sikerült betölteni a MediaPipe 'solutions' (Hands) API-t.\n"
            "Valószínűleg nem kompatibilis MediaPipe build van telepítve.\n"
            "Javasolt: Python 3.11/3.12 + a klasszikus solutions API-t tartalmazó\n"
            "verzió, pl.:  pip install 'mediapipe==0.10.21'\n"
            f"Eredeti hiba: {exc}"
        ) from exc


# --- Konfiguráció --------------------------------------------------------------

SMOOTHING_WINDOW = 5        # mozgóátlag ablakmérete a kurzor simításához
CLICK_COOLDOWN = 0.4        # két kattintás közti minimum idő (s)
SCROLL_SENSITIVITY = 60     # görgetés erőssége (nagyobb = gyorsabb)
FRAME_MARGIN = 0.15         # holtsáv a kép szélén a kényelmesebb tartományhoz
TRACKED_HAND = "Right"      # "Right" | "Left" | "Any"

# Swipe (legyintés) felismerés: ha a mutatóujj vízszintes sebessége (normalizált
# egység / másodperc) ezt meghaladja nyitott tenyérrel, lapozásnak vesszük.
SWIPE_SPEED = 1.8
SWIPE_COOLDOWN = 0.8        # két lapozás közti minimum idő (s)


def _is_frame_usable(frame) -> bool:
    """Igaz, ha a képkocka nem (majdnem) teljesen fekete.

    macOS-en a Continuity Camera (iPhone) néha megnyílik, de fekete képet ad.
    """
    if frame is None or frame.size == 0:
        return False
    return float(frame.mean()) > 5.0


def _open_camera(preferred: int | None):
    """Használható (nem fekete) webkamera megnyitása 0..5 indexek között."""
    candidates = [preferred] if preferred is not None else list(range(6))
    for idx in candidates:
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            continue
        usable = False
        for _ in range(10):
            ok, frame = cap.read()
            if ok and _is_frame_usable(frame):
                usable = True
                break
            time.sleep(0.05)
        if usable:
            print(f"[FingerTracker] Kamera megnyitva, index={idx}")
            return cap, idx
        cap.release()
    return None, None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kézvezérelt egér + virtuális billentyűzet."
    )
    parser.add_argument("--camera", type=int, default=None,
                        help="Kamera index (alapból automatikus keresés 0..5).")
    parser.add_argument("--hand", choices=["Right", "Left", "Any"],
                        default=TRACKED_HAND,
                        help='Melyik kezet kövesse (alap: "%(default)s").')
    parser.add_argument("--keyboard", action="store_true",
                        help="A virtuális billentyűzet indításkor bekapcsolva.")
    args = parser.parse_args()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    screen_w, screen_h = pyautogui.size()

    mp_hands, mp_draw = _load_mediapipe_solutions()

    cap, _ = _open_camera(args.camera)
    if cap is None:
        raise RuntimeError(
            "Nem találtam használható (nem fekete) webkamerát a 0..5 indexeken.\n"
            "macOS-en gyakori ok a Continuity Camera (iPhone), ami fekete képet ad.\n"
            "Tipp: kapcsold ki az iPhone-t kameraként, vagy add meg kézzel az\n"
            "indexet, pl.:  python finger_tracker.py --camera 1"
        )

    # Állapot.
    mouse = MouseController(
        screen_w, screen_h,
        smoothing_window=SMOOTHING_WINDOW,
        click_cooldown=CLICK_COOLDOWN,
        scroll_sensitivity=SCROLL_SENSITIVITY,
        frame_margin=FRAME_MARGIN,
    )
    last_swipe_time = 0.0
    prev_index_x: float | None = None
    prev_time = time.time()

    keyboard = VirtualKeyboard()
    if args.keyboard:
        keyboard.toggle()
    mouse_enabled = True

    with mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=1,
        model_complexity=1,
        min_detection_confidence=0.7,
        min_tracking_confidence=0.6,
    ) as hands:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = hands.process(rgb)

            status = "Nincs kez a kepen"
            pointer_px: tuple[int, int] | None = None
            gesture = Gesture.NONE

            now = time.time()
            dt = max(1e-3, now - prev_time)

            if results.multi_hand_landmarks and results.multi_handedness:
                for landmarks, handedness in zip(
                    results.multi_hand_landmarks, results.multi_handedness
                ):
                    label = handedness.classification[0].label
                    if args.hand != "Any" and label != args.hand:
                        continue

                    state = gestures.analyze_hand(landmarks, label)
                    gesture = gestures.classify_gesture(state)

                    ix = int(state.index_x * w)
                    iy = int(state.index_y * h)
                    pointer_px = (ix, iy)

                    # Swipe (legyintés) felismerés nyitott tenyérnél.
                    if prev_index_x is not None and state.num_fingers_up >= 4:
                        vx = (state.index_x - prev_index_x) / dt
                        if abs(vx) > SWIPE_SPEED and \
                                (now - last_swipe_time) > SWIPE_COOLDOWN:
                            if vx > 0:
                                pyautogui.press("right")
                                gesture = Gesture.SWIPE_RIGHT
                            else:
                                pyautogui.press("left")
                                gesture = Gesture.SWIPE_LEFT
                            last_swipe_time = now
                    prev_index_x = state.index_x

                    # --- Virtuális billentyűzet elsőbbsége ------------------
                    pinch_now = state.pinch_index < gestures.PINCH_THRESHOLD
                    kb_captured = keyboard.update(pointer_px, pinch_now)

                    # --- Egérvezérlés (ha nem a billentyűzeten vagyunk) -----
                    if mouse_enabled and not kb_captured:
                        mouse.handle(gesture, state, now)

                    status = f"{label}: {gesture.name}"

                    # Kéz kirajzolása.
                    mp_draw.draw_landmarks(frame, landmarks,
                                           mp_hands.HAND_CONNECTIONS)
                    cv2.circle(frame, (ix, iy), 9, (0, 255, 0), cv2.FILLED)
                    break
            else:
                prev_index_x = None

            prev_time = now

            # Billentyűzet rárajzolása (ha be van kapcsolva).
            keyboard.draw(frame, pointer_px)

            _draw_hud(frame, status, keyboard.enabled, mouse_enabled)

            cv2.imshow("FingerTracker", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                break
            elif key == ord("k"):
                keyboard.toggle()
            elif key == ord("m"):
                mouse_enabled = not mouse_enabled

    cap.release()
    cv2.destroyAllWindows()


def _draw_hud(frame, status: str, kb_on: bool, mouse_on: bool) -> None:
    """Állapotsáv és súgó kirajzolása a kép tetejére/aljára."""
    h, w = frame.shape[:2]
    cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (255, 255, 0), 2, cv2.LINE_AA)

    kb_txt = "BE" if kb_on else "KI"
    ms_txt = "BE" if mouse_on else "KI"
    hud = f"[k] Billentyuzet: {kb_txt}   [m] Eger: {ms_txt}   [q/ESC] Kilepes"
    cv2.putText(frame, hud, (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX,
                0.55, (200, 200, 200), 1, cv2.LINE_AA)


if __name__ == "__main__":
    main()
