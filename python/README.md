> ## ⚠️ 改版声明（Modified / Derivative Version）
>
> 本仓库是 **B站月匠** 原创作品 **DeepSeek-Balance-Whale-Widget** 的**改版（衍生作品）**，原项目与其中全部主要代码、设计、素材的著作权归原作者所有。
>
> - 原作者 B 站主页：<https://space.bilibili.com/345797244>
> - 原作者 GitHub 仓库：<https://github.com/MeteorNOX/DeepSeek-Balance-Whale-Widget>
> - 本改版仓库：<https://github.com/QingCheng3962/DSH-Balance-Desk-Pet>
>
> 本仓库仅在原作品基础上进行修改与再分发，保留原作者的 MIT 许可与其署名（见 [LICENSE](LICENSE) 与 [PROVENANCE.md](PROVENANCE.md)）。

# DSH 小鲸鱼挂件 · Python 桌面版

Bongo Cat Mver 形态的桌面宠物：**一个贴着桌面的小透明窗口，只有鲸鱼本体能点，其余像素点击直接穿透到桌面**；可拖动、悬停会放大、按下 Q 弹并有音效；右键出菜单，双击刷余额，滚轮调大小；支持开机自启。

和 `desktop/`（Electron 版）的区别：这版不需要 Electron、不需要打包，**装个 Python 就能跑**，改一行代码立刻生效。

## 依赖

只需要 Python 3.9+ 和两样东西：

| 依赖 | 说明 |
|---|---|
| `tkinter` | Python 官方自带（Windows 版默认包含） |
| `Pillow` | 唯一的第三方依赖：`python -m pip install pillow` |

音频用 Windows 自带的 MCI（`winmm`）播 mp3、`winsound` 播 wav，**不需要额外装库**；
托盘/穿透/自启全部走 `ctypes` 调 Win32，也没有额外依赖。

检查环境：

```powershell
python -c "import tkinter, PIL; print('tk', tkinter.TkVersion, 'pillow', PIL.__version__)"
```

## 启动

```powershell
# 方式 1：双击（推荐）
小鲸鱼挂件.pyw

# 方式 2：命令行
python dsh_whale_pet.py

# 方式 3：想省掉 .pyw 关联问题时
wscript 启动小鲸鱼挂件.vbs
```

素材从插件的 `assets/` 读取：脚本会自动在自身目录、上一级、上两级里找 `assets/DSniang1.png`；
也可以用环境变量指定：

```powershell
$env:DSHW_ASSETS = "D:\path\to\DSH-Whale-Widget\assets"
```

## 操作

| 操作 | 效果 |
|---|---|
| 左键拖动 | 移动挂件（位置与大小记在 `~/.dsh/.dshw-py-pet.json`） |
| 左键单击 | 原版语义：点鲸鱼开第 1 项；点泡泡推进下一项，最后一项则收起 |
| 双击 | 立刻刷新余额 |
| 滚轮 | 缩放（0.4×–4.0×，默认跟随 DSH 设置的 1.4×） |
| 右键 | 菜单（见下） |
| Esc | 退出 |

### 点击压缩：对齐原版的数值与曲线

原版按下去就一行 `body.style.transform = SQUISH`：

```js
var SQUISH = 'scaleY(0.88) scaleX(1.05)'
/* .dshwv-body{transform-origin:50% 100%;transition:transform .22s cubic-bezier(.34,1.56,.64,1)} */
```

这里逐字对齐：**纵向压 12%、横向鼓 5%，底边中心为原点，0.22s**，并用
`cubic-bezier(.34,1.56,.64,1)` 求值 —— y1=1.56 会**冲过 1**，也就是按下后回弹的过冲手感。
实测曲线：

| 进度 | 0% | 15% | 45% | 60% | 100% |
|---|---|---|---|---|---|
| 形变量 | 0 | 0.566 | **1.066** | **1.097** | 1.000 |
| scaleX | 1.000 | 1.028 | 1.053 | 1.055 | **1.050** |
| scaleY | 1.000 | 0.932 | 0.872 | 0.868 | **0.880** |

