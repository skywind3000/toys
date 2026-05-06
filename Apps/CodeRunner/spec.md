# CodeRunner 技术规格

## 1. 架构概览

MainWindow 为 QMainWindow，从上到下五个区域：

```
MenuBar → Toolbar → TabBar → MainArea → StatusLine
```

- **MainArea**：QSplitter 水平分割 → 左侧 CodeEditor | 右侧 QSplitter 垂直分割 → InputSection + OutputSection
- **单一 Widget 组**：每个标签页持有三个独立 QTextDocument（editor_doc / input_doc / output_doc），切换标签时通过 `setDocument()` 交换文档，Widget 不销毁重建。Splitter 位置全局共享
- **状态栏**：左侧 QLabel 仅显示状态机当前状态；右侧 QLabel 显示光标位置/编码/编辑模式
- **主题**：Fusion，Toolbar 七个按钮使用 QPainter 自绘彩色图标（详见第 8 节）

### 类列表

| 类 | 基类 | 职责 |
|----|------|------|
| MainWindow | QMainWindow | 主窗口，协调所有组件 |
| CodeEditor | QTextEdit | 代码编辑器（因 PyQt5 QPlainTextEdit.setDocument() 不工作而改用 QTextEdit，setAcceptRichText=False）|
| LineNumberArea | QWidget | 行号区域，paintEvent 委托给 CodeEditor |
| CppHighlighter | QSyntaxHighlighter | C++ 语法高亮 |
| InputPanel | QTextEdit | 输入面板（同 CodeEditor 原因改用 QTextEdit）|
| OutputPanel | QTextEdit | 输出面板（只读，支持多色富文本）|
| TabData | object | 单个标签页的全部状态数据 |
| TabManager | object | 纯数据管理器，无 UI 操作，不持有 main_window 引用 |
| ProcessManager | QObject | 编译/运行进程管理（QProcess），busy/mode 由状态机驱动 |
| EncodingManager | object | 编码检测、编译标志生成、I/O 编码转换 |
| Settings | object | 配置数据，实例化设计，支持 copy()/apply_from() |
| SettingsDialog | QDialog | 设置面板（三页 Tab）|
| FindDialog | QDialog | 非模态查找对话框 |
| ReplaceDialog | QDialog | 非模态替换对话框 |

## 2. 数据模型

### 2.1 TabData

```python
class TabData:
    file_path: str              # None = 新文件
    is_new: bool                # True = 从未保存到磁盘
    is_dirty: bool              # True = 有未保存更改
    editor_doc: QTextDocument   # 含 undo/redo 栈
    input_doc: QTextDocument
    output_doc: QTextDocument   # 含富文本颜色
    cursor: QTextCursor         # 编辑器光标位置
    scroll_pos: int             # 编辑器垂直滚动条位置
    input_cursor: QTextCursor
    input_scroll: int
    encoding: str               # 'UTF-8' 或系统编码名
    zoom_font_size: int         # 会话级，不持久化
    compiler_mtime: float       # 上次编译时的参数修改时间戳
    _highlight_pending: bool    # 分批高亮尚未完成
```

**标签名规则**：is_new+dirty → `*untitledN*`；is_new+非dirty → `untitledN`；已保存+dirty → `*filename*`；已保存+非dirty → `filename`

**CppHighlighter 挂载**：TabData 创建时 `CppHighlighter(editor_doc, deferred=True)` 挂载到 editor_doc，生命周期与 TabData 一致。deferred 模式下 highlightBlock 仅追踪多行注释状态，不产生 format spans，避免大文件打开瓶颈。分批高亮由 `_start_batch_highlight` 在文档显示后触发。

**脏标记信号**：每个 TabData 的 `editor_doc.modificationChanged` 信号连接到该 TabData 的 dirty 标记逻辑，信号跟随 document 生命周期，不受 Widget 切换影响。

### 2.2 TabManager

```python
class TabManager:
    tabs: list              # TabData 列表
    current_index: int      # -1 = 无标签（零标签状态）
    untitled_counter: int   # untitled 编号递增器
```

