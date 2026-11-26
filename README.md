# pymat

**一个用 Python 写的科学计算桌面，界面基于上一个文件夹的
[pydui](../pydui)（dui 的 Python 绑定）。**

这是一个 Python 工作台，不是 MATLAB 克隆：没有 M 语言、没有 M 语法翻译、也没有
MATLAB 风格函数名。桌面里直接写普通 Python，`numpy` / `pandas` / `scipy` /
`matplotlib` 已经以常用别名注入命名空间：

```python
np   numpy        pd  pandas        sp  scipy        plt  matplotlib.pyplot
```

```python
A = np.array([[4.0, -2.0], [1.0, 1.0]])
b = np.array([6.0, 3.0])
x = np.linalg.solve(A, b)

df = pd.DataFrame({"x": [1, 2, 3], "y": [3, 1, 2]})
print(df.describe())

plt.plot(df["x"], df["y"], "o-")
plt.title("a normal matplotlib plot")
plt.show()
```

## 环境

已经创建 conda 环境 `pymat`（Python 3.14），安装 numpy / pandas / scipy /
matplotlib。重新搭建：

```sh
./setup_env.sh
# 或者手动：
conda create -n pymat python=3.14 -y
conda activate pymat
pip install numpy pandas scipy matplotlib
pip install -e .
# 让 pydui 可导入（setup_env.sh 也会自动写入）：
echo "$PWD/../pydui/python" > "$(python -c 'import site;print(site.getsitepackages()[0])')/pydui-local.pth"
```

`pydui` 使用 `../pydui` 已经构建好的 `_native` 扩展；它没有发布到 PyPI，所以
以本地路径接入。`run.sh` 也会设置 `PYTHONPATH`。

## 运行

```sh
./run.sh                       # 打开桌面
./run.sh --cli                 # 终端 REPL
./run.sh -e 'print(np.arange(5) ** 2)'
./run.sh examples/numpy_pandas.py
./run.sh examples/plot_demo.py

python -m pymat                # 等价入口（环境已激活时）
pymat                          # pip install -e . 之后的命令
```

## 桌面布局

经典科学 IDE 排列：左侧是文件和变量，右上是编辑器，右下是控制台。

```
┌──────────────────────────────────────────────┐
│ pymat 工具栏：New / Open / Save / Run ...      │
├──────────────┬───────────────────────────────┤
│ FILES        │  welcome.py                   │
│  当前目录     │  行号 │ 高亮代码                │
│  文件树       │       │                       │
│              │       │                       │
│ WORKSPACE    │───────┴───────────────────────│
│  变量列表     │ CONSOLE                       │
│              │ >>> np.arange(5)              │
│              │ array([0, 1, 2, 3, 4])        │
│              │ >>>                           │
├──────────────┴───────────────────────────────┤
│ 状态栏                                        │
└──────────────────────────────────────────────┘
```

- **FILES**（左上）：树形目录，单击文件夹展开/折叠，单击文件直接在右侧编辑器打开；
  带文件夹/文件图标、选中高亮，支持 Up/刷新。
- **WORKSPACE**（左下）：变量名、shape、类型、预览；支持 numpy、pandas、matplotlib Figure。
- FILES 和 WORKSPACE 之间、编辑器与 Console 之间都有**可拖动分隔条**。
- **Editor**（右上）：多标签、未保存显示 `*`、Run / Save / 关闭标签；Python 语法高亮、
  行号栏、`Ln, Col`、与高亮层同步滚动。
- **Console**（编辑器正下方，不再横跨左侧栏）：Python REPL，`↑`/`↓` 翻历史；
  赋值不打印，表达式打印 `repr` 并存入 `_`；多行块自动续行，`Esc` 取消。
  编辑器与 Console 之间有可**上下拖动**的分隔条。
- **Figure**：`plt.show()` 不弹 Tk/Qt 窗口，而是把 matplotlib 图形显示成 pymat 窗口。

## 直接使用标准库

控制台没有自定义的数值函数层，标准库怎么用就怎么写：

```python
np.linspace(0, 2*np.pi, 200)
np.linalg.solve(A, b)
np.fft.fft(signal)
pd.read_csv("data.csv")
df.groupby("key").mean()
sp.optimize.minimize(f, x0)
sp.stats.norm.pdf(x, mu, sigma)
sp.signal.butter(4, 0.2)
plt.plot(x, y); plt.xlabel("x"); plt.show()
```

命名空间里另有 `linalg`、`optimize`、`stats`、`signal`、`interpolate`、
`integrate`、`math`、`random`，省去重复 import。

## pysimu：块图仿真

工具栏的 **pysimu** 按钮打开一个 Simulink 风格的块图窗口（参考 simupy 的
`DynamicalSystem` + `BlockDiagram` 思路，但由 pymat 自己维护）：

- 左侧 Block Library 按 Simulink 风格分组，可上下/左右滚动：
  - Sources：Step / Sine / Constant / Ramp / Clock / Pulse
  - Sinks：Scope / Terminator
  - Continuous：Integrator / Derivative / Transfer Fcn / State Space / PID
  - Math：Gain / Sum / Product / Divide / Abs / Math Function / MinMax /
    Sign / Saturation
  - Signal：Bias / Dead Zone
  - Logic：Compare / Switch / Logical Op
  
  每个 block 都有自己的小图标。Derivative 使用带时间常数 `tau` 的滤波微分，
  避免纯微分带来的代数环。右侧画布也可以上下/左右滚动，图很大时能平移查看。
