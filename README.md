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

```bash
pip install -r requirements.txt
```

> Megjegyzés: a MediaPipe Python 3.8–3.11 verziókat támogatja a legjobban.

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
