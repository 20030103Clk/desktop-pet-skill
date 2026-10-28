# -*- coding: utf-8 -*-
"""桌面宠物程序
功能：
- 透明、无边框、始终置顶
- 鼠标左键拖动位置；单击触发互动动画（跳跃/压扁回弹/左右抖动，轮流触发）
- 互动时随机显示中文对话白气泡（背景不透明、置于角色上方不遮挡）
- 右键菜单：调整大小 / 置顶开关 / 退出程序
- 鼠标滚轮调整大小
- 定时随机在屏幕上乱跑，奔跑时带流星拖尾特效
- 打包为 exe 后双击即可运行
"""
import os
import sys
import random
import math
import time
import collections

import tkinter as tk

from PIL import Image, ImageTk

# 关键色：窗口内此颜色将被置为透明（Windows transparentcolor）
KEY = "#FF00FE"
KEY_RGB = (255, 0, 254)
ALPHA_CUT = 128          # alpha 低于此值的像素视为透明
BUBBLE_HIDE_MS = 2600    # 气泡显示时长

BASE_HEIGHT = 175        # 初始显示高度(px)
MIN_HEIGHT = 90
MAX_HEIGHT = 500

TRAIL_MARGIN = 90        # 拖尾留在角色周围的边距(px)，同时为跳跃留出头顶空间
TRAIL_R0_RATIO = 0.11    # 拖尾最大半径 = 角色高度 * 此比例
TRAIL_HISTORY = 42       # 记录的运动轨迹点数
TRAIL_COLORS = ["#FF5A1F", "#FF7A26", "#FF943A", "#FFAD54", "#FFC470",
                "#FFD98F", "#FFE9B8", "#FFF3D6", "#FFFAEC", "#FFFDF7"]

WANDER_MIN_DELAY = 4000  # 乱跑间隔下限(ms)
WANDER_MAX_DELAY = 10000 # 乱跑间隔上限(ms)
WANDER_SPEED = 300       # 乱跑速度(px/s)
WANDER_FRAME = 28        # 乱跑步进间隔(ms)

BUBBLE_LINES = [
    "点我干嘛呀～",
    "嘿，别戳我！",
    "摸鱼中，勿扰～",
    "今天也要加油鸭！",
    "有零食吗？分我点～",
    "陪我玩会儿嘛～",
    "屏幕看久啦，休息一下～",
    "我跳！我再跳！",
    "弹～弹～弹～",
    "呼，吓我一跳！",
    "充电中…0%",
    "主人你最好啦！",
    "冲鸭——！",
    "溜了溜了～",
]

ANIMATIONS = ["jump", "squash", "shake"]  # 轮流顺序

SLEEP_DELAY = 20000         # 无任何操作多少毫秒后进入睡眠
SLEEP_CHECK_MS = 3000       # 空闲/睡眠检查间隔(ms)
SLEEP_LINES = ["Zzz…", "好困…呼～", "Zzz…💤", "呼噜噜…"]

PARTICLE_COLORS = ["#FF6B81", "#FF8FA3", "#FFD166", "#FFB84D", "#7DE1FF", "#C77DFF"]
PARTICLE_SHAPES = ["♥", "★", "●"]


