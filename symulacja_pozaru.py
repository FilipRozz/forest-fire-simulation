import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
from PIL import Image, ImageTk

# =========================
# Stany automatu
# =========================
WATER   = 0
ROCK    = 1
URBAN   = 2
TREE    = 3
BURNING = 4
BURNED  = 5
FIREBREAK = 6  # pas przeciwpożarowy / ziemia / "beton" - niepalne

STATE_NAMES = {
    WATER: "Water",
    ROCK: "Rock",
    URBAN: "Urban",
    TREE: "Tree",
    BURNING: "Burning",
    BURNED: "Burned",
    FIREBREAK: "Firebreak",
}

# Kolory bazowe (RGB)
COLORS = {
    WATER:     ( 30,  90, 200),
    ROCK:      (120, 120, 120),
    URBAN:     (200, 200, 200),
    TREE:      ( 30, 160,  60),  # modyfikowany wilgotnością
    BURNING:   (240,  70,  20),
    BURNED:    ( 45,  45,  45),
    FIREBREAK: (160, 120,  70),
}


# =========================
# Symulacja
# =========================
class FireCA:
    def __init__(self, n=160, seed=0):
        self.n = n
        self.rng = np.random.default_rng(seed)

        self.state = np.full((n, n), TREE, dtype=np.int8)
        self.humidity = np.full((n, n), 0.35, dtype=np.float32)     # [0..1]
        self.elevation = np.zeros((n, n), dtype=np.float32)          # [0..1]
        self.burn_age = np.zeros((n, n), dtype=np.int16)

        # Parametry globalne (sterowane z GUI)
        self.p_spread = 0.42
        self.burn_time = 10
        self.wind_dir_deg = 0.0      # 0 = w prawo
        self.wind_speed = 1.0        # 0..3
        self.rain = 0.0              # 0..1 (nawilżanie)
        self.lightning = 0.00001     # pioruny

        self.evaporation = 0.015     # wysuszanie przez ogień
        self.water_influence = 0.010 # nawilżanie przy wodzie

    def reset_random(self):
        n = self.n
        self.state[:] = TREE
        # losowe "niepalne" plamy
        rock_mask = self.rng.random((n, n)) < 0.03
        urban_mask = self.rng.random((n, n)) < 0.02
        water_mask = self.rng.random((n, n)) < 0.03
        self.state[rock_mask] = ROCK
        self.state[urban_mask] = URBAN
        self.state[water_mask] = WATER

        self.elevation[:] = self.rng.random((n, n)).astype(np.float32)
        self.humidity[:] = (0.25 + 0.25 * self.rng.random((n, n))).astype(np.float32)
        self.humidity[self.state == WATER] = 1.0
        self.burn_age[:] = 0

    def load_from_image(self, path, n=None):
        if n is None:
            n = self.n
        img = Image.open(path).convert("RGB")
        img = img.resize((n, n), Image.Resampling.BILINEAR)
        arr = np.asarray(img).astype(np.int16)
        r = arr[..., 0]
        g = arr[..., 1]
        b = arr[..., 2]
        gray = ((r + g + b) // 3).astype(np.int16)

        # Prosta klasyfikacja "mapy":
        # - dużo niebieskiego => woda
        # - bardzo ciemne => skały/cień => ROCK
        # - jasne szare => URBAN
        # - dużo zielonego => TREE
        water = (b > 140) & (b > r + 20) & (b > g + 10)
        rock  = (gray < 55)
        urban = (gray > 185) & (np.abs(r - g) < 20) & (np.abs(g - b) < 20)
        tree  = (g > 105) & (g > r + 15) & (g > b + 15)

        self.state[:] = URBAN  # domyślnie
        self.state[tree] = TREE
        self.state[water] = WATER
        self.state[rock] = ROCK
        # "firebreak" zostaje do rysowania z GUI

        # Wilgotność: zależna od zieleni + bonus przy wodzie
        self.humidity[:] = np.clip((g / 255.0) * 0.55, 0.05, 0.75).astype(np.float32)
        self.humidity[self.state == WATER] = 1.0

        # "Wysokość" z jasności (albo z kanału R dla różnorodności) – tu z gray
        self.elevation[:] = (gray / 255.0).astype(np.float32)

        self.burn_age[:] = 0

    def _wind_unit(self):
        ang = np.deg2rad(self.wind_dir_deg)
        wx = np.cos(ang)
        wy = np.sin(ang)
        return wx, wy

    def step(self):
        s = self.state
        n = self.n

        burning = (s == BURNING)
        trees = (s == TREE)

        # =========================
        # REGUŁA 1: Pioruny (losowy zapłon)
        # =========================
        if self.lightning > 0:
            strike = (self.rng.random((n, n)) < self.lightning) & trees
            s[strike] = BURNING
            self.burn_age[strike] = 0

        burning = (s == BURNING)
        trees = (s == TREE)

        # =========================
        # REGUŁA 2: Rozprzestrzenianie ognia od sąsiadów (8-neighborhood)
        # zależne od: wilgotności, wiatru, nachylenia (wysokości)
        # =========================
        wx, wy = self._wind_unit()

        # kierunki (dx, dy) + wektory jednostkowe dla wiatru
        dirs = [
            (-1,  0), ( 1,  0), ( 0, -1), ( 0,  1),
            (-1, -1), (-1,  1), ( 1, -1), ( 1,  1),
        ]

        ignite_prob = np.zeros((n, n), dtype=np.float32)

        for dx, dy in dirs:
            src_burning = np.roll(np.roll(burning, dx, axis=0), dy, axis=1)

            # czynnik wiatru: jeśli ogień "idzie" w stronę komórki zgodnie z wiatrem, rośnie
            # wektor od źródła do celu: (-dx, -dy)
            vlen = np.sqrt(dx*dx + dy*dy)
            vx = (-dx) / vlen
            vy = (-dy) / vlen
            wind_align = max(0.0, (vx * wx + vy * wy))  # 0..1
            wind_factor = 1.0 + self.wind_speed * 0.9 * wind_align

            # czynnik nachylenia: ogień łatwiej idzie "pod górę"
            elev_src = np.roll(np.roll(self.elevation, dx, axis=0), dy, axis=1)
            slope = np.clip(self.elevation - elev_src, -1.0, 1.0)
            slope_factor = 1.0 + 0.8 * np.maximum(0.0, slope)

            # prawdopodobieństwo zapłonu od tego kierunku
            base = self.p_spread * wind_factor * slope_factor
            # im większa wilgotność, tym mniejsze szanse
            p = base * (1.0 - self.humidity)

            # jeśli źródło płonie, to może podpalić
            ignite_prob = np.maximum(ignite_prob, p * src_burning.astype(np.float32))

        can_ignite = trees
        rand = self.rng.random((n, n)).astype(np.float32)
        new_ignite = can_ignite & (rand < ignite_prob)

        # niepalne: woda, skała, urban, firebreak
        nonburnable = (s == WATER) | (s == ROCK) | (s == URBAN) | (s == FIREBREAK) | (s == BURNED)
        new_ignite &= ~nonburnable

        s[new_ignite] = BURNING
        self.burn_age[new_ignite] = 0

        # =========================
        # REGUŁA 3: Płonące -> spalone po burn_time krokach
        # =========================
        burning = (s == BURNING)
        self.burn_age[burning] += 1
        done = burning & (self.burn_age >= self.burn_time)
        s[done] = BURNED
        self.burn_age[done] = 0

        # =========================
        # REGUŁA 4: Wilgotność dynamiczna:
        # - deszcz zwiększa wilgotność
        # - ogień wysusza okolicę
        # - sąsiedztwo wody nawilża
        # =========================
        if self.rain > 0:
            self.humidity = np.clip(self.humidity + 0.02 * self.rain, 0.0, 1.0)

        # wysuszanie przy ogniu (lokalnie + sąsiedztwo)
        burn_field = burning.astype(np.float32)
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            burn_field += 0.6 * np.roll(np.roll(burning, dx, axis=0), dy, axis=1).astype(np.float32)
        self.humidity = np.clip(self.humidity - self.evaporation * np.clip(burn_field, 0, 2), 0.0, 1.0)

        # nawilżanie przy wodzie (4-neighborhood)
        water = (s == WATER)
        near_water = water.copy()
        for dx, dy in [(-1,0),(1,0),(0,-1),(0,1)]:
            near_water |= np.roll(np.roll(water, dx, axis=0), dy, axis=1)
        self.humidity = np.clip(self.humidity + self.water_influence * near_water.astype(np.float32), 0.0, 1.0)

        # woda zawsze maksymalnie wilgotna
        self.humidity[s == WATER] = 1.0


# =========================
# GUI
# =========================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("2D Automat Komórkowy – Pożar Lasu (GUI)")
        self.geometry("1100x720")

        self.n = 180
        self.cell_px = 3  # powiększenie przy renderze
        self.sim = FireCA(n=self.n, seed=1)
        self.sim.reset_random()

        self.running = False
        self.after_id = None

        self.tool = tk.StringVar(value="ignite")
        self.brush = tk.IntVar(value=6)

        self._build_ui()
        self._render()

    def _build_ui(self):
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)

        left = ttk.Frame(root)
        left.pack(side="left", fill="y", padx=10, pady=10)

        right = ttk.Frame(root)
        right.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        # Canvas
        w = self.n * self.cell_px
        h = self.n * self.cell_px
        self.canvas = tk.Canvas(right, width=w, height=h, bg="black", highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_paint)
        self.canvas.bind("<B1-Motion>", self._on_paint)

        # Buttons
        btns = ttk.LabelFrame(left, text="Sterowanie")
        btns.pack(fill="x", pady=5)

        ttk.Button(btns, text="Start / Pause", command=self.toggle).pack(fill="x", pady=2)
        ttk.Button(btns, text="Step", command=self.step_once).pack(fill="x", pady=2)
        ttk.Button(btns, text="Reset (random)", command=self.reset).pack(fill="x", pady=2)
        ttk.Button(btns, text="Load terrain image", command=self.load_image).pack(fill="x", pady=2)

        # Tool selection (mechanizmy modyfikacji w trakcie)
        tools = ttk.LabelFrame(left, text="Narzędzia (zmiana przestrzeni)")
        tools.pack(fill="x", pady=8)

        ttk.Radiobutton(tools, text="Ignite (podpal)", value="ignite", variable=self.tool).pack(anchor="w")
        ttk.Radiobutton(tools, text="Water drop (zrzut wody)", value="water", variable=self.tool).pack(anchor="w")
        ttk.Radiobutton(tools, text="Firebreak (pas ppoż.)", value="firebreak", variable=self.tool).pack(anchor="w")
        ttk.Radiobutton(tools, text="Plant trees (dosadź)", value="plant", variable=self.tool).pack(anchor="w")
        ttk.Radiobutton(tools, text="Erase -> urban (wyczyść)", value="erase", variable=self.tool).pack(anchor="w")

        ttk.Label(tools, text="Brush size").pack(anchor="w", pady=(6,0))
        ttk.Scale(tools, from_=1, to=18, variable=self.brush, orient="horizontal").pack(fill="x")

        # Sliders for parameters
        params = ttk.LabelFrame(left, text="Parametry")
        params.pack(fill="x", pady=8)

        self._slider(params, "p_spread", 0.0, 1.0, self.sim.p_spread, 0.01)
        self._slider(params, "burn_time", 2, 30, self.sim.burn_time, 1, is_int=True)
        self._slider(params, "wind_dir_deg", 0, 360, self.sim.wind_dir_deg, 1, is_int=True)
        self._slider(params, "wind_speed", 0.0, 3.0, self.sim.wind_speed, 0.05)
        self._slider(params, "rain", 0.0, 1.0, self.sim.rain, 0.02)
        self._slider(params, "lightning", 0.0, 0.0002, self.sim.lightning, 0.000005)

        # Legend
        legend = ttk.LabelFrame(left, text="Legenda stanów")
        legend.pack(fill="x", pady=8)
        txt = "\n".join([f"{k}: {v}" for k, v in STATE_NAMES.items()])
        ttk.Label(legend, text=txt, justify="left").pack(anchor="w", padx=6, pady=4)

        note = ttk.LabelFrame(left, text="Reguły (min. 4)")
        note.pack(fill="x", pady=8)
        ttk.Label(
            note,
            justify="left",
            text=(
                "1) Pioruny: losowy zapłon drzew.\n"
                "2) Zapłon od sąsiadów: wiatr + wilgotność + nachylenie.\n"
                "3) Burning -> Burned po burn_time.\n"
                "4) Wilgotność: deszcz nawilża, ogień wysusza, woda nawilża.\n"
                "Dodatkowo: tereny niepalne (water/rock/urban/firebreak)."
            )
        ).pack(anchor="w", padx=6, pady=4)

    def _slider(self, parent, name, a, b, init, step, is_int=False):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)

        ttk.Label(row, text=name, width=12).pack(side="left")

        var = tk.DoubleVar(value=float(init))
        scale = ttk.Scale(row, from_=a, to=b, variable=var, orient="horizontal")
        scale.pack(side="left", fill="x", expand=True, padx=4)

        val_label = ttk.Label(row, width=10)
        val_label.pack(side="right")

        def update_label(*_):
            v = var.get()
            if is_int:
                v = int(round(v))
                var.set(v)
            val_label.config(text=str(v))
            setattr(self.sim, name, v)

        var.trace_add("write", update_label)
        update_label()

    def load_image(self):
        path = filedialog.askopenfilename(
            title="Wybierz obraz terenu",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All", "*.*")]
        )
        if not path:
            return
        try:
            self.sim.load_from_image(path, n=self.n)
            self._render()
        except Exception as e:
            messagebox.showerror("Błąd", f"Nie udało się wczytać obrazu:\n{e}")

    def reset(self):
        self.sim.reset_random()
        self._render()

    def toggle(self):
        self.running = not self.running
        if self.running:
            self._loop()
        else:
            if self.after_id is not None:
                self.after_cancel(self.after_id)
                self.after_id = None

    def step_once(self):
        if not self.running:
            self.sim.step()
            self._render()

    def _loop(self):
        # kilka kroków na klatkę dla płynniejszej symulacji
        for _ in range(2):
            self.sim.step()
        self._render()
        self.after_id = self.after(33, self._loop)  # ~30 FPS

    def _on_paint(self, event):
        x = event.x // self.cell_px
        y = event.y // self.cell_px
        if x < 0 or y < 0 or x >= self.n or y >= self.n:
            return

        r = int(self.brush.get())
        xs = slice(max(0, x - r), min(self.n, x + r + 1))
        ys = slice(max(0, y - r), min(self.n, y + r + 1))

        tool = self.tool.get()
        s = self.sim.state
        h = self.sim.humidity
        ba = self.sim.burn_age

        if tool == "ignite":
            mask = (s[ys, xs] == TREE)
            s[ys, xs][mask] = BURNING
            ba[ys, xs][mask] = 0

        elif tool == "water":
            # Mechanizm 1: zrzut wody (gasi i nawilża)
            # - płonące -> tree (uratowane) albo burned (w zależności od wieku), tu uproszczenie: -> TREE
            burning = (s[ys, xs] == BURNING)
            s[ys, xs][burning] = TREE
            ba[ys, xs][burning] = 0
            # nawilżenie obszaru
            h[ys, xs] = np.clip(h[ys, xs] + 0.6, 0.0, 1.0)

        elif tool == "firebreak":
            # Mechanizm 2: pas przeciwpożarowy (niepalne)
            non = (s[ys, xs] != WATER)
            s[ys, xs][non] = FIREBREAK
            ba[ys, xs][non] = 0

        elif tool == "plant":
            # Mechanizm 3: dosadzanie drzew
            can = (s[ys, xs] != WATER) & (s[ys, xs] != ROCK)
            s[ys, xs][can] = TREE
            # trochę wilgoci dla "nowego" lasu
            h[ys, xs] = np.clip(h[ys, xs] + 0.1, 0.0, 1.0)

        elif tool == "erase":
            # dodatkowy mechanizm: czyszczenie do URBAN (niepalne)
            can = (s[ys, xs] != WATER)
            s[ys, xs][can] = URBAN
            ba[ys, xs][can] = 0

        self._render()

    def _render(self):
        s = self.sim.state
        h = self.sim.humidity

        rgb = np.zeros((self.n, self.n, 3), dtype=np.uint8)

        for st, col in COLORS.items():
            mask = (s == st)
            rgb[mask] = col

        # Drzewa: kolor zależny od wilgotności (bardziej wilgotne -> ciemniejsze/zimniejsze)
        tree_mask = (s == TREE)
        if np.any(tree_mask):
            base = np.array(COLORS[TREE], dtype=np.float32)
            # wilgotność 0..1 => skala 0.7..1.1 (subtelnie)
            scale = (0.7 + 0.4 * h).astype(np.float32)
            tr = (base[0] * scale)
            tg = (base[1] * (0.8 + 0.6 * h))
            tb = (base[2] * (0.8 + 0.3 * h))
            rgb[..., 0] = np.where(tree_mask, np.clip(tr, 0, 255), rgb[..., 0]).astype(np.uint8)
            rgb[..., 1] = np.where(tree_mask, np.clip(tg, 0, 255), rgb[..., 1]).astype(np.uint8)
            rgb[..., 2] = np.where(tree_mask, np.clip(tb, 0, 255), rgb[..., 2]).astype(np.uint8)

        img = Image.fromarray(rgb, mode="RGB")
        img = img.resize((self.n * self.cell_px, self.n * self.cell_px), Image.Resampling.NEAREST)
        self.tk_img = ImageTk.PhotoImage(img)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)


if __name__ == "__main__":
    App().mainloop()