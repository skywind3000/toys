# CodeRunner 技术规格

## 架构概览

### 顶层布局

MainWindow 为 QMainWindow，从上到下五个区域：

```
MenuBar (QMenuBar)
Toolbar (QToolBar)
TabBar  (QTabBar)
MainArea (QSplitter 水平 → CodeEditor | QSplitter 垂直 → InputSection(QLabel "INPUT:" + InputPanel) | OutputSection(QLabel "OUTPUT:" + OutputPanel))
StatusLine (QStatusBar)
```

- TabBar 与 MainArea 协同：切换标签时通过 `setDocument()` 交换每个 Widget 的 QTextDocument
- MainArea 使用**单一可见 Widget 组**（而非每标签一套 Widget），每个标签页持有独立的 QTextDocument 三件套（editor_doc / input_doc / output_doc），切换标签时交换 document，Splitter 位置全局共享
- 状态栏左侧为 QLabel 显示消息，右侧为 QLabel 显示光标位置/编码/模式

### 类列表

所有类集中在 `CodeRunner.py` 单文件中：

| 类 | 基类 | 职责 |
|----|------|------|
| MainWindow | QMainWindow | 主窗口，协调所有组件 |
| CodeEditor | QPlainTextEdit | 代码编辑器，语法高亮/括号补全/自动缩进/改写模式 |
| CppHighlighter | QSyntaxHighlighter | C++ 语法高亮规则 |
| InputPanel | QPlainTextEdit | 输入面板，纯文本，外层包装 QWidget + QLabel "INPUT:" |
| OutputPanel | QTextEdit | 输出面板，只读，支持多色富文本，外层包装 QWidget + QLabel "OUTPUT:" |
| TabData | object | 单个标签页的全部状态数据 |
| TabManager | object | 标签页列表管理与切换逻辑 |
| ProcessManager | QObject | 编译/运行进程管理（QProcess），busy 状态控制 |
| EncodingManager | object | 编码检测、编译标志生成、I/O 编码转换 |
| Settings | object | 配置数据，JSON 读写 |
| SettingsDialog | QDialog | 设置面板（三页 Tab） |
| FindDialog | QDialog | 非模态查找对话框 |
| ReplaceDialog | QDialog | 非模态替换对话框 |

## 数据模型

### TabData

每个标签页的状态封装：

```python
class TabData:
    file_path: str              # 文件路径，None 表示新文件
    is_new: bool                # True = 从未保存到磁盘（新文件标志）
    is_dirty: bool              # True = 有未保存更改
    editor_doc: QTextDocument   # 编辑器文档（独立实例，含 undo/redo 栈）
    input_doc: QTextDocument    # InputPanel 文档（独立实例）
    output_doc: QTextDocument   # OutputPanel 文档（独立实例，含富文本颜色）
    cursor: QTextCursor         # 编辑器光标位置（含选区）
    scroll_pos: int             # 编辑器垂直滚动条位置
    input_cursor: QTextCursor   # InputPanel 光标位置
    input_scroll: int           # InputPanel 垂直滚动条位置
    encoding: str               # 文件编码：'UTF-8' 或系统编码名
    zoom_font_size: int         # 当前 zoom 字号（会话级，不持久化）
    compiler_mtime: float       # 上次编译时的编译参数修改时间戳，用于判断是否需要重编译
```

**QTextDocument 模型说明**：每个标签页持有三个独立的 QTextDocument 实例（editor_doc、input_doc、output_doc）。Widget 层共享单一 QPlainTextEdit/QTextEdit，切换标签时通过 `widget.setDocument(tab.xxx_doc)` 交换文档。此设计的关键优势：
- **undo/redo 完整保留**：QTextDocument 自带 undo 栈，切换标签不丢失撤销历史
- **语法高亮状态保留**：CppHighlighter 挂在 editor_doc 上，切换后无需重新解析
- **无需 setPlainText**：避免内容销毁重建和 undo 栈清空