纯数据管理器，不操作 Widget。所有 UI 操作由 MainWindow 负责。首次启动 `current_index = -1`，关闭最后一个标签后重新进入零标签状态。

**Switch Tab 快捷键**：Alt+1~Alt+9 切换到第 1~9 个标签，Alt+0 切换到第 10 个。超出数量时忽略。

### 2.3 标签切换机制

由 MainWindow._switch_to_tab 实现：

1. 保存旧标签 Widget 状态（cursor、scroll_pos、input_cursor、input_scroll）
2. `setUpdatesEnabled(False)` 冻结重绘
3. 交换 document：`editor.setDocument(new_tab.editor_doc)` 等
4. 恢复 IO 面板光标（小文档，无延迟）
5. `setUpdatesEnabled(True)` 解冻 — 文档内容瞬间显示
6. `QTimer.singleShot(0)` 延迟恢复编辑器光标和滚动位置（避免 setTextCursor 的全文档布局开销，7500 行文件约 1.2s → 延迟后 ~3ms 显示内容）
7. 延迟回调检查标签索引是否仍是当前标签，防止快速切换竞态

**文档字体同步**：CodeEditor/InputPanel/OutputPanel 的 `setDocument()` 重写中调用 `doc.setDefaultFont(self.font())`。文档布局（Tab 定位等）使用 `defaultFont` 计算，字体不一致会导致 Tab 显示宽度错误。

### 2.4 零标签状态

QTextEdit 始终持有一个 QTextDocument，不能为 null。采用**初始 document 占位**策略：

- MainWindow.__init__ 保存三个 Widget 自带的初始空 QTextDocument（`self.empty_editor_doc` 等）
- 进入零标签状态：切回空 document，三个面板 `setEnabled(False)` 灰显，状态栏右侧清空
- 恢复：切回新标签 document，面板 `setEnabled(True)`

### 2.5 Settings

实例化设计（__init__ 从 `_SETTINGS_DEFAULTS` 拷贝到实例属性），从 `~/.config/coderunner/settings.json` 读写：

```python
_SETTINGS_DEFAULTS = {
    'compiler_path': 'gcc',
    'compiler_flags': '',
    'env_vars': {},
    'run_timeout': 10,
    'compile_timeout': 20,
    'editor_font_family': '',   # set by _init_font_defaults()
    'editor_font_size': 11,
    'io_font_family': '',       # set by _init_font_defaults()
    'io_font_size': 11,
    'bracket_completion': True,
    'indent_style': 'tab',      # 'tab' or 'space'
    'indent_size': 4,           # tab 宽度 / 空格缩进步长
    'word_wrap': False,
    'compiler_mtime': 0,        # 编译参数最后修改时间戳
    'template_text': '...',
}
```

**关键设计要点**：
- MainWindow 持有唯一 `self.settings` 实例，所有代码通过 `self.settings.xxx` 访问
- SettingsDialog 操作 `settings.copy()` 临时副本，OK 时 `apply_from(copy)` 提交，Cancel 丢弃副本
- 修改 compiler_path/flags/env_vars 时记录 `compiler_mtime = time.time()`，`_apply_settings()` 将所有 TabData 的 compiler_mtime 更新为 settings.compiler_mtime（若旧值更小）
- env_vars 的值中 `$VAR_NAME` 语法在运行时展开为实际环境变量值
- editor_font_family / io_font_family 默认值按平台自动检测 monospace 字体（Windows: Consolas→Courier New→monospace；macOS: Menlo→SF Mono→monospace；Linux: DejaVu Sans Mono→Ubuntu Mono→monospace）

### 2.6 Settings JSON 格式

```json
{
    "compiler_path": "gcc",
    "compiler_flags": "",
    "env_vars": {"PATH": "$PATH;/custom/bin"},
    "run_timeout": 10,
    "compile_timeout": 20,
    "editor_font_family": "Consolas",
    "editor_font_size": 11,
    "io_font_family": "Consolas",
    "io_font_size": 11,
    "bracket_completion": true,
    "indent_style": "tab",
    "indent_size": 4,
    "word_wrap": false,
    "compiler_mtime": 0,
    "template_text": "#include <iostream>\n..."
}
```

