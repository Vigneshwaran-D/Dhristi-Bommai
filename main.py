import sys
import platform
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, List

import tkinter as tk
from tkinter import Canvas, Menu
from PIL import Image, ImageTk


# Enable DPI awareness on Windows for razor-sharp rendering and accurate cursor tracking
if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


@dataclass
class Config:
    charm_size: int = 130
    rope_nodes: int = 14              # Number of flexible rope segments
    rope_length: int = 210
    gravity: float = 2400.0           # Screen gravity (px/s^2)
    damping: float = 0.988            # Velocity retention per frame
    window_width: int = 520
    window_height: int = 580
    target_fps: int = 60
    margin_right: int = 220
    transparent_color: str = "#010101"


CHARM_CATALOG: List[Tuple[str, str]] = [
    ("drishti-bommai.png", "Drishti Bommai (Demon Mask)"),
    ("nimbu-lemon.png", "Nimbu Mirchi (Lemon & Chilies)"),
    ("nazar.png", "Nazar Amulet (Turkish Eye)"),
    ("daruma.png", "Daruma Doll"),
    ("ghanta.png", "Ghanta (Temple Bell)"),
    ("maneki-neko.png", "Maneki Neko (Lucky Cat)"),
    ("chinese-knot.png", "Chinese Lucky Knot"),
    ("hamsa.png", "Hamsa Hand"),
    ("horseshoe.png", "Lucky Horseshoe"),
    ("gem.png", "Auspicious Gemstone"),
    ("charm.png", "Traditional Amulet"),
    ("charm_new.png", "Modern Lucky Charm"),
]


class PlatformAdapter:
    def __init__(self, root: tk.Tk, window_width: int, window_height: int, transparent_color: str):
        self.root = root
        self.window_width = window_width
        self.window_height = window_height
        self.transparent_color = transparent_color
        self.is_windows = platform.system() == "Windows"
        self.is_macos = platform.system() == "Darwin"
        self.clickthrough_enabled = False
        self.setup_window()

    def setup_window(self):
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        if self.is_windows:
            self.root.attributes("-transparentcolor", self.transparent_color)
            self._setup_windows()
        elif self.is_macos:
            self.root.attributes("-transparent", True)
            self.root.attributes("-alpha", 1.0)
            self._setup_macos()

        screen_width = self.root.winfo_screenwidth()
        x = max(0, screen_width - self.window_width - 15)
        y = 0
        self.root.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

    def _setup_windows(self):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TOPMOST = 0x00000008

            ex_style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            ex_style |= WS_EX_LAYERED | WS_EX_TOPMOST
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex_style)
        except Exception as e:
            print(f"Windows setup warning: {e}")

    def _setup_macos(self):
        try:
            self.root.wm_attributes("-transparent", True)
        except Exception as e:
            print(f"macOS setup warning: {e}")

    def set_clickthrough(self, enabled: bool):
        if not self.is_windows:
            return
        if self.clickthrough_enabled == enabled:
            return

        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_TRANSPARENT = 0x00000020
            ex_style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            if enabled:
                ex_style |= WS_EX_TRANSPARENT
            else:
                ex_style &= ~WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex_style)
            self.clickthrough_enabled = enabled
        except Exception as e:
            print(f"Click-through toggle warning: {e}")

    def get_cursor_pos(self) -> Tuple[int, int]:
        if self.is_windows:
            try:
                import ctypes
                from ctypes import wintypes
                pt = wintypes.POINT()
                ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                return pt.x, pt.y
            except Exception:
                pass
        return self.root.winfo_pointerx(), self.root.winfo_pointery()

    def is_left_button_down(self) -> bool:
        if self.is_windows:
            try:
                import ctypes
                return (ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000) != 0
            except Exception:
                pass
        return False