- `is_new` 标志：新建文件时为 True，首次保存后变为 False
- `is_dirty` 标志：编辑器文本变化时置 True，保存后置 False；新建文件预填充模板后也视为 dirty
- 标签名生成规则：`is_new` 且 `is_dirty` → `*untitledN*`；`is_new` 且非 dirty → `untitledN`；已保存文件 dirty → `*filename*`；已保存文件非 dirty → `filename`
- 退出时持久化：已保存文件记录 file_path；新文件记录 editor_doc.toPlainText() + input_doc.toPlainText()
- CppHighlighter 在 TabData 创建时即挂载到 editor_doc，生命周期与 TabData 一致

### TabManager

```python
class TabManager:
    tabs: list              # TabData 列表
    current_index: int      # 当前活跃标签索引，-1 表示无标签
    untitled_counter: int   # untitled 编号递增器

    def switch_tab(index): ...     # 保存旧标签状态，加载新标签状态到 Widget
    def add_tab(tab_data): ...     # 添加新标签并切换
    def close_tab(index): ...      # 关闭标签，返回是否成功（用户可能取消保存）
    def get_current() -> TabData: ...
```

- 首次启动时 `current_index = -1`，即零标签状态；用户通过 New 或 Open 创建第一个标签页
- 关闭最后一个标签后 `current_index = -1`，重新进入零标签状态
- **Switch Tab 快捷键**：Alt+1 ~ Alt+9 切换到第 1~9 个标签，Alt+0 切换到第 10 个标签。索引超出当前标签数量时忽略。通过 `QShortcut` 或 `QAction` 绑定 `Alt+数字` 快捷键，回调调用 `switch_tab(N-1)`

**标签切换（setDocument 模式）**：

`switch_tab` 通过交换 QTextDocument 实现标签切换，不销毁/重建文本内容。光标和滚动条位置需手动保存/恢复（它们属于 Widget 而非 Document）。使用 `setUpdatesEnabled(False)` 冻结重绘，避免多步操作产生中间帧闪烁。示例流程：

```python
# 保存旧标签的光标和滚动条状态
old_tab.cursor = editor.textCursor()
old_tab.scroll_pos = editor.verticalScrollBar().value()
old_tab.input_cursor = input_panel.textCursor()
old_tab.input_scroll = input_panel.verticalScrollBar().value()

# 冻结重绘
editor.setUpdatesEnabled(False)
input_panel.setUpdatesEnabled(False)

# 交换文档（undo/redo 栈、高亮状态自动跟随 document）
editor.setDocument(new_tab.editor_doc)
input_panel.setDocument(new_tab.input_doc)
output_panel.setDocument(new_tab.output_doc)

# 恢复新标签的光标和滚动条状态
editor.setTextCursor(new_tab.cursor)
editor.verticalScrollBar().setValue(new_tab.scroll_pos)
input_panel.setTextCursor(new_tab.input_cursor)
input_panel.verticalScrollBar().setValue(new_tab.input_scroll)

# 解冻
editor.setUpdatesEnabled(True)
input_panel.setUpdatesEnabled(True)
```

注意：`setDocument` 不会触发 `textChanged` 信号，因此不需要 `blockSignals`。但 dirty 状态的 `textChanged` 信号连接需要注意——应连接到 TabData 层的 dirty 标记逻辑，而非直接连接到 Widget。具体做法：每个 TabData 的 editor_doc 创建时连接 `editor_doc.contentsChanged` 信号到该 TabData 的 dirty 标记方法，信号跟随 document 生命周期，不受 Widget 切换影响。

**零标签状态**：

QPlainTextEdit/QTextEdit 始终持有一个 QTextDocument，不能为 null。为避免关闭最后一个标签后 Widget 引用已销毁的 TabData.editor_doc 导致崩溃，采用**初始 document 占位**策略：

MainWindow 初始化时，保存三个 Widget 自带的初始空 QTextDocument 引用：

```python
# MainWindow.__init__
self.empty_editor_doc = self.editor.document()
self.empty_input_doc = self.input_panel.document()
self.empty_output_doc = self.output_panel.document()
```