最终精确落在原版的 `scaleX(1.05) / scaleY(0.88)`。原版**没有悬停放大**（我查过 CSS，
`:hover` 只用在调色板等控件上），所以这一版也去掉了自创的 hover 缩放。

### 吸附 · 镜像 · 贴顶倒挂

- **贴边吸附**：鲸鱼本体进入左/右/上/下吸附区即贴边（角落可组合），宽度按显示器
  `rcWork` 百分比；默认左右 10%、上 12%、下 15%（原版 v3 是 0/10/15，这里为"贴顶倒挂"
  把上吸附打开）
- **左右镜像**：中心越过翻转线（默认屏宽 50%）整体水平镜像
- **贴顶倒挂**：吸到**上边**时整体旋转 180°（像挂在天花板上），此时不再叠加左右镜像；
  离开上边自动转回来。挂件倒挂时气泡会自动改挂到**下方、尾巴朝上**
- 菜单「吸附与翻转」里可切：吸附区宽度（窄/默认/宽）、翻转线（25/50/75%）、倒挂开关、
  镜像时文字是否反向、立即校正

### 图片台词（GIF）速度

`rua.gif` 自带 **20ms/帧（合 50fps）**，偏快。现在帧间隔按 **GIF 自带时长**走，
再乘速度倍率；菜单 →「图片台词速度」可选 **0.25× / 0.5× / 0.75× / 1× / 1.5×**
（0.25× 即 80ms/帧）。

**右键菜单**：刷新余额 / 今日已用·记账 / 音效 / 每轮消耗提示 / **余额预警（开关 + 阈值）** /
**贴边吸附 / 镜像翻转 / 吸附与翻转子菜单** / 始终置顶 / 全局穿透 / 点击不抢焦点 /
开机自启 / 大小 / 回到右下角 / 打开数据目录 / 退出。

> 「全局穿透」故意**不跨启动保留**：它会让整只挂件（含右键菜单）都不吃鼠标，
> 一旦被记住就再也点不回来了。重启挂件即可恢复可交互。

## 气泡：直接使用原版的 SVG（不是照着眼睛画）

气泡**原样**使用 `assets/whale-widget.js:11552` 里那段 SVG —— 路径数据、填充、描边、
两个点、文字区位置全部照搬，见 [whale_svg.py](whale_svg.py)：

```xml
<svg viewBox="0 0 1026 700">
  <path class="dshwv-bshape" fill="#FFFFFF" stroke="#203170" stroke-width="18"
        stroke-linejoin="round" stroke-linecap="round"
        d="M 827 248 A 373 232 0 1 0 81 246 A 373 232 0 0 0 301 465
           A 57 32 10 0 0 413 484 A 373 232 0 0 0 827 248 Z"/>
  <ellipse class="dshwv-b1" cx="352" cy="561" rx="37.5" ry="26" .../>
  <ellipse class="dshwv-b2" cx="442" cy="646" rx="24.5" ry="18" .../>
</svg>

.dshwv-text{left:44.25%;top:36%;width:66%;height:64%;color:#536ba9;line-height:1.15}
```

`whale_svg.py` 按 SVG 规范 F.6.5 把 `A`（椭圆弧）从端点参数化换算成中心参数化再展平，
用 Pillow 画出同样的填充与**跨在路径上**的描边（stroke 18 → 内 9 / 外 9），
文字写在原版的文字区里（中心 44.25%/36%、可用 66%×64%、颜色 #536ba9）。

**怎么证明还原准确**：用 Chromium（仓库里现成的 Electron）把同一段 SVG 原样渲染成 PNG,
再和 Pillow 的输出逐像素比 —— 见 [`render_svg_ref.js`](render_svg_ref.js)：

| 对比 | 显著差异(>40) | 轻微差异(>8) |
|---|---|---|
| 初版（残留"描边后重填"的 bug） | 0.88% | 2.00% |
| 修掉重填 + 点的描边外扩之后 | **0.20%** | 1.40% |

