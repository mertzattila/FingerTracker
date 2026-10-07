# AirControl

**Érintés nélküli egér- és billentyűzetvezérlés webkamerával.** A program a
[MediaPipe](https://developers.google.com/mediapipe) kézdetektorával követi a
kezed, gesztusokból teljes értékű egérként viselkedik, és egy be/ki kapcsolható
virtuális billentyűzetet vetít a kameraablakra, amin a kezeddel gépelhetsz.
Az akciókat a [PyAutoGUI](https://pyautogui.readthedocs.io/) hajtja végre.

> Az egérvezérlés **rendszerszintű**: a kurzor és a kattintások bármelyik
> alkalmazásban hatnak (böngésző, szövegszerkesztő stb.), nem csak akkor, ha a
> kameraablak van előtérben. A kameraablak csak vizuális visszajelzés — alapból
> mindig felül marad, hogy böngészés közben is lásd a kezed.

## Funkciók

**Gesztus-egér**

| Gesztus | Művelet |
|---|---|
| Csak a **mutatóujj** fent | kurzor mozgatása (simítva, mozgóátlaggal) |
| **Hüvelyk + mutató** csippentés | bal kattintás |
| **Hüvelyk + középső** csippentés | jobb kattintás |
| **Mutató + középső** együtt fent | függőleges görgetés (a kéz fel/le mozgása) |
| **Ököl** (minden ujj behajlítva) | fogd és vidd (drag): mozgasd, majd nyisd ki a kezed az elengedéshez |
| Gyors **legyintés** nyitott tenyérrel | oldallapozás (balra/jobbra nyílbillentyű) |

**Virtuális billentyűzet**

- A kameraablakra kivetített QWERTY billentyűzet, `k` billentyűvel **be/ki**.
- A **mutatóujjaddal célzol** egy gombra, és egy **csippentéssel leütöd**.
- SPACE, Backspace és Enter is van. A leütés az éppen fókuszban lévő
  alkalmazásba kerül (szövegszerkesztő, böngésző kereső stb.).

**Egyéb**

- **Simítás (mozgóátlag)** a kurzoron, hogy ne remegjen.
- Minden kattintás él-vezérelt + cooldownos (egy gesztus = egy kattintás).
- Billentyűk a kameraablakon: `k` billentyűzet be/ki, `m` egér be/ki,
  `q`/`ESC` kilépés.

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
> A `aircontrol.py` a 3. esetet kezeli: ha az `mp.solutions` nem elérhető,
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

### macOS engedélyek (M1/M2 is) — FONTOS

- **Kamera**: első futtatáskor a rendszer engedélyt kér.
- **Kisegítő lehetőségek (Accessibility)**: e **nélkül a kurzor csak a saját
  ablakunkban tűnik mozogni**, böngészőben/más appban némán nem hat. Ez a
  leggyakoribb ok, ha "csak akkor működik, ha a kameraablak van felül".

**Hogyan engedélyezd (ez oldja meg a böngészős működést):**

1. Rendszerbeállítások → **Adatvédelem és biztonság** → **Kisegítő lehetőségek**.
2. Kapcsold **BE** azt az alkalmazást, amelyikből indítod az AirControl-t:
   - ha Terminálból indítod → **Terminal**
   - ha iTerm2-ből → **iTerm**
   - ha VS Code beépített termináljából → **Code** (Visual Studio Code)
3. **Indítsd újra** az AirControl-t (sőt, néha az egész terminált), hogy az új
   engedély életbe lépjen.

Az AirControl induláskor **önellenőrzést** futtat: ha nem tudja mozgatni az
egeret, kiír egy figyelmeztetést a fenti teendővel. Ha ezt látod, a 2–3. lépés
hiányzik.

## Használat

```bash
python aircontrol.py
```

Mutasd a kezed a kamerának, és használd a fenti gesztusokat. A kameraablakon
mindig látszik, épp melyik gesztust ismeri fel.

**Gépelés a virtuális billentyűzettel:**
1. Kattints (vagy válaszd ki egérrel) a célmezőt, ahova gépelni szeretnél.
2. Kapcsold be a billentyűzetet a `k` billentyűvel (a billentyűzet-ablak legyen
   fókuszban a `k`-hoz; a leütések viszont az előző, fókuszált alkalmazásba
   mennek).
3. Célozz a mutatóujjaddal egy gombra, és **csippents** a leütéshez.
4. Tipp: `m`-mel kikapcsolhatod az egérvezérlést, ha csak gépelni akarsz, hogy
   a kurzor ne mozogjon közben.

Kilépés: `q` vagy `ESC`.

### Parancssori opciók

```bash
python aircontrol.py --camera 1      # adott kamera index használata
python aircontrol.py --hand Any      # bármelyik kéz vezérelhet
python aircontrol.py --hand Left     # a bal kéz kövesse
python aircontrol.py --keyboard      # billentyűzet indításkor bekapcsolva
```

- `--camera N`: ha nem adod meg, a program automatikusan végigpróbálja a 0..5
  indexeket, és az első **nem fekete** képet adó kamerát használja.
- `--hand`: `Right` (alap), `Left` vagy `Any`.
- `--keyboard`: a virtuális billentyűzet már indításkor bekapcsolva.
- `--no-topmost`: ne tartsa a kameraablakot mindig felül (alapból felül marad).

> **Megjegyzés a billentyűkről (`m`, `k`, `q`):** ezek csak akkor jutnak be, ha
> **az AirControl kameraablaka van fókuszban** (ez OpenCV-korlát). Maga az
> **egérvezérlés viszont fókusztól függetlenül, rendszerszinten működik** — tehát
> böngészőben is mozog a kurzor és kattint, akkor is, ha nem a kameraablak aktív.
> Ha a módokat kapcsolgatni akarod, előbb kattints a kameraablakra.

### macOS: fekete a kamerakép?

Ha a kameraablak fekete, és a logban `Continuity Camera` szerepel, a macOS az
**iPhone-odat** nyitotta meg kameraként. Megoldás:

- Kapcsold ki az iPhone-t kameraként (iPhone: Beállítások → Általános → AirPlay
  és Folytonosság → Folytonossági kamera KI), **vagy**
- add meg kézzel a beépített kamerát, pl. `python aircontrol.py --camera 1`.

Az automatikus keresés a fekete képet adó kamerákat kihagyja, de a kézi index
mindig a legbiztosabb.

## Felépítés

| Fájl | Szerep |
|---|---|
| `aircontrol.py` | Fő program: kamera, fő ciklus, HUD, billentyűzetkapcsolók. |
| `gestures.py` | Kéz-landmarkokból gesztusfelismerés (tiszta logika). |
| `mouse_controller.py` | Gesztus → egérakció (mozgatás, kattintás, görgetés, drag). |
| `virtual_keyboard.py` | A kivetített virtuális billentyűzet. |
| `test_gestures.py` | Offline tesztek a gesztuslogikára (kamera nélkül). |

## Hangolható paraméterek (`aircontrol.py` tetején)

| Paraméter | Jelentés |
|---|---|
| `SMOOTHING_WINDOW` | Hány legutóbbi pozíciót átlagoljon a simítás. Nagyobb = simább, de "lustább". |
| `CLICK_COOLDOWN` | Két kattintás közti minimális idő (s). |
| `SCROLL_SENSITIVITY` | A görgetés erőssége (nagyobb = gyorsabb). |
| `FRAME_MARGIN` | A kép szélén hagyott holtsáv aránya a kényelmesebb mozgástartományhoz. |
| `SWIPE_SPEED` | Mekkora vízszintes sebességtől számít legyintésnek (lapozás). |
| `SWIPE_COOLDOWN` | Két lapozás közti minimális idő (s). |
| `gestures.PINCH_THRESHOLD` | A csippentés küszöbe (kézmérethez normalizált távolság). |

## Tesztek

A gesztuslogika kamera nélkül is tesztelhető:

```bash
python test_gestures.py
# vagy: pip install pytest && pytest
```

## Biztonság

A PyAutoGUI **failsafe** be van kapcsolva: ha az egeret gyorsan a képernyő
bal felső sarkába húzod, a program megszakad.