进入零标签状态（`current_index = -1`）时：
- 三个 Widget 切回初始空 document：`editor.setDocument(self.empty_editor_doc)` 等
- 三个面板统一 `setEnabled(False)` 灰显不可交互
- 状态栏右侧清空（不显示行号/编码/模式信息）
- TabData 销毁时其 QTextDocument 不再被任何 Widget 引用，可安全释放

从零标签状态恢复（新建或打开文件）时：
- `editor.setDocument(new_tab.editor_doc)` 切换到新标签的 document
- 三个面板恢复 `setEnabled(True)`

### Settings

配置数据结构，从 `~/.config/coderunner/settings.json` 读写：

```python
class Settings:
    compiler_path: str          # g++ 路径，默认 'g++'
    compiler_flags: str         # 编译参数，默认 '-std=c++14'
    env_vars: dict              # 环境变量 {key: value}
    run_timeout: int            # 运行超时秒数，默认 10
    compile_timeout: int        # 编译超时秒数，默认 20
    editor_font_family: str     # 编辑器字体，默认 'Consolas'
    editor_font_size: int       # 编辑器字号，默认 11
    io_font_family: str         # IO 面板字体，默认 'Consolas'
    io_font_size: int           # IO 面板字号，默认 11
    bracket_completion: bool    # 括号补全开关，默认 True
    template_text: str          # 新建模板内容
```

- 修改 `compiler_path`、`compiler_flags` 或 `env_vars` 时，记录当前时间戳到 `compiler_mtime`，供重编译判断使用（`compiler_path` 变更意味着使用不同编译器，旧产物需要重编译；`env_vars` 变更可能影响编译器搜索路径等行为，属于刻意扩展的安全策略）
- `env_vars` 的值中 `$VAR_NAME` 语法在运行时展开为实际环境变量值

### Settings JSON 格式

```json
{
    "compiler_path": "g++",
    "compiler_flags": "-std=c++14",
    "env_vars": {"PATH": "$PATH;/custom/bin"},
    "run_timeout": 10,
    "compile_timeout": 20,
    "editor_font_family": "Consolas",
    "editor_font_size": 11,
    "io_font_family": "Consolas",
    "io_font_size": 11,
    "bracket_completion": true,
    "template_text": "#include <iostream>\n..."
}
```

首次运行不存在配置文件时使用默认值。

### Window State JSON 格式

`~/.cache/coderunner/window.json`：

```json
{
    "geometry": {"x": 100, "y": 100, "w": 1000, "h": 650},
    "h_splitter": [500, 500],
    "v_splitter": [325, 325],
    "last_file_dir": "C:/Users/xxx/Documents",
    "tabs": [
        {
            "file_path": "C:/Users/xxx/test.cpp",
            "input_text": "3 5"
        },
        {
            "is_new": true,
            "editor_text": "#include ...",
            "input_text": ""
        }
    ],
    "active_tab": 0,
    "recent_files": ["C:/Users/xxx/test.cpp", ...]
}
```

- `h_splitter` / `v_splitter`：Splitter 各段尺寸列表，用于恢复分割条位置
- `recent_files`：最近文件列表，最多 10 条，按时间倒序
- OutputPanel 内容不持久化，重启后为空

## 核心组件实现

### CodeEditor

继承 QPlainTextEdit，扩展功能：

**行号显示**：使用 QPlainTextEdit 的 `blockCountChanged` / `updateRequest` 信号，在左侧绘制行号区域（参考 Qt Line Number Example）。行号区域宽度按最大行号位数动态调整。

**C++ 语法高亮**：CppHighlighter 挂载到 CodeEditor.document()，规则见下方 CppHighlighter 章节。

**括号补全**：覆盖 `keyPressEvent`，输入以下开符号时自动插入对应闭符号，并将光标置于两者之间：

| 开符号 | 闭符号 |
|--------|--------|
| `(` | `)` |
| `{` | `}` |
| `[` | `]` |
| `"` | `"` |
| `'` | `'` |