首次运行不存在时使用默认值。`load()` 只加载 `_SETTINGS_DEFAULTS` 中存在的键，忽略未知键。

### 2.7 Window State JSON 格式

`~/.cache/coderunner/window.json`：

```json
{
    "geometry": {"x": 100, "y": 100, "w": 1000, "h": 650},
    "h_splitter": [500, 500],
    "v_splitter": [325, 325],
    "last_file_dir": "C:/Users/xxx/Documents",
    "tabs": [
        {"file_path": "C:/Users/xxx/test.cpp", "input_text": "3 5"},
        {"is_new": true, "editor_text": "...", "input_text": "", "untitled_number": 3}
    ],
    "active_tab": 0,
    "recent_files": ["C:/Users/xxx/test.cpp"]
}
```

- recent_files 最多 10 条，按时间倒序
- OutputPanel 内容不持久化，重启后为空
- 恢复新文件标签时 `is_dirty=True` + `editor_doc.setModified(True)`
- 恢复已保存文件时跳过已删除文件

## 3. 编辑器组件

### 3.1 CodeEditor

继承 QTextEdit（setAcceptRichText=False），核心功能：

**行号显示**：左侧 LineNumberArea 作为子 Widget，宽度按最大行号位数动态调整。`_paint_line_numbers` 通过 `_estimate_first_visible_block()` 估算首个可见 block，仅迭代可见区域（7500+ 行文件滚动到底部仅迭代约 50 个 block）。

**Tab 制表符**：插入 `\t`，不转换为空格。Tab 宽度 = `fontMetrics().horizontalAdvance('x') * indent_size`，indent_size 默认 4，可在 Settings 中配置。

**字体变更联动**：更换字体或字号时，必须调用 `updateFontMetrics()` 重新计算 Tab 宽度，并同步 `document.setDefaultFont(editor.font())`，否则 Tab 显示宽度错误。

**括号补全**：输入开符号自动插入闭符号并光标置中间；输入闭符号时光标右侧恰好同一闭符号则跳过；删除开符号时右侧紧邻闭符号一并删除。可通过 Settings 开关控制（默认开启）。

**自动缩进**：Enter 键 — 取当前行前导空白作为新行基础缩进；当前行末 `{` 时增加一级缩进（indent_style='tab' 加 `\t`，indent_style='space' 加 `indent_size` 个空格）；下一行以 `}` 开头且当前行是 `{` 时 `}` 行减少一级缩进。

**Smart Backspace**：光标无选区、列号在缩进整数倍边界、左侧到行首全是空格时，一次删除 indent_size 个空格。不限定 indent_style。

**改写模式**：Insert 键切换 overwrite_mode，输入字符时先删除光标右侧一个字符再插入。状态栏显示 INS/OVR。Paste 操作不受改写模式影响。

**Zoom**：Ctrl++ 放大字号（步长 1pt），Ctrl+- 缩小（最小 6pt）。仅改 CodeEditor，不影响 IO 面板；会话级不持久化。字号存入 TabData.zoom_font_size。

### 3.2 CppHighlighter

规则分组与颜色：

| 分组 | 颜色 |
|------|------|
| 关键字 `\b(int|float|...)\b` | 蓝色（非粗体） |
| 预处理器 `^#\s*(include|define|...)` | 蓝色 |
| 字符串 `"..."` | 深红色 |
| 字符 `'.'` | 深红色 |
| 单行注释 `//[^\n]*` | 绿色 |
| 多行注释 `/\*...\*/` | 绿色 |
| 数字（含十六进制、二进制） | 深蓝色 |
| 符号/运算符 | 深青色 |

规则顺序决定优先级（first-match-wins）：单行注释 → 字符串 → 字符 → 关键字 → 预处理器 → 数字 → 符号。多行注释在单行规则之后单独处理，直接 `setFormat` 覆盖已有格式。多行注释使用 `setCurrentBlockState/previousBlockState` 跟踪跨块状态。

