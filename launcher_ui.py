import os
import signal
import subprocess
import sys
import time
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, PhotoImage
from pathlib import Path
from urllib.request import urlopen
import json
import math

from config import config

IS_FROZEN = getattr(sys, "frozen", False)
BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

# 供需要半透明效果的颜色与深色背景混合，返回 #RRGGBB
DEFAULT_BG = "#0a0b14"

def blend_color(fg_hex: str, opacity: float, bg_hex: str = DEFAULT_BG) -> str:
    fg_hex = fg_hex.lstrip('#')
    bg_hex = bg_hex.lstrip('#')
    fr, fg, fb = int(fg_hex[0:2], 16), int(fg_hex[2:4], 16), int(fg_hex[4:6], 16)
    br, bg, bb = int(bg_hex[0:2], 16), int(bg_hex[2:4], 16), int(bg_hex[4:6], 16)
    r = int(fr * opacity + br * (1 - opacity))
    g = int(fg * opacity + bg * (1 - opacity))
    b = int(fb * opacity + bb * (1 - opacity))
    return f"#{r:02x}{g:02x}{b:02x}"


# 启动命令：打包后 sys.executable 即为当前 exe
APP_CMD = [sys.executable, "--run-server"] if IS_FROZEN else [sys.executable, __file__, "--run-server"]

# 在这里填写或通过环境变量提供腾讯云密钥
TENCENTCLOUD_SECRET_ID = os.getenv("TENCENTCLOUD_SECRET_ID", "AKID1veibWPEB2gAUbWFn8GC6ufFdyOcs46v")
TENCENTCLOUD_SECRET_KEY = os.getenv("TENCENTCLOUD_SECRET_KEY", "f8OVVMBtTq0oaEj8LNFwRq357ze8PTKz")

APP_URL = f"http://127.0.0.1:{config.PORT}/"
ICON_CANDIDATES = [
    BASE_DIR / "static" / "icon.png",
    BASE_DIR / "static" / "icon.ico",
    ]