额外行为：
- 输入闭符号且光标右侧恰好是同一闭符号时：跳过（不重复插入），直接右移光标
- 删除开符号时：如果右侧紧邻对应闭符号，一并删除
- 括号补全功能可通过设置开关控制（默认开启）

**自动缩进**：覆盖 `keyPressEvent`，Enter 键行为：
1. 取当前行的前导空白（缩进）作为新行基础缩进
2. 如果当前行末尾是 `{`，新行增加一级缩进（+4 个空格或 1 个 Tab，取决于当前行缩进字符类型）
3. 如果下一行（原光标右侧）以 `}` 开头且当前行是 `{`，则在 `}` 行减少一级缩进（光标停留在增加缩进的新行）

**Tab 键**：插入 Tab 制表符（`\t`），不转换为空格。Tab 宽度设为 4（`setTabStopWidth` 或 `setTabStopDistance`）。

**改写模式（Overtype）**：
- `overwrite_mode: bool` 属性，初始为 False（Insert 模式）
- Insert 键切换 overwrite_mode
- 覆盖 `keyPressEvent`：在 overwrite_mode 下，输入普通字符时先删除光标右侧一个字符再插入（模拟覆盖），而非默认的插入行为
- 状态栏右侧显示 `INS` 或 `OVR`，随模式切换实时更新
- Paste 操作在 overwrite_mode 下仍为插入行为（不逐字符覆盖）

**Zoom**：
- Ctrl++ 放大字号（步长 1pt），Ctrl+- 缩小字号（步长 1pt，最小 6pt）
- Zoom 仅改变 CodeEditor 字号，不影响 IO 面板；仅会话有效，不写入 Settings
- Zoom 字号存入 TabData.zoom_font_size，切换标签时恢复对应标签的 zoom 状态

### CppHighlighter

规则分组与颜色：

| 分组 | 正则/规则 | 颜色 |
|------|-----------|------|
| 关键字 | `\b(int|float|double|char|void|bool|long|short|unsigned|signed|const|static|extern|inline|virtual|override|final|class|struct|enum|union|namespace|using|template|typename|public|private|protected|if|else|while|for|do|switch|case|default|break|continue|return|try|catch|throw|new|delete|this|nullptr|true|false|sizeof|typedef|auto|register|volatile|friend|operator|explicit|mutable|constexpr|decltype|static_assert|noexcept|thread_local|alignas|alignof)\b` | 蓝色粗体 |
| 预处理器 | `^#\s*(include|define|ifdef|ifndef|endif|if|elif|else|pragma|error|warning)\b` | 绿色 |
| 字符串 | `"..."`（双引号，不含换行） | 深红色 |
| 字符 | `'.'`（单引号字符常量） | 深红色 |
| 注释单行 | `//[^\n]*` | 灰色 |
| 注释多行 | `/\*...\*/`（multiline 模式） | 灰色 |
| 数字 | `\b[0-9]+(\.[0-9]*)?([eE][+-]?[0-9]+)?[fFlLuU]*\b` | 深蓝色 |

高亮器使用 `QRegularExpression` + `QSyntaxHighlighter`，按规则顺序依次匹配，同一文本区域只应用最先匹配的规则（关键字优先级高于数字等）。

多行注释需要特殊处理：使用 `setCurrentBlockState` / `previousBlockState` 机制跟踪跨块注释状态。

### InputPanel

继承 QPlainTextEdit，外层用 QWidget + QVBoxLayout 包装，顶部放 QLabel 显示固定文字 "INPUT:"：
- QLabel 文字使用小号粗体，与 IO 面板字体一致
- 无行号显示
- 字号/字体跟随 Settings.io_font_family / io_font_size
- Tab 键行为同 CodeEditor（插入制表符）
- 标签切换时通过 `setDocument(tab.input_doc)` 交换文档
- 整个 InputSection（标签 + 编辑区）在零标签状态下随 InputPanel 一起灰显

### OutputPanel