**延迟+分批高亮**：deferred=True 模式下 highlightBlock 仅追踪多行注释状态不产生 format spans；文档先以无高亮状态显示（layout 快 ~0.5s）；`_switch_to_tab` 通过 `QTimer.singleShot(0)` 触发 `_start_batch_highlight`；每批 rehighlightBlock 100 个 block，批间 `QTimer.singleShot(0)` 保持 UI 响应；切换标签时取消旧标签的 batch highlighting，设置 `_highlight_pending=True`。

### 3.3 InputPanel

继承 QTextEdit（setAcceptRichText=False），外层 `_make_io_section` 包装（QWidget + QLabel "INPUT"）。字号/字体跟随 Settings.io_font_family/io_font_size。Tab 键插入制表符，tabStopWidth = `indent_size * charWidth`。setDocument() 重写中同步文档字体。零标签状态下灰显。

### 3.4 OutputPanel

继承 QTextEdit，外层 `_make_io_section` 包装（QWidget + QLabel "OUTPUT"）。只读，支持多色富文本。

**自动滚动**：仅当滚动条已在底部时才自动跟随新输出。用户翻看历史输出时不被强制拉回底部。按 END 键可回到底部跟踪模式。滚动通过 per-tab 的 `_need_scroll` 标志和 50ms 共享 QTimer 批量执行，避免逐行滚动影响性能。每次 `_output_clear` 后视为"在底部"，新内容开始后默认自动跟踪。`_is_output_at_bottom()` 判断滚动条距离底部不超过 3px 即视为在底部。

**颜色规范**：

| 内容类型 | 颜色 |
|----------|------|
| stdout | 默认前景色（QPalette.Text） |
| stderr | 灰色 |
| 退出状态行 / Build 成功 / Process stopped | 灰色 |
| 编译错误 / Runtime Error / 超时 / Failed to start | 红色 |

**退出状态行换行**：所有运行结果行（exit with code、Runtime Error、Timeout、Process stopped、Program crashed）前追加 `\n`，确保程序输出不以换行结尾时（如 `printf("0")`）状态行不接在输出末尾。

每次 Test/Build 清空后重新写入全部内容，不追加。

## 4. 编译运行系统

### 4.1 ProcessManager

```python
class ProcessManager(QObject):
    process: QProcess
    busy: bool                # 由状态机驱动
    mode: str                 # 'compile' / 'test_run' / None
    target_tab: TabData       # 输出路由目标

    signals:
        compile_finished(exit_code, stderr_text, reason)
        run_finished(exit_code, elapsed, peak_memory, reason)
        run_stdout_ready(text)
        run_stderr_ready(text)
```

**reason 参数**：统一传达退出原因，消除信号竞争。

| reason | 含义 | 触发场景 |
|--------|------|----------|
| normal | 正常退出 | 进程正常结束 |
| killed | 被 kill 终止 | 用户 Stop 或自然崩溃（CrashExit） |
| timeout | 超时 | QTimer 超时，先 kill 再 emit |
| failed_to_start | 无法启动 | waitForStarted 返回 False |

防止二次 emit：`_finished_emitted` 标志位。

**killed 分支行为**：自然崩溃（如 Windows access violation）QProcess 报 CrashExit + 负 exit code，`_describe_exit_code` 附加已知 NTSTATUS 码可读描述（红色），无描述时显示灰色 "Process stopped"。

**输出路由**：启动 Test/Build 时记录 `target_tab`，stdout/stderr 和结束信号始终写入 `target_tab.output_doc`，不受标签切换影响。

**QProcess 配置**：SeparateChannels；编译进程只读 stderr；运行进程分别读 stdout/stderr；Test 模式写入 stdin 后 closeWriteChannel()。

### 4.2 状态机

MainWindow 使用显式状态机：`_flow_state`（IDLE/COMPILING/RUNNING）、`_flow_intent`（build/test/run）、`_flow_tab`。

| 状态 | status bar | 按钮响应 |
|------|------------|----------|
| IDLE | Ready | Build/Test/Run 正常，Stop 无效 |
| COMPILING | Compiling... | Build/Test/Run 弹 Busy 提示，Stop → killed |
| RUNNING | Running... | 同 COMPILING |

按钮**保持可点击，不禁用灰显**，busy 时弹提示。IDLE 下 Stop 静默忽略。

**状态转移表**：