0.20% 基本就是抗锯齿噪声量级。**文字和卡片都装在椭圆里**：台词/余额/今日是纯文字；
余额预警与每轮消耗是原版模块化卡片（文字 + 图片 + 可点按钮），按椭圆的**内接矩形**缩放
并从椭圆内沿裁切，保证不切字、不戳出描边。

### 弹出/收起的时序（照搬原版）

原版那三层 `.dshwv-b1/.dshwv-b2/.dshwv-bshape` 就是**两个圆点 + 椭圆本体**，时序也照搬：

| 阶段 | 原版 CSS | 这里 |
|---|---|---|
| 小点 | `.b2 transition-delay 0s` | 0s |
| 大点 | `.b1 delay .13s` | .13s |
| 椭圆 | `.bshape delay .26s` | .26s（整体 scale .7 → 1，共 .46s） |
| 文字 | `.dshwv-text opacity .16s ease .36s` | 0.36s 起、0.16s 淡入 |
| 收起 | 延迟反向 | 整体 ease-in 收缩，**文字与气球一起淡出** |

**文字淡入怎么做到的**：色键透明没有"半透明"，但在**白色椭圆内部**做淡入有个等价办法 ——
把文字颜色朝椭圆的白色混过去，视觉上就是透明度。所以文字是真渐变，不是"到点蹦出来"，
收起时也不再中途被切掉。不喜欢这个错时节奏，菜单里有「文字与气泡同步出现」开关
（原版是错时的，默认照原版）。

气泡挂在挂件上方时两点朝下；挂件贴顶倒挂时气泡挂到下方、两点朝上。

### 气泡跟着挂件走 / 跟着一起翻

- **拖动追随**：拖鲸鱼、贴边、滚轮缩放、跨屏 DPI 变化时，正在显示的气泡**实时跟着移位**
  （不是只在弹出时定位一次）；拖到屏幕顶部空间不够时，气泡自动翻到下方、两点朝上
- **翻转同步**：鲸鱼左右镜像时，**气泡一起镜像**（尾巴缺口、两个点的位置跟着换边）；
  贴顶倒挂时气泡也一起上下翻。文字是否也跟着反向由菜单里的「镜像时文字也反向」决定
  （默认只翻气泡，保证台词/金额还能读）
- 这两条都有自检项：`--selftest` 里的 `bubbleFollow.followed` 与 `bubbleFlip.mirrorIsExact`

> 验证时踩到的坑记录一下：Toplevel 的 `winfo_x()` 是**相对父窗口**的，而根窗口 withdrawn
> 时 Tk 根本不更新坐标 —— 用它测"跟随"必然误判。所以自检里改用 Win32 `GetWindowRect`
> 取绝对坐标，并且短暂显示窗口再测。

### 台词预设、权重、行样式与配色（全部取自源码）

**预设与权重** —— `whale_presets.py` 逐行取自 `whale-widget.js:11799` 的 `RANDOM_GROUPS`：

| 组 | 权重 | 内容 |
|---|---|---|
| `B` 样式 | **7** | `pickOne(['好模型... ↓','好女孩...↓'])` |
| `A` 样式（折行） | **7** | 6 条吐槽随机（`不知道用户有什么用，先赶走吧~` …） |
| gif | **10** | `{gif:true}` → 放 rua 动图 |
| `A` 样式（折行） | **3** | 3 条吐槽随机（`你目录里的dsh是什么...大烧货吗...?` …） |
| `B` 样式 | **1** | `'哦鲸鲸... '` |

抽签规则也照搬：先按**组权重**抽一组（`pickRandomLines`），组内 `pickOne` 等概率；
模块级随机的 `bubblePickLine` 用 `Math.max(1, w||1)` 加权、最多重试 6 次避免与上一条重复。
实测 2 万次抽样：gif **35.6%**、两组 A 合计约 25% / 11%、B 组 12.4%+12.0%、`哦鲸鲸` 3.6%
（原版 7/7/10/3/1 → 25/25/36/11/4）✓

**行样式与字号** —— 字号一律 `u = 挂件宽 / 1026`（原版 `--dshw-u`），**随挂件尺寸自动缩放**：