继承 QTextEdit，外层用 QWidget + QVBoxLayout 包装，顶部放 QLabel 显示固定文字 "OUTPUT:"：
- QLabel 文字使用小号粗体，与 IO 面板字体一致
- `setReadOnly(True)`
- 字号/字体跟随 Settings.io_font_family / io_font_size
- 标签切换时通过 `setDocument(tab.output_doc)` 交换文档
- 关闭标签时对应 TabData 的 output_doc 随 TabData 一起销毁

**颜色渲染**：使用 `QTextCursor` + `QTextCharFormat` 插入不同颜色的文本段：

| 内容类型 | QTextCharFormat 颜色 |
|----------|----------------------|
| stdout | 默认前景色（QPalette.Text） |
| stderr | 灰色（Qt.gray） |
| 退出状态行 | 灰色 |
| Build 成功 | 灰色 |
| 编译错误 | 红色（Qt.red） |
| Runtime Error | 红色 |
| 超时信息 | 红色 |

每次 Test/Build 清空 OutputPanel 后重新写入全部内容，不追加。

### ProcessManager

继承 QObject，管理编译和运行进程：

```python
class ProcessManager(QObject):
    process: QProcess         # 当前活跃的 QProcess（编译或运行）
    busy: bool                # True = 正在编译或运行
    mode: str                 # 'compile' / 'run' / None
    target_tab: TabData       # 发起本次操作的标签页引用，输出路由目标

    signals:
        compile_finished(exit_code, stderr_text)
        run_finished(exit_code, stdout_text, stderr_text, elapsed_ms)
        run_timeout()
        compile_timeout()
```

**Test 流程**：
1. MainWindow 调用 `save_if_dirty()`（见文件操作章节）。如果返回失败（用户取消了保存对话框），则终止整个 Test 流程，不继续编译和运行
2. EncodingManager 生成编译命令（见编码章节）
3. 判断是否需要重编译：exe 不存在 / exe_mtime < source_mtime / exe_mtime < tab.compiler_mtime → 需要重编译。编译产物（exe）放在源文件同目录下，文件名与源文件同名（如 `test.cpp` → `test.exe`），与 Dev-C++ 单文件模式行为一致
4. 如需重编译：ProcessManager 启动 QProcess 执行编译命令，等待 compile_finished 信号
   - 编译成功：继续步骤 5
   - 编译失败：OutputPanel 显示红色错误信息，状态栏显示 Build failed，结束
5. 启动 QProcess 运行 exe：
   - 设置工作目录为 exe 所在目录
   - 设置环境变量（Settings.env_vars 展开 $VAR_NAME 后合并到 QProcessEnvironment）
   - 将 InputPanel 内容转换为平台编码后写入 stdin
   - stdout/stderr 数据到达时实时追加到 OutputPanel（stdout 默认色，stderr 灰色）。此"追加"是指在单次运行的输出中逐步追加新到达的数据；跨运行间则整体替换（每次 Test/Build 开始时先清空 OutputPanel 再写入新内容）
   - 进程结束时：显示退出状态行（灰色），返回码非 0 标红色 Runtime Error
   - 运行超时：QTimer 计时，到期后 kill 进程，OutputPanel 末尾追加红色超时信息
   - 内存占用：如果 `psutil` 可用，进程启动后启动一个 QTimer（间隔约 100ms）定期轮询 `psutil.Process(pid).memory_info()`，记录 `rss`（Linux/macOS）或 `rss`（Windows）的峰值到局部变量 `peak_memory`。每次轮询用 try/except 捕获 `NoSuchProcess`（进程已结束时忽略）。进程结束时停止 QTimer，将 `peak_memory` 追加到退出状态行（如 "exit with code 0 in 0.015s, 1.2MB"）。此方案不依赖进程结束时仍然存活，是最可靠的采集方式

