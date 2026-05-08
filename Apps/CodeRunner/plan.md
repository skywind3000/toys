# CodeRunner 实施计划

## 总览

分 11 个阶段实施，每个阶段产出可独立运行的程序。阶段完成后需用户手工确认验收通过，才能进入下一阶段。

每个阶段可在新会话中实施：新会话读 prd.md → spec.md → plan.md → 当前 CodeRunner.py，找到第一个 `pending` 阶段开始工作。完成后将该阶段状态改为 `done`，用户验收确认后才能推进下一阶段。

| 阶段 | 状态 |
|------|------|
| 1. 骨架与布局 | done |
| 2. 标签管理与文件操作 | done |
| 3. 编辑器核心 | done |
| 4. 语法高亮与编辑器特性 | done |
| 5. 编译与运行 | done |
| 6. 设置与持久化 | done |
| 7. 查找替换与收尾 | done |
| 8. 编辑器增强与体验优化 | done |
| 9. OutputPanel: pinned_to_bottom 状态重构 | pending |
| 10. OutputPanel: buffer + flush timer 机制 | pending |
| 11. OutputPanel: 交互式 flush 与清理 | pending |

## 阶段 1：骨架与布局 **[done]**

**目标**：启动后能看到完整的界面骨架，各区域位置正确，分割条可拖动。

**实现的类**：
- MainWindow（QMainWindow）：五大区域布局搭建
- InputPanel（QPlainTextEdit）：占位，外层 QWidget + QLabel "INPUT" 包装
- OutputPanel（QTextEdit）：占位，setReadOnly(True)，外层 QWidget + QLabel "OUTPUT" 包装
- Settings（object）：仅默认值，不读写文件

**具体内容**：
- MenuBar：四个菜单（File / Edit / Run / View），菜单项为空占位
- Toolbar：七个按钮（New / Save / Open / Run / Test / Stop / Settings），自绘彩色图标，点击无响应
- TabBar（QTabBar）：空状态，无标签页
- MainArea：水平 QSplitter（左 CodeEditor 占位 / 右垂直 QSplitter（上 InputSection: QLabel "INPUT" + InputPanel / 下 OutputSection: QLabel "OUTPUT" + OutputPanel）），默认 1:1
- StatusBar：左 QLabel（空消息）+ 右 QLabel（零标签时清空）
- DPI：`Qt.AA_EnableHighDpiScaling`
- 主题：`app.setStyle('Fusion')`
- 字体：按平台优先列表检测 monospace 字体设为 Settings 默认值
- 主入口：`def main()`，窗口 1000x650 居中
- 启动时无标签页，CodeEditor / InputSection / OutputSection 三个区域 `setEnabled(False)` 灰显，内容为空

**自动测试项**：无（纯视觉）

**手动验收清单**：
- [x] `python CodeRunner.py` 启动，看到完整五区域布局
- [x] 水平分割条可左右拖动，垂直分割条可上下拖动
- [x] 窗口大小约 1000x650
- [x] InputPanel 顶部显示 "INPUT" 标签，OutputPanel 顶部显示 "OUTPUT" 标签
- [x] 无标签页时 CodeEditor / InputSection / OutputSection 灰显不可交互
- [x] 无标签页时状态栏右侧为空（不显示行号/编码/模式）
- [x] Toolbar 七个按钮都有彩色图标（New灰/Save蓝/Open黄/Run绿/Test蓝/Stop红/Settings灰齿轮）
- [x] Fusion 主题风格统一

---

## 阶段 2：标签管理与文件操作 **[done]**

**目标**：能新建/打开/保存/关闭标签页，编辑文字，基本的多文档编辑器可用。

**实现的类**：
- TabData（object）：标签页状态数据
- TabManager（object）：标签列表与切换逻辑
- CodeEditor（QPlainTextEdit）：基础编辑（无行号、无高亮、无补全），Tab 键插入制表符