- 添加块：单击图标，或从左侧把图标拖到右侧画布上。拖动时跟随鼠标的是完整的
  块预览（外框、左侧图标、标题和参数），放下后直接成为画布上的块。
- 画布上的每个块顶部也带自己的图标，不再只是纯方框。
- Block Library 和画布之间有一条可左右拖动的分隔条，可以按需要调整两边宽度。
- 画布是白色点阵底；块可以拖动，尺寸更紧凑。
- 单击块就会选中它，并把光标放进 `params` 输入框、全选当前参数；改完点
  `Apply` 或回车。双击效果相同。
- 块面只显示紧凑的参数摘要（如 `order 2`、`Kp=1 Ki=0`）；摘要过长会截断成
  `…`，完整参数放在鼠标悬停 tooltip 和 `params` 输入框里。
- 手动连线：从块右侧的绿色输出点按住拖到目标块或左侧蓝色输入点即可
  （Sum 这类多输入块会按落点选择对应端口）。也可以点 `Connect` 后再点源块、
  目标块，自动选第一个空闲端口。
- 连线会自动绕开中间的块；反馈线走块下方，不再穿过块。
- 连线可以用鼠标按住拖动：水平段上下移动，竖直段左右移动，手动调整走线位置。
- 单击块会显示蓝色边框和浅蓝底；单击连线会变成蓝色线。
  右键连线弹出删除菜单，按 `Delete` 也能删除选中的线。
- 块右键菜单：编辑参数 / 复制块 / 断开连线 / 删除块。
- `params` 输入框可以修改选中块的参数，例如 `gain=2` 或
  `num=[1]; den=[1,2,1]`，点 Apply 生效。
- `Run` 用 `scipy.integrate.solve_ivp` 仿真，Scope 信号通过 matplotlib 显示在
  pymat 图窗里。
- `Save` / `Load` 保存块图 JSON（默认 `pysimu/pysimu_diagram.json`）。
- 首次打开是空白画布，不再自动插入示例块；如果当前目录存在
  `pysimu_diagram.json`，会自动加载上次保存的图。

引擎位于 `pymat/sim/`：

| 文件 | 内容 |
|---|---|
| `blocks.py` | 块类型、状态初值、输出/导数 |
| `diagram.py` | 连线、拓扑排序、代数环检测、`solve_ivp` 仿真、JSON |
| `gui.py` | dui 块图窗口、拖动块、连线绘制、运行/保存/加载 |

当前支持标量信号和连续时间；代数环必须由 Integrator 或 `D=0` 的传递函数打破，
否则会明确报错。

## 代码高亮实现

dui 的 `RichEdit` 没有“可编辑富文本”接口，所以编辑器用两层严格对齐的控件：

- 底层只读 `RichText`：显示彩色 Python 代码（只用颜色，不用粗体/斜体，避免改变字宽）；
- 上层透明文字 `RichEdit`：负责输入、光标、选区、撤销、鼠标定位和滚动；
- 独立的行号 `RichText`：与编辑区同步垂直滚动。

两层使用同一字体、padding、行距；测试会校验：

```text
colored scroll range == edit scroll range
gutter scroll range  == edit scroll range
scroll x/y 同步一致
```

高亮由 Python 标准库 `tokenize` 完成；输入到一半、代码暂时不合法时退化为正则高亮，
不会中断编辑。RichText 底层的 pugixml 会丢弃“纯空白”文本节点（会导致缩进和词间空格
消失），所以生成 markup 时会把空白段并入相邻的非空段，缩进和空格都保留。

## 代码结构

```
pymat/
  session.py        Python 命名空间、REPL、workspace
  mpl.py            matplotlib <-> dui 图窗桥接（plt.show/close 接管）
  cli.py            GUI/REPL/脚本入口
  gui/
    main_window.py   两栏主窗口：左 Console/Workspace/Files，右编辑器
    code_editor.py   语法高亮 + 行号 + 滚动同步
    figure_window.py matplotlib 图窗（PNG 背景图 + 缩放重绘）
    app.py           Session + 主窗口 + 图窗接线
    theme.py         配色、语法色板与小组件
tests/
  test_core.py         命名空间 / numpy / pandas / scipy / matplotlib
  test_code_editor.py  高亮 markup、行高与滚动同步
  test_gui_smoke.py    真实 dui 窗口里 Run 示例、开图、工作区
  test_layout.py       两栏布局与控件几何
  test_live_editor.py  消息循环内输入后高亮刷新
  test_live_plot.py    消息循环内 plt.show() 开图
  test_sim.py          pysimu 引擎 / 块图窗口 / 保存加载
examples/
  numpy_pandas.py      numpy / pandas / scipy
  plot_demo.py         matplotlib
```

## 测试

```sh
conda activate pymat
python tests/test_core.py          # 无 GUI
python tests/test_code_editor.py   # 需要桌面会话
python tests/test_gui_smoke.py
python tests/test_layout.py
python tests/test_live_editor.py
python tests/test_live_plot.py
```

## 许可

MIT。`pydui` / `dui` 的许可见各自仓库。
