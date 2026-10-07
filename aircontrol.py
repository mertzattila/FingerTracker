"""
AirControl — érintés nélküli egér- és billentyűzetvezérlés webkamerával
=======================================================================

A webkamera képéből MediaPipe-pal követi a kezed, és egy teljes értékű,
gesztus-alapú egérként viselkedik. Emellett egy be/ki kapcsolható virtuális
billentyűzetet is kivetít a kameraablakra, amin a kezeddel tudsz gépelni.

Az egérvezérlés RENDSZERSZINTŰ: a kurzor és a kattintások bármelyik
alkalmazásban hatnak (böngésző, szövegszerkesztő stb.), nem csak akkor, ha a
kameraablak van előtérben. A kameraablak csak vizuális visszajelzés.

macOS: a rendszerszintű egérvezérléshez a terminálodnak "Kisegítő lehetőségek"
(Accessibility) engedély kell — lásd a README-t. Enélkül a kurzor csak a saját
ablakunkban tűnik működőnek, más appban némán nem hat.

Gesztusok (alap: a jobb kéz vezérel; lásd --hand):
  - Csak a MUTATÓUJJ fent ............. kurzor mozgatása
  - Hüvelyk + mutató CSIPPENTÉS ....... bal kattintás
  - Hüvelyk + középső CSIPPENTÉS ...... jobb kattintás
  - MUTATÓ + KÖZÉPSŐ együtt fent ...... függőleges görgetés (a kéz fel/le)
  - ÖKÖL (minden ujj behajlítva) ...... fogd és vidd (drag): mozgasd, majd nyisd
  - Gyors LEGYINTÉS nyitott tenyérrel .. oldallapozás (balra/jobbra nyíl)

Billentyűk a kameraablakon:
  - 'k' .... virtuális billentyűzet be/ki (KÜLÖN, mozgatható/méretezhető ablak)
  - 'm' .... egérvezérlés be/ki (ha csak gépelni akarsz)
  - 'q' / ESC .... kilépés

Virtuális billentyűzet: a 'k'-val megnyílik egy ÖNÁLLÓ ablak, amit a képernyőn
bárhova húzhatsz és átméretezhetsz (pl. a böngésző mellé). A kezeddel (egérmód)
ráviszed a kurzort egy gombra, és egy hüvelyk-mutató CSIPPENTÉSSEL leütöd. A
leütés az éppen fókuszban lévő alkalmazásba kerül.
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


def _warn_if_mouse_control_blocked() -> None:
    """Ellenőrzi, hogy a PyAutoGUI tényleg tudja-e mozgatni a kurzort.

    macOS-en szintetikus egérmozgatáshoz a terminálnak "Kisegítő lehetőségek"
    (System Settings -> Privacy & Security -> Accessibility) engedély kell.
    Ha ez hiányzik, a moveTo "lefut", de a kurzor nem mozdul rendszerszinten,
    és a felhasználó azt hiszi, csak a saját ablakban működik a vezérlés.

    Nem végzetes: csak figyelmeztetünk, mert más platformon ez nem probléma.
    """
    try:
        start = pyautogui.position()
        # Pici, azonnal visszavont teszt-mozgatás a jelenlegi pozícióhoz képest.
        pyautogui.moveTo(start[0] + 2, start[1] + 2, _pause=False)
        moved = pyautogui.position()
        pyautogui.moveTo(start[0], start[1], _pause=False)
        if abs(moved[0] - (start[0] + 2)) > 1 or abs(moved[1] - (start[1] + 2)) > 1:
            print(
                "\n[AirControl] FIGYELEM: a rendszer blokkolja az egérmozgatást.\n"
                "  macOS-en engedélyezd a terminálodnak (vagy iTerm/VS Code):\n"
                "  Rendszerbeállítások -> Adatvédelem és biztonság ->\n"
                "  Kisegítő lehetőségek -> kapcsold BE az alkalmazást, majd\n"
                "  indítsd újra az AirControl-t. Enélkül a kurzor csak a saját\n"
                "  ablakunkban tűnik működőnek, böngészőben/más appban nem.\n"
            )
    except Exception:
        # Platformtól függően a pozíció-lekérdezés sem mindig megy; ne akassza
        # meg az indulást.
        pass


def _apply_window_topmost(window_name: str, topmost: bool) -> None:
    """A kameraablakot (ha a backend támogatja) mindig felülre teszi.

    Így böngészés közben is látod a kezed visszajelzését anélkül, hogy
    vissza kellene váltanod a kameraablakra. Nem minden OpenCV-backend
    támogatja; ilyenkor csendben kihagyjuk.
    """
    try:
        prop = getattr(cv2, "WND_PROP_TOPMOST", None)
        if prop is not None:
            cv2.setWindowProperty(window_name, prop, 1.0 if topmost else 0.0)
    except Exception:
        pass


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
            print(f"[AirControl] Kamera megnyitva, index={idx}")
            return cap, idx
        cap.release()
    return None, None


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="AirControl",
        description="AirControl — érintés nélküli egér- és billentyűzetvezérlés.",
    )
    parser.add_argument("--camera", type=int, default=None,
                        help="Kamera index (alapból automatikus keresés 0..5).")
    parser.add_argument("--hand", choices=["Right", "Left", "Any"],
                        default=TRACKED_HAND,
                        help='Melyik kezet kövesse (alap: "%(default)s").')
    parser.add_argument("--keyboard", action="store_true",
                        help="A virtuális billentyűzet indításkor bekapcsolva.")
    parser.add_argument("--no-topmost", action="store_true",
                        help="Ne tartsa a kameraablakot mindig felül.")
    args = parser.parse_args()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.0
    screen_w, screen_h = pyautogui.size()

    # Önteszt: tud-e a PyAutoGUI tényleg egeret mozgatni? Ha nem, az szinte
    # biztosan a macOS "Kisegítő lehetőségek" engedély hiánya. Korán jelezzük,
    # hogy ne tűnjön úgy, mintha "csak a saját ablakban" működne a vezérlés.
    _warn_if_mouse_control_blocked()

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

    window_name = "AirControl"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    _apply_window_topmost(window_name, topmost=not args.no_topmost)

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

                    # --- Egérvezérlés -------------------------------------
                    # A kurzort MINDIG mozgatjuk (hogy a billentyűzet célzása a
                    # valódi kurzorpozícióra működjön). A KATTINTÁST azonban
                    # elnyomjuk, ha a kurzor épp a billentyűzet egy gombja
                    # fölött van — különben egy csippentés egyszerre kattintana
                    # ÉS billentyűt is leütne (dupla művelet).
                    pinch_now = state.pinch_index < gestures.PINCH_THRESHOLD
                    cursor = pyautogui.position()
                    over_key = keyboard.update((cursor.x, cursor.y), pinch_now)

                    if mouse_enabled:
                        effective = gesture
                        if over_key and gesture in (
                            Gesture.LEFT_CLICK, Gesture.RIGHT_CLICK
                        ):
                            # Ne kattintson; csak kövesse a kurzort.
                            effective = Gesture.MOVE
                        mouse.handle(effective, state, now)

                    status = f"{label}: {gesture.name}"
                    if keyboard.enabled:
                        status += "  [KB]"

                    # Kéz kirajzolása.
                    mp_draw.draw_landmarks(frame, landmarks,
                                           mp_hands.HAND_CONNECTIONS)
                    cv2.circle(frame, (ix, iy), 9, (0, 255, 0), cv2.FILLED)
                    break
            else:
                prev_index_x = None

            prev_time = now

            # A (külön OpenCV-ablakban megjelenő) billentyűzet újrarajzolása.
            # Ha nincs kéz a képen, akkor is hívjuk, hogy az ablak frissüljön.
            keyboard.pump()

            _draw_hud(frame, status, keyboard.enabled, mouse_enabled)

            cv2.imshow(window_name, frame)
            # A topmost tulajdonságot minden képkockán megerősítjük, mert néhány
            # platformon az ablak elvesztheti az "always on top" állapotot.
            _apply_window_topmost(window_name, topmost=not args.no_topmost)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                break
            elif key == ord("k"):
                keyboard.toggle()
            elif key == ord("m"):
                mouse_enabled = not mouse_enabled

    keyboard.shutdown()
    cap.release()
    cv2.destroyAllWindows()


def _draw_hud(frame, status: str, kb_on: bool, mouse_on: bool) -> None:
    """Állapotsáv és súgó kirajzolása a kép tetejére/aljára."""
    h, w = frame.shape[:2]
    cv2.putText(frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (255, 255, 0), 2, cv2.LINE_AA)

    ms_txt = "BE" if mouse_on else "KI"
    kb_txt = "BE" if kb_on else "KI"
    hud = (f"AirControl  |  [m] Eger: {ms_txt}   [k] Billentyuzet: {kb_txt}"
           f"   [q/ESC] Kilepes")
    cv2.putText(frame, hud, (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (200, 200, 200), 1, cv2.LINE_AA)
    # A billentyűk (m/k/q) csak akkor jutnak be, ha EZ az ablak van fókuszban.
    # Az egérvezérlés viszont fókusztól függetlenül, rendszerszinten működik.
    cv2.putText(frame, "(gombok: kattints eloszor erre az ablakra)",
                (10, h - 32), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (150, 150, 150), 1, cv2.LINE_AA)


if __name__ == "__main__":
    main()