**具体内容**：
- TabData 全部属性：file_path, is_new, is_dirty, editor_doc(QTextDocument), input_doc(QTextDocument), output_doc(QTextDocument), cursor, scroll_pos, input_cursor, input_scroll, encoding, zoom_font_size, compiler_mtime
- 每个 TabData 创建时新建三个独立 QTextDocument 实例，CppHighlighter 实例化但不挂载到 editor_doc（延迟挂载避免大文件打开时的 re-highlight 逐块处理开销，Phase 4 实现规则后再 setDocument 挂载）
- TabManager：add_tab, close_tab, switch_tab, get_current, untitled_counter
- 标签切换：通过 `editor.setDocument(tab.editor_doc)` 交换文档，手动保存/恢复光标和滚动条位置，使用 `setUpdatesEnabled(False)` 冻结重绘
- dirty 信号：连接 editor_doc.contentsChanged 到 TabData 的 dirty 标记方法（信号跟随 document，不受 Widget 切换影响）
- 标签名显示规则：is_new+dirty → `*untitledN*`，is_new+非dirty → `untitledN`，已保存+dirty → `*filename*`，已保存+非dirty → `filename`
- 关闭最后标签后进入零标签状态（current_index = -1），三个面板 `setEnabled(False)` 灰显
- 新建/打开标签时从零标签状态恢复：三个面板 `setEnabled(True)`
- Switch Tab 快捷键：Alt+1 ~ Alt+9 切换第 1~9 个标签，Alt+0 切第 10 个，通过 QShortcut 绑定
- New（Ctrl+N）：创建 TabData（is_new=True, is_dirty=True, editor_doc 初始内容为默认模板, encoding='UTF-8'）
- Open（Ctrl+O）：QFileDialog 选择 .cpp/.c 文件，读取内容到 TabData.editor_doc
- Save（Ctrl+S）：新文件弹出 QFileDialog；已保存文件直接写入 editor_doc.toPlainText()，使用 TabData.encoding 编码
- Save As（Ctrl+Shift+S）：始终弹出 QFileDialog
- Close（Ctrl+W）：dirty 时弹出 QMessageBox（Save / Don't Save / Cancel）
- MenuBar：File 菜单填充 New / Open / Save / Save As / Close / Settings 占位
- Toolbar：New / Save / Open 按钮连线到动作
- InputPanel / OutputPanel 随标签切换通过 setDocument 交换
- Settings 默认值（template_text 为 C++ 骨架，editor/io 字体按平台自动检测 monospace）

**自动测试项**：
- TabData 状态转换逻辑（is_new/is_dirty 组合 → 标签名）
- Settings 默认值完整性

**手动验收清单**：
- [x] Ctrl+N 创建新标签，编辑器显示模板内容，标签名 `*untitled1*`
- [x] 输入文字后标签名保持 `*untitled1*`（dirty）
- [x] Ctrl+S 保存，弹出文件对话框，保存后标签名变为 `*filename*` → `filename`
- [x] Ctrl+O 打开一个 .cpp 文件，内容正确显示
- [x] Ctrl+W 关闭标签，有未保存更改时弹出确认对话框
- [x] 关闭最后一个标签后三个面板灰显不可交互
- [x] 零标签状态下 Ctrl+N 创建新标签，面板恢复可用
- [x] Ctrl+N 再次创建新标签，编号递增
- [x] 多标签快速切换时无闪烁、无内容跳变
- [x] 多标签切换时编辑器内容和 InputPanel 内容正确切换
- [x] 切换标签后 Ctrl+Z 撤销历史仍然有效（setDocument 保留 undo 栈）
- [x] Alt+1 切换到第一个标签，Alt+2 切换到第二个，索引超出时无反应

---

## 阶段 3：编辑器核心（行号、光标、Zoom） **[done]**

**目标**：编辑器具备行号显示、光标位置跟踪、字号调整，状态栏信息实时更新。

**实现的类**：
- CodeEditor 扩展：行号区域绘制、Tab 制表符宽度、Zoom

**具体内容**：
- 行号显示：左侧 LineNumberArea（QWidget），paintEvent 绘制行号，blockCountChanged / updateRequest 信号驱动重绘
- 行号区域宽度按最大行号位数动态调整，宽度值乘 DPI factor
- Tab 制表符宽度：tabStopWidth / tabStopDistance 设为 4 字符宽度
- 状态栏右侧 QLabel：`Ln {当前行}/{总行}, Col {列} | {编码} | INS/OVR`
  - 行号列号从 1 开始，cursorPositionChanged 信号更新
  - 编码从 TabData.encoding 读取
  - INS/OVR 初始为 INS（Overtype 在阶段 4 实现）
- Zoom：Ctrl++ 放大 1pt，Ctrl+- 缩小 1pt（最小 6pt）
  - Zoom 字号存入 TabData.zoom_font_size
  - 切换标签时恢复 zoom_font_size
  - Zoom 不写入 Settings