```
IDLE +Build(需编译)       → COMPILING(intent=build)
IDLE +Test(需编译)        → COMPILING(intent=test)
IDLE +Test(不需编译)      → RUNNING
IDLE +Run(需编译)         → COMPILING(intent=run)
IDLE +Run(不需编译)       → IDLE（弹外部终端）

COMPILING +normal(exit0)+build → IDLE（"Build OK"）
COMPILING +normal(exit0)+test  → RUNNING
COMPILING +normal(exit0)+run   → IDLE（弹外部终端）
COMPILING +normal(exit≠0)      → IDLE（红色错误）
COMPILING +failed_to_start     → IDLE（"Failed to start compiler" + Settings 提示）
COMPILING +timeout             → IDLE（"Compilation timeout"）
COMPILING +killed              → IDLE（"Compilation stopped"）

RUNNING +normal(exit0)         → IDLE（灰色退出状态行）
RUNNING +normal(exit≠0)        → IDLE（红色 "Runtime Error"）
RUNNING +failed_to_start       → IDLE（"Failed to start program"）
RUNNING +timeout               → IDLE（红色 "Timeout after Xs"）
RUNNING +killed(crash描述)     → IDLE（红色 "Program crashed"）
RUNNING +killed(无描述)        → IDLE（灰色 "Process stopped"）
```

**重编译判断**：exe 不存在 / exe_mtime < source_mtime / exe_mtime < tab.compiler_mtime → 需要重编译。

### 4.3 编译命令

`_build_compile_command` 生成的完整命令：

```
[resolved_compiler] [编码flags] [用户compiler_flags] source.cpp -o source.exe -lstdc++
```

- `resolved_compiler`：通过 `_resolve_compiler_path` 解析 compiler_path（裸名→原值，绝对路径→原值+取bin_dir，相对路径→基于 __file__ resolve 成绝对路径+取bin_dir）
- 编码 flags 由 EncodingManager.build_flags 生成（详见第 5 节）
- `-lstdc++` 末尾固定追加，确保误选 gcc 时也能链接 C++ 标准库

### 4.4 PATH 注入

compiler_path 含路径组件时，自动将编译器所在目录 prepend 到 PATH：

- `_resolve_compiler_path(compiler_path)` 返回 `(resolved_path, bin_dir)`，bin_dir 为空字符串时（裸名）不修改 PATH
- `_make_process_env()` 在 bin_dir 非空时 prepend 到 PATH 前端（Windows 用 `;` 分隔，其他平台用 `:`）
- 编译进程和 Test 运行进程均通过此 QProcessEnvironment 获得正确的 PATH
- 不修改 CodeRunner 主进程 PATH，每个子进程获得干净独立的 PATH

### 4.5 Run 外部终端（Windows）

使用固定路径 `%TEMP%\coderunner.cmd`：

```batch
@echo off
if defined CR_PATH_PREFIX set PATH=%CR_PATH_PREFIX%;%PATH%
call %CR_COMMAND%
set CR_EXITCODE=%ERRORLEVEL%
call %CR_PAUSE%
exit %CR_EXITCODE%
```

环境变量：CR_COMMAND（exe 路径）、CR_PAUSE（`pause` 或 `rem`）、CR_PATH_PREFIX（compiler bin_dir，裸名时不设置）。

设计要点：固定文件名避免残留垃圾；固定内容消除并发竞态；环境变量隔离天然安全。

启动流程：检查/创建 bat → 临时设 os.environ → QProcess.startDetached → 还原 os.environ。

### 4.6 内存占用采集

如果 `psutil` 可用：进程启动后 QTimer（100ms 间隔）轮询 `psutil.Process(pid).memory_info()`，记录 rss 峰值到 `peak_memory`。NoSuchProcess 异常忽略（进程已结束）。进程结束时停止 QTimer，将 peak_memory 追加到退出状态行（如 "exit with code 0 in 0.015s, 1.2MB"）。

## 5. 编码策略

### 5.1 EncodingManager

核心原则：**用户不需要关心编码，CodeRunner 自动处理一切**。