**输出路由（跨标签切换场景）**：
- 启动 Test/Build 时，ProcessManager 记录 `target_tab` 为发起操作的 TabData 引用
- stdout/stderr 数据到达时，始终写入 `target_tab.output_doc`（通过 QTextCursor 操作 document），而非"当前可见标签"
- 由于 QTextDocument 与 Widget 解耦，即使当前显示的是其它标签的 document，写入 target_tab.output_doc 也不会影响当前显示；用户切换回该标签时 `setDocument` 即可看到完整输出
- 进程结束信号、超时信号同理——状态行和错误信息写入 `target_tab.output_doc`
- 状态栏消息（左侧 Message）仍然实时更新，不受标签切换影响

**Run 流程**：
1. MainWindow 调用 `save_if_dirty()`，失败则终止 Run 流程
2. 同 Test 步骤 2-3 判断是否重编译
3. 如需重编译：编译（同 Test 步骤 4）
4. 编译成功后：启动外部终端窗口运行 exe
   - Windows：使用固定批处理 + 环境变量方案（详见下方"Run 外部终端实现"）
   - Linux/macOS：`QProcess.startDetached('xterm', ['-e', exe_path])`，或检测可用终端模拟器
5. startDetached 成功后立即标记 Run 完成，busy 状态解除；如果 startDetached 返回 False（启动失败），状态栏显示 "Failed to launch terminal" 提示用户

**Run 外部终端实现（Windows）**：

使用固定路径 `%TEMP%\coderunner.cmd` 作为启动批处理，内容固定不变：

```batch
@echo off
call %CR_COMMAND%
set CR_EXITCODE=%ERRORLEVEL%
call %CR_PAUSE%
exit %CR_EXITCODE%
```

变化部分通过环境变量传入：
- `CR_COMMAND`：要运行的 exe 完整路径（如 `"C:\Users\xxx\test.exe"`）
- `CR_PAUSE`：程序结束后的行为，正常 Run 设为 `pause`（显示"Press any key..."），不需要暂停时设为 `rem`（无操作）

**设计要点**：
- **固定文件名**：避免每次 Run 生成新临时文件，崩溃/死机后不会残留大量垃圾文件
- **固定内容**：多个 Run 并发时，即使互相覆盖写入也写入相同内容，消除批处理"边运行边读取"导致的竞态破坏
- **环境变量隔离**：每个 `cmd.exe` 子进程在创建时获得环境变量的独立副本，多个 Run 之间天然隔离

**启动流程**：
1. 检查 `%TEMP%\coderunner.cmd` 是否存在：不存在则创建；已存在则读取内容与预期对比，内容一致时跳过写入，不一致时才覆盖重写。避免每次 Run 都触发文件写操作，减少与正在运行的批处理之间的临界情况
2. 临时修改 `os.environ`：设置 `CR_COMMAND` 为 exe 路径，`CR_PAUSE` 为 `pause`
3. 调用 `QProcess.startDetached('cmd', ['/c', 'start', '', '/D', work_dir, bat_path])`（startDetached 同步返回，子进程创建完毕即拿到环境副本）
4. 还原 `os.environ`（删除 `CR_COMMAND` 和 `CR_PAUSE`）

**Build 流程**：
1. MainWindow 调用 `save_if_dirty()`，失败则终止 Build 流程
2. 强制重新编译（不判断是否需要）
3. 结果显示到 OutputPanel：成功灰色 "Build OK in X.XXXs"，失败红色错误信息

**Busy 状态控制**：
- busy 为 True 时：Build/Test/Run 不启动新进程，弹出 QMessageBox 提示 "A process is currently running. Please wait or press Stop before starting a new operation."
- Toolbar 上的 Build/Test/Run/Stop 按钮**保持可点击状态，不禁用灰显**——用户始终能看到并点击这些按钮，busy 时通过弹出提示而非视觉禁用来阻止操作
- Stop 按钮调用 `process.kill()`，终止当前编译或运行进程
- Run（外部终端）不占用 busy 状态

**QProcess 配置**：
- 合并 stderr 到独立通道：`setProcessChannelMode(QProcess.SeparateChannels)`
- stdin：Test 模式下写入后关闭写入通道 `closeWriteChannel()`
- 编译进程：只读 stderr（g++ 错误信息在 stderr）
- 运行进程：分别读 stdout 和 stderr