| 样式（原版 class） | 字号 | 其它 |
|---|---|---|
| `A` `.dshwv-label` | **66u** | 600 字重、`letter-spacing .06em` |
| `B` `.dshwv-amount` | **128u** | 800 字重、`line-height 1.05` |
| `P` `.dshwv-period` | **104u** | 800 字重、`line-height 1.05` |
| `C` `.dshwv-hint` | **56u** | 颜色 **#9fb0d9**、`margin-top 9u`、`min-height 64u` |
| 折行 `wrap` | — | `max-width 560u`、`line-height 1.2` |

气泡默认内容也照原版：`label='DeepSeek 余额'` / `amount=余额` / `hint='今日已用 …'`；
随机台词走原版的 `singleCenter`（内容放在**中间那行**）。

**配色** —— `whale_colors.py` 由 [extract_colors.py](extract_colors.py) 从源码 CSS **机器提取**
（14 套渐变方案：candy/rouge/bamboo/aurora/deepsea/sunset/forest/champagne/lavender/mint/lava/galaxy/ink/indigo，
各含 6–11 个 RGB 停点），加上纯色名与基色 `#536ba9`。文字渐变按原版的 `90deg` 横向铺在字形上。

## 自定义泡泡编辑器（复刻原版，与 DSH 共用同一份配置）

右键菜单 **「编辑气泡…」** 打开（[whale_editor.py](whale_editor.py)）。它读写的就是
**DSH 网页端那份** `$DSH_HOME/.dshw-bubble.json`：

```json
{ "v": 1,
  "items": [ {"kind":"normal"} | {"kind":"random"} | {"kind":"custom","modules":[…]} |
             {"kind":"choice","options":[{"w":3,"item":{…}}]} ],
  "lib":   [ {"id":"m1","name":"模块名","module":{…}} ],
  "tapAdvance": false }
```

所以在 Python 挂件里改完，DSH 网页端挂件立刻用同一份；反过来也一样。

**序列语义**（原版）：`normal` = 默认余额内容；`random` = 随机台词段（原版 `RANDOM_GROUPS`）；
`custom` = 自定义模块列表；`choice` = **并列步骤**，每次按 `w` 权重抽一个候选。
`tapAdvance` = 点鲸鱼**推进**队列（原版是点鲸鱼回到第 1 项）。

**模块字段与原版完全一致**：

| 字段 | 含义 |
|---|---|
| `type` | `text` / `balance` / `today` / `peak` / `session` / `image` / `random` |
| `size` | 档位 **1..50** → `bubbleModuleFontU` = `round(40 + (n-1)*200/49)` × u（40u…240u） |
| `bold` / `italic` / `ul` | 字重 / 斜体 / 下划线 |
| `rgb` / `color` | 配色方案（渐变）/ 纯色 `#rrggbb` |
| `bgRgb` / `bg` | 底色块（方案 / 纯色） |
| `row` | 行号：**相邻同号模块并排一行**（原版 `bubbleRowsOf`）；图片模块独占一行 |
| `imgId` / `imgScale` | 图片：先查内置（`bimg_petpet`/`bimg_money1`）再查 `$DSH_HOME/whale-bubble-imgs` |
| `lines` | `random` 的 `[{t,w}]`，**每行还能自带 bold/size/rgb/italic**，覆盖模块属性（原版如此） |
| `peakStyle` | `default` / `liangwen`（梁文峰/谷）/ `qiangqiang`（!?峰峰?!）/ `count`（倒计时）/ `mini`（峰/谷） |
| `peakColor` `offColor` `peakRgb` `offRgb` `peakBgRgb` `offBgRgb` | 峰/谷分别取色（原版 `bubblePeakText` + 逐峰谷切换） |
| `tpl` | 占位符模板：`{balance_ds}` `{expense_ds}` `{status}` `{countdown}` `{session}` `{cost}` … |

编辑器界面：左边**点击序列**、中间**当前项的模块 + 模块库**（可存/插）、右边**属性面板**
（含「编辑随机台词行」的文本+权重小窗口）、下边**实时预览**——预览用的就是挂件同一套渲染器，
所见即所得。保存是原子写（`.tmp` + `os.replace`），只规范化 `items/lib/tapAdvance` 三个顶层字段，
**你配置里其它字段原样保留**。