- InputPanel / OutputPanel 字号：从 Settings.io_font_size 读取
- 编辑器字号：从 Settings.editor_font_size 读取，Zoom 基于此值偏移

**自动测试项**：
- 行号宽度计算（1~9 行 → 1 位宽，10~99 → 2 位宽，等）
- DPI factor 计算逻辑

**手动验收清单**：
- [x] 行号可见，输入多行后行号正确递增
- [x] 行号宽度随行数增加自动扩展
- [x] 光标移动时状态栏 Ln/Col 实时更新
- [x] 状态栏编码显示正确（新文件 UTF-8，GBK 文件 GBK）
- [x] Ctrl++ 放大编辑器字号，Ctrl+- 缩小
- [x] Zoom 后切换标签再切回，字号恢复到该标签的 zoom 值

---

## 阶段 4：语法高亮与编辑器特性 **[done]**

**目标**：编辑器功能完整——C++ 高亮、括号补全、自动缩进、改写模式。

**实现的类**：
- CppHighlighter（QSyntaxHighlighter）：C++ 语法高亮全部规则
- CodeEditor 扩展：括号补全、自动缩进、改写模式

**具体内容**：
- CppHighlighter 七组规则（按优先级从高到低：单行注释绿色、字符串深红、字符深红、关键字蓝色非粗体、预处理器蓝色、数字深蓝、符号深青色；多行注释绿色单独处理覆盖已有格式）
- 多行注释使用 setCurrentBlockState / previousBlockState
- 括号补全：覆盖 keyPressEvent，输入 `(` `{` `[` `"` `'` 时自动插入闭符号
- 括号跳过：输入闭符号且右侧匹配时跳过
- 括号删除：Backspace 删除开符号时右侧紧邻闭符号一并删除
- 自动缩进：Enter 后保持当前缩进，`{` 后增加缩进
- 改写模式：Insert 键切换 overwrite_mode，OVR 下输入字符覆盖光标右侧字符
- 状态栏 INS/OVR 随 Insert 键切换实时更新
- 括号补全开关：Settings 中增加 bracket_completion 字段，控制是否启用

**自动测试项**：
- 编码检测：UTF-8 BOM 文件、纯 UTF-8 文件、GBK 文件、混合非法字节
- 编译标志生成：UTF-8 源文件 → 加 -finput-charset=UTF-8，GBK 源文件 → 不加

**手动验收清单**：
- [x] C++ 关键字蓝色粗体高亮
- [x] 注释灰色，字符串深红，预处理器绿色
- [x] 多行注释 `/* ... */` 正确高亮
- [x] 输入 `(` → 自动插入 `)`，光标在中间
- [x] 输入 `{` → 自动插入 `}`，光标在中间
- [x] 输入 `"` → 自动插入 `"`，光标在中间
- [x] 输入 `)` 且右侧是 `)` → 光标跳过
- [x] Enter 在 `{` 后 → 新行增加缩进
- [x] Insert 键切换 INS/OVR，状态栏显示更新
- [x] OVR 模式下输入字符覆盖右侧字符

---

## 阶段 5：编译与运行 **[done]**

**目标**：核心功能可用——编译 C++ 代码、Test 传入 stdin 取 stdout、Run 弹终端、Stop 终止进程。

**实现的类**：
- EncodingManager（object）：编码检测、编译标志生成、I/O 编码转换
- ProcessManager（QObject）：QProcess 管理、busy 状态、超时控制

**具体内容**：
- EncodingManager 全部功能：
  - 文件编码检测（BOM → UTF-8 strict → 系统编码）
  - 编译标志生成（-fexec-charset, -finput-charset）
  - I/O 编码转换（InputPanel → stdin encode，stdout/stderr → decode）
- ProcessManager 全部功能：
  - QProcess 启动编译/运行
  - Test 流程完整实现（保存 → 判断重编译 → 编译 → 运行 → 输出）
  - Run 流程完整实现（保存 → 判断重编译 → 编译 → 弹外部终端）
  - Build 流程完整实现（保存 → 强制重编译）
  - Stop 终止进程
  - Busy 状态控制（互斥，提示消息）
  - 运行超时 QTimer，编译超时 QTimer