### EncodingManager

编码检测与转换的核心逻辑：

**文件编码检测**（打开文件时）：
1. 读取文件前 3 字节，如果为 `\xEF\xBB\xBF` → UTF-8 BOM，跳过 BOM 后解码
2. 尭试将整个文件用 UTF-8 严格解码（`bytes.decode('utf-8', 'strict')`）→ 成功则 UTF-8
3. 以上失败 → 系统编码（Windows 为 'gbk'，其他平台为 'utf-8'）

**编译标志生成**（根据源文件编码）：
```python
def build_flags(source_encoding):
    flags = []
    platform_charset = 'gbk' if sys.platform == 'win32' else 'utf-8'
    flags.append(f'-fexec-charset={platform_charset}')
    if source_encoding.lower().replace('-', '') == 'utf8':
        flags.append('-finput-charset=UTF-8')
    return flags
```

**I/O 编码转换**（Test 模式）：
- InputPanel → stdin：`text.encode(platform_charset)` 转为 bytes 写入 QProcess stdin
- stdout → OutputPanel：QProcess stdout bytes → `bytes.decode(platform_charset, 'replace')` 转为 str 显示
- stderr → OutputPanel：同 stdout 转换方式

**保存文件**：使用检测到的原始编码写回，UTF-8 文件不加 BOM。

### 文件操作

**New**：
1. 创建 TabData（is_new=True, is_dirty=True, encoding='UTF-8'），editor_doc 初始内容为 Settings.template_text，挂载 CppHighlighter
2. 递增 untitled_counter 生成名称 `untitledN`
3. 添加到 TabManager 并切换

**Open**：
1. QFileDialog 选择文件（初始目录为 window_state.last_file_dir）
2. EncodingManager 检测编码，读取文件内容
3. 创建 TabData（is_new=False, is_dirty=False, file_path=路径, encoding=检测结果），editor_doc 初始内容为文件文本，挂载 CppHighlighter
4. 添加到 TabManager 并切换
5. 更新 last_file_dir 和 recent_files

**Save**：
- 新文件（is_new=True）：弹出 QFileDialog 让用户选择路径，保存后 is_new→False, file_path→路径, is_dirty→False
- 已保存文件：直接写入 file_path，使用 TabData.encoding 编码
- 保存成功后刷新标签名显示

**Save As**：
- 始终弹出 QFileDialog，保存后更新 file_path 和 encoding

**Close Tab**：
- 如果 is_dirty：弹出 QMessageBox（Save / Don't Save / Cancel）
  - Save → 执行 Save 流程后关闭
  - Don't Save → 直接关闭
  - Cancel → 取消关闭，返回 False
- 否则直接关闭

**拖放打开**：
- MainWindow 设置 `setAcceptDrops(True)`
- dragEnterEvent 检查 MIME 类型含文件路径且后缀为 .cpp/.c
- dropEvent 获取文件路径，执行 Open 流程

**Recent Files**：
- 存储在 window.json 的 recent_files 列表
- File 菜单下 Recent Files 子菜单（QMenu），最多 10 条
- 点击已删除文件时弹出 QMessageBox 提示 "File not found"

## 对话框

### SettingsDialog

模态 QDialog，底部 OK / Cancel 按钮。使用 QTabWidget 分三个页：

**Compiler 页**：
- 编译器路径：QLineEdit + "Auto Detect" 按钮
  - Auto Detect 逻辑：依次检查以下路径是否存在 g++/gcc 可执行文件：
    - `C:\MinGW\bin\g++.exe`、`C:\TDM-GCC-64\bin\g++.exe`、`C:\Program Files\Dev-Cpp\MinGW64\bin\g++.exe`
    - `C:\Program Files (x86)\Dev-Cpp\MinGW64\bin\g++.exe`、`C:\msys64\mingw64\bin\g++.exe`
    - PATH 环境变量中的 g++
  - 检测到后填入 QLineEdit