**文件编码检测**（打开文件时）：
1. 前 3 字节为 `\xEF\xBB\xBF` → UTF-8 BOM，跳过 BOM 后解码
2. 整文件 UTF-8 严格解码成功 → UTF-8
3. 以上失败 → 系统编码（Windows 'gbk'，其他 'utf-8'）

不做概率检测，只用 BOM 和严格 UTF-8 验证两种确定性方法。

**编译标志生成**：

```python
def build_flags(source_encoding):
    flags = ['-fexec-charset={platform_charset}']
    if source_encoding is UTF-8:
        flags.append('-finput-charset=UTF-8')
    return flags
```

**I/O 编码转换**（Test 模式）：
- InputPanel → stdin：`text.encode(platform_charset)`
- stdout/stderr → OutputPanel：`bytes.decode(platform_charset, 'replace')`

**编码处理链路**：
```
UTF-8 源文件 → g++(-finput-charset=UTF-8, -fexec-charset=GBK) → 程序输出 GBK → CodeRunner 转 Unicode → OutputPanel
GBK 源文件  → g++(-fexec-charset=GBK)                          → 同上
```

**保存文件**：使用检测到的原始编码写回，UTF-8 不加 BOM。

**编译 stderr 解码**：使用平台编码（而非 UTF-8），中文 Windows 下 g++ 输出 GBK 不乱码。

## 6. 对话框

### 6.1 SettingsDialog

模态 QDialog，底部 OK/Cancel，QTabWidget 三页。

**Compiler 页**：
- 编译器路径：QLineEdit + Browse... 按钮 + Auto Detect 按钮
  - Browse：QFileDialog 选择 g++.exe，起始目录智能定位（绝对路径取其目录，相对路径 resolve 后取目录，空取 ProgramFiles）
  - Auto Detect：依次检查 MinGW/TDM-GCC/Dev-Cpp/msys64 等常见路径 + PATH 中的 g++
- 编译参数：QLineEdit（如 `-std=c++14 -O2`），默认留空
- 环境变量：QTableWidget（Key/Value），Add Row 按钮，Value tooltip 提示 `$VAR_NAME` 语法
- 运行超时：QSpinBox（1-300，默认 10）
- 编译超时：QSpinBox（1-300，默认 20）

**Editor 页**：
- 编辑器字体/字号：QFontComboBox + QSpinBox（6-72，默认 11）
- IO 面板字体/字号：QFontComboBox + QSpinBox
- 括号补全：QCheckBox（默认勾选）
- 缩进风格：QComboBox（Tab / Space）
- Tab 宽度：QSpinBox（2-16，默认 4）— 同时控制 Tab 视觉宽度和空格缩进步长

**Template 页**：
- QPlainTextEdit 编辑模板文本
  - tabStopWidth 实时跟随 Tab Width 设置（`spin_indent_size.valueChanged` 信号联动 `_update_template_tab_width`）
  - 自动缩进：eventFilter 处理 Enter 键，复制当前行前导空白到新行，行末 `{` 时增加一级缩进（Tab 模式插入 `\t`，Space 模式插入 indent_size 个空格）
- Reset to Default 按钮

OK 时：验证 → apply_from(copy) → save JSON → compiler_path/flags/env_vars 变化则更新 compiler_mtime。Cancel 时丢弃副本。

### 6.2 FindDialog

非模态 QDialog：QLineEdit + 大小写敏感 QCheckBox + 向上/向下 QRadioButton + Find Next/Close 按钮。目标为 CodeEditor，使用 `QTextDocument.find()`。未找到时标题栏提示 "Not found"。关闭时 `hide()` 不销毁，保留上次输入。

### 6.3 ReplaceDialog

非模态 QDialog，FindDialog 基础增加：替换文本 QLineEdit + Replace/Replace All 按钮。关闭时隐藏保留状态。

### 6.4 GotoLineDialog

`QInputDialog.getInt()` 弹出，输入行号（1 ~ 文档总行数），确认后移动光标到目标行首并居中滚动。快捷键 Ctrl+G。

### 6.5 编码选择菜单

状态栏编码标签点击 → QMenu："Reopen with Encoding" / "Save with Encoding"，列出常见编码（UTF-8、GBK、Big5、Shift_JIS、ISO-8859-1 等）。

