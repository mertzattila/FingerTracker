# FingerTracker

Kézkövetéses egérvezérlés webkamerával. A program a [MediaPipe](https://developers.google.com/mediapipe)
kézdetektorával követi a **jobb kezedet**, a mutatóujjad hegyének pozícióját a
képernyőd felbontására skálázza, és a [PyAutoGUI](https://pyautogui.readthedocs.io/)
segítségével odamozgatja az egérkurzort.

## Funkciók

- **Jobb kéz követése** a webkameráról (MediaPipe + OpenCV).
- **Kurzormozgatás**: a mutatóujj hegye vezérli az egeret, a képernyő teljes
  felbontására skálázva.
- **Simítás (mozgóátlag)**: a kurzor pozícióját egy csúszó ablakos átlag
  tompítja, így nem remeg.
- **Kattintás csippentéssel**: ha a mutató- és hüvelykujj hegye összeér (a
  kézmérethez normalizált távolságuk a küszöb alá esik), a program egy bal
  egérkattintást szimulál. A trigger él-vezérelt és van benne várakozási idő,
  így egy csippentés egy kattintást jelent.

## Telepítés

A MediaPipe `solutions` API **Python 3.9–3.12** verziókhoz érhető el (3.13/3.14
még nem támogatott). Használj dedikált virtuális környezetet:

```bash
# Python 3.11 ajánlott (macOS: brew install python@3.11)
python3.11 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Ellenőrzés, hogy a **valódi** MediaPipe van-e fent:

```bash
python -c "import mediapipe as mp; print(mp.__version__, hasattr(mp, 'solutions'))"
# várt kimenet:  0.10.x True
```

> **Gyakori hiba — `AttributeError: module 'mediapipe' has no attribute 'solutions'`**
> Három lehetséges ok:
> 1. **Túl új Python** (3.13/3.14) — hozz létre venv-et Python 3.11/3.12-vel.
> 2. **Rossz csomag** — a PyPI-n létezik egy azonos nevű `mediapipe` **1.x**
>    csomag, ami NEM a Google MediaPipe és nincs benne a `solutions` API.
> 3. **Újabb 0.10.x build** (pl. 0.10.3x), ahol az `mp.solutions` már nem
>    töltődik be automatikusan a sima `import mediapipe as mp`-vel.
>
> A `finger_tracker.py` a 3. esetet kezeli: ha az `mp.solutions` nem elérhető,
> explicit `import mediapipe.python.solutions.hands` úton tölti be. Gyors teszt:
>
> ```bash
> python -c "import mediapipe.python.solutions.hands as h; print('OK', h.Hands)"
> ```
>
> Ha ez is hibázik, válts egy ismert jó Google-buildre:
>
> ```bash
> pip uninstall -y mediapipe && pip install "mediapipe==0.10.21"
> python -c "import mediapipe as mp; print(mp.__version__, hasattr(mp,'solutions'))"
> # -> 0.10.21 True
> ```

### macOS engedélyek (M1/M2 is)

- **Kamera**: első futtatáskor a rendszer engedélyt kér.
- **Kisegítő lehetőségek**: a PyAutoGUI csak akkor tudja mozgatni a kurzort, ha
  a Terminál/iTerm engedélyt kap itt: Rendszerbeállítások → Adatvédelem és
  biztonság → Kisegítő lehetőségek.

## Használat

```bash
python finger_tracker.py
```

Mutasd a **jobb kezedet** a kamerának, mozgasd a mutatóujjaddal a kurzort,
és érintsd össze a mutató- és hüvelykujjad a kattintáshoz.
Kilépés: `q` vagy `ESC` a megjelenített ablakon.

## Hangolható paraméterek (`finger_tracker.py` tetején)

| Paraméter | Jelentés |
|---|---|
| `SMOOTHING_WINDOW` | Hány legutóbbi pozíciót átlagoljon a simítás. Nagyobb = simább, de "lustább". |
| `PINCH_THRESHOLD` | A csippentés küszöbe (kézmérethez normalizált távolság). |
| `CLICK_COOLDOWN` | Két kattintás közti minimális idő (s). |
| `FRAME_MARGIN` | A kép szélén hagyott holtsáv aránya a kényelmesebb mozgástartományhoz. |

## Biztonság

A PyAutoGUI **failsafe** be van kapcsolva: ha az egeret gyorsan a képernyő
bal felső sarkába húzod, a program megszakad.