- 编译参数：QLineEdit（如 `-std=c++14 -O2`）
- 环境变量：QTableWidget（2 列：Key / Value），每行右侧有删除按钮，底部有"Add Row"按钮
  - Value 中 `$VAR_NAME` 在 tooltip 中提示"将展开为实际环境变量值"
- 运行超时：QSpinBox（范围 1-300，默认 10）
- 编译超时：QSpinBox（范围 1-300，默认 20）

**Editor 页**：
- 编辑器字体：QFontComboBox
- 编辑器字号：QSpinBox（范围 6-72，默认 11）
- IO 面板字体：QFontComboBox
- IO 面板字号：QSpinBox（范围 6-72，默认 11）
- 括号补全：QCheckBox（默认勾选）

**Template 页**：
- QPlainTextEdit，多行编辑模板文本
- 右侧 "Reset to Default" 按钮，恢复默认 C++ 骨架

OK 按钮点击后：验证数据 → 更新 Settings 对象 → 写入 JSON → 如果 compiler_path、compiler_flags 或 env_vars 变化则更新 compiler_mtime

### FindDialog

非模态 QDialog（用户可在查找窗口打开的同时编辑代码），参考 Windows 记事本 / Dev-C++ 风格：
- QLineEdit 输入查找文本
- QCheckBox 大小写敏感
- 向上 / 向下 QRadioButton（控制搜索方向，默认向下）
- Find Next / Close 两个按钮（Find Next 按当前方向搜索）
- 查找目标为 CodeEditor（QPlainTextEdit），使用 `QTextDocument.find()` 方法
- 未找到时状态栏提示 "Not found"
- 对话框关闭时不销毁，隐藏即可（`hide()`），再次打开时保留上次输入内容

### ReplaceDialog

非模态 QDialog，在 FindDialog 基础增加：
- QLineEdit 输入替换文本
- Replace / Replace All 按钮
- Replace 替换当前选中并跳到下一个匹配
- Replace All 替换全部匹配
- 同样非模态，关闭时隐藏保留状态

### GotoLineDialog

使用 `QInputDialog.getInt()` 弹出简易对话框，输入目标行号（范围 1 ~ 当前文档总行数）。确认后将 CodeEditor 光标移动到目标行首，并滚动视图使目标行居中可见。快捷键 Ctrl+G。

### 编码选择菜单

状态栏编码标签点击后弹出 QMenu：
- "Reopen with Encoding"：列出常见编码（UTF-8、GBK、Big5、Shift_JIS、ISO-8859-1 等），选择后用指定编码重新加载文件内容
- "Save with Encoding"：同上列表，选择后用指定编码保存文件

### 保存确认对话框

关闭 dirty 标签时使用 QMessageBox：
- 标题为 "Save Changes?"
- 文本为 "File '{filename}' has unsaved changes."
- 三个按钮：Save（Default）、Don't Save、Cancel

退出程序时如果有多个 dirty 标签，逐个弹出确认（不使用 "Save All" 批量按钮，保持简单）。

## DPI 处理

- `QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)` 启用高 DPI 缩放
- 所有固定尺寸值（如行号区域宽度、Splitter 初始尺寸等）乘以 DPI factor
- DPI factor 通过 `QScreen.logicalDotsPerInch() / 96.0` 计算
- 字号由 Qt 的 DPI 缩放自动处理，无需手动乘 DPI factor
- 状态栏、Toolbar 按钮等默认尺寸由 Qt 自动缩放

## 主程序入口

```python
def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
```

窗口默认大小 1000x650，首次启动居中显示。

## 编码风格注意

遵循 AGENTS.md 中的编码规范：
- `def method (self, arg)` — 参数括号前有空格
- `arg:QWidget` — 类型注解紧凑格式
- 字符串优先单引号
- 成功返回 0，失败返回 -1/-2
- Python 3.8 兼容（无 walrus operator、无 str.removeprefix 等）