### 交付前的实测

用你那份真实的 364 行 `.dshw-bubble.json` 直接渲染验证（**只读**，不动你的文件）：
`{balance_ds}` + `rgb:'indigo'` 显示为**渐变大号余额**、`peak` 的 `mini` 样式显示为
**带 bamboo 底色的「谷」小标签**、`peakStyle:'count'` 显示为**绿色渐变加下划线的倒计时**、
`random` 行自带的 `bold/size/rgb` 生效。见 `real-item1.png` / `real-item2.png`。

## 自动适配

按 `u` 算出字号后，若整块内容超出椭圆内接矩形，再整体等比缩小
（原版靠字号随挂件缩放；这里多兜一层，保证长句不会戳出气泡）。

## 居中：按**墨迹**钉在椭圆中心（所有路径共用一条规则）

只把"画布"居中是不够的 —— 会偏的其实是**看得见的那部分**：

- 图片模块自带透明边距 → 画布中心 ≠ 视觉中心
- 文字的字形上下伸不对称（`textbbox` 的 `box[1]` 常不为 0）→ 系统性偏上几像素
- chip 的内边距、折行后的行尾空白 → 视觉重心被带偏

所以 [whale_svg.py](whale_svg.py) 里统一成两个函数，**所有渲染路径都走它**：

| 函数 | 作用 |
|---|---|
| `place_ink_centered(content, width, tail)` | 按 alpha 包围盒把内容钉到椭圆中心（倒挂时自动换到下半），越界自动裁 |
| `clip_to_balloon(layer, width, tail)` | 按椭圆内沿裁切，保证内容永远不戳出气泡 |

调用方：`render_slots`（默认余额/台词）、`render_bubble_modules`（自定义模块＋编辑器预览）、
`render_card`（预警/消耗卡片）。实测七条路径（含长句折行、超大字、真实配置两项、卡片、
倒挂）的**墨迹中心与椭圆中心偏差都 ≤0.5px**。

**自动适配**：按 `u` 算出字号后，若整块内容超出椭圆内接矩形，再整体等比缩小
（原版靠字号随挂件缩放；这里多兜一层，保证长句不会戳出气泡）。

## 说话弹出（对齐原版）

原版前端（`whale-widget.js`）的气泡是三层 SVG 错时"充气"+ 文字延迟淡入：

```css
/* 开：b2 延迟 0s → b1 0.13s → bshape 0.26s，各 0.2s 从 scale(.7) 到 1 */
.dshwv-pop .dshwv-b1,.dshwv-b2,.dshwv-bshape{opacity:0;transform:scale(.7)}
.dshwv-pop.dshwv-pop-open .dshwv-text{opacity:1;transition:opacity .16s ease .36s}
/* 关：延迟反向（bshape .1s → b1 .2s → b2 .3s） */
```

这里按同一时序复刻（卡通用于**同一个时间轴**）：

| 阶段 | 时间 | 表现 |
|---|---|---|
| 气球成形 | 0 → 0.46s | 气球层 `scale 0.7 → 1.0`（ease-out），窗口整体 `alpha 0.35 → 1.0` |
| 文字出现 | 0.36s 起 | 内容层（文字/图片/按钮）叠上去 |
| 收起 | 0 → 0.32s | `scale → 0.7`、`alpha → 0`（ease-in），文字先撤 |

> **实现要点（踩过的坑）**：色键透明 `-transparentcolor` **没有"半透明"**，只有全透/全不透 ——
> 把半透明的图贴到键色底上只会混出**品红鬼影**。所以淡入必须走**窗口级 `-alpha`**
> （已用 `GetLayeredWindowAttributes` 验证：`LWA_COLORKEY` 与 `LWA_ALPHA` 同时置位，
> 淡入期间色键仍然生效），缩放则走重绘。

**点击语义也对齐原版**：

- **点鲸鱼**：没泡泡 → 从第 1 项开始；正显示第 1 项 → 只**续时**不清内容；
  第 2 项及以后 → 回到第 1 项；**系统提醒（预警/消耗）期间点鲸鱼不动作**
