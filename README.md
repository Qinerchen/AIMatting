# AIMatting - 基于 BiRefNet 的高精度抠图工具

> 更新日志见 [CHANGELOG.md](CHANGELOG.md)。

一款专业、易用的本地抠图桌面软件：基于 **BiRefNet 高精度模型**精细边缘 matting，
支持**笔刷遮罩**快速圈定主体、**裁剪**去冗余、单张/批量抠图、纯色背景填充（含不透明度）、
手动微调（去色边 / 边缘羽化）、图片预处理、
撤销/重做（20 步）与多种格式导出。所有处理均在本机完成，不上传任何图片。

## 功能总览

| 需求 | 实现 |
| --- | --- |
| 单张高精度抠图 | BiRefNet HR-matting / lite-2K 精细 matting，软 alpha，发丝、毛发、玻璃等边缘效果好 |
| 笔刷遮罩 | 画前景 / 擦除笔刷，大致涂出主体即可；AI 自动做精细边缘；专业笔刷光标 |
| 裁剪 | 框选保留区域，一键裁掉图片无用部分 |
| 前后对比 | 原图 / 结果滑动对比条，随时检查抠图质量 |
| 发丝级精修 | 去色边（消除彩色描边）、边缘羽化（柔化边缘过渡） |
| 格式兼容 | JPG / PNG / WEBP / TIFF / BMP，支持 320×320 到 4K 及以上 |
| 批量抠图 | 一次导入多张，统一参数 + 逐张独立设置，失败项可单独重试，可单独微调 |
| 纯色背景填充 | 常用色一键选择 + 色板 / RGB / HEX 自定义，0-100% 不透明度实时预览 |
| 手动微调 | 修复边缘 / 误抠擦除笔刷（大小、硬度可调），边缘羽化、反选遮罩 |
| 图片预处理 | 亮度 / 对比度 / 饱和度 / 色温调节 |
| 撤销 / 重做 | 最多 20 步操作记录 |
| 界面与交互 | 导入区、预览区、功能区、参数区四区布局；拖拽导入；滚轮缩放预览；进度提示 |
| 输出 | PNG 透明素材 / PNG 带色背景 / JPG / WEBP；自定义保存目录与命名后缀 |
| 窗口体验 | QGoodWindow 风格无边框窗口：原生缩放边框、拖拽贴靠（Win11 贴靠布局）、系统菜单、深色标题栏、自绘标题栏按钮，现代暗色主题 |
| 模型快捷切换 | 顶部栏下拉框一键在 BiRefNet HR-matting / lite 2K 间切换，无需打开模型管理 |
| 可靠性 | 模型下载断点续传 + 完整性校验；任务可取消；崩溃日志 |
| 隐私 | 全本地处理，无广告、无捆绑、不联网收集数据 |

## 技术方案