- OutputPanel 颜色渲染：stdout 默认色、stderr 灰色、编译错误红色、退出状态行灰色
- 重编译判断：exe 不存在 / exe_mtime < source_mtime / exe_mtime < compiler_mtime
- 编译命令拼接：compiler_path + 编译标志 + compiler_flags + 源文件 + -o + exe文件
- exe 文件路径：源文件同目录，同名 .exe
- 工作目录：exe 所在目录
- Run 外部终端：Windows 用固定批处理 `%TEMP%\coderunner.cmd`（内容固定，变化部分通过 `CR_COMMAND`/`CR_PAUSE` 环境变量传入），临时修改 `os.environ` 后 `startDetached` 启动
- psutil 内存占用：可选，QTimer 100ms 轮询记录峰值 rss，进程结束后追加到退出状态行
- 输出路由：ProcessManager 记录 target_tab，stdout/stderr 始终写入发起操作的 TabData，非当前标签时仅更新缓冲
- save_if_dirty 中止：Test/Run/Build 流程中 save_if_dirty 返回失败时终止整个流程
- MenuBar：Run 菜单填充 Build / Test / Run / Stop
- Toolbar：Run / Test / Stop 按钮连线
- 状态栏左侧：编译/运行结果消息更新

**自动测试项**：
- 编码检测：各种字节序列的判定结果
- 编译标志生成：不同编码组合的 flags
- I/O 编码转换：UTF-8 ↔ GBK 双向转换
- 环境变量 $VAR_NAME 展开逻辑

**手动验收清单**：
- [x] 写一个简单 C++（如 `scanf a+b, printf a+b`），按 F9 → OutputPanel 显示正确输出
- [x] InputPanel 内容作为 stdin 正确传入程序
- [x] 编译错误时 OutputPanel 显示红色错误信息，状态栏显示 "Build failed"
- [x] Runtime Error（返回码非 0）显示红色
- [x] F5 弹出外部终端窗口，程序结束后提示"按任意键关闭"
- [x] F7 终止正在运行的进程
- [x] 运行超时后 OutputPanel 显示红色超时信息
- [x] 编译超时后 OutputPanel 显示红色超时信息
- [x] Busy 状态下按 Build/Test/Run 弹出英文提示，不启动新操作
- [x] stderr 输出用灰色字体显示
- [x] Tab A 运行 Test 期间切到 Tab B，切回 Tab A 后看到 Tab A 的运行结果
- [x] 新文件按 F9 → 弹出保存对话框 → 取消保存 → 不执行编译运行

---

## 阶段 6：设置与持久化 **[done]**

**目标**：设置可修改可保存，重启后恢复窗口状态和标签页。

**实现的类**：
- Settings 扩展：JSON 读写、compiler_mtime 跟踪
- SettingsDialog（QDialog）：三页 Tab 对话框

**具体内容**：
- Settings JSON 读写：`~/.config/coderunner/settings.json`
- SettingsDialog 三页 Tab：
  - Compiler 页：编译器路径 + Auto Detect 按钮、编译参数、环境变量表格、运行超时、编译超时
  - Editor 页：编辑器字体/字号、IO 面板字体/字号、括号补全开关
  - Template 页：多行编辑框 + Reset to Default 按钮
- Auto Detect：检查常见 MinGW/TDM-GCC/Dev-Cpp 路径 + PATH 中 g++
- OK → 保存 Settings JSON；Cancel → 放弃修改
- compiler_path、compiler_flags 或 env_vars 变化 → 更新 compiler_mtime
- Window state 持久化：`~/.cache/coderunner/window.json`
  - 退出时保存：窗口几何、分割条位置、标签列表、活跃标签、last_file_dir、recent_files
  - 启动时恢复：重新打开标签、恢复 InputPanel 内容、恢复分割条位置
- 最近文件列表：File > Recent Files 子菜单，最多 10 条
- 拖放打开：setAcceptDrops，接受 .cpp/.c 文件拖入
- 文件对话框初始目录：window_state.last_file_dir
- Toolbar：Settings 按钮连线到 SettingsDialog

**自动测试项**：
- Settings JSON 序列化/反序列化（写入 → 读回 → 一致）
- 环境变量 $VAR_NAME 展开为实际值
- Window state JSON 格式完整性