### 6.6 保存确认对话框

QMessageBox："Save Changes?" — "File '{filename}' has unsaved changes." — Save / Don't Save / Cancel。多个 dirty 标签逐个确认，不使用 Save All 批量按钮。

## 7. 文件操作

**New**：创建 TabData（is_new=True, is_dirty=True, encoding='UTF-8'），editor_doc 填充 template_text，挂载 CppHighlighter(deferred=True)，add_tab → tabbar → _switch_to_tab。

**Open**：QFileDialog 选择文件 → `os.path.normpath` 统一路径 → 遍历已有标签检查重复（已打开则 _switch_to_tab 激活）→ `_read_file` 检测编码并读取 → 创建 TabData → add_tab + _switch_to_tab。文件不可读时弹 QMessageBox 警告。更新 last_file_dir 和 recent_files。

**Save**：新文件弹 QFileDialog 选路径，保存后 is_new→False, is_dirty→False。已保存文件直接写入，使用 TabData.encoding 编码。保存成功后刷新标签名。

**Save As**：始终弹 QFileDialog，保存后更新 file_path 和 encoding。

**Close Tab**（_handle_close_tab）：dirty 时弹确认对话框 → 断 modificationChanged 信号 → 移除 tabbar → remove_tab → 调整零标签或切换。

**拖放打开**：MainWindow `setAcceptDrops(True)`，dragEnterEvent 检查 MIME URLs 后缀匹配 `_SOURCE_EXTENSIONS`（`.cpp/.c/.cc/.cxx/.h/.hpp/.hh`）。CodeEditor/InputPanel/OutputPanel 的 dragEnterEvent/dragMoveEvent/dropEvent 遇到 URL 拖放时 ignore，让事件传播到 MainWindow 处理；纯文本拖放则交给 QTextEdit 默认行为。Menu Open 和 drag-drop 共用 `_open_file_path()`，重复文件检测逻辑统一生效。

**Recent Files**：File 菜单 Recent Files 子菜单（QMenu），最多 10 条按时间倒序。点击已删除文件弹 QMessageBox "File not found" 并从列表移除。`_open_file_path(add_recent=True)` 自动调用 `_add_recent_file()`。

## 8. UI 细节

### 8.1 DPI 处理

- `Qt.AA_EnableHighDpiScaling` 启用高 DPI 缩放，Widget 几何和字号由 Qt 自动处理
- `_dpi_factor()`（`QScreen.logicalDotsPerInch() / 96.0`）用于手动绘制场景：
  - 图标 pixmap：物理尺寸按 DPI 放大，devicePixelRatio(dpi)，QPainter `scale(dpi,dpi)` 在逻辑坐标系绘制
  - IO 面板标签 padding：`label.setFixedHeight` 使用 `+ int(4 * dpi)`

### 8.2 Toolbar 图标

七个按钮 QPainter 自绘，逻辑尺寸 24x24（`_ICON_BASE = 24`），Fusion 主题：

| 按钮 | 形状 | 颜色 |
|------|------|------|
| New | 文档折角 | 灰框+白底+黑文字行 |
| Save | 3.5 寸软盘 | 蓝色(60,100,200) |
| Open | Win2K 文件夹 | 黄色(220,180,40) |
| Run | 播放三角 | 绿色(0,160,0) |
| Test | 烧瓶 | 蓝色(50,100,220) |
| Stop | 圆角方块 | 红色(220,50,50) |
| Settings | 齿轮 | palette.windowText() |

生成函数：`_generate_xxx_icon(dpi)`，在 QPainter 中 `scale(dpi,dpi)`。由 `_create_toolbar_icons()` 统一创建返回 dict。toolbar 显示纯图标，菜单显示文字。

## 9. 主程序入口

启动前安装 Qt message handler 过滤 Windows 平台无害警告（`setMouseGrabEnabled`、`setKeyboardGrabEnabled`），其余消息交给默认 handler 处理。

