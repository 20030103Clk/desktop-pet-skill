---
name: desktop-pet-builder
description: 用一张人物/角色照片制作 Windows 桌面宠物（Q版桌宠）并打包成可双击运行的 exe。适用于“做个桌宠”“把这张图变成桌面宠物”“做个Q版桌宠”“桌面宠物程序”等需求。角色统一做成 Q版（小短身、有腿、卡通萌系），输出透明无边框置顶窗口，支持拖动、点击互动动画（跳跃/压扁/抖动轮流 + 爱心粒子）、中文白气泡、右键菜单（调大小/置顶/退出）、滚轮缩放、定时乱跑+流星拖尾、奔跑时左跑↔右跑两帧交替、睡眠姿势（蜷缩躺沙发睡觉 + Zzz）、点击唤醒。本 skill 不内置任何角色图片，每次必须由用户提供角色照片，从该照片出发生成全套 Q版素材并复现相同效果。
---

# 桌面宠物制作 (desktop-pet-builder)

## 目标
把一张角色照片做成一款 Windows 桌面宠物，打包为单个 exe，对方双击即可运行（无需装 Python）。用户只提供一张照片，即可完整复现与标准版一致的桌宠效果。

## 通用原则（重要）
- **本 skill 不内置任何角色图片**。assets/ 目录已清空，不携带任何具体角色的图（避免沉淀后残留某张特定形象）。每次制作都必须由用户提供角色照片，流程从该照片出发生成全套 Q版素材。
- 角色统一做 **Q版**：小短身、有清晰两条小短腿、大头比例、卡通萌系。
- 透明背景用**绿幕 + 色键抠图**（Windows 打包时用 `transparentcolor` 关键色显示透明）。

## 默认配方（记住：Q版）
- 需要 **4 张透明图**：站姿 `stand.png` + 睡眠姿势 `sleep.png` + 左跑 `run_L.png` + 右跑 `run_R.png`。
- 跑姿动画 = **左跑图 ↔ 右跑图两帧来回切换**：程序每 `_stride_ticks=5` 步在 `run_L` 与 `run_R` 之间切换一次（起点帧按奔跑方向选，向左先 `run_L`、向右先 `run_R`），并叠加正弦上下颠动（`_bob_amp`），形成 2 帧跑步循环。
- 睡眠模式：闲置约 `SLEEP_DELAY=20s` 后切换为 `sleep.png`（Q版角色蜷缩侧躺沙发睡觉）+ 周期性 Zzz 气泡；点击唤醒恢复站姿。
- 互动：单击轮流触发跳跃 / 压扁回弹 / 左右抖动，同时随机显示中文白气泡并爆发爱心粒子。
- 拖尾：定时随机乱跑时带流星拖尾（`TRAIL_HISTORY=42` 个轨迹点、10 段渐变色、先画尾后画头、头端亮晕）。

## 关键经验（务必遵守，均被反复验证）
- **跑姿两帧 = 左跑图 + 右跑图（两种朝向的真实跑姿图），不是“左右腿互换”的两帧**。生图模型无法可靠生成两个明显不同的左右腿跑姿帧（多次尝试两帧几乎一样、腿看不出在动，被打回）。左跑图朝左、右跑图朝右，切换即形成“跑步循环”，两图相似度高、切换自然不夸张。
- **右跑图不要用水平镜像**。整体镜像会让跑姿朝向和细节反相；采用 `image_edit` 基于左跑图生成一张朝右、右腿在前的右跑图（保留角色与服装细节，非镜像），或用 `image_edit` 生成。若用户已提供左右各一张跑姿图，直接使用。
- **互动动画绝不移动窗口（黑框修复）**：跳跃/压扁/抖动全部在**固定窗口内**用 `itemconfig`+`coords` 更新已有画布项，绝不用 `geometry()` 移动窗口，否则透明窗口 relocate 会闪现黑色大框；`TRAIL_MARGIN` 同时为跳跃留出头顶空间。
- **睡眠 bug（睡过一次后永不再睡）**：`_wake()` 必须重新调用 `_start_sleep_checker()` 重启空闲检查，否则睡眠检查器指针为 None，之后不会再入睡。此修复已内置在脚本。
- **奔跑交替避免闪烁**：切换跑姿用 `itemconfig` 只换当前图像，**不要** `canvas.delete("char")`+`create_image` 全量重建（每步幅周期重建会闪）。
- **对象命名不要与方法撞名**：跑姿图片容器用 `self._run_poses`，不要命名成 `_run_frames`（会与互动动画方法 `_run_frames()` 撞名，导致点击互动静默失败）。