class AnimatedBackground:
    def __init__(self, canvas, width, height):
        self.canvas = canvas
        self.width = width
        self.height = height
        self.particles = []
        self.connections = []
        self.grid_size = 50
        self.grid_points = []
        self.pulse_value = 0
        self.pulse_direction = 1

        # 创建网格点
        for x in range(0, width + self.grid_size, self.grid_size):
            for y in range(0, height + self.grid_size, self.grid_size):
                self.grid_points.append((x, y))

        # 创建粒子
        for _ in range(15):
            x = width * 0.2 + width * 0.6 * (hash(str(_)) % 100) / 100
            y = height * 0.2 + height * 0.6 * (hash(str(_ + 1)) % 100) / 100
            vx = (hash(str(_)) % 100 - 50) / 100
            vy = (hash(str(_ + 2)) % 100 - 50) / 100
            size = 2 + (hash(str(_)) % 100) / 100 * 3
            self.particles.append({
                'x': x, 'y': y, 'vx': vx, 'vy': vy,
                'size': size, 'color': '#2e8bff' if _ % 3 == 0 else '#ff5f52' if _ % 3 == 1 else '#00d4aa'
            })

        self.animate()

    def animate(self):
        # 更新脉冲效果
        self.pulse_value += 0.05 * self.pulse_direction
        if self.pulse_value > 1 or self.pulse_value < 0:
            self.pulse_direction *= -1

        # 清除之前的绘制
        self.canvas.delete("animated")

        # 绘制连接线
        for i, (x1, y1) in enumerate(self.grid_points):
            for (x2, y2) in self.grid_points[i+1:]:
                dist = math.sqrt((x2-x1)**2 + (y2-y1)**2)
                if dist < 100:
                    opacity = 0.1 * (1 - dist/100)
                    self.canvas.create_line(
                        x1, y1, x2, y2,
                        fill=self._color_with_opacity('#2e8bff', opacity),
                        width=1, tags="animated"
                    )

        # 更新和绘制粒子
        for p in self.particles:
            # 更新位置
            p['x'] += p['vx']
            p['y'] += p['vy']

            # 边界碰撞
            if p['x'] < 20 or p['x'] > self.width - 20:
                p['vx'] *= -1
            if p['y'] < 20 or p['y'] > self.height - 20:
                p['vy'] *= -1

            # 绘制粒子
            size = p['size'] + math.sin(time.time() * 2) * 0.5
            glow_size = size * 3

            # 粒子光晕
            self.canvas.create_oval(
                p['x'] - glow_size, p['y'] - glow_size,
                p['x'] + glow_size, p['y'] + glow_size,
                fill=self._color_with_opacity(p['color'], 0.2),
                outline="", tags="animated"
            )

            # 粒子核心
            self.canvas.create_oval(
                p['x'] - size, p['y'] - size,
                p['x'] + size, p['y'] + size,
                fill=p['color'], outline="", tags="animated"
            )

            # 从粒子到附近网格点的连接线
            for x, y in self.grid_points:
                dist = math.sqrt((x - p['x'])**2 + (y - p['y'])**2)
                if dist < 80:
                    opacity = 0.15 * (1 - dist/80) * (0.8 + 0.2 * math.sin(time.time()))
                    self.canvas.create_line(
                        p['x'], p['y'], x, y,
                        fill=self._color_with_opacity(p['color'], opacity),
                        width=1, tags="animated"
                    )

        # 绘制中心光环（脉冲效果）
        center_x, center_y = self.width/2, self.height/2
        for i in range(3):
            radius = 120 + i * 40 + self.pulse_value * 20
            opacity = 0.1 - i * 0.02
            self.canvas.create_oval(
                center_x - radius, center_y - radius,
                center_x + radius, center_y + radius,
                outline=self._color_with_opacity('#00d4aa', opacity),
                width=2, tags="animated"
            )

        # 继续动画
        self.canvas.after(30, self.animate)

    def _color_with_opacity(self, color, opacity):
        """将颜色转换为与背景混合后的不透明颜色，避免 Tk 对 #AARRGGBB 报错"""
        return blend_color(color, opacity, DEFAULT_BG)


class GlowingButton(tk.Canvas):
    def __init__(self, parent, text, color, command, **kwargs):
        super().__init__(parent, highlightthickness=0, **kwargs)
        self.text = text
        self.color = color
        self.command = command
        self.is_hovered = False
        self.glow_intensity = 0

        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_click)

        self.animate_glow()

    def on_enter(self, event):
        self.is_hovered = True

    def on_leave(self, event):
        self.is_hovered = False

    def on_click(self, event):
        self.command()

    def animate_glow(self):
        if self.is_hovered:
            self.glow_intensity = min(1, self.glow_intensity + 0.1)
        else:
            self.glow_intensity = max(0, self.glow_intensity - 0.1)

        self.draw_button()
        self.after(20, self.animate_glow)

    def draw_button(self):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()

        if width <= 1 or height <= 1:
            return

        # 按钮背景
        self.create_rectangle(2, 2, width-2, height-2,
                              fill=self.color, outline="", tags="button")

        # 发光效果
        if self.glow_intensity > 0:
            glow_size = 10 * self.glow_intensity
            self.create_rectangle(2-glow_size, 2-glow_size,
                                  width-2+glow_size, height-2+glow_size,
                                  fill=self._color_with_opacity(self.color, 0.3 * self.glow_intensity),
                                  outline="", tags="button")

        # 按钮文字
        self.create_text(width/2, height/2,
                         text=self.text,
                         fill=self._text_color(),
                         font=("Segoe UI", 11, "bold"),
                         tags="button")

    def _color_with_opacity(self, color, opacity):
        """Blend with parent background to avoid unsupported alpha colors in Tk."""
        bg = DEFAULT_BG
        try:
            bg = self.master.cget("bg") or bg
        except Exception:
            pass
        return blend_color(color, opacity, bg)

    def _text_color(self):
        r = int(self.color[1:3], 16)
        g = int(self.color[3:5], 16)
        b = int(self.color[5:7], 16)
        luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return "#0b1220" if luminance > 150 else "#f8fbff"