class CharmRenderer:
    def __init__(self, canvas: Canvas, config: Config, assets_dir: Path):
        self.canvas = canvas
        self.config = config
        self.assets_dir = assets_dir
        self.current_asset_name = CHARM_CATALOG[0][0]
        self.current_charm_label = CHARM_CATALOG[0][1]
        self.visible = True

        self.base_image: Optional[Image.Image] = None
        self.charm_width = self.config.charm_size
        self.charm_height = self.config.charm_size
        self._rotated_cache: Dict[int, ImageTk.PhotoImage] = {}
        self.current_photo: Optional[ImageTk.PhotoImage] = None

        # Canvas item IDs for dangle
        self.slider_plate_id: Optional[int] = None
        self.slider_text_id: Optional[int] = None
        self.anchor_mount_id: Optional[int] = None
        self.rope_outer_id: Optional[int] = None
        self.rope_inner_id: Optional[int] = None
        self.bead_ids: List[int] = []
        self.knot_id: Optional[int] = None
        self.charm_id: Optional[int] = None

        # Badge pill notification (displays briefly on key press)
        self.badge_bg_id: Optional[int] = None
        self.badge_text_id: Optional[int] = None

        self.init_canvas_items()
        self.load_charm(self.current_asset_name, self.current_charm_label)

    def sanitize_image(self, img: Image.Image) -> Image.Image:
        img = img.convert("RGBA")
        r, g, b, a = img.split()
        a = a.point(lambda p: 255 if p >= 85 else 0)
        b = b.point(lambda p: 2 if p == 1 else p)
        return Image.merge("RGBA", (r, g, b, a))

    def load_charm(self, asset_filename: str, label: str):
        self.current_asset_name = asset_filename
        self.current_charm_label = label
        self._rotated_cache.clear()

        asset_path = self.assets_dir / asset_filename
        if not asset_path.exists():
            available = list(self.assets_dir.glob("*.png"))
            if available:
                asset_path = available[0]

        try:
            raw_img = Image.open(asset_path)
            raw_img.thumbnail(
                (self.config.charm_size, self.config.charm_size),
                Image.Resampling.LANCZOS,
            )
            self.base_image = self.sanitize_image(raw_img)
            self.charm_width, self.charm_height = self.base_image.size
        except Exception as e:
            print(f"Failed to load charm {asset_filename}: {e}")
            self.base_image = Image.new("RGBA", (self.config.charm_size, self.config.charm_size), (180, 40, 20, 255))
            self.charm_width, self.charm_height = self.base_image.size

    def get_rotated_frame(self, degrees: float) -> ImageTk.PhotoImage:
        deg_int = int(round(degrees))
        deg_clamped = max(-85, min(85, deg_int))
        if deg_clamped not in self._rotated_cache:
            rotated = self.base_image.rotate(deg_clamped, resample=Image.Resampling.BICUBIC, expand=True)
            self._rotated_cache[deg_clamped] = ImageTk.PhotoImage(rotated)
        return self._rotated_cache[deg_clamped]

    def init_canvas_items(self):
        # 1. Top ceiling slider plate
        self.slider_plate_id = self.canvas.create_rectangle(
            0, 0, 0, 0, fill="#B8860B", outline="#FFD700", width=1.5, tags="slider"
        )
        self.slider_text_id = self.canvas.create_text(
            0, 0, text="◄ SLIDE ►", fill="#FFFFFF", font=("Segoe UI", 7, "bold"), tags="slider"
        )
        # 2. Suspension ring
        self.anchor_mount_id = self.canvas.create_oval(
            0, 0, 0, 0, fill="#D4AF37", outline="#8B6508", width=1.5, tags="anchor"
        )
        # 3. Supple braided cord with smooth spline curves
        self.rope_outer_id = self.canvas.create_line(
            0, 0, 0, 0, fill="#7A180E", width=4.0, capstyle=tk.ROUND, smooth=True, tags="rope"
        )
        self.rope_inner_id = self.canvas.create_line(
            0, 0, 0, 0, fill="#C48E28", width=1.5, capstyle=tk.ROUND, smooth=True, tags="rope"
        )
        # 4. 3 decorative beads along the cord
        self.bead_ids = []
        bead_colors = ["#D4AF37", "#6B2D18", "#D4AF37"]
        for i in range(3):
            bid = self.canvas.create_oval(
                0, 0, 0, 0, fill=bead_colors[i], outline="#3A1A0A", width=1.0, tags="bead"
            )
            self.bead_ids.append(bid)
        # 5. Charm image (placed below knot)
        self.charm_id = self.canvas.create_image(
            0, 0, anchor=tk.CENTER, tags="charm"
        )
        # 6. Lower knot connector (drawn on top of the attachment point at the top edge of charm)
        self.knot_id = self.canvas.create_oval(
            0, 0, 0, 0, fill="#8B1E0F", outline="#D4AF37", width=1.2, tags="knot"
        )

        # 7. Notification Badge Pill
        self.badge_bg_id = self.canvas.create_rectangle(
            0, 0, 0, 0, fill="#181818", outline="#D4AF37", width=1.0, tags="badge"
        )
        self.badge_text_id = self.canvas.create_text(
            0, 0, text="", fill="#FFD700", font=("Segoe UI", 8, "bold"), tags="badge"
        )

        self.canvas.itemconfigure("badge", state="hidden")

    def draw(self, nodes: List[List[float]], angle: float, show_badge: bool = False, badge_label: str = ""):
        if not self.visible:
            self.canvas.itemconfigure("all", state="hidden")
            return

        self.canvas.itemconfigure("all", state="normal")

        anchor_x, anchor_y = nodes[0][0], nodes[0][1]
        attach_x, attach_y = nodes[-1][0], nodes[-1][1]  # The bottom tip of the rope

        # Top ceiling slider handle bracket
        plate_w = 34.0
        plate_h = 10.0
        self.canvas.coords(
            self.slider_plate_id,
            anchor_x - plate_w, 0,
            anchor_x + plate_w, plate_h
        )
        self.canvas.coords(self.slider_text_id, anchor_x, 5)

        # Suspension ring
        mount_r = 6.0
        self.canvas.coords(
            self.anchor_mount_id,
            anchor_x - mount_r, anchor_y + 2,
            anchor_x + mount_r, anchor_y + mount_r * 2 + 2
        )

        # Rope curved spline through all nodes (stops right at attach_x, attach_y)
        rope_points = []
        for p in nodes:
            rope_points.extend([p[0], p[1]])

        self.canvas.coords(self.rope_outer_id, *rope_points)
        self.canvas.coords(self.rope_inner_id, *rope_points)

        # Position beads along the flexible rope
        N = len(nodes)
        bead_indices = [max(1, int(N * 0.25)), max(2, int(N * 0.50)), max(3, int(N * 0.75))]
        for idx, node_idx in enumerate(bead_indices):
            bx = nodes[node_idx][0]
            by = nodes[node_idx][1]
            br = 5.0 if idx != 1 else 6.0
            self.canvas.coords(self.bead_ids[idx], bx - br, by - br, bx + br, by + br)

        # Rotate charm: positive angle = swing right, Pillow rotates CCW, so use +degrees
        rotation_deg = math.degrees(angle)
        self.current_photo = self.get_rotated_frame(rotation_deg)

        # ATTACHMENT TO TOP EDGE OF CHARM:
        # Place charm center exactly half_h below the rope tip along the tangent direction.
        # This ensures the charm's top pixel lands precisely at the rope bottom node.
        half_h = self.charm_height * 0.5
        charm_center_x = attach_x + half_h * math.sin(angle)
        charm_center_y = attach_y + half_h * math.cos(angle)

        self.canvas.coords(self.charm_id, int(round(charm_center_x)), int(round(charm_center_y)))
        self.canvas.itemconfig(self.charm_id, image=self.current_photo)

        # Lower knot connector sits right on top edge of the charm where rope attaches
        kr = 5.0
        self.canvas.coords(self.knot_id, attach_x - kr, attach_y - kr, attach_x + kr, attach_y + kr)

        # Notification Badge (positioned cleanly below the charm body)
        if show_badge and badge_label:
            self.canvas.itemconfigure("badge", state="normal")
            badge_y = charm_center_y + half_h + 14.0
            badge_text = f"◄  {badge_label}  ►"
            self.canvas.itemconfig(self.badge_text_id, text=badge_text)

            badge_half_w = min(130.0, len(badge_text) * 4.2 + 16.0)
            self.canvas.coords(
                self.badge_bg_id,
                charm_center_x - badge_half_w, badge_y - 10,
                charm_center_x + badge_half_w, badge_y + 10
            )
            self.canvas.coords(self.badge_text_id, charm_center_x, badge_y)
        else:
            self.canvas.itemconfigure("badge", state="hidden")

    def set_visible(self, visible: bool):
        self.visible = visible
        if not visible:
            self.canvas.itemconfigure("all", state="hidden")
        else:
            self.canvas.itemconfigure("all", state="normal")