**手动验收清单**：
- [ ] Settings 按钮打开设置对话框，三个 Tab 页正确显示
- [ ] Compiler 页 Auto Detect 找到 g++ 路径
- [ ] 修改编译参数 → OK → 重启后参数保持
- [ ] 修改字体 → OK → 编辑器和 IO 面板字体立即变化
- [ ] Template 页编辑模板 → OK → Ctrl+N 使用新模板
- [ ] 打开多个标签 → 退出 → 重新启动 → 标签恢复，InputPanel 内容恢复
- [ ] 拖拽 .cpp 文件到窗口 → 文件被打开
- [ ] Recent Files 菜单显示最近打开的文件
- [ ] 点击已删除的最近文件 → 提示 "File not found"

---

## 阶段 7：查找替换与收尾 **[done]**

**目标**：所有 PRD 功能完整覆盖，细节打磨。

**实现的类**：
- FindDialog（QDialog）：非模态查找
- ReplaceDialog（QDialog）：非模态替换

**具体内容**：
- FindDialog：查找文本、大小写敏感、向上/向下 RadioButton、Find Next / Close，非模态，关闭时隐藏保留状态
- ReplaceDialog：查找文本 + 替换文本、Replace / Replace All / Close，非模态
- GotoLineDialog：使用 QInputDialog.getInt() 输入目标行号，跳转并居中显示（Ctrl+G）
- Edit 菜单完善：Undo / Redo / Cut / Copy / Paste / Find (Ctrl+F) / Replace (Ctrl+H) / Goto Line (Ctrl+G)
- View 菜单完善：Zoom In (Ctrl++) / Zoom Out (Ctrl+-)
- 编码选择菜单：状态栏编码点击 → QMenu（Reopen with Encoding / Save with Encoding）
- Reopen with Encoding：列出常见编码（UTF-8, GBK, Big5, Shift_JIS, ISO-8859-1），选择后重新加载文件
- Save with Encoding：同上列表，选择后保存文件为新编码
- 退出时 dirty 标签逐个确认保存
- 全部快捷键最终验证
- MenuBar / Toolbar 所有动作最终连线验证
- 细节打磨：tooltip 显示"动作名 (快捷键)"等

**自动测试项**：
- 无显著可自动化的新增逻辑（对话框行为为 UI 层）

**手动验收清单**：
- [ ] Ctrl+F 打开 Find 对话框（非模态，可同时编辑代码），查找功能正常
- [ ] Ctrl+H 打开 Replace 对话框（非模态），替换/全部替换功能正常
- [ ] Ctrl+G 弹出 Goto Line 对话框，输入行号后跳转正确
- [ ] Edit 菜单全部动作可用（Undo, Redo, Cut, Copy, Paste, Find, Replace, Goto Line）
- [ ] View 菜单 Zoom In / Zoom Out 可用
- [ ] 状态栏编码标签点击 → 弹出编码选择菜单
- [ ] Reopen with Encoding 重新加载文件内容
- [ ] Save with Encoding 以新编码保存文件
- [ ] 退出时 dirty 标签逐个弹出保存确认
- [ ] 所有快捷键与 PRD 一致
- [ ] Toolbar 按钮 tooltip 显示"动作名 (快捷键)"格式

---

## 阶段 8：编辑器增强与体验优化 **[done]**

**目标**：高频编辑操作便捷化，编辑器视觉辅助增强，IO 面板快捷操作。

**新增功能**（按优先级分组）：

**P1 — 高频操作**：
- Ctrl+/ 注释/取消注释（选中行或当前行，toggle 逻辑）
- Tab/Shift+Tab 多行缩进/反缩进（有选区时）
- Ctrl+D 复制当前行（不操作剪贴板）
- 当前行高亮（ExtraSelections 浅色背景标记）
- 编辑器右键上下文菜单（Undo/Redo/Cut/Copy/Paste/Comment/Indent/Unindent/Duplicate/Delete）

**P2 — 体验增强**：
- 括号匹配高亮（ExtraSelections 背景色标记配对括号，非注释/字符串上下文）
- #include <> 自动补全（输入 `<` 且行以 `#include` 开头时补 `>`）
- /* */ 多行注释自动闭合（输入 `/*` 补 `*/`，输入 `*/` 右侧匹配时跳过）

**P3 — 锦上添花**：
- Ctrl+Shift+K 删除当前行
- Alt+Up/Alt+Down 上下移动当前行
- 保存时行尾空白自动清理