def resource_path(rel):
    """兼容 PyInstaller 打包后的资源路径。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


class DesktopPet:
    def __init__(self, master):
        self.master = master
        self._stand_img = Image.open(resource_path("stand.png")).convert("RGBA")
        # 睡眠姿势：蜷缩侧躺沙发睡觉
        self._sleep_img = Image.open(resource_path("sleep.png")).convert("RGBA")
        # 跑姿：左跑 run_L.png、右跑 run_R.png，奔跑时两帧交替形成跑步动画
        self._run_poses = [Image.open(resource_path("run_L.png")).convert("RGBA"),
                           Image.open(resource_path("run_R.png")).convert("RGBA")]
        self._run_fidx = 0
        self._cur_img = self._stand_img
        mw, mh = self._stand_img.size
        self.aspect = mw / mh

        # 跑动动画状态
        self._stride_ticks = 5      # 每 N 步切换一次左右腿
        self._bob_amp = 6           # 奔跑时上下颠动幅度(px)

        # 窗口：无边框、置顶、透明关键色
        self.master.overrideredirect(True)
        self.master.attributes("-topmost", True)
        self.master.configure(bg=KEY)
        self.master.wm_attributes("-transparentcolor", KEY)

        # 画布渲染（角色居中，四周留拖尾边距）
        self.canvas = tk.Canvas(self.master, bg=KEY, bd=0, highlightthickness=0)
        self.canvas.pack()

        # 尺寸与位置
        self.h = BASE_HEIGHT
        self.w = int(round(BASE_HEIGHT * self.aspect))
        self.photo = None
        self.char_item = None
        self._apply_size(self.w, self.h)
        self.basex = 0
        self.basey = 0

        # 初始位置：屏幕右下角
        sw = self.master.winfo_screenwidth()
        sh = self.master.winfo_screenheight()
        self.basex = sw - self.ww - 30
        self.basey = sh - self.wh - 50
        self._place()

        # 状态
        self.topmost_on = True
        self.busy = False          # 互动动画进行中
        self.wandering = False     # 正在乱跑
        self.dragging = False
        self._drag = None
        self._anim_seq = 0
        self._history = collections.deque(maxlen=TRAIL_HISTORY)
        self._wander_job = None
        self._wander_step_job = None
        self._fade_job = None
        self._bubble = None
        self._bubble_job = None

        # 睡眠模式
        self._last_activity = time.time()
        self._sleeping = False
        self._sleep_checker_job = None
        self._sleep_tick_job = None

        # 粒子/爱心特效
        self._particles = []
        self._ptc_job = None

        # 事件
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_menu)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.master.bind("<MouseWheel>", self._on_wheel)
        self.master.bind("<Button-3>", self._on_menu)

        # 右键菜单
        self.menu = tk.Menu(self.master, tearoff=0)
        size_menu = tk.Menu(self.menu, tearoff=0)
        size_menu.add_command(label="放大", command=lambda: self.resize_step(1.15))
        size_menu.add_command(label="缩小", command=lambda: self.resize_step(0.87))
        size_menu.add_command(label="恢复默认大小", command=lambda: self.resize_abs(BASE_HEIGHT))
        self.menu.add_cascade(label="调整大小", menu=size_menu)
        self.top_var = tk.BooleanVar(value=True)
        self.menu.add_checkbutton(label="置顶", variable=self.top_var, command=self._toggle_topmost)
        self.menu.add_separator()
        self.menu.add_command(label="退出程序", command=self.master.destroy)

        # 开始定时乱跑 + 睡眠检查
        self._schedule_wander()
        self._start_sleep_checker()

    # ---------- 图像渲染 ----------
    def _keyed_image(self, w=None, h=None, master=None):
        """缩放并做关键色处理：不透明像素保留，透明像素变关键色。"""
        if w is None:
            w = self.cw
        if h is None:
            h = self.ch
        if master is None:
            master = self._cur_img
        img = master.resize((w, h), Image.LANCZOS)
        rgb = img.convert("RGB")
        magenta = Image.new("RGB", (w, h), KEY_RGB)
        mask = img.getchannel("A").point(lambda a: 255 if a >= ALPHA_CUT else 0)
        return Image.composite(rgb, magenta, mask)

    def _update_char_image(self):
        """按当前主图/镜像重建画布上的角色图像。"""
        self.photo = ImageTk.PhotoImage(self._keyed_image(self.cw, self.ch))
        self.canvas.delete("char")
        self.char_item = self.canvas.create_image(
            self.ww // 2, self.wh // 2, image=self.photo, tags=("char",))
        self.canvas.tag_raise("char")

    def _apply_size(self, w, h):
        self.cw, self.ch = int(w), int(h)
        self.ww, self.wh = self.cw + 2 * TRAIL_MARGIN, self.ch + 2 * TRAIL_MARGIN
        self.canvas.config(width=self.ww, height=self.wh)
        self.canvas.delete("all")
        if getattr(self, "_ptc_job", None):
            self.master.after_cancel(self._ptc_job)
            self._ptc_job = None
        self._particles = []
        self._update_char_image()
        self.master.geometry(f"{self.ww}x{self.wh}")

    def _place(self):
        self.master.geometry(f"{self.ww}x{self.wh}+{int(self.basex)}+{int(self.basey)}")

    def _center(self):
        return (self.basex + self.ww / 2.0, self.basey + self.wh / 2.0)

    # ---------- 拖动 / 点击 ----------
    def _on_press(self, e):
        self._note_interaction()
        self.dragging = True
        self._drag = (e.x_root, e.y_root, e.x, e.y)

    def _on_drag(self, e):
        if not self._drag:
            return
        sx, sy, ox, oy = self._drag
        self.basex = e.x_root - ox
        self.basey = e.y_root - oy
        self._place()

    def _on_release(self, e):
        if not self._drag:
            return
        sx, sy, ox, oy = self._drag
        self._drag = None
        self.dragging = False
        if abs(e.x_root - sx) < 5 and abs(e.y_root - sy) < 5:
            self._stop_wander()
            self._trigger_interaction()

    # ---------- 右键菜单 ----------
    def _on_menu(self, e):
        self.menu.tk_popup(e.x_root, e.y_root)

    def _toggle_topmost(self):
        self.topmost_on = self.top_var.get()
        self.master.attributes("-topmost", self.topmost_on)

    # ---------- 滚轮 / 尺寸 ----------
    def _on_wheel(self, e):
        if self.busy or self.wandering:
            return
        self._note_interaction()
        self.resize_step(1.1 if e.delta > 0 else 0.9)

    def resize_step(self, factor):
        self.resize_abs(self.h * factor)

    def resize_abs(self, new_h):
        new_h = max(MIN_HEIGHT, min(MAX_HEIGHT, int(new_h)))
        if abs(new_h - self.h) < 3:
            return
        cx, cy = self._center()
        self._apply_size(int(round(new_h * self.aspect)), new_h)
        self.basex = cx - self.ww / 2.0
        self.basey = cy - self.wh / 2.0
        self._place()

    # ---------- 互动动画 ----------
    def _trigger_interaction(self):
        if self.busy:
            return
        name = ANIMATIONS[self._anim_seq % len(ANIMATIONS)]
        self._anim_seq += 1
        self._show_bubble(random.choice(BUBBLE_LINES))
        self._spawn_particles(12)
        getattr(self, "_anim_" + name)()

    def _run_frames(self, frames):
        """播放一帧帧动画，全部在固定窗口内完成（缩放/位移角色图），绝不移动窗口，
        避免透明窗口被 relocate 时闪现黑色大框。frames 每项 (offx, offy, sw, sh)。"""
        self.busy = True
        i = [0]

        def step():
            if i[0] >= len(frames):
                self.busy = False
                self._restore_normal()
                return
            offx, offy, sw, sh = frames[i[0]]
            i[0] += 1
            ncw = max(1, int(self.cw * sw))
            nch = max(1, int(self.ch * sh))
            self.photo = ImageTk.PhotoImage(self._keyed_image(ncw, nch))
            self.canvas.itemconfig(self.char_item, image=self.photo)
            self.canvas.coords(self.char_item, self.ww // 2 + offx, self.wh // 2 + offy)
            self.canvas.tag_raise("char")
            self.master.after(25, step)

        step()

    def _restore_normal(self):
        self._cur_img = self._stand_img
        self._update_char_image()
        self._place()

    def _anim_jump(self):
        n = 22
        frames = []
        for i in range(n):
            t = i / (n - 1)
            offy = -int(78 * 4 * t * (1 - t))
            frames.append((0, offy, 1, 1))
        self._run_frames(frames)

    def _anim_shake(self):
        amps = [12, -12, 10, -10, 8, -7, 5, -4, 2, 0]
        frames = [(a, 0, 1, 1) for a in amps]
        self._run_frames(frames)

    def _anim_squash(self):
        frames = [
            (0, 4, 1.14, 0.82),
            (0, 1, 1.10, 0.87),
            (0, -8, 1.0, 1.0),
            (0, -6, 1.0, 1.0),
            (0, 0, 1.0, 1.0),
        ]
        self._run_frames(frames)

    # ---------- 定时乱跑 + 拖尾 ----------
    def _schedule_wander(self):
        if self._sleeping:
            return
        delay = random.randint(WANDER_MIN_DELAY, WANDER_MAX_DELAY)
        self._wander_job = self.master.after(delay, self._wander)

    def _stop_wander(self):
        self.wandering = False
        if self._wander_step_job:
            self.master.after_cancel(self._wander_step_job)
            self._wander_step_job = None
        self._cur_img = self._stand_img
        self._update_char_image()
        self._fade_trail()

    def _wander(self):
        if self.busy:
            self._schedule_wander()
            return
        sw = self.master.winfo_screenwidth()
        sh = self.master.winfo_screenheight()
        # 目标中心点，限制在屏幕内（避开边缘与底部任务栏）
        minx = self.ww / 2 + 15
        maxx = sw - self.ww / 2 - 15
        miny = self.wh / 2 + 15
        maxy = sh - self.wh / 2 - 45
        if maxx <= minx or maxy <= miny:
            self._schedule_wander()
            return
        tx = random.uniform(minx, maxx)
        ty = random.uniform(miny, maxy)
        cx, cy = self._center()
        dist = ((tx - cx) ** 2 + (ty - cy) ** 2) ** 0.5
        if dist < 1:
            self._schedule_wander()
            return
        frames = max(2, int(dist / (WANDER_SPEED * WANDER_FRAME / 1000.0)))
        step_x = (tx - cx) / frames
        step_y = (ty - cy) / frames
        # 干净起点（不含颠动偏移），在干净坐标上插值，避免落点漂移
        ax = cx
        ay = cy
        self.wandering = True
        # 奔跑时两帧跑姿交替：起点帧按奔跑方向（向左=左跑图、向右=右跑图），随后每步幅周期切换
        self._run_fidx = 0 if step_x < 0 else 1
        self._cur_img = self._run_poses[self._run_fidx]
        self._update_char_image()
        done = [0]

        def step():
            nonlocal ax, ay
            if not self.wandering:
                return
            if self.dragging:
                self._wander_step_job = self.master.after(WANDER_FRAME, step)
                return
            done[0] += 1
            if done[0] >= frames:
                ax, ay = tx, ty
            else:
                ax += step_x
                ay += step_y
            # 硬性限制不出屏
            if ax < minx:
                ax = minx
            elif ax > maxx:
                ax = maxx
            if ay < miny:
                ay = miny
            elif ay > maxy:
                ay = maxy
            # 两帧跑姿交替（左跑↔右跑）：只换图不清除重建，避免闪烁
            if done[0] % self._stride_ticks == 0:
                self._run_fidx = 1 - self._run_fidx
                self.photo = ImageTk.PhotoImage(
                    self._keyed_image(self.cw, self.ch, self._run_poses[self._run_fidx]))
                self.canvas.itemconfig(self.char_item, image=self.photo)
                self.canvas.tag_raise("char")
            # 上下颠动（仅视觉偏移，不影响插值落点）
            bob = -int(self._bob_amp * abs(math.sin(done[0] * math.pi / self._stride_ticks)))
            this_y = ay + bob
            self.basex = ax - self.ww / 2.0
            self.basey = this_y - self.wh / 2.0
            self._place()
            self._history.append((ax, this_y))
            self._draw_trail()
            if done[0] >= frames:
                self.wandering = False
                # 落地回正，落在目标点（去掉颠动偏移，避免漂移）
                self.basex = tx - self.ww / 2.0
                self.basey = ty - self.wh / 2.0
                self._cur_img = self._stand_img
                self._update_char_image()
                self._place()
                self._fade_trail()
            else:
                self._wander_step_job = self.master.after(WANDER_FRAME, step)

        step()

    def _draw_trail(self):
        self.canvas.delete("trail")
        cx, cy = self._center()
        n = len(self._history)
        if n == 0:
            return
        r0 = max(6, int(self.ch * TRAIL_R0_RATIO))
        cols = TRAIL_COLORS
        # 先画尾(最旧)，后画头(最新)，头叠在最上层；半径与颜色随距头距离渐隐，成彗星尾
        for i in range(n - 1, -1, -1):
            px, py = self._history[i]
            dx = px - cx
            dy = py - cy
            if abs(dx) > self.ww or abs(dy) > self.wh:
                continue
            d = n - 1 - i                 # 距头距离：0=贴角色(最新)
            t = d / max(1, n - 1)         # 0=头 1=尾
            r = max(1, int(r0 * (1 - 0.86 * t)))
            color = cols[min(int(t * (len(cols) - 1) + 0.5), len(cols) - 1)]
            # 头部一小段画亮色外晕，增强“燃烧”感
            if d <= 2:
                halo = int(r * 1.6)
                self.canvas.create_oval(
                    self.ww / 2 + dx - halo, self.wh / 2 + dy - halo,
                    self.ww / 2 + dx + halo, self.wh / 2 + dy + halo,
                    fill=cols[0], outline="", tags=("trail",))
            self.canvas.create_oval(
                self.ww / 2 + dx - r, self.wh / 2 + dy - r,
                self.ww / 2 + dx + r, self.wh / 2 + dy + r,
                fill=color, outline="", tags=("trail",))
        self.canvas.tag_raise("char")

    def _fade_trail(self):
        if self._fade_job:
            self.master.after_cancel(self._fade_job)

        def fade():
            if self._history:
                self._history.popleft()
                self._draw_trail()
                self._fade_job = self.master.after(WANDER_FRAME, fade)
            else:
                self.canvas.delete("trail")
                self._fade_job = None
                self._schedule_wander()

        fade()

    # ---------- 睡眠模式 ----------
    def _note_interaction(self):
        self._last_activity = time.time()
        if self._sleeping:
            self._wake()

    def _start_sleep_checker(self):
        if self._sleep_checker_job:
            return
        self._sleep_checker_job = self.master.after(SLEEP_CHECK_MS, self._sleep_checker)

    def _sleep_checker(self):
        self._sleep_checker_job = None
        if self._sleeping:
            return
        if (not self.busy and not self.dragging and not self.wandering
                and time.time() - self._last_activity >= SLEEP_DELAY / 1000.0):
            self._enter_sleep()
        else:
            self._sleep_checker_job = self.master.after(SLEEP_CHECK_MS, self._sleep_checker)

    def _enter_sleep(self):
        self._sleeping = True
        if self._wander_job:
            self.master.after_cancel(self._wander_job)
            self._wander_job = None
        # 切换为睡眠姿势（蜷缩躺沙发），随后周期性冒 Zzz 气泡
        self._cur_img = self._sleep_img
        self._update_char_image()
        self._show_bubble(random.choice(SLEEP_LINES))
        self._sleep_tick_job = self.master.after(SLEEP_CHECK_MS, self._sleep_tick)

    def _sleep_tick(self):
        if not self._sleeping:
            self._sleep_tick_job = None
            return
        self._show_bubble(random.choice(SLEEP_LINES))
        self._sleep_tick_job = self.master.after(SLEEP_CHECK_MS, self._sleep_tick)

    def _wake(self):
        self._sleeping = False
        if self._sleep_tick_job:
            self.master.after_cancel(self._sleep_tick_job)
            self._sleep_tick_job = None
        self._hide_bubble()
        # 恢复站姿
        self._cur_img = self._stand_img
        self._update_char_image()
        self._schedule_wander()
        # 重新启动空闲检查，否则睡醒后永远不会再入睡
        self._start_sleep_checker()

    # ---------- 粒子 / 爱心特效 ----------
    def _spawn_particles(self, n):
        lx = self.ww / 2.0
        ly = self.wh / 2.0
        for _ in range(n):
            ang = random.uniform(math.pi * 0.3, math.pi * 0.7)
            speed = random.uniform(1.5, 4.5)
            self._particles.append({
                "x": lx + random.uniform(-self.cw * 0.28, self.cw * 0.28),
                "y": ly + random.uniform(-self.ch * 0.1, 0),
                "vx": math.cos(ang) * speed,
                "vy": -abs(math.sin(ang)) * speed - random.uniform(0.5, 2.0),
                "g": random.uniform(0.04, 0.10),
                "life": random.randint(28, 48),
                "maxlife": 48,
                "color": random.choice(PARTICLE_COLORS),
                "shape": random.choice(PARTICLE_SHAPES),
                "size": random.randint(9, 17),
                "id": None,
            })
        self._start_particle_loop()

    def _start_particle_loop(self):
        if self._ptc_job:
            return
        self._particle_step()

    def _particle_step(self):
        alive = []
        for p in self._particles:
            if p["id"] is not None:
                self.canvas.delete(p["id"])
            if p["life"] <= 0:
                continue
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += p["g"]
            p["vx"] *= 0.98
            p["life"] -= 1
            frac = p["life"] / max(1, p["maxlife"])
            sz = max(2, int(p["size"] * frac))
            if p["shape"] in ("♥", "★"):
                p["id"] = self.canvas.create_text(
                    p["x"], p["y"], text=p["shape"], fill=p["color"],
                    font=("Segoe UI Symbol", sz), tags=("ptc",))
            else:
                p["id"] = self.canvas.create_oval(
                    p["x"] - sz / 2, p["y"] - sz / 2,
                    p["x"] + sz / 2, p["y"] + sz / 2,
                    fill=p["color"], outline="", tags=("ptc",))
            alive.append(p)
        self._particles = alive
        if alive:
            self._ptc_job = self.master.after(33, self._particle_step)
        else:
            self._ptc_job = None

    # ---------- 对话气泡 ----------
    def _show_bubble(self, text):
        if self._bubble is None:
            b = tk.Toplevel(self.master)
            b.withdraw()                      # 先隐藏，避免首次闪现空窗
            b.overrideredirect(True)
            b.attributes("-topmost", True)
            frame = tk.Frame(b, bg="white", bd=0, highlightthickness=1,
                             highlightbackground="#B0B0B0")
            frame.pack(fill="both", expand=True)
            lab = tk.Label(frame, text="", bg="white", fg="#333333",
                           font=("Microsoft YaHei", 11), padx=14, pady=8,
                           justify="left")
            lab.pack()
            self._bubble = (b, lab)
        b, lab = self._bubble
        lab.config(text=text)
        b.update_idletasks()
        cw = lab.winfo_reqwidth()
        ch = lab.winfo_reqheight()
        cx, _ = self._center()
        top = self.basey + TRAIL_MARGIN        # 角色顶端
        by = int(top - ch - 10)
        if by < 0:
            by = int(self.basey + TRAIL_MARGIN + self.ch + 10)  # 角色底端下方
        bx = int(cx - cw / 2.0)
        bx = max(4, min(self.master.winfo_screenwidth() - cw - 4, bx))
        b.geometry(f"{cw}x{ch}+{bx}+{by}")
        b.deiconify()
        b.lift()
        if self._bubble_job:
            self.master.after_cancel(self._bubble_job)
        self._bubble_job = self.master.after(BUBBLE_HIDE_MS, self._hide_bubble)

    def _hide_bubble(self):
        if self._bubble:
            self._bubble[0].withdraw()


def main():
    root = tk.Tk()
    pet = DesktopPet(root)
    if "--selftest" in sys.argv:
        out = os.environ.get("PET_SELFTEST_OUT") or resource_path("selftest_ok.txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write("ok\n")
        root.after(1500, root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
