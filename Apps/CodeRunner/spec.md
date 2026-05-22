# CodeRunner 技术规格

## 0. 快速索引

### 0.1 类列表

| 类 | 基类 | 职责 | 代码行 |
|----|------|------|--------|
| EncodingManager | object | 编码检测、编译标志生成、I/O 编码转换 | 275 |
| Settings | object | 配置数据，实例化设计，支持 copy()/apply_from() | 424 |
| CppHighlighter | QSyntaxHighlighter | C++ 语法高亮（deferred+分批，first-match-wins via format_if_free） | 501 |
| TabData | object | 单个标签页的全部状态数据 | 790 |
| TabManager | object | 纯数据管理器，无 UI 操作 | 854 |
| ProcessManager | QObject | 编译/运行进程管理（QProcess），busy/mode 由状态机驱动 | 904 |
| FlowController | QObject | 编译/运行状态机，管理状态转移；输出通过 output_clear/output_append 信号委托 MainWindow | 1216 |
| FileDragMixin | — | Mixin：URL 拖放 ignore→MainWindow，文本拖放→QTextEdit 默认 | 1561 |
| _IOPanelBase | FileDragMixin, QTextEdit | IO 面板基类，共享 setDocument 逻辑 | 1584 |
| _ClickableLabel | QLabel | 状态栏编码标签，点击弹出编码菜单 | 1595 |
| LineNumberArea | QWidget | 行号区域，paintEvent 委托给 CodeEditor | 1615 |
| CodeEditor | FileDragMixin, QTextEdit | 代码编辑器（setAcceptRichText=False） | 1631 |
| InputPanel | _IOPanelBase | 输入面板（setAcceptRichText=False） | 2538 |
| OutputPanel | _IOPanelBase | 输出面板（只读，buffer+flush 机制，pinned_to_bottom 滚动，双击错误跳转） | 2600 |
| SettingsDialog | QDialog | 设置面板（三页 Tab） | 2661 |
| FindDialog | QDialog | 非模态查找对话框 | 3033 |
| ReplaceDialog | QDialog | 非模态替换对话框 | 3112 |
| MainWindow | QMainWindow | 主窗口，协调所有组件 | 3231 |

### 0.2 模块级函数索引

| 函数 | 职责 |
|------|------|
| `_dpi_factor()` | 计算 DPI 缩放比例（logicalDPI / 96） |
| `_detect_monospace_font()` | 检测平台最佳 monospace 字体 |
| `_init_font_defaults(settings)` | 空字体设置填充平台检测值 |
| `_ensure_dir(path)` | 创建目录（makedirs） |
| `_settings_path()` | 返回 `~/.config/coderunner/settings.json` |
| `_window_state_path()` | 返回 `~/.cache/coderunner/window.json` |
| `_make_io_section()` | 包装 IO 面板（QLabel + QTextEdit） |
| `_read_file(path)` | 文件编码检测+读取，返回 (content, encoding) |
| `_expand_env_vars(value)` | 展开 `$VAR_NAME` 引用 |
| `_resolve_compiler_path(path)` | 解析编译器路径 → (resolved_path, bin_dir) |
| `_ensure_cmd_file()` | 创建 `%TEMP%\coderunner.cmd` bat 文件 |
| `_describe_exit_code(code)` | Windows NTSTATUS 码可读描述 |
| `_output_clear(doc)` | 清空 QTextDocument 内容 |
| `_strip_trailing_whitespace(text)` | 字符串级行尾空白清理 |
| `_strip_trailing_whitespace_in_doc(doc)` | QTextDocument 内 cursor 操作原地清理行尾空白 |
| `_auto_detect_compiler()` | 搜索 `_COMPILER_SEARCH_PATHS` + PATH 查找 g++/gcc |
| `_icon_canvas(dpi)` | 创建 icon pixmap+painter |
| `_generate_new_icon/save_icon/open_icon/run_icon/test_icon/stop_icon/settings_icon(dpi)` | QPainter 自绘 toolbar 图标 |
| `_create_toolbar_icons()` | 统一创建所有图标返回 dict |

### 0.3 菜单 & 快捷键索引