- **点泡泡**：跳到下一项；已是最后一项则收起；系统提醒则是关掉它（接着放队列里的下一条）
- **系统提醒优先级队列**：今日预算(1) > 余额预警(2) > 本轮消耗(3) > 等待交互(4)；
  **同档「每轮消耗」后入先出**（新一轮插到旧的前面 ⇒ 新的置顶、旧的排队），其它档先入先出
- **停留时长**：余额预警 6.5s（原版 `USAGE_ALERT_TTL`）、每轮消耗按
  `.dshw-size.json` 的 `turnCostCloseMs`、随机台词 5s；到点自动收起并接着放下一条

## 余额预警（阈值可设）

- 菜单 →「预警阈值：余额 ≤ ¥5…」可改（默认 **¥5**，取自 DSH 的设置）
- 触发判定与原版一致：**余额 > 0 且 余额 ≤ 阈值** → 弹出预警卡（并且响一声）；
  余额回升到阈值以上后**重新武装**，下次再跌破会再提醒一次；同一次跌破不会重复弹
- 余额取不到 / 为 0 时不提醒；余额每 60 秒刷新一次，也可以双击挂件手动刷
- 阈值与开关只写本挂件自己的 `~/.dsh/.dshw-py-pet.json`，**不会动** DSH 的账本文件

## 吸附与翻转（对齐原版）

- **贴边吸附**：鲸鱼本体进入左/右/上/下吸附区就贴到该边，角落可组合；
  吸附区宽度按显示器**可用区域**（`rcWork`，自动避开任务栏）的百分比 ——
  默认左右 10%、上 0%（关）、下 15%，与 DSH 原版 v3 一致
- **镜像翻转**：鲸鱼中心越过**翻转线**（默认屏宽 50%）就整体水平镜像，回到右侧自动翻回
- 菜单「吸附与翻转」里可切换 吸附区宽度（窄/默认/宽）、翻转线（25%/50%/75%）、立即校正
- 默认**只翻鲸鱼，不翻文字**（台词与金额保持可读）；想要原版那种"文字一起反向"，
  勾上「镜像时文字也反向（原版样式）」

- **全局穿透**：整只挂件不吃鼠标（临时想让下面的窗口可点时用）。
- **点击不抢焦点**：给窗口加 `WS_EX_NOACTIVATE`，点挂件不会把焦点从你正在打字的窗口抢走。

## 它读的是 DSH 的同一份数据

挂件不复制、不缓存、不中转，直接读 DSH 已经落地的文件：

| 文件 | 用途 |
|---|---|
| `~/.dsh/.credentials.yaml` | 取 `DEEPSEEK_API_KEY`（环境变量优先） |
| `~/.dsh/.dshw-size.json` | 缩放、音效开关、音量、音效组、每轮消耗开关 |
| `~/.dsh/.dshw-usage.json` | 今日已用、账本历史、`events` 里的逐轮消耗 |
| `~/.dsh/.dshw-turn.json` | 每轮消耗的 seq（用来判断"又聊了一轮"） |

余额直接请求 `https://api.deepseek.com/user/balance`（默认 60 秒一次）。
本挂件自己的状态只写 `~/.dsh/.dshw-py-pet.json`，**不会碰上面任何 DSH 文件**。

## 自检与排错

```powershell
# 不显示界面，打印一份 JSON 诊断（素材/窗口样式/余额/账本/自启状态）
python dsh_whale_pet.py --selftest

# 离屏合成预览图（棋盘底 + 鲸鱼 + 气泡），用来核对构图
python dsh_whale_pet.py --snapshot preview.png

# 抓某个窗口自身的像素（分层/透明窗口不会出现在普通截屏里）
python capture_window.py "DSH 小鲸鱼桌面挂件" pet-window.png
```

日志写在 `~/.dsh/.dshw-py-pet.log`（该目录不可写时自动退回脚本目录）。
启动参数写错、素材缺失、余额接口失败都会记在这里。

常见问题：