**实现的类/方法**：
- CodeEditor 扩展：keyPressEvent 新增 Ctrl+/、Ctrl+D、Ctrl+Shift+K、Alt+Up/Alt+Down 处理；Tab/Shift+Tab 选区缩进；ExtraSelections 当前行高亮 + 括号匹配高亮；括号补全扩展（#include <>、/* */）；contextMenuEvent 右键菜单
- MainWindow 扩展：Edit 菜单新增动作项；保存前行尾空白清理

**自动测试项**：
- Comment/Uncomment 逻辑：单行注释、多行注释、取消注释（行首已有 `//`）
- Indent/Unindent 逻辑：Tab 模式和 Space 模式下选区缩进
- Duplicate Line：单行复制、多行复制
- 行尾空白清理：含尾部空格/Tab 的行保存后被移除

**手动验收清单**：
- [ ] Ctrl+/ 注释当前行（加 `//`），再次 Ctrl+/ 取消注释（移除 `//`）
- [ ] 选中多行 Ctrl+/ → 每行加 `//`；选中已注释多行 Ctrl+/ → 每行移除 `//`
- [ ] 选中多行 Tab → 每行增加一级缩进
- [ ] 选中多行 Shift+Tab → 每行减少一级缩进
- [ ] Ctrl+D 复制当前行到下一行，剪贴板不受影响
- [ ] Ctrl+Shift+K 删除当前行
- [ ] Alt+Up/Alt+Down 上下移动当前行
- [ ] 当前行有浅色背景标记，切换行后高亮跟随
- [ ] 光标停在括号上时，配对括号背景色高亮
- [ ] 输入 `#include <` → 自动插入 `>`，光标在中间
- [ ] 输入 `/*` → 自动补 `*/`，光标在中间
- [ ] 输入 `*/` 且右侧是 `*/` → 光标跳过
- [ ] 保存文件时行尾空白被自动清理
- [ ] 编辑器右键菜单包含 Comment/Uncomment、Indent、Unindent、Duplicate Line、Delete Line
- [ ] Edit 菜单包含新增的所有动作项

---

## 阶段 9：OutputPanel — pinned_to_bottom 状态重构 **[pending]**

**目标**：将 `_need_scroll` 替换为语义更清晰的 `pinned_to_bottom`，引入 `__programmatic_scroll` 标志区分用户与程序滚动，改进 tab 切换时的输出面板 scroll 位置恢复。此阶段不引入 buffer 机制，输出仍直接写入 document。

**具体内容**：

1. TabData：`_need_scroll` → `pinned_to_bottom`（初始 True）
2. 所有 `tab._need_scroll = True` 赋值点 → `tab.pinned_to_bottom = True`（约 15 处）
3. 所有 `tab._need_scroll` 读取点 → `tab.pinned_to_bottom`
4. MainWindow：新增 `__programmatic_scroll = False` 属性
5. `_on_output_scroll_changed`：`__programmatic_scroll` 为 True 时忽略；不在底部 → pinned=False；在底部 → pinned=True
6. `_on_scroll_output_timer` → `_on_scroll_output_timer`（名称暂不变），程序性滚动前设 `__programmatic_scroll=True`，滚动后设 `False`
7. `_switch_to_tab`：恢复 output_scroll 时，pinned=True → setValue(maximum)；pinned=False → setValue(saved_output_scroll)
8. 程序启动（进入 compiling / running 状态时）重置 `pinned_to_bottom = True`
9. OutputPanel.keyPressEvent End 键：设置 pinned=True + 启动 scroll timer + 滚到底部
10. `_output_clear` + `pinned_to_bottom=True` 组合保持不变（清空后视为在底部）

**不改的部分**：
- `_output_append` 仍直接写入 document（buffer 机制在阶段 10）
- `_scroll_output_timer` 仍用 start/stop（永不停 timer 在阶段 10）
- `scroll_requested` 信号暂不移除（阶段 10 移除）

**手动验收清单**：
- [ ] 编译/运行输出自动滚到底部，新输出持续跟随
- [ ] 手动将输出滚动条往上拉 → 新输出不再自动滚动（pinned=False）
- [ ] 滚动条拉回底部 → 新输出恢复自动滚动（pinned=True）
- [ ] 按 End 键 → 滚到底部 + 恢复自动跟随
- [ ] 编译/运行开始时自动重置为 pinned=True
- [ ] pinned=False 时切换到其他 tab 再切回 → 输出面板恢复到之前看的位置（不是底部）
- [ ] pinned=True 时切换 tab 再切回 → 输出面板在底部
- [ ] 程序性滚动不误触发 pinned 状态变化

---