class FlexibleRopePhysics:
    def __init__(self, config: Config):
        self.config = config
        self.N = config.rope_nodes
        self.rope_length = float(config.rope_length)
        self.seg_len = self.rope_length / (self.N - 1)
        self.anchor_x = 0.0
        self.anchor_y = 0.0

        self.pos: List[List[float]] = []
        self.prev: List[List[float]] = []
        self.dragging = False
        self.drag_node = -1
        self.drag_offset_x = 0.0
        self.drag_offset_y = 0.0
        self.mouse_vx = 0.0
        self.mouse_vy = 0.0

    def set_anchor(self, x: float, y: float):
        self.anchor_x = x
        self.anchor_y = y
        self.reset()

    def reset(self):
        self.pos = [[self.anchor_x, self.anchor_y + i * self.seg_len] for i in range(self.N)]
        self.prev = [[p[0], p[1]] for p in self.pos]
        self.dragging = False
        self.drag_node = -1

    def get_attachment_point(self) -> Tuple[float, float]:
        """Returns the bottom tip of the rope where the charm attaches."""
        return self.pos[-1][0], self.pos[-1][1]

    def get_bottom_tangent_angle(self) -> float:
        dx = self.pos[-1][0] - self.pos[-2][0]
        dy = self.pos[-1][1] - self.pos[-2][1]
        return math.atan2(dx, max(1e-3, dy))

    def get_charm_center(self, charm_height: float) -> Tuple[float, float]:
        """Returns the visual center of the charm hanging below the rope tip."""
        ax, ay = self.get_attachment_point()
        angle = self.get_bottom_tangent_angle()
        half_h = charm_height * 0.5
        cx = ax + half_h * math.sin(angle)
        cy = ay + half_h * math.cos(angle)
        return cx, cy

    def get_closest_node(self, px: float, py: float) -> Tuple[int, float]:
        min_dist = float("inf")
        best_idx = self.N - 1
        for i in range(1, self.N):
            d = math.hypot(self.pos[i][0] - px, self.pos[i][1] - py)
            if d < min_dist:
                min_dist = d
                best_idx = i
        return best_idx, min_dist

    def get_rope_distance(self, px: float, py: float) -> float:
        min_d = float("inf")
        for i in range(self.N - 1):
            x1, y1 = self.pos[i]
            x2, y2 = self.pos[i + 1]
            dx, dy = x2 - x1, y2 - y1
            lsq = dx * dx + dy * dy
            if lsq > 1e-4:
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / lsq))
                cx = x1 + t * dx
                cy = y1 + t * dy
                d = math.hypot(px - cx, py - cy)
            else:
                d = math.hypot(px - x1, py - y1)
            if d < min_d:
                min_d = d
        return min_d

    def apply_hover_bend(self, mouse_x: float, mouse_y: float, vx: float, vy: float, dt: float, charm_height: float):
        if self.dragging:
            return

        # 1. Bend rope nodes around cursor
        cursor_r = 26.0
        for i in range(1, self.N - 1):
            dx = self.pos[i][0] - mouse_x
            dy = self.pos[i][1] - mouse_y
            d = math.hypot(dx, dy)
            if d < cursor_r and d > 1e-4:
                push = (cursor_r - d)
                self.pos[i][0] += (dx / d) * push * 0.75
                self.pos[i][1] += (dy / d) * push * 0.75
                if abs(vx) > 15.0:
                    self.pos[i][0] += vx * dt * 0.45

        # 2. Deflect charm if cursor touches or sweeps the charm body
        charm_cx, charm_cy = self.get_charm_center(charm_height)
        dist_charm = math.hypot(mouse_x - charm_cx, mouse_y - charm_cy)
        charm_r = self.config.charm_size * 0.52

        if dist_charm < charm_r:
            dx = charm_cx - mouse_x
            dy = charm_cy - mouse_y
            penetration = (charm_r - dist_charm) / charm_r
            if abs(vx) > 15.0:
                nudge_x = 1.0 if vx > 0 else -1.0
            elif abs(dx) > 1.0:
                nudge_x = 1.0 if dx > 0 else -1.0
            else:
                nudge_x = 1.0
            self.pos[-1][0] += nudge_x * penetration * 6.0
            if abs(vx) > 15.0:
                self.pos[-1][0] += vx * dt * 0.65

    def update_physics(self, dt: float):
        gravity = self.config.gravity
        damping = self.config.damping

        # 1. Verlet integration for non-fixed nodes
        for i in range(1, self.N):
            if self.dragging and i == self.drag_node:
                continue
            vx = (self.pos[i][0] - self.prev[i][0]) * damping
            vy = (self.pos[i][1] - self.prev[i][1]) * damping
            self.prev[i][0] = self.pos[i][0]
            self.prev[i][1] = self.pos[i][1]

            g_mult = 1.0 if i == self.N - 1 else 0.70
            self.pos[i][0] += vx
            self.pos[i][1] += vy + (gravity * g_mult) * dt * dt

        # 2. Distance constraint relaxation
        iterations = 16
        for _ in range(iterations):
            self.pos[0] = [self.anchor_x, self.anchor_y]

            for i in range(self.N - 1):
                p1 = self.pos[i]
                p2 = self.pos[i + 1]
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                d = math.hypot(dx, dy)
                if d > 1e-4:
                    err = (d - self.seg_len) / d

                    p1_fixed = (i == 0) or (self.dragging and i == self.drag_node)
                    p2_fixed = (self.dragging and i + 1 == self.drag_node)

                    if p1_fixed and not p2_fixed:
                        p2[0] -= dx * err
                        p2[1] -= dy * err
                    elif p2_fixed and not p1_fixed:
                        p1[0] += dx * err
                        p1[1] += dy * err
                    elif not p1_fixed and not p2_fixed:
                        if i + 1 == self.N - 1:
                            p1[0] += dx * err * 0.78
                            p1[1] += dy * err * 0.78
                            p2[0] -= dx * err * 0.22
                            p2[1] -= dy * err * 0.22
                        else:
                            p1[0] += dx * err * 0.50
                            p1[1] += dy * err * 0.50
                            p2[0] -= dx * err * 0.50
                            p2[1] -= dy * err * 0.50

    def start_drag(self, mouse_x: float, mouse_y: float, charm_height: float):
        charm_cx, charm_cy = self.get_charm_center(charm_height)
        dist_charm = math.hypot(mouse_x - charm_cx, mouse_y - charm_cy)
        charm_r = self.config.charm_size * 0.55

        if dist_charm <= charm_r:
            self.drag_node = self.N - 1
            # Offset from the attachment point
            self.drag_offset_x = mouse_x - self.pos[-1][0]
            self.drag_offset_y = mouse_y - self.pos[-1][1]
        else:
            closest_idx, _ = self.get_closest_node(mouse_x, mouse_y)
            self.drag_node = closest_idx
            self.drag_offset_x = mouse_x - self.pos[self.drag_node][0]
            self.drag_offset_y = mouse_y - self.pos[self.drag_node][1]

        self.dragging = True
        self.mouse_vx = 0.0
        self.mouse_vy = 0.0

    def update_drag(self, mouse_x: float, mouse_y: float, vx: float, vy: float):
        if not self.dragging:
            return

        self.mouse_vx = vx
        self.mouse_vy = vy

        target_x = mouse_x - self.drag_offset_x
        target_y = mouse_y - self.drag_offset_y

        max_reach = self.seg_len * self.drag_node + 20.0
        rel_x = target_x - self.anchor_x
        rel_y = target_y - self.anchor_y
        dist = math.hypot(rel_x, rel_y)
        if dist > max_reach and dist > 1e-4:
            target_x = self.anchor_x + (rel_x / dist) * max_reach
            target_y = self.anchor_y + (rel_y / dist) * max_reach

        target_y = max(self.anchor_y + 8.0, target_y)

        self.pos[self.drag_node][0] = target_x
        self.pos[self.drag_node][1] = target_y

    def end_drag(self, dt: float):
        if not self.dragging:
            return
        self.prev[self.drag_node][0] = self.pos[self.drag_node][0] - self.mouse_vx * dt
        self.prev[self.drag_node][1] = self.pos[self.drag_node][1] - self.mouse_vy * dt
        self.dragging = False
        self.drag_node = -1

    def apply_impulse(self, impulse: float):
        for i in range(1, self.N):
            weight = (i / self.N)
            self.pos[i][0] += impulse * weight * 12.0