- **看不到挂件**：先 `--selftest` 看 `sprite.content` 和 `window` 尺寸是否正常；
  再用 `capture_window.py` 抓一张窗口像素图 —— 如果抓得到鲸鱼，说明窗口本身没问题，
  多半是被全屏/顶层窗口盖住了（菜单里切一下"始终置顶"）。
- **没声音**：`assets/` 里没 mp3/wav，或菜单里"音效"被关了；mp3 走 MCI，
  系统缺 MPEG 解码时会静默降级（log 里有记录）。
- **点击穿透失效**：色键透明依赖 `-transparentcolor`（Windows 专有）。
  菜单里的"全局穿透"是另一回事 —— 它让**整只**挂件都不吃鼠标。
- **挂件太靠边/跑到屏幕外**：右键 →"回到右下角"。

## 技术要点

- **透明 + 逐像素穿透**：窗口背景设为色键 `#ff00fe`，用 Tk 的 `-transparentcolor`；
  Windows 下色键像素既透明、也不参与命中测试，所以"只有鲸鱼可点"是系统层面成立的，
  不需要自己算形状。代价是半透明边缘会和键色混出彩边，所以贴图 alpha 被二值化（硬边）。
- **高清 DPI**：启动时声明 `SetProcessDpiAwareness(2)`（per-monitor），并按窗口所在显示器的
  DPI 放大贴图与字号（144 DPI → 界面 ×1.5）。不声明的话，Windows 会把整个窗口**位图拉伸**，
  在 125%/150% 的屏幕上就是糊的。跨屏拖动会每 2 秒复查一次 DPI，变了就重建尺寸与帧表。
- **平滑（关键）**：动画的每一档形变都在启动时**预渲染**成窗口整图（25 帧），
  运行时每帧只做一次 `canvas.itemconfig` 换图 —— 没有 LANCZOS 缩放、色键合成、
  新建画布或 PhotoImage 重建。实测单帧开销 **0.009–0.011ms**（60fps 预算 16.7ms），
  余量 100%。缓动用**时间差**推进（`1-exp(-dt·k)`），所以帧率波动时手感一致。
- **Q 弹**：按压不是等比缩小，而是**横向鼓起 3.85% + 纵向压扁 11%**（底边中心锚定不动）。
- **窗口尺寸不变**：窗口比贴图大一圈（`WINDOW_MARGIN`），形变都在窗口内部重绘，
  避免动画期间反复改窗口造成闪烁与坐标漂移。
- **缩放基准是内容包围盒**：源图 610×610 且四周有透明留白，1.0× = 鲸鱼本体约 206px
  （再乘 DPI 缩放），和 DSH Web 挂件里的观感一致。
- **气泡锚在鲸鱼头顶**：位置由鲸鱼本体的实际上沿算出（不是锚在窗口上），
  水平居中于鲸鱼；屏幕上方放不下时自动翻到下方并把尾巴朝上。定位用显示器的
  `rcWork`（自动避开任务栏）。

## 文件

| 文件 | 作用 |
|---|---|
| `dsh_whale_pet.py` | 主程序：窗口、交互、动画、菜单、自启、气泡调度、吸附翻转 |
| `whale_data.py` | 数据层：凭据 / 余额接口 / 账本 / 设置 |
| `whale_audio.py` | 音频层：MCI 播 mp3、winsound 播 wav |
| `whale_bubble.py` | 图形层：色键合成、文本气泡绘制、GIF 拆帧 |
| `whale_card.py` | 卡片层：按原版模块结构渲染提醒卡片（文本/底色块/图片/可点按钮） |
| `capture_window.py` | 调试工具：抓分层窗口自身像素 |
| `小鲸鱼挂件.pyw` | 双击启动（无控制台窗口） |
| `启动小鲸鱼挂件.vbs` | 同上，绕开 .pyw 关联问题 |

## 打包成 exe（可选）

```powershell
python -m pip install pyinstaller
pyinstaller --noconsole --onefile --add-data "..\assets;assets" dsh_whale_pet.py
```

打包后 `assets/` 会随 exe 一起走；若不打包素材，就用 `DSHW_ASSETS` 指向现成的 `assets/`。