class Launcher:
    def __init__(self, root):
        self.root = root
        self.proc = None

        # 窗口设置
        root.title("智能文本翻译助手")
        root.geometry("600x400")
        root.resizable(False, False)
        root.configure(bg="#0a0b14")

        self._set_icon(root)

        # 创建动画背景
        self.canvas = tk.Canvas(root, width=600, height=400, highlightthickness=0, bg="#0a0b14")
        self.canvas.place(x=0, y=0)

        # 初始化动画背景
        self.bg_animation = AnimatedBackground(self.canvas, 600, 400)

        # 创建主卡片（玻璃拟态效果）
        card = tk.Frame(root, bg="#111722", bd=0, relief="ridge")
        card.place(relx=0.5, rely=0.5, anchor="center", width=500, height=280)

        # 添加模糊背景效果
        self.canvas.create_rectangle(50, 60, 550, 340,
                                     fill=blend_color("#111722", 0.6), outline=blend_color("#2e8bff", 0.13), width=1)

        # 标题
        title = tk.Label(card, text="智能文本翻译助手",
                         fg="#e8f0ff", bg="#111722",
                         font=("Segoe UI", 20, "bold"))
        title.pack(pady=(25, 5))

        # 副标题
        subtitle = tk.Label(card, text="· AI 智能翻译 · 多语言支持 · 实时处理 ·",
                            fg="#8aa2c4", bg="#111722",
                            font=("Segoe UI", 10))
        subtitle.pack(pady=(0, 20))

        # 按钮容器
        btn_container = tk.Frame(card, bg="#111722")
        btn_container.pack(pady=10)

        # 启动按钮
        self.start_btn_canvas = GlowingButton(
            btn_container, "🚀 启动服务", "#2e8bff",
            self.start_app,
            width=150, height=45
        )
        self.start_btn_canvas.grid(row=0, column=0, padx=15, pady=5)

        # 退出按钮
        self.stop_btn_canvas = GlowingButton(
            btn_container, "⏻ 退出应用", "#ff5f52",
            self.exit_all,
            width=150, height=45
        )
        self.stop_btn_canvas.grid(row=0, column=1, padx=15, pady=5)

        # 状态显示区域
        status_frame = tk.Frame(card, bg="#1a2332", bd=0, relief="flat")
        status_frame.pack(pady=(15, 0), padx=40, fill="x")

        # 状态图标和文字
        self.status_canvas = tk.Canvas(status_frame, width=30, height=30,
                                       bg="#1a2332", highlightthickness=0)
        self.status_canvas.pack(side="left", padx=(10, 5))
        self.status_circle = self.status_canvas.create_oval(5, 5, 25, 25,
                                                            fill="#ff5f52", outline="")

        self.status_var = tk.StringVar(value="服务未启动")
        self.status_label = tk.Label(status_frame,
                                     textvariable=self.status_var,
                                     fg="#8aa2c4", bg="#1a2332",
                                     font=("Segoe UI", 10))
        self.status_label.pack(side="left", padx=5)

        # 底部信息
        info_label = tk.Label(card,
                              text="网络2301 杨霄宇 胡宇煊制作",
                              fg="#4a5a7a", bg="#111722",
                              font=("Segoe UI", 8))
        info_label.pack(side="bottom", pady=10)

        # 绑定窗口关闭事件
        root.protocol("WM_DELETE_WINDOW", self.exit_all)

        # 初始化状态动画
        self.status_animation()

    def _set_icon(self, root):
        for path in ICON_CANDIDATES:
            if path.exists():
                try:
                    if path.suffix.lower() == ".ico":
                        root.iconbitmap(path)
                    else:
                        icon_img = PhotoImage(file=path)
                        root.iconphoto(False, icon_img)
                    break
                except Exception:
                    continue

    def _ffmpeg_env(self):
        env = os.environ.copy()
        ffmpeg_dir = BASE_DIR / "ffmpeg" / "bin"
        ffmpeg_exe = ffmpeg_dir / "ffmpeg.exe"
        ffprobe_exe = ffmpeg_dir / "ffprobe.exe"
        if ffmpeg_exe.exists():
            env.setdefault("FFMPEG_BIN", str(ffmpeg_exe))
        if ffprobe_exe.exists():
            env.setdefault("FFPROBE_BIN", str(ffprobe_exe))
        return env

    def status_animation(self):
        """状态指示灯的呼吸灯效果"""
        current_color = self.status_canvas.itemcget(self.status_circle, "fill")
        if current_color == "#ff5f52":  # 红色
            new_color = "#ff7b73"
        elif current_color == "#ff7b73":  # 亮红
            new_color = "#ff5f52"
        elif current_color == "#00d4aa":  # 绿色
            new_color = "#2effd4"
        elif current_color == "#2effd4":  # 亮绿
            new_color = "#00d4aa"
        else:
            new_color = current_color

        self.status_canvas.itemconfig(self.status_circle, fill=new_color)
        self.root.after(800, self.status_animation)

    def _update_status(self, text, color="#00d4aa"):
        self.status_var.set(text)
        self.status_canvas.itemconfig(self.status_circle, fill=color)
        self.root.update_idletasks()

    def _wait_and_open(self):
        url = APP_URL
        for _ in range(30):
            try:
                urlopen(url, timeout=1)
                webbrowser.open(url)
                self._update_status("✓ 服务运行中，已打开浏览器", "#00d4aa")
                self.start_btn_canvas.config(state="disabled")
                return
            except Exception:
                time.sleep(1)
        messagebox.showerror("错误", "服务启动超时，请稍后重试")
        self._update_status("✗ 服务启动失败", "#ff5f52")
        self.start_btn_canvas.config(state="normal")

    def start_app(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showinfo("提示", "服务已在运行中")
            return
        env = self._ffmpeg_env()
        if TENCENTCLOUD_SECRET_ID:
            env["TENCENTCLOUD_SECRET_ID"] = TENCENTCLOUD_SECRET_ID
        if TENCENTCLOUD_SECRET_KEY:
            env["TENCENTCLOUD_SECRET_KEY"] = TENCENTCLOUD_SECRET_KEY
        try:
            self._update_status("⏳ 正在启动服务...", "#2e8bff")
            self.start_btn_canvas.config(state="disabled")
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            self.proc = subprocess.Popen(APP_CMD, env=env, cwd=BASE_DIR, creationflags=creation_flags)
            threading.Thread(target=self._wait_and_open, daemon=True).start()
        except Exception as exc:
            self.start_btn_canvas.config(state="normal")
            self._update_status("✗ 启动失败", "#ff5f52")
            messagebox.showerror("错误", f"启动失败: {exc}")

    def exit_all(self):
        if self.proc and self.proc.poll() is None:
            try:
                self._update_status("正在关闭服务...", "#ffa500")
                if os.name == "nt":
                    try:
                        self.proc.send_signal(signal.CTRL_BREAK_EVENT)
                    except Exception:
                        self.proc.terminate()
                else:
                    self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                    self.proc.wait(timeout=3)
                except Exception:
                    pass
            finally:
                self.proc = None
        self.root.destroy()
        os._exit(0)


def main():
    # 服务器运行模式（避免再次弹出 GUI）
    if "--run-server" in sys.argv:
        os.chdir(BASE_DIR)
        from config import config
        from app import create_app

        app = create_app()
        app.run(host=config.HOST, port=config.PORT, debug=False, use_reloader=False)
        return

    # GUI 启动器模式
    root = tk.Tk()
    Launcher(root)
    root.mainloop()


if __name__ == "__main__":
    main()

