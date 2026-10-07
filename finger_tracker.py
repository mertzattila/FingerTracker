"""
FingerTracker
=============

A webkamera képéből MediaPipe-pal követi a JOBB kezet, a mutatóujj hegyének
koordinátáit a képernyő felbontására skálázza, és PyAutoGUI-val oda mozgatja
az egérkurzort. A kurzor remegését mozgóátlag (exponenciális simítás) tompítja.

Ha a mutató- és a hüvelykujj hegye összeér (a köztük lévő, kézmérethez
normalizált távolság egy küszöb alá csökken), a program bal egérkattintást
szimulál. A "csippentés" él-triggerelt: egy összeérintés egyetlen kattintást
vált ki, nem folyamatos kattintássorozatot.

Kilépés: 'q' billentyű vagy ESC a megjelenített ablakon.
"""

from __future__ import annotations

import math
import time
from collections import deque

import cv2
import pyautogui


def _load_mediapipe_solutions():
    """A MediaPipe `solutions` API betöltése verziótól függetlenül.

    Az újabb MediaPipe buildekben (pl. 0.10.3x, 1.x) a `mp.solutions` már NEM
    töltődik be automatikusan a `import mediapipe as mp`-vel, ezért a megszokott
    `mp.solutions.hands` AttributeError-t ad. Itt több utat is megpróbálunk:

    1. a klasszikus `mediapipe.solutions` (régebbi buildek),
    2. az explicit `mediapipe.python.solutions` almodulok (újabb buildek).

    Visszatér: (hands_module, drawing_utils_module).
    """
    # 1) Klasszikus út.
    try:
        import mediapipe as mp  # noqa: F401

        if hasattr(mp, "solutions"):
            return mp.solutions.hands, mp.solutions.drawing_utils
    except Exception:
        pass

    # 2) Explicit almodul-import (az újabb buildeken ez működik).
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

# A simítás mértéke: hány legutóbbi pozíciót átlagoljunk a mozgóátlaghoz.
SMOOTHING_WINDOW = 5

# A csippentés küszöbe. A mutató- és hüvelykujj hegyének távolságát a
# kéz méretéhez (csukló -> középső ujj töve) normalizáljuk, így a küszöb
# független attól, milyen messze van a kéz a kameratól.
PINCH_THRESHOLD = 0.35

# Két kattintás között eltelő minimális idő (másodperc), hogy egy hosszabb
# csippentés ne okozzon kattintás-áradatot.
CLICK_COOLDOWN = 0.4

# A képernyő szélei felé hagyott "holtsáv" aránya. A kézzel kényelmetlen
# pontosan a kamera képének a sarkáig elérni, ezért a kéz mozgástartományát
# a kép középső részére szűkítjük, és azt feszítjük ki a teljes képernyőre.
FRAME_MARGIN = 0.15