| 菜单 | 菜单项 | QAction attr | 快捷键 | 图标 |
|------|--------|-------------|--------|------|
| File | New | act_new | Ctrl+N | new |
| File | Save | act_save | Ctrl+S | save |
| File | Open | act_open | Ctrl+O | open |
| File | Save As | act_save_as | Ctrl+Shift+S | — |
| File | Close | act_close | Ctrl+W | — |
| File | Recent Files | — (submenu) | — | — |
| File | Settings | act_settings | — | settings |
| Edit | Undo | act_undo | Ctrl+Z | — |
| Edit | Redo | act_redo | Ctrl+Y | — |
| Edit | Cut | act_cut | Ctrl+X | — |
| Edit | Copy | act_copy | Ctrl+C | — |
| Edit | Paste | act_paste | Ctrl+V | — |
| Edit | Find | act_find | Ctrl+F | — |
| Edit | Replace | act_replace | Ctrl+H | — |
| Edit | Goto Line | act_goto_line | Ctrl+G | — |
| Edit | Comment/Uncomment | act_comment | Ctrl+/ | — |
| Edit | Indent | act_indent | Ctrl+] | — |
| Edit | Unindent | act_unindent | Ctrl+[ | — |
| Edit | Duplicate Line | act_duplicate | Ctrl+D | — |
| Edit | Delete Line | act_delete_line | Ctrl+Shift+K | — |
| Edit | Move Line Up | act_move_up | Alt+Up | — |
| Edit | Move Line Down | act_move_down | Alt+Down | — |
| Run | Build | act_build | Ctrl+B | — |
| Run | Test | act_test | F9 | test |
| Run | Run | act_run | F5 | run |
| Run | Stop | act_stop | F7 | stop |
| View | Zoom In | act_zoom_in | Ctrl++/Ctrl+= | — |
| View | Zoom Out | act_zoom_out | Ctrl+- | — |
| Help | About | act_about | — | — |

**标签切换**：Alt+1~9 → 第 1~9 标签，Alt+0 → 第 10 标签。

**Toolbar**：New | Save | Open | (sep) | Run | Test | Stop | (sep) | Settings（纯图标，无文字）。

### 0.4 信号链路图

```
ProcessManager ───────────────────────────────────────────────
  compile_finished(exit_code, stderr, reason)  ──→  FlowController.on_compile_finished
  run_finished(exit_code, elapsed, peak, reason, error_detail) ──→  FlowController.on_run_finished
  run_stdout_ready(text)  ──→  FlowController.run_stdout_ready  ──→  MainWindow._on_run_stdout_ready ──→  tab.output_buffer.append((None, text))
  run_stderr_ready(text)  ──→  FlowController.run_stderr_ready  ──→  MainWindow._on_run_stderr_ready ──→  tab.output_buffer.append((gray, text))

FlowController ──────────────────────────────────────────────
  state_changed(str)         ──→  MainWindow._update_status_from_state
  status_message(str)        ──→  MainWindow._update_status_message
  busy_message_requested()   ──→  MainWindow._show_busy_message
  terminal_requested(TabData)──→  MainWindow._on_terminal_requested
  output_clear(TabData)      ──→  MainWindow._on_output_clear ──→  tab.output_buffer.clear + _output_clear(tab.output_doc) + pinned_to_bottom=True
  output_append(TabData, color, text) ──→  MainWindow._on_output_append ──→  tab.output_buffer.append((color, text))

TabData ──────────────────────────────────────────────────────
  editor_doc.modificationChanged ──→  TabData._on_modified_changed ──→  dirty_callback ──→  MainWindow._on_tab_dirty_changed

MainWindow ───────────────────────────────────────────────────
  tabbar.currentChanged       ──→  _on_tabbar_current_changed ──→  _switch_to_tab
  tabbar.tabCloseRequested    ──→  _on_tab_close_requested ──→  _handle_close_tab
  tabbar.tabMoved             ──→  _on_tab_moved ──→  TabManager.reorder_tabs
  editor.cursorPositionChanged──→  _on_cursor_position_changed ──→  _update_status_info
  output_panel.vScrollBar.valueChanged──→  _on_output_scroll_changed ──→  pinned_to_bottom 管理
  output_panel.error_jump_requested(filename, line, col)──→  _goto_error_line ──→  ensureCursorVisible + setFocus
  _flush_output_timer (50ms, never stops) ──→  _on_flush_timer ──→  扫描各 tab: flush buffer + truncate if needed + scroll if pinned
```

### 0.5 MainWindow 方法索引

| 分类 | 方法 | 职责 |
|------|------|------|
| **初始化** | `__init_settings` | settings/DPI/icons/windowIcon/geometry |
| | `__init_core_state` | TabManager/FlowController/dialog refs |
| | `__init_widgets` | editor/input/output/placeholder docs |
| | `__init_ui` | actions/menubar/toolbar/mainarea/tabbar/statusbar |
| | `__init_connections` | scroll timer/signals/shortcuts |
| | `__init_final` | drag-drop/zero-tab/window state restore |
| **UI 构建** | `__create_actions` | 从 `_ACTION_DEFS` 数据驱动创建 QAction |
| | `__build_menubar` | File/Edit/Run/View/Help 五个菜单 |
| | `__build_toolbar` | 七个图标按钮 |
| | `__build_mainarea` | splitter/io_section |
| | `__build_tabbar_and_layout` | QTabBar + centralWidget |
| | `__build_statusbar` | status_message(左) + status_info(右, _ClickableLabel) |
| **信号连接** | `__connect_signals` | 所有 action.triggered + tabbar/editor/process signals |
| | `__setup_tab_switch_shortcuts` | Alt+0~9 |
| **File 操作** | `_action_new` | 创建 TabData+add+switch |
| | `_open_file_path` | 打开/切换文件（重复检测） |
| | `_action_open` | QFileDialog → `_open_file_path` |
| | `_action_save` | → `_save_tab_data` |
| | `_action_save_as` | QFileDialog → save + rollback on error |
| | `_action_close` | → `_handle_close_tab` |
| **Edit/View** | `_action_zoom_in/out` | zoom_font_size ± 1 → `_apply_zoom` |
| | `_action_undo/redo/cut/copy/paste` | 路由到 focusWidget |
| | `_action_find/replace/goto_line` | 惰性创建/显示 dialog |
| | `_action_build/run/test/stop` | → FlowController entry methods |
| | `_action_about` | QMessageBox.about |
| **Flow 信号** | `_update_status_from_state` | idle→Ready, compiling→Compiling..., running→Running... |
| | `_update_status_message` | 覆盖 status bar 左侧 |
| | `_show_busy_message` | QMessageBox.information |
| | `_on_terminal_requested` | → `_launch_terminal` + error handling |
| **Settings** | `_action_settings` | SettingsDialog → `_apply_settings` |
| | `_apply_settings` | 更新所有 widget 字体/缩进/wrap/compiler_mtime |
| | `_launch_terminal` | 创建 bat/env → QProcess.startDetached |
| **Output 滚动** | `_on_flush_timer` | 50ms 全局 timer，扫描各 tab flush buffer + truncate if needed + scroll if pinned |
| | `_flush_output_buffer` | 合并相邻同色条目 → 写入 output_doc |
| | `_truncate_output_if_needed` | output_doc 超 `_OUTPUT_MAX_CHARS`(500000) 时裁剪前半+插入截断提示 |
| | `_immediate_flush` | 立即 flush 当前 tab（stdin 提交 / 大输出保护时调用） |
| | `_check_buffer_overflow` | buffer 超 200 条或 64KB 时立即 flush |
| | `_is_output_at_bottom` | sb.maximum() - sb.value() ≤ 3 |
| | `_goto_error_line` | OutputPanel 双击编译错误 → basename 校验 + clamp行列 + setTextCursor + ensureCursorVisible + setFocus |
| | `_on_output_scroll_changed` | __programmatic_scroll=True → 忽略；用户 scroll-up → pinned=False；scroll to bottom → pinned=True |
| | `_on_output_clear(tab)` | FlowController.output_clear 信号 → buffer.clear + _output_clear(doc) + pinned=True |
| | `_on_output_append(tab, color, text)` | FlowController.output_append 信号 → buffer.append |
| | `_on_run_stdout/stderr_ready` | `tab.output_buffer.append((color, text))` |
| **Tab 管理** | `_save_widget_state` | cursor/scroll/input_cursor/input_scroll/output_scroll → tab |
| | `_switch_to_tab` | 保存旧/交换文档/恢复 IO/延迟恢复 editor |
| | `_handle_close_tab` | dirty确认/disconnect/remove/零标签切换/进程清理(cancel_flow) |
| | `_enter/exit_zero_tab_state` | 空文档/灰显/恢复 |
| | `_restore_deferred_cursor` | setTextCursor + scroll |
| | `_start_batch_highlight` | → highlighter.start_batch_highlight |
| **状态/标题** | `_update_status_info` | Ln X/Total, Col X/encoding/INS/OVR |
| | `_show_encoding_menu` | Reopen/Save with Encoding QMenu |
| | `_on_reopen_with_encoding` | dirty确认+重新读取+高亮 |
| | `_on_save_with_encoding` | 新文件→SaveAs + 写入 + rollback |
| | `_update_tab_name/all/window_title` | 标签/窗口标题更新 |
| **保存/确认** | `_save_if_dirty` | dirty→save, clean→0 |
| | `_save_tab_data` | strip trailing + write + rollback on error |
| | `_confirm_close_tab` | Save/Discard/Cancel |
| | `_confirm_reopen_encoding` | Save/Discard/Cancel |
| **信号处理** | `_on_tabbar_current_changed` | → `_switch_to_tab` |
| | `_on_tab_close_requested` | → `_handle_close_tab` |
| | `_on_tab_moved` | → TabManager.reorder_tabs + 更新 current_index |
| | `_on_tab_dirty_changed` | → `_update_tab_name/window_title` |
| | `_on_cursor_position_changed` | → `_update_status_info` |
| **Window state** | `_save_window_state` | geometry/splitter/tabs/recent → JSON |
| | `_load_window_state` | restore all + clamp geometry to screen |
| | `_add_recent_file` | dedup + limit 10 |
| | `_update_recent_menu` | rebuild submenu |
| | `_on_recent_file` | open or warn "not found" |
| **Drag-Drop** | `dragEnterEvent` | URL + extension match → accept |
| | `dropEvent` | → `_open_file_path` for each URL |
| **Lifecycle** | `closeEvent` | dirty确认 + kill process + save state + cancel highlighters |

## 1. 架构概览

MainWindow 为 QMainWindow，从上到下五个区域：

```
MenuBar → Toolbar → TabBar → MainArea → StatusLine
```

- **MenuBar**：File / Edit / Run / View / Help（详见 0.3）
- **MainArea**：QSplitter 水平分割 → 左侧 CodeEditor | 右侧 QSplitter 垂直分割 → InputSection + OutputSection
- **单一 Widget 组**：每个标签页持有三个独立 QTextDocument（editor_doc / input_doc / output_doc），切换标签时通过 `setDocument()` 交换文档，Widget 不销毁重建。Splitter 位置全局共享
- **状态栏**：左侧 `status_message` QLabel（显示状态机默认文本或具体结果覆盖）；右侧 `status_info` _ClickableLabel（显示光标位置/编码/编辑模式，点击弹出编码菜单）
- **UI 语言**：英文（所有界面文字、菜单、对话框、消息均使用英文）
- **主题**：Fusion，Toolbar 七个按钮使用 QPainter 自绘彩色图标（详见第 8 节）
- **初始化分阶段**：MainWindow.__init__ 拆为 `__init_settings` → `__init_core_state` → `__init_widgets` → `__init_ui` → `__init_connections` → `__init_final` 六个子方法
- **FlowController 输出委托**：FlowController 不直接操作 `tab.output_buffer` / `tab.output_doc`，而是通过 `output_clear` / `output_append` 信号委托 MainWindow 写入，保持状态机与数据结构的解耦
- **widget 状态保存**：`_save_widget_state(tab)` 统一保存 cursor/scroll 到 TabData，消除三处重复

## 2. 数据模型

### 2.1 TabData

```python
class TabData:
    file_path: str              # None = 新文件
    is_new: bool                # True = 从未保存到磁盘
    is_dirty: bool              # True = 有未保存更改
    untitled_number: int        # untitled 编号（TabManager 分配）
    editor_doc: QTextDocument   # 含 undo/redo 栈
    input_doc: QTextDocument
    output_doc: QTextDocument   # 含富文本颜色
    cursor: QTextCursor         # 编辑器光标位置
    scroll_pos: int             # 编辑器垂直滚动条位置
    input_cursor: QTextCursor
    input_scroll: int
    output_scroll: int          # 输出面板滚动位置
    encoding: str               # 'UTF-8' 或系统编码名
    zoom_font_size: int         # 字号偏移量（非绝对字号），会话级不持久化
    compiler_mtime: float       # 上次编译时的参数修改时间戳
    _highlight_pending: bool    # 分批高亮尚未完成
    pinned_to_bottom: bool      # 输出面板是否自动跟随最新输出（替代旧 _need_scroll）
    output_buffer: list         # [(color, text)] 缓冲列表，由 flush timer 定期写入 output_doc
    _dirty_callback: callable   # dirty 变化时回调 MainWindow
    highlighter: CppHighlighter # 挂载在 editor_doc 上
```

**标签名规则**：is_new+dirty → `*untitledN*`；is_new+非dirty → `untitledN`；已保存+dirty → `*filename*`；已保存+非dirty → `filename`（`TabData.tab_name()` 方法）。

**脏标记信号**：每个 TabData 的 `editor_doc.modificationChanged` 信号连接到该 TabData 的 `_on_modified_changed`，信号跟随 document 生命周期，不受 Widget 切换影响。`_on_modified_changed` 更新 `is_dirty` 并调用 `_dirty_callback(self)` → MainWindow._on_tab_dirty_changed。

**CppHighlighter 挂载**：TabData 创建时 `CppHighlighter(editor_doc, deferred=True)` 挂载到 editor_doc，生命周期与 TabData 一致。deferred 模式下 highlightBlock 仅追踪多行注释状态，不产生 format spans，避免大文件打开瓶颈。分批高亮由 `_start_batch_highlight` 在文档显示后触发。

### 2.2 TabManager

```python
class TabManager:
    tabs: list              # TabData 列表
    current_index: int      # -1 = 无标签（零标签状态）
    untitled_counter: int   # untitled 编号递增器
```

纯数据管理器，不操作 Widget。所有 UI 操作由 MainWindow 负责。首次启动 `current_index = -1`，关闭最后一个标签后重新进入零标签状态。

**add_tab**：is_new 且 untitled_number ≤ 0 时分配新编号；恢复标签时保留已有编号（untitled_number > 0 时更新 counter）。

**Switch Tab 快捷键**：Alt+1~Alt+9 切换到第 1~9 个标签，Alt+0 切换到第 10 个。超出数量时忽略。

### 2.3 标签切换机制

由 MainWindow._switch_to_tab 实现：

1. 保存旧标签 Widget 状态（cursor、scroll_pos、input_cursor、input_scroll、output_scroll）
2. 取消旧标签 batch highlighting（`highlighter.cancel_batch_highlight()`，设 `_highlight_pending=True`）
3. `setUpdatesEnabled(False)` 冻结重绘（editor + input + output 三个面板）
4. 交换 document：`editor.setDocument(new_tab.editor_doc)` 等
5. 恢复 IO 面板光标（小文档，无延迟）
6. 恢复 zoom 字号
7. `setUpdatesEnabled(True)` 解冻 — 文档内容瞬间显示
8. 恢复输出面板滚动位置（pinned_to_bottom=True 时滚到底部，否则恢复保存的 output_scroll）
9. 设置 tabbar currentIndex（`_tab_switching=True` 阻止 currentChanged 信号）
10. `QTimer.singleShot(0)` 延迟恢复编辑器光标和滚动位置（避免 setTextCursor 的全文档布局开销）
11. 延迟回调检查标签索引是否仍是当前标签，防止快速切换竞态
12. 如果 `_highlight_pending`，触发 `_start_batch_highlight`

**文档字体同步**：CodeEditor/InputPanel/OutputPanel 的 `setDocument()` 重写中调用 `doc.setDefaultFont(self.font())`。文档布局（Tab 定位等）使用 `defaultFont` 计算，字体不一致会导致 Tab 显示宽度错误。

**CodeEditor.setDocument 额外逻辑**：断旧文档的 `blockCountChanged` 信号，连新文档的信号，更新行号区域宽度。同步 `self._highlighter = getattr(doc, '_highlighter', None)`，从文档属性获取 highlighter 引用，消除对 window 层级的穿越访问。TabData 创建 highlighter 时将引用写入 `editor_doc._highlighter`。

**关键属性**：

```python
class MainWindow(QMainWindow):
    settings: Settings                # 全局配置实例
    tab_manager: TabManager           # 纯数据管理器
    flow_ctrl: FlowController         # 状态机
    enc_mgr: EncodingManager          # 编码管理器
    editor: CodeEditor                # 代码编辑器
    input_panel: InputPanel           # 输入面板
    output_panel: OutputPanel         # 输出面板
    tabbar: QTabBar                   # 标签栏
    main_splitter: QSplitter          # 水平分割
    v_splitter: QSplitter             # 垂直分割
    icons: dict                       # toolbar 图标 dict
    _dpi: float                       # DPI factor
    empty_editor_doc: QTextDocument   # 零标签占位文档
    empty_input_doc: QTextDocument
    empty_output_doc: QTextDocument
    _find_dialog: FindDialog          # 惰性创建，初始 None
    _replace_dialog: ReplaceDialog    # 惰性创建，初始 None
    _flush_output_timer: QTimer     # 输出 flush timer（50ms，永不停止）
    __programmatic_scroll: bool     # True 时忽略 scrollbar valueChanged
    _tab_switching: bool              # True 时阻止 currentChanged 信号
    _deferred_restore_tab: int        # 延迟恢复标签索引，-1 = 无
    _last_file_dir: str               # 最近文件目录
    _recent_files: list               # 最近文件列表
    status_message: QLabel            # 状态栏左侧
    status_info: _ClickableLabel      # 状态栏右侧
```

### 2.4 零标签状态

QTextEdit 始终持有一个 QTextDocument，不能为 null。采用**初始 document 占位**策略：

- MainWindow.__init_widgets 创建三个独立的空 QTextDocument 作为占位（`self.empty_editor_doc = QTextDocument(self)` 等），设置 MainWindow 为 parent
- 进入零标签状态：切回空 document，editor `setEnabled(False)` + `setExtraSelections([])` + 隐藏行号区域，input/output section `setEnabled(False)` 灰显，状态栏右侧清空
- 恢复：切回新标签 document，面板 `setEnabled(True)`，editor 行号区域 show

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
- SettingsDialog 操作 `settings.copy()` 临时副本，OK 时 `apply_from(copy)` 提交（deep-copy 可变对象防止共享引用），Cancel 丢弃副本
- 修改 compiler_path/flags/env_vars 时记录 `compiler_mtime = time.time()`，`_apply_settings()` 将所有 TabData 的 compiler_mtime 更新为 settings.compiler_mtime（若旧值更小）
- env_vars 的值中 `$VAR_NAME` 语法在运行时通过 `_expand_env_vars()` 展开为实际环境变量值
- editor_font_family / io_font_family 默认值按平台自动检测 monospace 字体（Windows: Consolas→Courier New→monospace；macOS: Menlo→SF Mono→monospace；Linux: DejaVu Sans Mono→Ubuntu Mono→monospace）
- Settings 有 `to_dict()` 方法序列化为 dict，用于 JSON 保存

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

首次运行不存在时使用默认值。`load()` 只加载 `_SETTINGS_DEFAULTS` 中存在的键，忽略未知键。env_vars 值非 dict 时回退为 {}。

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
- last_file_dir 恢复后若目录不存在则回退到 ~/
- geometry 保存时：最大化窗口使用 normalGeometry；clamp 坐标确保标题栏在屏幕可见区域内；恢复时 clamp 窗口尺寸和位置到当前屏幕可用区域
- 跳过 is_new 且非 dirty 的标签（用户选择了 Discard）

## 3. 编辑器组件

### 3.1 CodeEditor

继承 QTextEdit（setAcceptRichText=False），核心功能：

**行号显示**：左侧 LineNumberArea 作为子 Widget，宽度按最大行号位数动态调整。`_paint_line_numbers` 通过 `_estimate_first_visible_block()` 估算首个可见 block，仅迭代可见区域（7500+ 行文件滚动到底部仅迭代约 50 个 block）。

**Tab 制表符**：indent_style='tab' 时插入 `\t`，indent_style='space' 时插入 `indent_size` 个空格。Tab 宽度 = `fontMetrics().horizontalAdvance('x') * indent_size`，indent_size 默认 4，可在 Settings 中配置。

**字体变更联动**：更换字体或字号时，必须调用 `updateFontMetrics()` 重新计算 Tab 宽度，并同步 `document.setDefaultFont(editor.font())`，否则 Tab 显示宽度错误。CodeEditor 有专门的 `setFontSize(point_size)` 方法设置字号并刷新 metrics，Zoom 功能通过此方法实现。

**括号补全**：输入开符号自动插入闭符号并光标置中间；输入闭符号时光标右侧恰好同一闭符号则跳过；删除开符号时右侧紧邻闭符号一并删除。可通过 Settings 开关控制（默认启用）。**上下文感知**：`_is_bracket_in_comment_or_string(pos)` 检查光标位置是否在注释/字符串内，是则跳过自动补全。开符号 `_handle_bracket_open` 返回 False 表示不处理；闭符号 `_handle_bracket_close` 返回 False 表示不跳过，均使用 `self._highlighter`（从 CodeEditor._highlighter 获取，通过 setDocument 同步），而非穿越 window 层级。该方法检查 highlighter.format() 的前景色，deferred 模式下检查 block state（多行注释）+ 行内文本 regex 检查字符串。引号 `"` `'` 也纳入括号补全（`_BRACKET_OPEN` 包含引号），引号闭符号跳过逻辑：光标右侧恰好同一引号时跳过。

**自动缩进**：Enter 键 — `_handle_enter_key` 取当前行前导空白作为新行基础缩进（`__extract_indent`）；当前行末 `{` 时增加一级缩进（indent_style='tab' 加 `\t`，indent_style='space' 加 `indent_size` 个空格）；光标在 `{` 和 `}` 之间时插入两行（`{` 后新行 + 缩进 + `}` 行缩进），光标置中间行。

**Smart Backspace**：光标无选区、列号在缩进整数倍边界、左侧到行首全是空格时，一次删除 indent_size 个空格。不限定 indent_style。

**改写模式**：Insert 键切换 overwrite_mode，输入字符时先删除光标右侧一个字符再插入。状态栏显示 INS/OVR。**光标宽度变化**：overwrite 模式时光标宽度设为 `fontMetrics().horizontalAdvance('x')`（一个字符宽），正常模式宽度为 1px。`_notify_overwrite_changed` 方法处理光标形状更新。Paste 操作不受改写模式影响。

**Zoom**：Ctrl++ 放大字号（步长 1pt），Ctrl+- 缩小（最小 6pt）。仅改 CodeEditor，不影响 IO 面板；会话级不持久化。字号存入 TabData.zoom_font_size（**偏移量**，非绝对字号，显示字号 = settings.editor_font_size + tab.zoom_font_size）。Settings 中修改编辑器字号后所有标签的 zoom 偏移重置为 0，显示字号回到 Settings 基准值；修改非字体相关设置（如编译参数、超时）时 zoom 偏移保留不变。

**Comment/Uncomment (Ctrl+/)**：`_handle_comment_uncomment` 方法。无选区时操作当前行；有选区时操作所有被选中的行。Toggle 逻辑：检查所有操作行是否已以 `//` 开头（忽略行首空白，空行视为未注释），若全部已注释则移除 `//` 及紧随的所有空格，否则对每行首个非空白字符前插入 `// `（含空格）。

**Indent/Unindent**：`_handle_indent_selection` / `_handle_unindent_selection` 方法。有选区时 Tab → 选中行每行行首加 `\t`（indent_style='tab'）或 indent_size 个空格（indent_style='space'）；Shift+Tab → 选中行每行行首移除一个 `\t` 或 indent_size 个空格。无选区时 Tab 插入 `\t`（原有行为不变），Shift+Tab → 当前行行首移除一个 `\t` 或 indent_size 个空格（与 Ctrl+[ 一致）。菜单快捷键：Indent = Ctrl+]，Unindent = Ctrl+[。无选区时 Ctrl+] 缩进当前行，Ctrl+[ 反缩进当前行。操作后选区恢复为 linewise（锚点在首行行首，光标在末行行尾+1），确保多次缩进/反缩进不会让选区漂移到其他行。

**Duplicate Line (Ctrl+D)**：`_handle_duplicate_line` 方法。无选区 → 选中当前 block 全文，copy 后 insert 到下一行；有选区 → 复制选区文本 insert 到选区末尾之后。不操作剪贴板。

**Delete Line (Ctrl+Shift+K)**：`_handle_delete_line` 方法。无选区 → 删除当前 block；有选区 → 删除所有被选中的 block（含末尾 block 即使选区只到其开头）。

**Move Line Up/Down (Alt+Up/Alt+Down)**：`_handle_move_line_up` / `_handle_move_line_down` 方法。无选区 → 当前 block 与上方/下方 block 互换，光标跟随移动；有选区 → 选中 block 范围与上方/下方 block 互换，选区范围调整。

**当前行高亮**：使用 QTextEdit.ExtraSelection，浅色背景（`QColor(245, 245, 220)` 浅黄），cursorPositionChanged 信号触发 `_update_extra_selections`。每次光标移动时清空旧 ExtraSelection 再添加新的。只在 CodeEditor 中启用（`isEnabled()` 检查），不影响 InputPanel/OutputPanel。零标签状态下清空 ExtraSelection。

**括号匹配高亮**：使用 QTextEdit.ExtraSelection。光标位于括号字符旁时（检查光标位置和前一位置），通过 `_find_matching_bracket` 搜索配对括号位置，两个括号同时添加背景色高亮（`QColor(180, 220, 255)` 浅蓝）。仅在非注释/非字符串上下文中生效（`_is_bracket_in_comment_or_string` 检查）。与当前行高亮合并处理在同一 `_update_extra_selections` 方法中。

**#include <> 自动补全**：`_handle_include_angle` 方法。当输入 `<` 且当前行以 `#include` 开头时，自动插入 `>` 并光标置中间。否则 `<` 不触发补全。

**/* */ 自动补全**：两个独立方法处理：
- `_handle_star_for_comment_open`：输入 `*` 且光标左侧字符为 `/`（即刚输入 `/*`）时，自动插入 ` */`（含前导空格）并光标置 `/*` 和 `*/` 之间。不重复触发：右侧已有 ` */` 时不再次补全。
- `_handle_slash_for_comment`：输入 `/` 且光标左侧为 `*`（即正在输入 `*/`）且右侧恰好为 `/`（来自自动补全的闭合符）时跳过，与闭括号跳过逻辑一致。

**右键上下文菜单**：`contextMenuEvent` override。创建 QMenu 包含：Undo、Redo、separator、Cut、Copy、Paste、separator、Comment/Uncomment、Indent、Unindent、Duplicate Line、Delete Line。动作与 Edit 菜单和快捷键共享 QAction 实例。

**setDocument 重写**：断旧文档 `blockCountChanged` 信号，连新文档信号，更新行号区域宽度。

### 3.2 CppHighlighter

规则分组与颜色（`__init_rules` 方法，按优先级顺序）：

| # | 分组 | 正则 | 颜色 |
|---|------|------|------|
| 1 | 单行注释 | `//[^\n]*` | 绿色 `QColor(0, 128, 0)` |
| 2 | 字符串 | `"[^"\\\n]*(?:\\.[^"\\\n]*)*"` | 深红色 `QColor(163, 21, 21)` |
| 3 | 字符 | `'[^'\\\n]*(?:\\.[^'\\\n]*)*'` | 深红色 |
| 4 | 关键字 | `\b(CPP_KEYWORDS)\b` | 蓝色 `QColor(0, 0, 255)` |
| 5 | 预处理器 | `^#\s*(CPP_PREPROCESSOR)\b` | 蓝色 |
| 6 | 数字（含十六进制、二进制） | 复合正则 | 深蓝色 `QColor(0, 0, 128)` |
| 7 | 符号/运算符 | C++ 运算符复合正则 | 深青色 `QColor(0, 128, 128)` |

规则顺序决定优先级（first-match-wins）。多行注释**优先于**单行规则处理——`highlightBlock` 中先调用 `__highlight_multiline_comments` 再执行单行规则，原因是 Qt 的 format overlay 采用"first-format-wins"语义：先覆盖某位置的 format span 优先，后到的 `setFormat` 无法覆盖已设格式。若单行规则先运行，关键字/字符串等会占据注释内的位置，多行注释的绿色就无法覆盖。改为多行注释先运行后，注释内的位置先拿到绿色格式，后续 `__format_if_free` 检查时发现这些位置非"空闲"就自动跳过，保留绿色。`__highlight_multiline_comments` 查找 `/*` 时使用 `__is_position_masked`（regex 方式）而非 `self.format(idx)` 判断空闲，因为多行注释先运行时尚无 format spans 可查。多行注释使用 `setCurrentBlockState/previousBlockState` 跟踪跨块状态（0=正常，1=在注释内）。

**First-match-wins 实现细节**：

- `__format_if_free(start, length, fmt)`：遍历范围内的每个位置，检查 `self.format(i)` 的前景色——空或默认色（`QColor()`）视为"空闲"，仅在空闲位置设置格式，跳过已被更高优先级规则占据的位置。连续空闲段合并为一次 `setFormat` 调用。
- `__is_position_masked(text, pos)`：通过 regex 模拟 first-match-wins 语义——收集字符串/字符字面量范围，再收集不在字符串内的 `//` 注释范围，检查 pos 是否落入任一范围。在 deferred 模式和非 deferred 模式（多行注释先运行、尚无 format spans）下均使用此方法判断 `/*` 是否在字符串/单行注释内。
- `__find_free_multi_start(text, offset)`：查找下一个不被字符串/字符/单行注释遮蔽的 `/*`，使用 `__is_position_masked` 逐个跳过被遮蔽的匹配。deferred 和非 deferred 模式统一使用此方法。
- `__highlight_multiline_comments(text)`：非 deferred 模式的多行注释处理，使用 `__find_free_multi_start` 查找不被字符串/单行注释遮蔽的 `/*`。找到匹配的 `*/` 后格式化整段（直接 `setFormat`，不检查空闲——注释内容应全部绿色），然后继续搜索后续 `/* */` 对。
- `__track_multiline_state(text)`：deferred 模式的多行注释状态追踪，使用 `__find_free_multi_start` 替代 raw regex match，确保字符串内的 `/*` 不触发注释状态转移。

**延迟+分批高亮**：
- deferred=True 模式下 `highlightBlock` 仅追踪多行注释状态不产生 format spans
- 文档先以无高亮状态显示（layout 快 ~0.5s）
- `_switch_to_tab` 通过 `QTimer.singleShot(0)` 触发 `_start_batch_highlight`
- `start_batch_highlight(editor_widget, batch_size=100)` 方法：关闭 deferred，从 block 0 开始每批 rehighlightBlock 100 个 block，批间 `QTimer.singleShot(0)` 保持 UI 响应（`__process_highlight_batch`）
- 切换标签时取消旧标签的 batch highlighting（`cancel_batch_highlight`），设 `_highlight_pending=True`
- `cancel_batch_highlight` 停止 timer、断信号、重设 `_deferred=True`

**format(pos) 方法**：继承自 `QSyntaxHighlighter.format(int)`，返回指定位置（block 内 local position）的 QTextCharFormat。`_is_bracket_in_comment_or_string` 调用此方法查询高亮格式。

**关键属性**：

```python
class CppHighlighter:
    _rules: list           # [(QRegularExpression, QTextCharFormat)]
    _deferred: bool        # 是否延迟模式
    _batch_block_number: int  # 分批当前 block 编号
    _batch_timer: QTimer   # 分批 timer
    _batch_editor: QWidget # 分批关联的 editor widget
    _batch_size: int       # 每批 block 数量（默认 100）
```

### 3.3 FileDragMixin

Mixin 类（非 QObject），三个方法 override：`dragEnterEvent`、`dragMoveEvent`、`dropEvent`。URL 拖放时 `event.ignore()` 让事件传播到 MainWindow 处理；非 URL 拖放（纯文本）调用 `super()` 交给 QTextEdit 默认行为。

### 3.4 _IOPanelBase

继承 FileDragMixin + QTextEdit，共享 `setDocument()` 逻辑（`doc.setDefaultFont(self.font())` + `super().setDocument(doc)`），消除 InputPanel 和 OutputPanel 的重复。

### 3.5 InputPanel

继承 `_IOPanelBase`（setAcceptRichText=False），外层 `_make_io_section` 包装（QWidget + QLabel "INPUT"）。字号/字体跟随 Settings.io_font_family/io_font_size。Tab 键插入制表符（keyPressEvent override），tabStopWidth = `indent_size * charWidth`。Enter 键提交时立即 flush 当前 tab 的 output_buffer，确保交互式程序的 prompt 快速显示。setDocument() 由基类提供。零标签状态下灰显。

### 3.6 OutputPanel

继承 `_IOPanelBase`（只读），外层 `_make_io_section` 包装（QWidget + QLabel "OUTPUT"）。setDocument() 由基类提供。支持多色富文本。

**输出机制**：所有输出数据不直接写入 output_doc，而是追加到 TabData 的 `output_buffer` 列表（`(color, text)` 元组）。全局 `_flush_output_timer`（50ms 间隔，永不停止）定期扫描每个 tab 的 buffer：

1. buffer 非空时：合并相邻同 color 条目 → 逐条用 QTextCursor 写入 output_doc → 清空 buffer
2. flush 后检查 `_truncate_output_if_needed`：output_doc 字符数超过 `_OUTPUT_MAX_CHARS`（500000）时裁剪前半内容并插入灰色截断提示 `[...output truncated...]`
3. 当前 tab 且 `pinned_to_bottom=True` 时：滚动到最后一行
4. 非当前 tab：仅 flush，不滚动
5. tab 切换时：若新 tab `pinned_to_bottom=True` 则滚到底部，否则恢复保存的 `output_scroll`

**大输出保护**：`_check_buffer_overflow` 检查 buffer 积累超过 64KB 或 200 条时，立即执行 `_immediate_flush`（不等 tick）。stdin 提交（InputPanel Enter）时也立即 flush 当前 tab，保证交互式程序 prompt 快速显示。

**输出截断**：`_truncate_output_if_needed` 在每次 flush 后检查 output_doc 的 `characterCount`。超过 `_OUTPUT_MAX_CHARS`(500000) 时，删除前半部分内容并在开头插入灰色 `[...output truncated...]` 提示。防止失控程序消耗过多内存和拖慢 UI。

**pinned_to_bottom 状态管理**：

- 初始化 / 清空 OutputPanel / 程序启动（进入 compiling/running）时设为 True
- 用户将滚动条往上拉（离开最后一行）时设为 False
- 用户将滚动条拉回最后一行时设为 True
- End 键：设为 True 并立即滚到底部（OutputPanel.keyPressEvent 处理 `Qt.Key_End`）
- `_is_output_at_bottom()` 判断距离底部不超过 3px 即视为在底部

**双击跳转编译错误**：OutputPanel 定义 `pyqtSignal(str, int, int)` 信号 `error_jump_requested`（filename, line, col）。`mouseDoubleClickEvent` 中用 `cursorForPosition` 获取点击位置的文本行，正则 `^([^:\s]+):(\d+):(?:(\d+):)?\s*(?:error|warning)` 匹配 gcc 错误格式。匹配成功时 emit 信号并 `return`（跳过 QTextEdit 默认选词），匹配失败时调用 `super().mouseDoubleClickEvent` 正常选词。MainWindow 在 `__connect_signals` 中连接信号到 `_goto_error_line`。

`_goto_error_line(filename, line, col)`：获取当前 tab，校验 `os.path.normcase(basename)` 匹配 filename（防止跳到错误文件），clamp 行列到文档有效范围，`setTextCursor` + `ensureCursorVisible` + `setFocus`。

**区分用户滚动与程序滚动**：Timer tick 中的程序性滚动会触发 scrollbar valueChanged。引入 `MainWindow.__programmatic_scroll` 布尔标志，程序性滚动前设为 True，完成后设为 False。`_on_output_scroll_changed` 检测到 `__programmatic_scroll=True` 时忽略，不改变 pinned 状态。

**颜色规范**：

| 内容类型 | 颜色 |
|----------|------|
| stdout | 默认前景色（QPalette.Text）— color=None |
| stderr | 灰色 `QColor(128, 128, 128)` |
| 退出状态行 / Build 成功 / Process stopped | 灰色 |
| 编译错误 / Runtime Error / 超时 / Failed to start / Program crashed | 红色 `QColor(Qt.red)` |

**退出状态行换行**：所有运行结果行（exit with code、Runtime Error、Timeout、Process stopped、Program crashed）前追加 `\n`，确保程序输出不以换行结尾时状态行不接在输出末尾。

每次 Test/Build 清空后重新写入全部内容，不追加。

## 4. 编译运行系统

### 4.1 ProcessManager

```python
class ProcessManager(QObject):
    process: QProcess
    busy: bool                # 由状态机驱动
    mode: str                 # 'compile' / 'test_run' / None
    target_tab: TabData       # 输出路由目标
    start_time: float         # 进程启动时间戳
    _peak_memory: int         # 内存峰值（字节）
    _memory_timer: QTimer     # 内存轮询 timer
    _timeout_timer: QTimer    # 超时 timer
    _tracked_pid: int         # 被追踪进程 PID
    _tracked_process: Process # psutil.Process 缓存
    _stdin_data: bytes        # stdin 数据
    _enc_mgr: EncodingManager # 编码管理器
    _stderr_buffer: str       # 编译 stderr 缓存
    _finished_emitted: bool   # 防止二次 emit 标志

    signals:
        compile_finished(exit_code, stderr_text, reason)
        run_stdout_ready(text)
        run_stderr_ready(text)
        run_finished(exit_code, elapsed, peak_memory, reason, error_detail)
```

**reason 参数**：统一传达退出原因，消除信号竞争。

| reason | 含义 | 触发场景 |
|--------|------|----------|
| normal | 正常退出 | 进程正常结束 |
| killed | 被 kill 终止 | 用户 Stop 或自然崩溃（CrashExit） |
| timeout | 超时 | QTimer 超时，先 kill 再 emit |
| failed_to_start | 无法启动 | errorOccurred 信号异步处理 FailedToStart |

**error_detail 参数**：仅在 `failed_to_start` 时填充，内容为 `QProcess.errorString()`，其他 reason 时为空字符串。

**防止二次 emit**：`_finished_emitted` 标志位。`finished` 信号和 `errorOccurred` 信号可能竞态（进程快速崩溃），_finished_emitted 确保只 emit 一次。

**stdout/stderr handler None 保护**：`_on_compile_stderr_ready` / `_on_run_stdout_ready` / `_on_run_stderr_ready` 入口检查 `self.process is None`，防止 `_cleanup()` 后排队信号到达导致 AttributeError。

**异步错误处理**：使用 `errorOccurred` 信号（PyQt5 < 5.10 用 `error` 信号兼容）处理 FailedToStart，替代 `waitForStarted(5000)` 阻塞调用。`_on_compile_error` / `_on_run_error` 在 `_finished_emitted=False` 时处理 FailedToStart：停止 timeout timer → `_cleanup()` → emit finished 信号。

**_on_run_started**：Test 运行进程 `started` 信号触发，写入 stdin 数据 + `closeWriteChannel()`。确保进程已启动后才写入 stdin。

**killed 分支行为**：自然崩溃（如 Windows access violation）QProcess 报 CrashExit + 负 exit code，`_describe_exit_code` 附加已知 NTSTATUS 码可读描述（红色），无描述时显示灰色 "Process stopped"。已知的 NTSTATUS 码：Access violation (0xC0000005)、Stack overflow (0xC00000FD)、Integer divide by zero (0xC0000094)、Integer overflow (0xC0000095)、Float divide by zero (0xC0000090)、Float overflow (0xC0000091)、DLL not found (0xC0000135)、Heap corruption (0xC0000374)。

**输出路由**：启动 Test/Build 时记录 `target_tab`，stdout/stderr 和结束信号始终路由到 `target_tab`，不受标签切换影响。

**QProcess 配置**：SeparateChannels；编译进程只读 stderr；运行进程分别读 stdout/stderr；Test 模式写入 stdin 后 closeWriteChannel()。

**_cleanup() 方法**：停止内存追踪、停止 timeout timer、断所有 process 信号（finished/readyRead*/started/errorOccurred）、deleteLater process、重置 busy/mode/target_tab/_stdin_data 为 None/False。

**_stop_timeout_timer() 方法**：停止 `_timeout_timer` 并置为 None，供 timeout handler 和 error handler 调用，避免手动重复此逻辑。

**drain_remaining_output() 方法**：在 `_cleanup()` 之前调用，从 QProcess 排空残留 stdout/stderr 数据并解码为文本，返回 `(stdout_text, stderr_text)`。供 `FlowController.cancel_flow()` 使用，确保关闭标签/窗口时不丢失管道中剩余输出。

### 4.2 FlowController

FlowController 是独立的 QObject，持有编译/运行状态机的全部逻辑。**所有对 TabData 数据的写操作通过 output_clear/output_append 信号委托 MainWindow**，FlowController 不直接操作 `tab.output_buffer` 或 `tab.output_doc`。MainWindow 只负责 UI 跟进（status bar、QMessageBox、scroll timer、launch_terminal）和接收输出信号写入 TabData。

```python
class FlowController(QObject):
    state: str           # IDLE/COMPILING/RUNNING（使用常量 _FLOW_IDLE/_FLOW_COMPILING/_FLOW_RUNNING）
    intent: str          # build/test/run
    tab: TabData         # 发起流程的标签页
    proc_mgr: ProcessManager  # 内部持有的进程管理器
    settings: Settings   # 设置引用
    enc_mgr: EncodingManager  # 编码管理器引用

    signals:
        state_changed(str)        # 状态名 → MainWindow._update_status_from_state
        status_message(str)       # 具体结果消息 → MainWindow._update_status_message
        busy_message_requested()  # → MainWindow._show_busy_message
        terminal_requested(TabData) # → MainWindow._on_terminal_requested
        output_clear(TabData)     # → MainWindow._on_output_clear（清空 buffer + doc + pinned=True）
        output_append(TabData, color, text) # → MainWindow._on_output_append（追加到 buffer）
        run_stdout_ready(str)     # 转发 ProcessManager.run_stdout_ready → MainWindow
        run_stderr_ready(str)     # 转发 ProcessManager.run_stderr_ready → MainWindow
```

**核心方法**：

| 方法 | 说明 |
|------|------|
| start_build(tab) | 入口：检查 busy → set_state(COMPILING,intent=build) + clear_and_start_compile |
| start_test(tab) | 入口：检查 busy → need_recompile 则 COMPILING(intent=test)，否则 RUNNING + start_test_run |
| start_run(tab) | 入口：检查 busy → need_recompile 则 COMPILING(intent=run)，否则 emit terminal_requested |
| kill_if_busy() | 如果 COMPILING/RUNNING → proc_mgr.kill_process() |
| cancel_flow() | kill process + waitForFinished(500ms) + drain_remaining_output + _cleanup + set_state(IDLE)；排空数据通过 output_append 信号路由。返回被处理的 tab |
| set_state(state, tab, intent) | 状态转移 + emit state_changed |
| need_recompile(tab) | exe 不存在 / exe_mtime < source_mtime / exe_mtime < tab.compiler_mtime |
| get_exe_path(tab) | 源文件同目录 + .exe（Windows）/ 无扩展名（其他） |
| build_compile_command(tab) | [resolved_compiler] [编码flags] [用户flags] basename.cpp -o basename.exe -lstdc++ |
| make_process_env() | QProcessEnvironment.systemEnvironment + env_vars + bin_dir PATH prepend |
| clear_and_start_compile(tab) | emit output_clear + emit output_append(Compiling...) + start_compile |
| start_test_run(tab) | emit output_clear + start_test_run + stdin from input_doc |
| count_compile_errors(stderr) | 统计 `: error:` 行数，无则返回 1 或 0 |
| on_compile_finished(exit_code, stderr, reason) | 编译完成回调：状态转移 + emit output_clear/output_append + emit status_message |
| on_run_finished(exit_code, elapsed, peak, reason, error_detail) | 运行完成回调：状态转移 + emit output_append + emit status_message |

**信号分工**：FlowController **不直接操作** `tab.output_buffer` 或 `tab.output_doc`，所有对输出数据的写操作（清空、追加编译/运行结果行）通过 `output_clear` / `output_append` 信号委托 MainWindow。MainWindow 接收信号后写入对应 tab 的 `output_buffer`，全局 `_flush_output_timer` 定期 flush 到 output_doc 并处理滚动。`run_stdout_ready/run_stderr_ready` 由 FlowController 转发 ProcessManager 的信号到 MainWindow，MainWindow 接收后追加到 `tab.output_buffer`。`state_changed` 发出状态名用于 status bar 默认文本；`status_message` 发出具体结果文本覆盖 status bar。

**状态机**：FlowController 使用显式状态机：`state`（IDLE/COMPILING/RUNNING）、`intent`（build/test/run）、`tab`。

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

COMPILING +normal(exit0)+build → IDLE（"Build OK in Xs"）
COMPILING +normal(exit0)+test  → RUNNING
COMPILING +normal(exit0)+run   → IDLE（"Build OK" + 弹外部终端）
COMPILING +normal(exit≠0)      → IDLE（红色错误）
COMPILING +failed_to_start     → IDLE（"Failed to start compiler" + error_detail + Settings 提示）
COMPILING +timeout             → IDLE（"Compilation timeout after Xs"）
COMPILING +killed              → IDLE（灰色 "Compilation stopped in Xs"）

RUNNING +normal(exit0)         → IDLE（灰色 "exit with code 0 in Xs, XMB"）
RUNNING +normal(exit≠0)        → IDLE（红色 "Runtime Error (exit code X)" + crash detail）
RUNNING +failed_to_start       → IDLE（红色 "Failed to start program" + error_detail）
RUNNING +timeout               → IDLE（红色 "Timeout after Xs"）
RUNNING +killed(crash描述)     → IDLE（红色 "Program crashed: detail (exit code X)"）
RUNNING +killed(无描述)        → IDLE（灰色 "Process stopped in Xs"）
```

**重编译判断**：exe 不存在 / exe_mtime < source_mtime / exe_mtime < tab.compiler_mtime → 需要重编译。

**failed_to_start 处理细节**：
- 编译进程：清空 output_doc → 红色 "Failed to start compiler 'path'" + 红色 "Error: error_detail" + 灰色 "Please check Settings..."
- 运行进程：清空 output_doc → 红色 "Failed to start program" + 红色 "Error: error_detail"

### 4.3 编译命令

`FlowController.build_compile_command` 生成的完整命令：

```
[resolved_compiler] [编码flags] [用户compiler_flags] basename.cpp -o basename.exe -lstdc++
```

- `resolved_compiler`：通过 `_resolve_compiler_path` 解析 compiler_path（裸名→原值，绝对路径→原值+取bin_dir，相对路径→基于 __file__ resolve 成绝对路径+取bin_dir）
- 编码 flags 由 EncodingManager.build_flags 生成（详见第 5 节）
- 用户 `compiler_flags` 使用 `shlex.split()` 解析为 argv 列表，支持带引号参数和带空格路径；shlex 解析失败时 fallback 到 `split()`
- `-lstdc++` 末尾固定追加，确保误选 gcc 时也能链接 C++ 标准库
- 源文件名和 exe 名使用相对路径（`os.path.basename()` 取纯文件名），cwd 已设为源文件目录，gcc 报错信息简短
- 不再对文件路径做 `/` → `\\` 转换，`os.path.basename()` 已返回平台本地文件名

### 4.4 PATH 注入

compiler_path 含路径组件时，自动将编译器所在目录 prepend 到 PATH：

- `_resolve_compiler_path(compiler_path)` 返回 `(resolved_path, bin_dir)`，bin_dir 为空字符串时（裸名）不修改 PATH
- `FlowController.make_process_env()` 在 bin_dir 非空时 prepend 到 PATH 前端（Windows 用 `;` 分隔，其他平台用 `:`）
- 编译进程和 Test 运行进程均通过此 QProcessEnvironment 获得正确的 PATH
- 不修改 CodeRunner 主进程 PATH，每个子进程获得干净独立的 PATH

### 4.5 Run 外部终端（Windows）

使用固定路径 `%TEMP%\coderunner.cmd`：

```batch
@echo off
%CR_SET_PATH%
%CR_ENV_SETUP%
call %CR_COMMAND%
set CR_EXITCODE=%ERRORLEVEL%
call %CR_PAUSE%
exit %CR_EXITCODE%
```

环境变量：CR_COMMAND（exe 路径）、CR_PAUSE（`pause` 或 `rem`）、CR_SET_PATH（`set PATH=bin_dir;%PATH%` 或 `rem no path prefix`）、CR_ENV_SETUP（用户 env_vars 的 `set key=value` 行或 `rem no custom env`）。

`_ensure_cmd_file()` 检查 bat 文件是否已存在且内容一致，仅在内容不同时重写，避免每次运行写文件。

设计要点：固定文件名避免残留垃圾；固定内容消除并发竞态；环境变量隔离天然安全。CR_ 前缀变量只临时设在 os.environ 中（startDetached 前设置、后还原），不逐个设置用户环境变量，减少全局状态污染。用户 env_vars 中 CR_ 前缀的键不被设置到 bat 中。

启动流程：检查/创建 bat → 临时设 os.environ 4 个 CR_ 变量 → QProcess.startDetached → 还原 os.environ。

终端启动失败时：清空 output_doc → 红色 "Failed to launch terminal" + status_message 覆盖。

### 4.6 内存占用采集

如果 `psutil` 可用：进程启动后 QTimer（100ms 间隔）轮询 `psutil.Process(pid).memory_info()`，记录 rss 峰值到 `_peak_memory`。NoSuchProcess 异常忽略（进程已结束）。进程结束时停止 QTimer，将 peak_memory 追加到退出状态行（如 "exit with code 0 in 0.015s, 1.2MB"）。

**psutil.Process 缓存复用**：`_start_memory_tracking(pid)` 创建 Process 对象缓存到 `_tracked_process`，`_poll_memory` 直接使用缓存而非每 100ms 重新创建 Process。

## 5. 编码策略

### 5.1 EncodingManager

核心原则：**用户不需要关心编码，CodeRunner 自动处理一切**。

**文件编码检测**（`_read_file(path)` 函数，打开文件时）：
1. 前 3 字节为 `\xEF\xBB\xBF` → UTF-8 BOM，跳过 BOM 后解码
2. 整文件 UTF-8 严格解码成功 → UTF-8
3. 以上失败 → 系统编码（Windows 'GBK'，其他 'UTF-8'）

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
- InputPanel → stdin：`encode_stdin(text)` → `text.encode(platform_charset)`
- stdout/stderr → OutputPanel：`decode_stdout(data)` / `decode_stderr(data)` → `bytes.decode(platform_charset, 'replace')`

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
  - Auto Detect：`_auto_detect_compiler()` 搜索 `_COMPILER_SEARCH_PATHS` 列表（MinGW/TDM-GCC/Dev-Cpp/msys64）+ PATH 中的 g++/gcc
- 编译参数：QLineEdit（如 `-std=c++14 -O2`），默认留空
- 环境变量：QTableWidget（Key/Value），Add Row 按钮，Value tooltip 提示 `$VAR_NAME` 语法
- 运行超时：QSpinBox（1-300，默认 10）
- 编译超时：QSpinBox（1-300，默认 20）

**Editor 页**：
- 编辑器字体/字号：QFontComboBox（MonospacedFonts filter）+ QSpinBox（6-72，默认 11）
- IO 面板字体/字号：QFontComboBox + QSpinBox
- 括号补全：QCheckBox（默认勾选）
- 缩进风格：QComboBox（Tab / Space）
- Tab 宽度：QSpinBox（2-16，默认 4）— 同时控制 Tab 视觉宽度和空格缩进步长
- Word Wrap：QCheckBox（默认不勾选）

**Template 页**：
- QPlainTextEdit 编辑模板文本
  - tabStopWidth 实时跟随 Tab Width 设置（`spin_indent_size.valueChanged` 信号联动 `_update_template_tab_width`）
  - 自动缩进：`eventFilter` 处理 Enter 键，复制当前行前导空白到新行，行末 `{` 时增加一级缩进（Tab 模式插入 `\t`，Space 模式插入 indent_size 个空格）
- Reset to Default 按钮

OK 时：验证 → apply_from(copy) → save JSON → compiler_path/flags/env_vars 变化则更新 `compiler_mtime = time.time()`。Cancel 时丢弃副本。保存失败时弹警告但不 reject（accept 继续）。

### 6.2 FindDialog

非模态 QDialog：QLineEdit + 大小写敏感 QCheckBox + 向上/向下 QRadioButton + Find Next/Close 按钮。目标为 CodeEditor，使用 `QTextDocument.find()`。未找到时标题栏追加 "Not found"。关闭时 `hide()` 不销毁，保留上次输入。FindDialog 在 MainWindow 中惰性创建（`self._find_dialog`），Ctrl+F 时 show + activateWindow + focus + selectAll。搜索到末尾/开头时自动从头/尾继续搜索（wrap-around）。

### 6.3 ReplaceDialog

非模态 QDialog，FindDialog 基础增加：替换文本 QLineEdit + Replace / Replace All / Close 按钮。关闭时隐藏保留状态。ReplaceDialog 同样惰性创建。Replace 先检查当前选中文本是否匹配查找文本（区分大小写选项），匹配则替换后自动 Find Next。Replace All 用 QTextCursor 从头遍历替换所有匹配项，完成后标题栏显示替换数量。搜索同样支持 wrap-around。

### 6.4 GotoLineDialog

`QInputDialog.getInt()` 弹出，输入行号（1 ~ 文档总行数），确认后移动光标到目标行首并 `ensureCursorVisible()` 滚动到可见位置。快捷键 Ctrl+G。

### 6.5 About 对话框

`QMessageBox.about()` 弹出，标题 "About CodeRunner"，内容 "CodeRunner\n\nAuthor: skywind3000\n{当前时间}"。快捷键无（Help 菜单 About 项触发）。

### 6.6 编码选择菜单

状态栏编码标签使用 `_ClickableLabel`（继承 QLabel），设置 `PointingHandCursor` 提示可点击。`setMainWindow(mw)` 方法设置引用。点击 → `mousePressEvent` 调用 `mw._show_encoding_menu(self)`。`_show_encoding_menu` 创建 QMenu："Reopen with Encoding" / "Save with Encoding"，列出 `_COMMON_ENCODINGS`（UTF-8、GBK、GB18030、Big5、Shift_JIS、EUC-JP、EUC-KR、ISO-8859-1、ISO-8859-2、Windows-1252、Windows-1251）。菜单弹在标签底部左侧。

- **Reopen with Encoding**：`_on_reopen_with_encoding` — dirty 时弹出 `_confirm_reopen_encoding` 确认对话框（Save/Discard/Cancel）→ 用指定编码直接 `open(path, encoding=encoding)` 重新读取（不经过 `_read_file`，不做 BOM 检测/剥离）→ 更新 `tab.encoding` → blockSignals + setPlainText + setModified(False) → 重新触发语法高亮（`highlighter.cancel_batch_highlight()` + `highlighter.rehighlight()`）→ `_highlight_pending=False` + `is_dirty=False`。新文件（is_new=True）不可 Reopen。
- **Save with Encoding**：`_on_save_with_encoding` — 新文件先弹出 Save As 对话框选路径，取消则不保存。用指定编码直接写入文件（**不调用 `_strip_trailing_whitespace_in_doc`**，与 `_save_tab_data` 不同）。写入成功后更新 `tab.encoding` + `editor_doc.setModified(False)` + `is_dirty=False`。保存失败（如 UnicodeEncodeError）时 rollback file_path/is_new 并弹警告。

### 6.7 保存确认对话框

`_confirm_close_tab(tab)` — QMessageBox："Save Changes?" — "File '{filename}' has unsaved changes." — Save / Discard / Cancel。多个 dirty 标签逐个确认，不使用 Save All 批量按钮。

`_confirm_reopen_encoding(tab)` — QMessageBox："Unsaved Changes" — "Reopen with Encoding will discard unsaved changes in '{filename}'." — Save / Discard / Cancel。

## 7. 文件操作

**New**：`_action_new` — 创建 TabData（is_new=True, is_dirty=True, encoding='UTF-8', content=template_text, dirty_callback=self._on_tab_dirty_changed），editor_doc 填充 template_text，挂载 CppHighlighter(deferred=True)，光标定位到 main() 内部第一个 `{` 后的行缩进位置。add_tab → tabbar → _switch_to_tab。`tab.compiler_mtime = settings.compiler_mtime`。

**Open**：`_action_open` → QFileDialog → `_open_file_path(path)`。`_open_file_path`：`os.path.normpath` 统一路径 → 遍历已有标签检查重复（已打开则 _switch_to_tab 激活 + 刷新 recent order）→ `_read_file` 检测编码并读取 → 创建 TabData → add_tab + _switch_to_tab。文件不可读时弹 QMessageBox 警告。更新 last_file_dir 和 recent_files。

**FileDialog 起始路径**：`_start_dir()` 方法返回有效的起始目录 — 使用 `_last_file_dir`（从 window.json 恢复）若其仍存在于磁盘，否则回退到 `~/`。Open/Save As/Save（新文件）均使用 `_start_dir()` 作为对话框起始路径，成功选择文件后更新 `_last_file_dir`。

**Save**：`_save_tab_data(tab)` — 两阶段事务性保存。Phase 1：在纯文本副本上做行尾空白清理（`_strip_trailing_whitespace`），准备磁盘内容，此时文档未修改；Phase 2：写磁盘（新文件弹 QFileDialog 选路径，已保存文件直接写入），使用 TabData.encoding 编码，写失败或用户取消时文档内容不变；Phase 3（仅在写盘成功后）：在文档原地 `_strip_trailing_whitespace_in_doc` 使文档与磁盘一致，然后 `setModified(False)` 维护"脏=不一致"语义。编码转换失败时捕获 UnicodeEncodeError 弹警告，不崩溃。保存成功后 status_message 显示 "Saved: filename"。Save As 失败时 rollback file_path/is_new。

**Save As**：`_action_save_as` — 始终弹 QFileDialog，保存后更新 file_path、last_file_dir、recent_files。失败时 rollback。

**Close Tab**（`_handle_close_tab`）：dirty 时弹 `_confirm_close_tab` → 断 `modificationChanged` 信号 → 取消 batch highlighting → 如果该标签正在运行进程（FlowController.tab is this tab），调用 `flow_ctrl.cancel_flow()` 统一处理 kill + waitForFinished + drain_remaining_output + cleanup + set_state(IDLE)，然后 `_flush_output_buffer(tab)` 确保排空数据写入 output_doc → 如果当前标签不是被关闭标签，保存当前标签的 widget state（防止状态丢失）→ 移除 tabbar → remove_tab → 调整零标签或切换 → deferred save window state。

**拖放打开**：MainWindow `setAcceptDrops(True)`，`dragEnterEvent` 检查 MIME URLs 后缀匹配 `_SOURCE_EXTENSIONS`（`.cpp/.c/.cc/.cxx/.h/.hpp/.hh`）。`dropEvent` 对每个匹配 URL 调用 `_open_file_path(path, add_recent=True)`。CodeEditor/InputPanel/OutputPanel（FileDragMixin）的 drag 事件遇到 URL 时 ignore，让事件传播到 MainWindow；纯文本拖放交给 QTextEdit 默认行为。

**Recent Files**：File 菜单 Recent Files 子菜单（QMenu `_menu_recent`），最多 10 条按时间倒序。点击已删除文件弹 QMessageBox "File not found" 并从列表移除。`_open_file_path(add_recent=True)` 自动调用 `_add_recent_file()`。空列表显示 "(Empty)" 禁用项。

**Window Close**：`closeEvent` — 逐个确认所有 dirty 标签（Save/Discard/Cancel，Cancel 则 ignore event）→ kill + cleanup 运行中进程（**不调用 set_state(IDLE)**，窗口即将销毁无影响）→ `_save_window_state` → cancel 所有 batch highlighting timers → disconnect 所有 modificationChanged 信号 → accept event。

**Save If Dirty**：`_save_if_dirty(tab)` — tab 不 dirty 且不 new 时返回 0（无需保存），否则调用 `_save_tab_data`。Build/Test/Run 前调用，用户取消保存时返回 -1 阻止后续操作。

## 8. UI 细节

### 8.1 DPI 处理

- `Qt.AA_EnableHighDpiScaling` 启用高 DPI 缩放，Widget 几何和字号由 Qt 自动处理
- `_dpi_factor()`（`QScreen.logicalDotsPerInch() / 96.0`）用于手动绘制场景：
  - 图标 pixmap：物理尺寸按 DPI 放大，devicePixelRatio(dpi)，QPainter `scale(dpi,dpi)` 在逻辑坐标系绘制
  - IO 面板标签 padding：`label.setFixedHeight` 使用 `+ int(4 * dpi)`
  - 状态栏信息文本不手动缩放（Qt AA_EnableHighDpiScaling 处理）

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

生成函数：`_generate_xxx_icon(dpi)`，在 QPainter 中 `scale(dpi,dpi)`。由 `_create_toolbar_icons()` 统一创建返回 dict。toolbar 显示纯图标，菜单显示文字。图标 pixmap 使用 `_icon_canvas(dpi)` 工厂方法创建画布。

**窗口图标**：MainWindow.setWindowIcon 使用 run 图标（绿色播放三角）。

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

窗口默认 1000x650，首次居中（`__init_settings` 中计算 screen center）。Settings 实例传入 MainWindow，构造中 `_load_window_state()` 恢复窗口状态和标签页。

## 10. 编码风格

遵循 AGENTS.md：`def method (self, arg)` 参数括号前有空格；`arg:QWidget` 紧凑类型注解；字符串优先单引号；成功返回 0，失败 -1/-2；Python 3.8 兼容。

## 11. 技术决策摘要

| 决策 | 原因 |
|------|------|
| Open 重复文件检测 | 防止两次打开同一文件产生两个标签页 |
| 编译 stderr 用平台编码 | 中文 Windows 下 g++ 输出 GBK，UTF-8 解码会乱码 |
| 状态栏显示编译/运行结果 | 编译/运行结束后回到 Ready 丢失结果信息 |
| startDetached 返回值检查 | 失败时无提示 |
| 负 exit code crash 描述 | 已知 NTSTATUS 码附加可读描述（如 Access violation） |
| killed 不追踪 Stop 意图 | 自然崩溃也走 CrashExit，附加 crash 描述比一律灰色更有用 |
| compiler_mtime 传播 | Settings 变化后所有 TabData 的 mtime 更新，触发重编译 |
| Settings JSON 只加载已知键 | 忽略未知键，首次不存在时保留默认值 |
| Window state 持久化 | 恢复标签页状态、窗口几何、分割条位置、recent_files |
| Recent Files 子菜单 | 最多 10 条，点击已删除文件提示并移除 |
| Drag-drop 扩展后缀 | .cpp/.c/.cc/.cxx/.h/.hpp/.hh |
| 工具链 PATH 自动注入 | compiler_path 含路径时 prepend bin_dir 到 PATH |
| 运行结果行前换行 | 程序输出不以 `\n` 结尾时避免状态行接在末尾 |
| 编译命令加 -lstdc++ | 误选 gcc 时也能链接 C++ 标准库 |
| Settings Browse 按钮 | 方便用户通过文件对话框定位 g++ |
| Settings 缩进/Word Wrap 选项 | Tab 宽度、缩进风格、word wrap 可配置 |
| 模板编辑器自动缩进 | eventFilter 处理 Enter 键，遵从缩进风格设置 |
| 默认编译器 gcc + compiler_flags 留空 | gcc 从扩展名自动识别语言模式，-lstdc++ 覆盖 C++ 链接需求 |
| Qt message handler 过滤无害警告 | QMenu grab mouse 产生 setMouseGrabEnabled 警告，Qt Windows 已知问题 |
| Open 与 drag-drop 合并为 `_open_file_path` | 统一重复检测逻辑 |
| 子组件 drag-drop 事件转发 MainWindow | QTextEdit 会把文件拖放当文本插入，FileDragMixin 遇 URL 时 ignore |
| 保存捕获 UnicodeEncodeError | GBK 编码文件保存含非 GBK 字符时不崩溃 |
| 编码名统一大写 | 状态栏显示 'GBK' 而非 'gbk' |
| zoom 仅在字号变更时重置 | 修改非字体设置时不清零 zoom 偏移 |
| FileDialog 起始路径存在性检查 | `_start_dir()` 检查 `_last_file_dir` 是否仍存在于磁盘 |
| Find/Replace 惰性创建对话框 | Ctrl+F/Ctrl+H 时创建，close 时 hide 保留状态 |
| Find 搜索从头/尾循环 | wrap-around 搜索 |
| Replace All 计数显示 | 完成后标题栏显示替换数量 |
| Save with Encoding rollback | 新文件 Save 失败时 rollback file_path/is_new |
| 编码标签可点击 | `_ClickableLabel` + PointingHandCursor |
| Ctrl+/ 注释/取消注释 | 最高频调试操作 |
| Tab/Shift+Tab 选区缩进 | 有选区时缩进/反缩进；菜单快捷键 Ctrl+]/Ctrl+[ |
| 无选区 Tab 遵循 indent_style | indent_style='tab' 插入 `\t`，indent_style='space' 插入 indent_size 个空格 |
| Ctrl+D 复制行 | 不替换剪贴板 |
| 当前行高亮 | ExtraSelections 浅黄背景 |
| 括号匹配高亮 | ExtraSelections 背景色，非注释/字符串上下文 |
| 括号补全上下文感知 | `_is_bracket_in_comment_or_string` 检查，开符号和闭符号均检查 |
| #include <> 和 /* */ 自动补全 | 扩展括号补全逻辑 |
| 行尾空白自动清理 | `_strip_trailing_whitespace_in_doc` cursor 操作原地清理 |
| 保存流程两阶段事务 | 先在纯文本副本上 strip+写盘，成功后才原地修改文档，失败/取消时文档不变 |
| 编辑器右键菜单 | contextMenuEvent，动作与 Edit 菜单共享 QAction |
| Reopen with Encoding dirty 检查 | `_confirm_reopen_encoding` 弹 Save/Discard/Cancel |
| 行尾裁剪回写文档 | `_strip_trailing_whitespace_in_doc` 仅在写盘成功后执行，维护事务边界 |
| compiler_flags shlex 解析 | `shlex.split()` 支持带引号参数和空格路径，失败时 fallback 到 `split()` |
| Settings.apply_from deepcopy | 可变对象（dict/list/set）做 deepcopy，防止共享引用 |
| Run 终端 CR_SET_PATH/CR_ENV_SETUP | bat 脚本用占位符，os.environ 只临时设 4 个 CR_ 前缀变量 |
| waitForStarted 改为异步 | 移除阻塞调用，用 errorOccurred 信号处理 FailedToStart |
| psutil.Process 缓存复用 | _start_memory_tracking 缓存 Process 对象 |
| FlowController 拆出 MainWindow | 状态机独立类，MainWindow 只做 UI 跟进 |
| _IOPanelBase 提取 | InputPanel/OutputPanel 共享 setDocument |
| _save_widget_state helper | 三处重复代码提取 |
| MainWindow.__init__ 拆分 | 115 行拆为六个子方法 |
| ProcessManager._cleanup() | 断信号+deleteLater+重置状态，防止 stale finished 信号 |
| ProcessManager.run_finished 加 error_detail | failed_to_start 时传递 QProcess.errorString() |
| ProcessManager._on_run_started | 进程 started 后才写 stdin + closeWriteChannel |
| CodeEditor.setFontSize | Zoom 功能专用字号设置方法 |
| CodeEditor._notify_overwrite_changed | overwrite 模式切换时更新光标宽度（宽光标 vs 1px） |
| closeEvent 进程清理 | 关闭窗口时 kill + cleanup 运行中进程 |
| _handle_close_tab 进程清理 | 关闭正在运行的标签时调用 flow_ctrl.cancel_flow()，统一 kill+waitForFinished+drain+cleanup+set_state |
| FlowController 输出信号委托 | FlowController 不直接操作 tab.output_buffer/output_doc，通过 output_clear/output_append 信号委托 MainWindow，保持状态机与数据结构解耦 |
| FlowController.cancel_flow() | 统一封装 kill+waitForFinished+drain_remaining_output+cleanup+set_state(IDLE)，替代 _handle_close_tab 和 closeEvent 中散落的 kill/cleanup 逻辑 |
| ProcessManager.drain_remaining_output() | _cleanup() 前排空 QProcess 管道中残留 stdout/stderr，确保关闭标签/窗口时不丢失输出数据 |
| ProcessManager._stop_timeout_timer() | 停止并置空 timeout timer 的 helper，消除 timeout/error handler 中重复逻辑 |
| CppHighlighter first-match-wins 实现 | 单行规则用 __format_if_free 只格式化空闲位置；多行注释也检查空闲位置；deferred 模式用 __is_position_masked/__find_free_multi_start 模拟语义 |
| 输出截断 _OUTPUT_MAX_CHARS | output_doc 超 500000 字符时裁剪前半并插入截断提示，防止失控程序消耗过多内存 |
| _check_buffer_overflow 分离方法 | buffer 超 200 条或 64KB 时立即 flush，从 _on_flush_timer 中独立为方法 |
| ProcessManager stdout/stderr None 保护 | handler 入口检查 self.process is None，防止 cleanup 后排队信号 AttributeError |
| CodeEditor._highlighter 解耦 | 通过 setDocument 同步 getattr(doc, '_highlighter')，消除对 window/tab_manager 的穿越访问 |
| CodeEditor._handle_bracket_close 上下文检查 | 闭括号跳过也检查 _is_bracket_in_comment_or_string，与开括号一致 |
| Template 编辑器 Tab 键 | indent_style='space' 时插入 indent_size 个空格，indent_style='tab' 时默认行为 |
| 编译器路径验证 | SettingsDialog OK 时检查绝对/相对路径是否存在，裸名不检查（由 PATH 展开），不阻止保存 |
| About 对话框 | Help 菜单 About 项，显示作者和时间 |
| MainWindow 冗余 IDLE 检查 | _action_build/run/test 在调 FlowController 前先检查 IDLE 状态，FlowController 入口方法也检查，双重保护 |
| output_buffer + flush timer | 输出先追加到 per-tab buffer，全局 50ms timer 定期 merge+flush 到 output_doc，减少高频输出的 cursor 操作 |
| pinned_to_bottom 替代 _need_scroll | 语义更清晰：True=自动跟随新输出，False=用户在看老输出 |
| 全局 timer 永不停 | 不需要 start/stop，每 tick 只做有意义的操作，空循环开销极低 |
| 相邻同色合并 flush | 连续相同 color 的 buffer 条目合并为一条 cursor insert，减少 QTextCharFormat 切换次数 |
| __programmatic_scroll 标志 | 区分 timer 的程序性滚动与用户手动滚动，避免程序性滚动误改 pinned 状态 |
| stdin 提交即时 flush | 交互式程序 stdin 按回车后立即 flush buffer，prompt 不等 50ms tick |
| 大输出保护 | buffer 超 64KB/200 条立即 flush，防止高频输出 buffer 膨胀 |
| 编译命令用相对文件名 | cwd 已设为源文件目录，传 basename 给 gcc 使报错信息简短（`hello.cpp:3:5: error:` 而非绝对路径） |
| QProcess.start 两参数形式 | `start(exe_path, [])` 防止含空格路径被单参数形式拆解为"命令+参数" |
| OutputPanel 双击跳转编译错误 | `error_jump_requested` 信号 + `_goto_error_line`，basename 校验 + clamp 行列保护 + ensureCursorVisible |
| QTextEdit 使用 ensureCursorVisible | `centerCursor()` 是 QPlainTextEdit 方法，QTextEdit 无此方法，调用导致 segfault |