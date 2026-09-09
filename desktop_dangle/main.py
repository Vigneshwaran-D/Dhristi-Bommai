import sys
import platform
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import tkinter as tk
from tkinter import Canvas
from PIL import Image, ImageTk, ImageOps


@dataclass
class Config:
    charm_size: int = 80
    rope_length: int = 65
    gravity: float = 9.8
    damping: float = 0.992
    sensitivity: float = 0.008
    window_width: int = 280
    window_height: int = 500
    target_fps: int = 60
    margin_right: int = 120


@dataclass
class PhysicsState:
    angle: float = 0.0
    angular_velocity: float = 0.0
    dragging: bool = False
    last_mouse_x: int = 0
    last_mouse_y: int = 0
    last_mouse_time: float = 0.0
    mouse_velocity_x: float = 0.0
    mouse_velocity_y: float = 0.0


class PlatformAdapter:
    def __init__(self, root: tk.Tk, window_width: int, window_height: int):
        self.root = root
        self.window_width = window_width
        self.window_height = window_height
        self.is_windows = platform.system() == "Windows"
        self.is_macos = platform.system() == "Darwin"
        self.setup_window()

    def setup_window(self):
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)

        if self.is_windows:
            self.root.attributes("-transparentcolor", "white")
            self._setup_windows()
        elif self.is_macos:
            self.root.attributes("-transparent", True)
            self.root.attributes("-alpha", 1.0)
            self._setup_macos()

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = screen_width - self.window_width - 20
        y = 0
        self.root.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

    def _setup_windows(self):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            WS_EX_TOPMOST = 0x00000008

            ex_style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            ex_style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex_style)

            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0xFFFFFF, 255, 0x00000001)
        except Exception as e:
            print(f"Windows setup warning: {e}")

    def _setup_macos(self):
        try:
            self.root.wm_attributes("-transparent", True)
        except Exception as e:
            print(f"macOS setup warning: {e}")

    def set_clickthrough(self, enabled: bool):
        if self.is_windows:
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
            except Exception as e:
                print(f"Click-through toggle warning: {e}")