def main() -> None:
    # PyAutoGUI biztonsági beállítások.
    pyautogui.FAILSAFE = True   # bal felső sarokba húzott egér megszakítja
    pyautogui.PAUSE = 0.0       # ne lassítsa a mozgatást beépített szünet

    screen_w, screen_h = pyautogui.size()

    mp_hands, mp_draw = _load_mediapipe_solutions()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise RuntimeError("Nem sikerült megnyitni a webkamerát (index 0).")

    # Mozgóátlaghoz tartó a legutóbbi (x, y) képernyő-koordinátákkal.
    xs: deque[float] = deque(maxlen=SMOOTHING_WINDOW)
    ys: deque[float] = deque(maxlen=SMOOTHING_WINDOW)

    last_click_time = 0.0
    pinching = False  # az előző képkockán össze volt-e érintve a két ujj

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

            # Tükrözés, hogy a kameraképen a mozgás természetes irányú legyen.
            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]

            # MediaPipe RGB-t vár, OpenCV BGR-t ad.
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = hands.process(rgb)

            status_text = "Nincs jobb kez a kepen"

            if results.multi_hand_landmarks and results.multi_handedness:
                for landmarks, handedness in zip(
                    results.multi_hand_landmarks, results.multi_handedness
                ):
                    label = handedness.classification[0].label  # "Left" / "Right"

                    # A kép tükrözése miatt a MediaPipe "Right" címkéje felel meg
                    # a felhasználó valódi jobb kezének.
                    if label != "Right":
                        continue

                    status_text = "Jobb kez kovetve"

                    index_tip = landmarks.landmark[mp_hands.HandLandmark.INDEX_FINGER_TIP]
                    thumb_tip = landmarks.landmark[mp_hands.HandLandmark.THUMB_TIP]
                    wrist = landmarks.landmark[mp_hands.HandLandmark.WRIST]
                    middle_mcp = landmarks.landmark[
                        mp_hands.HandLandmark.MIDDLE_FINGER_MCP
                    ]

                    # --- Kurzor mozgatása -------------------------------------
                    # A mutatóujj hegyének normalizált (0..1) koordinátáit a
                    # holtsávval leszűkített tartományból a teljes képernyőre
                    # skálázzuk.
                    nx = _remap(index_tip.x, FRAME_MARGIN, 1.0 - FRAME_MARGIN)
                    ny = _remap(index_tip.y, FRAME_MARGIN, 1.0 - FRAME_MARGIN)

                    target_x = nx * screen_w
                    target_y = ny * screen_h

                    xs.append(target_x)
                    ys.append(target_y)

                    # Mozgóátlag (egyszerű, csúszó ablakos) a remegés ellen.
                    smooth_x = sum(xs) / len(xs)
                    smooth_y = sum(ys) / len(ys)

                    pyautogui.moveTo(smooth_x, smooth_y)

                    # --- Csippentés / kattintás -------------------------------
                    pinch_dist = _distance(index_tip, thumb_tip)
                    hand_size = _distance(wrist, middle_mcp)
                    # Normalizált távolság: független a kamera távolságtól.
                    norm_dist = pinch_dist / hand_size if hand_size > 1e-6 else 1.0

                    now = time.time()
                    if norm_dist < PINCH_THRESHOLD:
                        status_text = "Csippentes (kattintas)"
                        # Él-trigger: csak akkor kattintunk, ha az előző
                        # képkockán még NEM volt összeérintve a két ujj.
                        if not pinching and (now - last_click_time) > CLICK_COOLDOWN:
                            pyautogui.click()
                            last_click_time = now
                        pinching = True
                    else:
                        pinching = False

                    # --- Kirajzolás a visszajelzéshez -------------------------
                    mp_draw.draw_landmarks(
                        frame, landmarks, mp_hands.HAND_CONNECTIONS
                    )
                    ix, iy = int(index_tip.x * w), int(index_tip.y * h)
                    tx, ty = int(thumb_tip.x * w), int(thumb_tip.y * h)
                    color = (0, 0, 255) if norm_dist < PINCH_THRESHOLD else (0, 255, 0)
                    cv2.circle(frame, (ix, iy), 10, color, cv2.FILLED)
                    cv2.line(frame, (ix, iy), (tx, ty), color, 2)

                    break  # csak egy (jobb) kézzel foglalkozunk

            cv2.putText(
                frame,
                status_text,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.putText(
                frame,
                "Kilepes: 'q' vagy ESC",
                (10, h - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (200, 200, 200),
                1,
                cv2.LINE_AA,
            )

            cv2.imshow("FingerTracker", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:  # 'q' vagy ESC
                break

    cap.release()
    cv2.destroyAllWindows()


def _distance(a, b) -> float:
    """Euklideszi távolság két MediaPipe landmark között (normalizált térben)."""
    return math.hypot(a.x - b.x, a.y - b.y)


def _remap(value: float, lo: float, hi: float) -> float:
    """A [lo, hi] tartományba eső értéket [0, 1]-re skálázza, és levágja."""
    if hi <= lo:
        return value
    scaled = (value - lo) / (hi - lo)
    return max(0.0, min(1.0, scaled))


if __name__ == "__main__":
    main()