## 阶段 10：OutputPanel — buffer + flush timer 机制 **[pending]**

**目标**：引入 output_buffer 和永不停止的全局 flush timer，所有输出通过 buffer → merge → flush 写入 document，移除旧的 scroll_requested 信号。

**前置依赖**：阶段 9 完成（pinned_to_bottom 机制已就位）

**具体内容**：

1. TabData：新增 `output_buffer = []` 字段
2. 所有 `_output_append(tab.output_doc, text, color)` 调用 → `tab.output_buffer.append((color, text))`（约 15 处）
3. `_output_clear(tab.output_doc)` 调用点 → 附加 `tab.output_buffer.clear()` + `tab.pinned_to_bottom = True`
4. FlowController 中直接 `_output_append` 写入 output_doc 的地方（编译错误行、退出状态行等）→ 改为 `tab.output_buffer.append((color, text))`
5. 新增 `_flush_output_buffer(tab)` 方法：合并相邻同 color → QTextCursor 逐条写入 output_doc → 清空 buffer
6. `_scroll_output_timer` → `_flush_output_timer`：改为永不停（__init_connections 中 start，不再 start/stop）
7. `_on_scroll_output_timer` → `_on_flush_timer`：每 tick 遍历所有 tab，buffer 非空则 flush；当前 tab 且 pinned=True 则程序性滚动到底部
8. 移除 `scroll_requested` 信号及 `_on_flow_scroll_requested` 连接
9. FlowController 中所有 `self.scroll_requested.emit(tab)` → 移除（滚动由 timer tick 统一负责）
10. 移除 `_maybe_scroll_output` 方法
11. 大输出保护：buffer 超 64KB 或 200 条时，立即调用 `_flush_output_buffer(tab)` + scroll
12. InputPanel stdin 提交（Enter 发送）时，立即 flush 当前 tab（不等 tick）

**不改的部分**：
- `_output_append` 函数保留，仅供 `_flush_output_buffer` 内部调用（外部入口全部改用 buffer）
- `_output_clear` 函数保留
- pinned_to_bottom 逻辑不变（阶段 9 已完成）

**手动验收清单**：
- [ ] 编译输出（错误信息红色）正确显示
- [ ] Test 运行 stdout/stderr 输出正确，颜色区分
- [ ] 高频输出（循环 print 1000+ 行）不卡顿
- [ ] 交互式程序（scanf + printf）prompt 快速显示
- [ ] 非当前 tab 运行中切回 → 输出完整显示
- [ ] pinned=True 时新输出自动滚底
- [ ] pinned=False 时新输出不滚底
- [ ] 编译/运行开始时 pinned 重置为 True
- [ ] Timer 永不停，不出现 isActive/start/stop 调用

---

## 阶段 11：OutputPanel — 交互式 flush 与清理 **[pending]**

**目标**：完善交互式程序的即时 flush，清理废弃代码，运行质量检查。

**前置依赖**：阶段 10 完成（buffer + flush 机制已就位）

**具体内容**：

1. stdin 提交即时 flush：确认 InputPanel Enter 键提交时调用 `_immediate_flush(current_tab)`，flush 后若 pinned=True 则立即 scroll
2. 清理废弃代码：
   - 移除 `_output_append` 函数（如果 `_flush_output_buffer` 已内联了 cursor 逻辑，则 `_output_append` 不再有任何调用者）
   - 移除 `_maybe_scroll_output`（阶段 10 已移除则跳过）
   - 确认所有 `_need_scroll` 引用已消失
   - 确认 `scroll_requested` 信号和 `_on_flow_scroll_requested` 已移除
3. 代码质量检查：
   - pylint：排除 PyQt5 动态导入误报、E211/E231/E252/E265 等
   - flake8：排除项目规定风格
   - pyflakes：未使用导入和变量
4. 同步更新文档：
   - 确认 refactor_draft.md 内容与代码一致
   - 确认 spec.md 内容与代码一致

**手动验收清单**：
- [ ] 交互式程序（scanf 等待输入）prompt 立即显示，不等 50ms
- [ ] 所有原有功能正常（编译/Test/Run/Stop/Build/清空/颜色/滚动）
- [ ] pylint/flake8/pyflakes 无实际问题（仅风格争议可忽略）
- [ ] 代码中无 `_need_scroll` / `scroll_requested` / `_maybe_scroll_output` 残留
- [ ] spec.md 与代码一致