- **语言 / GUI**：Python 3.10+ / PySide6（Qt6）+ [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
  （Fluent Design 现代化界面，跨平台支持 Windows 与 macOS）
- **推理**：ONNX Runtime（自动优先 CUDA GPU，无 GPU 时回退 CPU）
- **算法**：[ZhengPeng7/BiRefNet](https://github.com/ZhengPeng7/BiRefNet)（MIT License）
  官方发布的 ONNX 模型：
  - `BiRefNet_HR-matting-epoch_135.onnx`（约 1GB，推荐）：2048×2048 训练，抠图质量最佳
  - `BiRefNet_lite-general-2K-epoch_232.onnx`（约 316MB）：轻量快速，适合批量与普通图片
- **图像处理**：Pillow + NumPy，无 OpenCV 依赖

### 窗口实现

界面整体基于 [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
的 `FluentWindow` 重构：

- **Fluent 导航**：左侧导航栏切换「单张 / 批量」页面；
- **现成组件**：按钮、下拉框、滑块、输入框、进度条、对话框等全部使用
  qfluentwidgets 组件，暗色主题 + 主题色统一；
- **窗口行为**：无边框窗口、标题栏最小化/最大化/关闭、拖拽贴靠、
  Windows 11 Mica 效果由 qfluentwidgets 自带支持；
- 无边框窗口由 qfluentwidgets 提供，无额外自绘实现。

## 安装与运行

### Windows

1. 双击 `setup.bat`（自动创建虚拟环境并安装依赖）。
2. 双击 `run.bat` 启动软件；首次使用请在「模型管理」中下载模型。

### 手动安装（Windows / macOS）

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

GPU 加速（可选，推荐）：

```bash
pip uninstall onnxruntime
pip install onnxruntime-gpu
```

### 下载模型

- 软件内：「模型管理」→ 选择模型 → 下载（带进度显示）。
- 命令行：`python scripts/download_model.py`（默认下载 HR-matting）或
  `python scripts/download_model.py --model lite`。

模型保存到 `models/` 目录，下载完成后离线可用。

## 使用教程

### 快速上手（5 步）

1. 下载模型（「模型管理」）。
2. 导入图片：点「选择图片」或直接把图片拖进左侧区域。
3. 可选：在「预处理」页调整亮度/对比度/饱和度/色温。
4. 可选：在「笔刷遮罩」页用「画前景」大致涂出主体（绿框高亮），或直接点「开始抠图」。
5. 用工具栏「对比」查看原图/结果差异；在「手动微调」页可去色边、边缘羽化。
6. 在「背景填充」选颜色与不透明度（实时预览），「输出设置」选格式与命名后缀，
   点「保存 / 导出」。

### 核心功能说明

- **背景填充**：预设白/黑/灰/红/绿/蓝等常用色，或点「自定义颜色」打开色板，
  也可直接输入 HEX 或 RGB。不透明度 0% 时导出为透明 PNG。
- **笔刷遮罩**：选「画前景」沿主体大致涂一遍（绿色高亮），涂错用「擦除」；
  画笔大小、硬度可调，**光标圆圈即画笔大小**（内圈表示硬度）。
  点「开始抠图」后，AI 会在遮罩范围内做精细 matting，边缘质量以 AI 结果为准。
- **裁剪**：工具栏「裁剪」后在预览图上框选保留区域，确认后裁掉无用部分。
- **前后对比 / 精修**：工具栏「对比」开启原图/结果滑动对比；
  「手动微调」页的「去色边」清除半透明边缘彩色描边，「边缘羽化」柔化边缘过渡。
- **批量进阶**：选中文件点「单独设置」可为该图指定背景/格式/质量/后缀；
  处理失败的文件可点「重试失败」只重跑失败项。
- **手动微调**：抠图完成后在「手动微调」页选择「修复边缘」或「误抠擦除」，
  在预览图上直接涂抹；放大视图可精修发丝等细节。画笔大小 1-300px、硬度可调。
- **批量抠图**：切到左侧「批量」页，添加图片，设置输出格式/后缀/目录，
  点「开始批量抠图」；列表中逐张显示状态，可中途停止。
  批量完成后可选中某张点「单独编辑选中图」进入单张微调。
- **撤销 / 重做**：Ctrl+Z / Ctrl+Y，最多 20 步。
- **预览缩放**：滚轮缩放、按住左键拖拽平移；工具栏可一键「适合窗口 / 100%」。

### 快捷键

| 快捷键 | 功能 |
| --- | --- |
| Ctrl+O | 导入图片 |
| Ctrl+R | 开始抠图 |
| Ctrl+S | 保存 / 导出 |
| Ctrl+Z / Ctrl+Y | 撤销 / 重做 |
| F1 | 使用教程 |

## 性能说明

性能受硬件影响较大：

- **注意**：当前两个捆绑 ONNX 模型均为固定输入尺寸
  （HR-matting 为 2048×2048，lite 2K 为 2560×1440），
  「输出设置 → 推理分辨率」选项对这两个模型暂不生效。
- **GPU（RTX 4070 级别实测）**：lite 模型每张约 16-22 秒，
  HR-matting 每张约 20-53 秒，显存占用约 12GB。
- **CPU**：明显更慢，建议仅在无独立显卡时使用。
- 加速建议：在「输出设置」中勾选 **TensorRT 加速**（首次需构建引擎，
  耗时较长，失败会自动回退 CUDA/CPU）；或更换支持动态输入、
  fp16 的 BiRefNet ONNX 模型。

## 常见问题

- **没有模型 / 下载中断**：在「模型管理」重新下载即可，软件会自动覆盖不完整文件。
- **笔刷遮罩怎么用？** 大致把主体涂满即可，边缘不需要精确；
  BiRefNet 会在遮罩范围内做精细 matting。若遮罩几乎覆盖整张图，
  模型无法识别主体时会按笔刷遮罩出图，建议缩小遮罩范围重试。
- **抠图结果边缘粗糙**：质量优先时用 HR-matting 模型。
- **JPG 为什么不能透明**：JPG/WEBP 格式不支持透明通道，半透明背景会平铺到白色底；
  透明素材请导出 PNG。
- **大图卡顿**：4K 以上图片建议使用 lite 模型，并避免同时运行其他占显存的应用。
- **隐私**：模型推理、预览、导出全部在本机完成；软件不包含任何联网上报代码。
- **无边框窗口**：顶部栏位于窗口最上方（导入、撤销、重做、模型切换、教程等
  都在这一栏），可拖动窗口、双击最大化/还原，右上角为自绘的最小化 / 最大化 / 关闭按钮；
  整体为现代暗色主题。

## 项目结构

```text
AIMatting/
├── run.py                     # 启动入口
├── setup.bat                  # Windows 一键安装
├── run.bat                    # Windows 一键启动
├── requirements.txt           # 依赖清单
├── aimatting/
│   ├── app.py                 # QApplication 装配
│   ├── core/                  # 核心逻辑（无 GUI 依赖，可独立测试）
│   │   ├── engine.py          # BiRefNet ONNX 推理引擎
│   │   ├── image_ops.py       # 预处理 / 背景合成 / 笔刷
│   │   ├── history.py         # 20 步撤销重做
│   │   ├── batch.py           # 批量任务线程
│   │   ├── io_utils.py        # 格式与命名规则
│   │   └── config.py          # 模型注册表与设置
│   ├── ui/                    # PySide6 界面
│   │   ├── main_window.py     # 主窗口与流程编排
│   │   ├── image_view.py      # 缩放/平移/笔刷画布
│   │   ├── panels.py          # 参数面板
│   │   ├── batch_panel.py     # 批量面板
│   │   └── dialogs.py         # 模型管理 / 教程 / 关于
│   └── workers/               # 工作线程
├── scripts/download_model.py  # 命令行下载模型
├── models/                    # ONNX 模型目录（下载后生成）
└── tests/                     # 单元测试
```

## 许可证

- 本软件代码：MIT License。
- BiRefNet 模型与仓库：MIT License（[ZhengPeng7/BiRefNet](https://github.com/ZhengPeng7/BiRefNet)）。
- 界面框架 PyQt-Fluent-Widgets：**GPL-3.0 License**（完整文本见
  `licenses/GPL-3.0.txt`）。

> 注意：由于界面框架为 GPL-3.0，若将本程序（含打包后的 exe）对外分发，
> 需遵循 GPL-3.0 要求公开源码并附带许可证文本。