class CharmRenderer:
    def __init__(self, canvas: Canvas, config: Config):
        self.canvas = canvas
        self.config = config
        self.charm_image: Optional[ImageTk.PhotoImage] = None
        self.charm_id: Optional[int] = None
        self.rope_id: Optional[int] = None
        self.rope_segments: list = []
        self.visible = True
        self.charm_width = self.config.charm_size
        self.charm_height = self.config.charm_size
        self.load_charm()

    def load_charm(self):
        try:
            app_dir = Path(__file__).resolve().parent
            asset_dirs = (app_dir.parent / "assets", app_dir / "assets")
            asset_dir = next((path for path in asset_dirs if path.exists()), None)
            if asset_dir is None:
                raise FileNotFoundError("Could not find an assets folder")

            chili_width = 175
            chili_images = []
            for index in range(1, 8):
                chili_path = asset_dir / f"nimbu-chili-{index}.png"
                chili = Image.open(chili_path).convert("RGBA")
                scale = chili_width / chili.width
                chili = chili.resize(
                    (chili_width, max(1, round(chili.height * scale))),
                    Image.Resampling.LANCZOS,
                )
                chili_images.append(chili)

            lemon = Image.open(asset_dir / "nimbu-lemon.png").convert("RGBA")
            lemon = ImageOps.contain(lemon, (150, 170), method=Image.Resampling.LANCZOS)
            coal = Image.open(asset_dir / "nimbu-coal.png").convert("RGBA")
            coal = ImageOps.contain(coal, (72, 72), method=Image.Resampling.LANCZOS)

            chili_overlap = 8
            chili_height = sum(image.height for image in chili_images)
            chili_height -= chili_overlap * (len(chili_images) - 1)
            image_width = max(chili_width, lemon.width, coal.width)
            image_height = chili_height + lemon.height + coal.height
            img = Image.new("RGBA", (image_width, image_height), (0, 0, 0, 0))

            y = 0
            for chili in chili_images:
                x = (image_width - chili.width) // 2
                img.alpha_composite(chili, (x, y))
                y += chili.height - chili_overlap

            img.alpha_composite(lemon, ((image_width - lemon.width) // 2, y))
            y += lemon.height
            img.alpha_composite(coal, ((image_width - coal.width) // 2, y))

            self.charm_width, self.charm_height = img.size
            self.charm_image = ImageTk.PhotoImage(img)
        except Exception as e:
            print(f"Failed to load charm image: {e}")
            self.charm_image = None

    def get_rope_points(self, anchor_x: float, anchor_y: float, charm_x: float, charm_y: float, angle: float):
        num_segments = 20
        points = [anchor_x, anchor_y]

        for i in range(1, num_segments):
            t = i / num_segments
            seg_x = anchor_x + math.sin(angle) * self.config.rope_length * t
            seg_y = anchor_y + math.cos(angle) * self.config.rope_length * t
            points.extend([seg_x, seg_y])

        points.extend([charm_x, charm_y])
        return points

    def draw_rope(self, anchor_x: float, anchor_y: float, charm_x: float, charm_y: float, angle: float):
        self.canvas.delete("rope")
        points = self.get_rope_points(anchor_x, anchor_y, charm_x, charm_y, angle)

        self.rope_id = self.canvas.create_line(
            *points,
            fill="#6B5B4A", width=3, capstyle=tk.ROUND, tags="rope"
        )

    def draw(self, anchor_x: float, anchor_y: float, charm_x: float, charm_y: float, angle: float):
        self.canvas.delete("all")

        if not self.visible:
            return

        self.draw_rope(anchor_x, anchor_y, charm_x, charm_y, angle)

        if self.charm_image:
            self.charm_id = self.canvas.create_image(
                int(charm_x), int(charm_y),
                image=self.charm_image, anchor=tk.N
            )

    def set_visible(self, visible: bool):
        self.visible = visible
        if not visible:
            self.canvas.delete("all")


class PhysicsEngine:
    def __init__(self, config: Config):
        self.config = config
        self.state = PhysicsState()
        self.anchor_x = 0.0
        self.anchor_y = 0.0
        self.charm_x = 0.0
        self.charm_y = 0.0
        self.last_update_time = time.time()
        self.drag_offset_x = 0.0
        self.drag_offset_y = 0.0

    def set_anchor(self, x: float, y: float):
        self.anchor_x = x
        self.anchor_y = y

    def get_charm_position(self) -> Tuple[float, float]:
        self.charm_x = self.anchor_x + math.sin(self.state.angle) * self.config.rope_length
        self.charm_y = self.anchor_y + math.cos(self.state.angle) * self.config.rope_length
        return self.charm_x, self.charm_y

    def update_physics(self, dt: float):
        if self.state.dragging:
            return

        g = self.config.gravity
        L = self.config.rope_length

        angular_acceleration = -(g / L) * math.sin(self.state.angle)
        self.state.angular_velocity += angular_acceleration * dt
        self.state.angular_velocity *= self.config.damping
        self.state.angle += self.state.angular_velocity * dt

        max_angle = math.pi / 2
        if self.state.angle > max_angle:
            self.state.angle = max_angle
            self.state.angular_velocity *= -0.3
        elif self.state.angle < -max_angle:
            self.state.angle = -max_angle
            self.state.angular_velocity *= -0.3

        idle_threshold = 0.0005
        if abs(self.state.angle) < idle_threshold and abs(self.state.angular_velocity) < idle_threshold:
            self.state.angle = 0.0
            self.state.angular_velocity = 0.0

    def start_drag(self, mouse_x: int, mouse_y: int):
        self.state.dragging = True
        self.state.last_mouse_x = mouse_x
        self.state.last_mouse_y = mouse_y
        self.state.last_mouse_time = time.time()
        self.state.mouse_velocity_x = 0.0
        self.state.mouse_velocity_y = 0.0
        self.drag_offset_x = mouse_x - self.charm_x
        self.drag_offset_y = mouse_y - self.charm_y

    def update_drag(self, mouse_x: int, mouse_y: int):
        if not self.state.dragging:
            return

        current_time = time.time()
        dt = current_time - self.state.last_mouse_time
        if dt > 0:
            dx = mouse_x - self.state.last_mouse_x
            dy = mouse_y - self.state.last_mouse_y
            self.state.mouse_velocity_x = dx / dt
            self.state.mouse_velocity_y = dy / dt

        self.state.last_mouse_x = mouse_x
        self.state.last_mouse_y = mouse_y
        self.state.last_mouse_time = current_time

        target_x = mouse_x - self.drag_offset_x
        target_y = mouse_y - self.drag_offset_y
        rel_x = target_x - self.anchor_x
        rel_y = target_y - self.anchor_y
        distance = math.hypot(rel_x, rel_y)

        if distance > 0:
            target_angle = math.atan2(rel_x, rel_y)
            max_angle = math.pi / 2 - 0.1
            target_angle = max(-max_angle, min(max_angle, target_angle))
            self.state.angle = target_angle

    def end_drag(self):
        if not self.state.dragging:
            return

        self.state.dragging = False
        tangent_x = math.cos(self.state.angle)
        tangent_y = -math.sin(self.state.angle)
        tangential_velocity = (
            self.state.mouse_velocity_x * tangent_x
            + self.state.mouse_velocity_y * tangent_y
        )
        self.state.angular_velocity = tangential_velocity / self.config.rope_length

    def is_point_near_rope(self, mouse_x: float, mouse_y: float, tolerance: float = 12.0):
        end_x, end_y = self.get_charm_position()
        start_x, start_y = self.anchor_x, self.anchor_y
        segment_x = end_x - start_x
        segment_y = end_y - start_y
        segment_length_squared = segment_x * segment_x + segment_y * segment_y
        if segment_length_squared == 0:
            return False

        projection = ((mouse_x - start_x) * segment_x + (mouse_y - start_y) * segment_y) / segment_length_squared
        projection = max(0.0, min(1.0, projection))
        closest_x = start_x + projection * segment_x
        closest_y = start_y + projection * segment_y
        return math.hypot(mouse_x - closest_x, mouse_y - closest_y) <= tolerance

    def apply_impulse(self, velocity: float):
        self.state.angular_velocity += velocity * self.config.sensitivity


class DesktopDangleApp:
    def __init__(self):
        self.config = Config()
        self.root = tk.Tk()
        self.root.title("Desktop Dangle")

        self.platform = PlatformAdapter(self.root, self.config.window_width, self.config.window_height)

        bg_color = "white" if platform.system() == "Windows" else "systemTransparent"
        self.canvas = Canvas(
            self.root,
            width=self.config.window_width,
            height=self.config.window_height,
            highlightthickness=0,
            bg=bg_color
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.renderer = CharmRenderer(self.canvas, self.config)
        self.physics = PhysicsEngine(self.config)

        self.anchor_x = self.config.window_width / 2
        self.anchor_y = 0
        self.physics.set_anchor(self.anchor_x, self.anchor_y)

        self.setup_bindings()
        self.running = True
        self.last_frame_time = time.time()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def setup_bindings(self):
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        self.root.bind("<Key-h>", self.toggle_visibility)
        self.root.bind("<Key-H>", self.toggle_visibility)
        self.root.bind("<Key-r>", self.reset_position)
        self.root.bind("<Key-R>", self.reset_position)
        self.root.bind("<Escape>", self.on_close)
        self.root.bind("<space>", self.bless_animation)

        self.root.focus_set()

    def on_mouse_down(self, event):
        charm_x, charm_y = self.physics.get_charm_position()
        object_left = charm_x - self.renderer.charm_width / 2
        object_right = charm_x + self.renderer.charm_width / 2
        object_bottom = charm_y + self.renderer.charm_height
        on_object = object_left <= event.x <= object_right and charm_y <= event.y <= object_bottom

        if on_object or self.physics.is_point_near_rope(event.x, event.y):
            self.physics.start_drag(event.x, event.y)
            self.platform.set_clickthrough(False)

    def on_mouse_drag(self, event):
        self.physics.update_drag(event.x, event.y)

    def on_mouse_up(self, event):
        if self.physics.state.dragging:
            self.physics.end_drag()
            self.platform.set_clickthrough(False)

    def toggle_visibility(self, event=None):
        self.renderer.set_visible(not self.renderer.visible)

    def reset_position(self, event=None):
        self.physics.state.angle = 0.0
        self.physics.state.angular_velocity = 0.0
        self.physics.state.dragging = False

    def bless_animation(self, event=None):
        self.physics.apply_impulse(1.5)

    def on_close(self, event=None):
        self.running = False
        self.root.quit()
        self.root.destroy()

    def update_loop(self):
        if not self.running:
            return

        current_time = time.time()
        dt = min(current_time - self.last_frame_time, 1.0 / 30.0)
        self.last_frame_time = current_time

        self.physics.update_physics(dt)
        charm_x, charm_y = self.physics.get_charm_position()
        self.renderer.draw(self.anchor_x, self.anchor_y, charm_x, charm_y, self.physics.state.angle)

        frame_delay = int(1000 / self.config.target_fps)
        actual_delay = max(1, frame_delay - int((time.time() - current_time) * 1000))
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