class DesktopDangleApp:
    def __init__(self):
        self.config = Config()
        self.root = tk.Tk()
        self.root.title("Dhristi Bommai Desktop Dangle")

        self.platform = PlatformAdapter(
            self.root, self.config.window_width, self.config.window_height, self.config.transparent_color
        )

        self.canvas = Canvas(
            self.root,
            width=self.config.window_width,
            height=self.config.window_height,
            highlightthickness=0,
            bg=self.config.transparent_color
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        assets_dir = Path(__file__).resolve().parent / "assets"
        self.renderer = CharmRenderer(self.canvas, self.config, assets_dir)
        self.physics = FlexibleRopePhysics(self.config)

        self.anchor_x = float(self.config.window_width - self.config.margin_right)
        self.anchor_y = 4.0
        self.physics.set_anchor(self.anchor_x, self.anchor_y)

        self.current_charm_idx = 0
        self.badge_expire_time = 0.0

        # OS-level key state tracking for Left and Right Arrow hotkeys
        self.last_vk_left = False
        self.last_vk_right = False

        # Repositioning state (Slide anywhere on screen top)
        self.sliding_window = False
        self.slide_start_cursor_x = 0
        self.slide_start_win_x = 0

        self.setup_menu()
        self.setup_bindings()

        self.running = True
        self.last_frame_time = time.time()
        self.last_cursor_x = self.anchor_x
        self.last_cursor_y = self.anchor_y

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_menu(self):
        self.context_menu = Menu(self.root, tearoff=0)

        # 1. Charm selection submenu with radio indicators
        charm_menu = Menu(self.context_menu, tearoff=0)
        for idx, (filename, label) in enumerate(CHARM_CATALOG):
            shortcut = f" ({idx + 1})" if idx < 9 else ""
            prefix = "● " if idx == self.current_charm_idx else "   "
            charm_menu.add_command(
                label=f"{prefix}{label}{shortcut}",
                command=lambda i=idx: self.select_charm_by_index(i)
            )
        self.context_menu.add_cascade(label="Select Charm (or Left/Right Arrow)", menu=charm_menu)

        # 2. Preset Reposition Menu (Screen Top Only)
        pos_menu = Menu(self.context_menu, tearoff=0)
        pos_menu.add_command(label="Top Left", command=lambda: self.reposition_to_x(20))
        pos_menu.add_command(label="Top Center", command=self.reposition_to_center)
        pos_menu.add_command(label="Top Right (Default)", command=self.reposition_to_default)
        self.context_menu.add_cascade(label="Reposition Screen Top", menu=pos_menu)

        self.context_menu.add_separator()
        self.context_menu.add_command(label="Reset Position (R)", command=self.reset_position)
        self.context_menu.add_command(label="Bless Impulse (Space)", command=self.bless_animation)
        self.context_menu.add_command(label="Toggle Visibility (H)", command=self.toggle_visibility)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Exit (Esc)", command=self.on_close)

    def setup_bindings(self):
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Button-2>", self.on_middle_mouse_down)
        self.canvas.bind("<Button-3>", self.show_context_menu)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)

        # Left and Right arrow keys for instant charm switching
        self.root.bind("<Left>", lambda e: self.cycle_charm(-1))
        self.root.bind("<Right>", lambda e: self.cycle_charm(1))
        self.root.bind("<Key-Left>", lambda e: self.cycle_charm(-1))
        self.root.bind("<Key-Right>", lambda e: self.cycle_charm(1))

        # Other Hotkeys
        self.root.bind("<Key-h>", self.toggle_visibility)
        self.root.bind("<Key-H>", self.toggle_visibility)
        self.root.bind("<Key-r>", self.reset_position)
        self.root.bind("<Key-R>", self.reset_position)
        self.root.bind("<space>", self.bless_animation)
        self.root.bind("<Escape>", self.on_close)

        # Tab / bracket keys to cycle charms
        self.root.bind("<Tab>", lambda e: self.cycle_charm(1))
        self.root.bind("<Shift-Tab>", lambda e: self.cycle_charm(-1))
        self.root.bind("<bracketright>", lambda e: self.cycle_charm(1))
        self.root.bind("<bracketleft>", lambda e: self.cycle_charm(-1))

        # Shift + Arrow keys to nudge window position on screen top
        self.root.bind("<Shift-Left>", lambda e: self.nudge_window(-35))
        self.root.bind("<Shift-Right>", lambda e: self.nudge_window(35))

        # Number keys 1-9 to directly pick charms
        for i in range(min(9, len(CHARM_CATALOG))):
            self.root.bind(str(i + 1), lambda e, idx=i: self.select_charm_by_index(idx))

    def select_charm_by_index(self, idx: int):
        self.current_charm_idx = idx % len(CHARM_CATALOG)
        filename, label = CHARM_CATALOG[self.current_charm_idx]
        self.renderer.load_charm(filename, label)
        self.badge_expire_time = time.time() + 1.8
        self.setup_menu()

    def cycle_charm(self, delta: int):
        self.select_charm_by_index(self.current_charm_idx + delta)

    def on_mouse_wheel(self, event):
        if event.delta > 0:
            self.cycle_charm(-1)
        else:
            self.cycle_charm(1)

    def is_in_top_bracket(self, local_x: float, local_y: float) -> bool:
        return (0 <= local_y <= 24.0) and (abs(local_x - self.anchor_x) <= 38.0)

    def is_in_interactive_zone(self, local_x: float, local_y: float) -> bool:
        if self.is_in_top_bracket(local_x, local_y):
            return True
        charm_cx, charm_cy = self.physics.get_charm_center(self.renderer.charm_height)
        dist_charm = math.hypot(local_x - charm_cx, local_y - charm_cy)
        dist_rope = self.physics.get_rope_distance(local_x, local_y)
        charm_radius = self.config.charm_size * 0.55
        return (dist_charm <= charm_radius + 36.0) or (dist_rope <= 26.0)

    def on_mouse_down(self, event):
        self.root.focus_set()

        # 1. Top ceiling mount slider plate
        if self.is_in_top_bracket(event.x, event.y) or (event.state & 0x0001):
            self.start_sliding_window()
            return

        # 2. Normal rope / charm drag
        if self.is_in_interactive_zone(event.x, event.y):
            self.physics.start_drag(event.x, event.y, self.renderer.charm_height)
            self.platform.set_clickthrough(False)

    def on_middle_mouse_down(self, event):
        self.start_sliding_window()

    def start_sliding_window(self):
        self.sliding_window = True
        screen_x, _ = self.platform.get_cursor_pos()
        self.slide_start_cursor_x = screen_x
        self.slide_start_win_x = self.root.winfo_x()
        self.canvas.config(cursor="sb_h_double_arrow")
        self.platform.set_clickthrough(False)

    def on_mouse_up(self, event):
        if self.sliding_window:
            self.sliding_window = False
            self.canvas.config(cursor="")
        if self.physics.dragging:
            dt = 1.0 / self.config.target_fps
            self.physics.end_drag(dt)

    def nudge_window(self, dx: int):
        cur_x = self.root.winfo_x()
        screen_width = self.root.winfo_screenwidth()
        new_x = max(0, min(screen_width - self.config.window_width, cur_x + dx))
        self.root.geometry(f"{self.config.window_width}x{self.config.window_height}+{new_x}+0")
        self.root.update_idletasks()
        for p in self.physics.pos[1:]:
            p[0] -= dx * 0.35

    def reposition_to_x(self, x: int):
        screen_width = self.root.winfo_screenwidth()
        new_x = max(0, min(screen_width - self.config.window_width, x))
        old_x = self.root.winfo_x()
        self.root.geometry(f"{self.config.window_width}x{self.config.window_height}+{new_x}+0")
        self.root.update_idletasks()
        delta = new_x - old_x
        for p in self.physics.pos[1:]:
            p[0] -= delta * 0.35

    def reposition_to_center(self):
        screen_width = self.root.winfo_screenwidth()
        cx = max(0, (screen_width - self.config.window_width) // 2)
        self.reposition_to_x(cx)

    def reposition_to_default(self):
        screen_width = self.root.winfo_screenwidth()
        rx = max(0, screen_width - self.config.window_width - 15)
        self.reposition_to_x(rx)

    def show_context_menu(self, event):
        self.context_menu.tk_popup(event.x_root, event.y_root)

    def toggle_visibility(self, event=None):
        self.renderer.set_visible(not self.renderer.visible)

    def reset_position(self, event=None):
        self.physics.reset()

    def bless_animation(self, event=None):
        self.physics.apply_impulse(2.0)

    def on_close(self, event=None):
        self.running = False
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    def check_arrow_hotkeys(self, cursor_in_window: bool):
        if not self.platform.is_windows:
            return

        is_focused = (self.root.focus_get() is not None)
        if not (cursor_in_window or is_focused):
            self.last_vk_left = False
            self.last_vk_right = False
            return

        try:
            import ctypes
            left_down = (ctypes.windll.user32.GetAsyncKeyState(0x25) & 0x8000) != 0
            right_down = (ctypes.windll.user32.GetAsyncKeyState(0x27) & 0x8000) != 0

            if left_down and not self.last_vk_left:
                self.cycle_charm(-1)
            if right_down and not self.last_vk_right:
                self.cycle_charm(1)

            self.last_vk_left = left_down
            self.last_vk_right = right_down
        except Exception:
            pass

    def update_loop(self):
        if not self.running:
            return

        current_time = time.time()
        dt = min(max(current_time - self.last_frame_time, 0.001), 0.05)
        self.last_frame_time = current_time

        # Track cursor
        screen_x, screen_y = self.platform.get_cursor_pos()
        win_x = self.root.winfo_x()
        win_y = self.root.winfo_y()
        local_x = float(screen_x - win_x)
        local_y = float(screen_y - win_y)

        cursor_vx = (local_x - self.last_cursor_x) / dt
        cursor_vy = (local_y - self.last_cursor_y) / dt
        self.last_cursor_x = local_x
        self.last_cursor_y = local_y

        cursor_in_window = (0 <= local_x <= self.config.window_width and 0 <= local_y <= self.config.window_height)

        # Check Left and Right arrow hotkeys
        self.check_arrow_hotkeys(cursor_in_window)

        # Handle window reposition sliding along screen top
        if self.sliding_window:
            if not self.platform.is_left_button_down():
                self.sliding_window = False
                self.canvas.config(cursor="")
            else:
                screen_width = self.root.winfo_screenwidth()
                dx = screen_x - self.slide_start_cursor_x
                new_win_x = max(0, min(screen_width - self.config.window_width, self.slide_start_win_x + dx))
                delta_x = new_win_x - win_x
                if delta_x != 0:
                    self.root.geometry(f"{self.config.window_width}x{self.config.window_height}+{int(new_win_x)}+0")
                    for p in self.physics.pos[1:]:
                        p[0] -= delta_x * 0.40

        # Safety check: if drag mouse released outside window
        if self.physics.dragging and not self.platform.is_left_button_down():
            self.physics.end_drag(dt)

        # Dynamic cursor styling on hover
        is_over_top_bracket = self.is_in_top_bracket(local_x, local_y)
        if is_over_top_bracket and not self.physics.dragging and not self.sliding_window:
            self.canvas.config(cursor="sb_h_double_arrow")
        elif not self.sliding_window:
            self.canvas.config(cursor="")

        in_interactive_zone = (
            self.sliding_window
            or self.physics.dragging
            or (cursor_in_window and self.is_in_interactive_zone(local_x, local_y))
        )

        if in_interactive_zone:
            self.platform.set_clickthrough(False)
        else:
            self.platform.set_clickthrough(True)

        if self.physics.dragging:
            self.physics.update_drag(local_x, local_y, cursor_vx, cursor_vy)
        elif cursor_in_window and not self.sliding_window:
            self.physics.apply_hover_bend(local_x, local_y, cursor_vx, cursor_vy, dt, self.renderer.charm_height)

        self.physics.update_physics(dt)

        show_badge = (time.time() < self.badge_expire_time)
        short_name = self.renderer.current_charm_label.split(" (")[0]
        badge_label = f"{short_name} [{self.current_charm_idx + 1}/{len(CHARM_CATALOG)}]"

        angle = self.physics.get_bottom_tangent_angle()
        self.renderer.draw(self.physics.pos, angle, show_badge=show_badge, badge_label=badge_label)

        frame_delay = int(1000 / self.config.target_fps)
        elapsed_ms = int((time.time() - current_time) * 1000)
        actual_delay = max(1, frame_delay - elapsed_ms)
        self.root.after(actual_delay, self.update_loop)

    def run(self):
        self.platform.set_clickthrough(False)
        self.update_loop()
        self.root.mainloop()


def main():
    app = DesktopDangleApp()
    app.run()


if __name__ == "__main__":
    main()
