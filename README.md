# 🔥 Forest Fire Simulation — 2D Cellular Automaton

A real-time interactive simulation of forest fire spread built in Python, using a **2D cellular automaton** model on a 180×180 grid with a full GUI.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python) ![NumPy](https://img.shields.io/badge/NumPy-vectorized-orange) ![tkinter](https://img.shields.io/badge/GUI-tkinter-green) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## 🧠 How It Works

Each cell on the grid represents a terrain tile with one of 7 states:

| State | Description |
|-------|-------------|
| 🌊 Water | Non-flammable, raises humidity of neighbors |
| 🪨 Rock | Non-flammable |
| 🏘️ Urban | Non-flammable (buildings, concrete) |
| 🌲 Tree | Flammable — the main fuel source |
| 🔥 Burning | Currently on fire |
| ⬛ Burned | Fully consumed, ash |
| 🟫 Firebreak | Manually placed firebreak, non-flammable |

### Transition Rules (automaton logic)

The simulation advances in discrete steps, applying four rules simultaneously:

1. **Lightning strikes** — trees ignite spontaneously with a configurable probability, simulating natural fire starts.
2. **Neighbor ignition** — a burning cell spreads fire to adjacent trees (8-neighborhood) with probability modulated by:
   - **Humidity** — wetter trees are harder to ignite
   - **Wind** — direction and speed bias fire spread; aligned neighbors are much more likely to catch fire
   - **Terrain elevation** — fire climbs uphill faster (slope factor)
3. **Burnout** — burning cells transition to *Burned* after a configurable number of steps (`burn_time`)
4. **Dynamic humidity** — humidity evolves every step: rain increases it globally, fire dries out nearby cells, water tiles raise humidity in their 4-neighborhood

---

## 🖥️ GUI & Interactive Features

The simulation runs with a **tkinter GUI** at ~30 FPS with real-time parameter control.

### Control Panel

| Control | Effect |
|---------|--------|
| Start / Pause | Toggle simulation |
| Step | Advance one tick manually |
| Reset (random) | Regenerate random terrain |
| Load terrain image | Import a PNG/JPG as terrain map |

### Paint Tools (click & drag on the grid)

| Tool | Effect |
|------|--------|
| Ignite | Set trees on fire |
| Water drop | Extinguish fire + raise local humidity |
| Firebreak | Place non-flammable barrier |
| Plant trees | Restore vegetation |
| Erase → Urban | Replace area with non-flammable urban tile |

### Real-time Sliders

- `p_spread` — base fire spread probability
- `burn_time` — how many steps a cell burns before turning to ash
- `wind_dir_deg` — wind direction (0–360°)
- `wind_speed` — wind intensity (0–3)
- `rain` — rainfall intensity, globally raises humidity
- `lightning` — spontaneous ignition probability

---

## 📷 Terrain from Image

You can load any image (PNG, JPG, BMP) as a terrain map. The loader classifies pixels by color:
- **Blue-dominant** → Water
- **Green-dominant** → Tree
- **Dark** → Rock
- **Light gray** → Urban

Humidity and elevation are derived from pixel brightness and green channel intensity.

---

## 🚀 Running the Simulation

### Requirements

```
pip install numpy pillow
```

> `tkinter` is part of the Python standard library — no extra install needed.

### Run

```bash
python symulacja_pozaru.py
```

---

## 🏗️ Project Structure

```
symulacja_pozaru.py
├── FireCA          # Core simulation engine (cellular automaton)
│   ├── state       # 2D numpy array of cell states
│   ├── humidity    # per-cell moisture [0..1]
│   ├── elevation   # per-cell height [0..1]
│   └── step()      # advances simulation by one tick
└── App             # tkinter GUI layer
    ├── _build_ui() # constructs controls and canvas
    ├── _render()   # converts state array to RGB image
    └── _on_paint() # handles mouse interaction
```

---

## 📐 Technical Highlights

- **Fully vectorized** with NumPy — no Python loops over cells during simulation
- Wind and slope factors computed per-direction using dot products and array rolling
- Humidity rendered visually — tree color shifts based on moisture level
- GUI runs at ~30 FPS using `tkinter.after()` scheduling

---

*Academic project — Discrete Modeling course*