## 素材与脚本
- `scripts/desktop_pet.py`：桌宠程序本体（全部功能已内置，运行时加载 `stand.png`/`sleep.png`/`run_L.png`/`run_R.png`，改顶部常量可调参数）。
- `scripts/matte.py`：通用绿幕/纯色底抠图脚本（`matte(绿幕图, 输出.png)`，色键 + 去边缘）。

## 完整流程（用户发一张照片 → 复现）
1. **Q版化生成 4 张绿幕素材**（用 `image_edit`，基于用户照片做 Q版化延展）：
   - **站姿** `stand_green.png`：Q版小短身、有腿、站姿、绿幕背景（竖版，比例约 1709×2452）。
   - **睡眠姿势** `sleep_green.png`：基于站姿生成——Q版角色蜷缩侧躺沙发睡觉、闭眼、绿幕，比例与站姿一致避免变形。
   - **左跑** `run_L_green.png`：基于站姿生成——面向左跑、双腿张开、绿幕，比例一致。
   - **右跑** `run_R_green.png`：基于左跑图 `image_edit` 生成——朝右跑、右腿在前、绿幕，保留角色与服装细节，**非镜像**。
   - 面部尽量保留原图特征；若模型把脸卡通化严重，优先接受 Q版卡通脸，向用户说明“Q版会更可爱但不会完全像本人”，必要时请用户提供更清晰的正面照。
   - 若用户已直接提供左跑/右跑图，可跳过对应生成。
2. **抠图**：把 4 张绿幕图抠成透明：
   `python scripts/matte.py <绿幕图> <输出.png>`（站姿→stand，睡眠→sleep，左跑→run_L，右跑→run_R）。
   用棋盘格预览检查边缘是否干净（无绿边、无红边）。
3. **打包 exe**：
   - 需要 venv，含 `Pillow` + `pyinstaller`（无则先建：`python -m venv venv` + 安装）。
   - 命令：
     `pyinstaller --onefile --noconsole --name DesktopPet --add-data "<项目>\stand.png;." --add-data "<项目>\sleep.png;." --add-data "<项目>\run_L.png;." --add-data "<项目>\run_R.png;." desktop_pet.py`
   - 产物在 `dist/DesktopPet.exe`。
4. **验证**：
   - 语法：`python -m py_compile desktop_pet.py`。
   - exe 自检：设 `$env:PET_SELFTEST_OUT=<marker路径>`，`Start-Process DesktopPet.exe -ArgumentList '--selftest'`，等待退出且 marker 存在即通过。
   - 功能点：拖动、单击互动（跳跃/压扁/抖动轮流 + 爱心粒子）、白气泡、右键菜单（调大小/置顶/退出）、滚轮缩放、定时乱跑+流星拖尾（左跑↔右跑两帧交替）、闲置 20s 后睡眠（切睡眠姿势 + Zzz 气泡）、点击唤醒恢复站姿、睡醒后可再次入睡。

## 可调参数（在 `desktop_pet.py` 顶部）
- 当前默认：`BASE_HEIGHT=175`、`MIN_HEIGHT=90`、`MAX_HEIGHT=500`、`TRAIL_MARGIN=90`、`TRAIL_HISTORY=42`、`TRAIL_R0_RATIO=0.11`、`WANDER_FRAME=28`、`_bob_amp=6`、`_stride_ticks=5`。
- `BASE_HEIGHT`：初始高度；`MIN_HEIGHT`/`MAX_HEIGHT`：缩放范围。
- `WANDER_MIN_DELAY`/`WANDER_MAX_DELAY`：乱跑间隔；`WANDER_SPEED`：速度。
- `TRAIL_COLORS`：拖尾颜色；`TRAIL_HISTORY`：拖尾点数；`TRAIL_R0_RATIO`：拖尾半径比例。
- `SLEEP_DELAY`：闲置多久入睡；`SLEEP_LINES`：睡眠气泡文案。
- `BUBBLE_LINES`：点击气泡文案；`PARTICLE_COLORS`：爱心粒子颜色。

## 注意
- 透明依赖 Windows `transparentcolor`，仅 Windows 可打包运行。
- 发 exe 给他人：只发一个 exe；对方 SmartScreen 选“更多信息→仍要运行”；杀软误报加信任。
- Mac 版无法在此跨平台编译，需在 Mac 上用 `--windowed` 重新打包。