```python
_SUPPRESSED_WARNINGS = ('setMouseGrabEnabled', 'setKeyboardGrabEnabled')

def _qt_message_handler(msg_type, context, msg):
    if msg_type == QtMsgType.QtWarningMsg:
        for pattern in _SUPPRESSED_WARNINGS:
            if pattern in msg:
                return
    _default_qt_handler(msg_type, context, msg)

_default_qt_handler = qInstallMessageHandler(_qt_message_handler)

def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    settings = Settings()
    _init_font_defaults(settings)
    settings.load()
    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec_())
```

窗口默认 1000x650，首次居中。Settings 实例传入 MainWindow，构造中 `_load_window_state()` 恢复窗口状态和标签页。

## 10. 编码风格

遵循 AGENTS.md：`def method (self, arg)` 参数括号前有空格；`arg:QWidget` 紧凑类型注解；字符串优先单引号；成功返回 0，失败 -1/-2；Python 3.8 兼容。

## 11. 技术决策摘要

以下决策影响当前实现，详细内容已整合到对应章节：

| 时间 | 决策 | 原因 |
|------|------|------|
| 2026/05/06 | Open 重复文件检测 | 防止两次打开同一文件产生两个标签页 |
| 2026/05/06 | 编译 stderr 用平台编码 | 中文 Windows 下 g++ 输出 GBK，UTF-8 解码会乱码 |
| 2026/05/06 | 状态栏显示编译/运行结果 | 编译/运行结束后回到 Ready 丢失结果信息 |
| 2026/05/06 | startDetached 返回值检查 | 失败时无提示 |
| 2026/05/06 | 负 exit code crash 描述 | 已知 NTSTATUS 码附加可读描述（如 Access violation） |
| 2026/05/06 | killed 不追踪 Stop 意图 | 自然崩溃也走 CrashExit，附加 crash 描述比一律灰色更有用 |
| 2026/05/06 | compiler_mtime 传播 | Settings 变化后所有 TabData 的 mtime 更新，触发重编译 |
| 2026/05/06 | Settings JSON 只加载已知键 | 忽略未知键，首次不存在时保留默认值 |
| 2026/05/06 | Window state 持久化 | 恢复标签页状态、窗口几何、分割条位置、recent_files |
| 2026/05/06 | Recent Files 子菜单 | 最多 10 条，点击已删除文件提示并移除 |
| 2026/05/06 | Drag-drop 扩展后缀 | 扩展文件类型覆盖 .cpp/.c/.cc/.cxx/.h/.hpp |
| 2026/05/07 | 工具链 PATH 自动注入 | compiler_path 含路径时 prepend bin_dir 到 PATH，确保运行时能找到 libstdc++ DLL |
| 2026/05/07 | 运行结果行前换行 | 程序输出不以 `\n` 结尾时避免状态行接在末尾 |
| 2026/05/07 | 编译命令加 -lstdc++ | 误选 gcc 时也能链接 C++ 标准库 |
| 2026/05/07 | Settings 浏览按钮 | 方便用户通过文件对话框定位 g++ |
| 2026/05/07 | Settings 缩进选项 | Tab 宽度和缩进风格可配置，CodeEditor/InputPanel/template 编辑器同步 |
| 2026/05/07 | 模板编辑器自动缩进 | eventFilter 处理 Enter 键，遵从缩进风格设置 |
| 2026/05/07 | 默认编译器改为 gcc + compiler_flags 留空 | 兼顾 C 和 C++ 学生：gcc 从扩展名自动识别语言模式，-lstdc++ 覆盖 C++ 链接需求，C 学生零配置即可使用 |
| 2026/05/07 | Qt message handler 过滤无害警告 | 首次运行 Open 文件时 QMenu 在窗口完全可见前 grab mouse 产生 `setMouseGrabEnabled` 警告，属于 Qt Windows 平台已知问题 |
| 2026/05/07 | Open 与 drag-drop 合并为 `_open_file_path` | dropEvent 的 `continue` 只跳了内层循环导致重复 tab，抽取公共方法后重复检测逻辑统一生效 |
| 2026/05/07 | 子组件 drag-drop 事件转发 MainWindow | CodeEditor/InputPanel/OutputPanel 默认 QTextEdit 会把文件拖放当文本插入，override drag 事件遇到 URL 时 ignore 让 MainWindow 处理 |