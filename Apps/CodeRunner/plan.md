# CodeRunner 实施计划

## 总览

分 7 个阶段实施，每个阶段产出可独立运行的程序。阶段完成后需用户手工确认验收通过，才能进入下一阶段。

每个阶段可在新会话中实施：新会话读 prd.md → spec.md → plan.md → 当前 CodeRunner.py，找到第一个 `pending` 阶段开始工作。完成后将该阶段状态改为 `done`，用户验收确认后才能推进下一阶段。

| 阶段 | 状态 |
|------|------|
| 1. 骨架与布局 | pending |
| 2. 标签管理与文件操作 | pending |
| 3. 编辑器核心 | pending |
| 4. 语法高亮与编辑器特性 | pending |
| 5. 编译与运行 | pending |
| 6. 设置与持久化 | pending |
| 7. 查找替换与收尾 | pending |

## 阶段 1：骨架与布局 **[pending]**

**目标**：启动后能看到完整的界面骨架，各区域位置正确，分割条可拖动。

**实现的类**：
- MainWindow（QMainWindow）：五大区域布局搭建
- InputPanel（QPlainTextEdit）：占位，无特殊配置
- OutputPanel（QTextEdit）：占位，setReadOnly(True)
- Settings（object）：仅默认值，不读写文件

**具体内容**：
- MenuBar：四个菜单（File / Edit / Run / View），菜单项为空占位
- Toolbar：七个按钮（New / Save / Open / Run / Test / Stop / Settings），点击无响应
- TabBar（QTabBar）：空状态，无标签页
- MainArea：水平 QSplitter（左 CodeEditor 占位 / 右垂直 QSplitter（上 InputPanel / 下 OutputPanel）），默认 1:1
- StatusBar：左 QLabel（空消息）+ 右 QLabel（零标签时清空）
- DPI：`Qt.AA_EnableHighDpiScaling`
- 主入口：`def main()`，窗口 1000x650 居中
- 启动时无标签页，CodeEditor / InputPanel / OutputPanel 三个面板 `setEnabled(False)` 灰显，内容为空

**自动测试项**：无（纯视觉）

**手动验收清单**：
- [ ] `python CodeRunner.py` 启动，看到完整五区域布局
- [ ] 水平分割条可左右拖动，垂直分割条可上下拖动
- [ ] 窗口大小约 1000x650
- [ ] 无标签页时 CodeEditor / InputPanel / OutputPanel 三个面板灰显不可交互
- [ ] 无标签页时状态栏右侧为空（不显示行号/编码/模式）

---

## 阶段 2：标签管理与文件操作 **[pending]**

**目标**：能新建/打开/保存/关闭标签页，编辑文字，基本的多文档编辑器可用。

**实现的类**：
- TabData（object）：标签页状态数据
- TabManager（object）：标签列表与切换逻辑
- CodeEditor（QPlainTextEdit）：基础编辑（无行号、无高亮、无补全），Tab 键插入制表符

**具体内容**：
- TabData 全部属性：file_path, is_new, is_dirty, editor_doc(QTextDocument), input_doc(QTextDocument), output_doc(QTextDocument), cursor, scroll_pos, input_cursor, input_scroll, encoding, zoom_font_size, compiler_mtime
- 每个 TabData 创建时新建三个独立 QTextDocument 实例，editor_doc 挂载 CppHighlighter（阶段 4 才实现高亮规则，此阶段先空挂）
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
- Settings 默认值（template_text 为 C++ 骨架）

**自动测试项**：
- TabData 状态转换逻辑（is_new/is_dirty 组合 → 标签名）
- Settings 默认值完整性

**手动验收清单**：
- [ ] Ctrl+N 创建新标签，编辑器显示模板内容，标签名 `*untitled1*`
- [ ] 输入文字后标签名保持 `*untitled1*`（dirty）
- [ ] Ctrl+S 保存，弹出文件对话框，保存后标签名变为 `*filename*` → `filename`
- [ ] Ctrl+O 打开一个 .cpp 文件，内容正确显示
- [ ] Ctrl+W 关闭标签，有未保存更改时弹出确认对话框
- [ ] 关闭最后一个标签后三个面板灰显不可交互
- [ ] 零标签状态下 Ctrl+N 创建新标签，面板恢复可用
- [ ] Ctrl+N 再次创建新标签，编号递增
- [ ] 多标签快速切换时无闪烁、无内容跳变
- [ ] 多标签切换时编辑器内容和 InputPanel 内容正确切换
- [ ] 切换标签后 Ctrl+Z 撤销历史仍然有效（setDocument 保留 undo 栈）
- [ ] Alt+1 切换到第一个标签，Alt+2 切换到第二个，索引超出时无反应

---

## 阶段 3：编辑器核心（行号、光标、Zoom） **[pending]**

**目标**：编辑器具备行号显示、光标位置跟踪、字号调整，状态栏信息实时更新。

**实现的类**：
- CodeEditor 扩展：行号区域绘制、Tab 制表符宽度、Zoom

**具体内容**：
- 行号显示：左侧 LineNumberArea（QWidget），paintEvent 绘制行号，blockCountChanged / updateRequest 信号驱动重绘
- 行号区域宽度按最大行号位数动态调整，宽度值乘 DPI factor
- Tab 制表符宽度：tabStopWidth / tabStopDistance 设为 4 字符宽度
- 状态栏右侧 QLabel：`Ln {行}, Col {列} | {编码} | INS/OVR`
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
- [ ] 行号可见，输入多行后行号正确递增
- [ ] 行号宽度随行数增加自动扩展
- [ ] 光标移动时状态栏 Ln/Col 实时更新
- [ ] 状态栏编码显示正确（新文件 UTF-8，GBK 文件 GBK）
- [ ] Ctrl++ 放大编辑器字号，Ctrl+- 缩小
- [ ] Zoom 后切换标签再切回，字号恢复到该标签的 zoom 值

---

## 阶段 4：语法高亮与编辑器特性 **[pending]**

**目标**：编辑器功能完整——C++ 高亮、括号补全、自动缩进、改写模式。

**实现的类**：
- CppHighlighter（QSyntaxHighlighter）：C++ 语法高亮全部规则
- CodeEditor 扩展：括号补全、自动缩进、改写模式

**具体内容**：
- CppHighlighter 七组规则（关键字蓝色粗体、预处理器绿色、字符串深红、字符深红、注释灰色、多行注释跨块、数字深蓝）
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
- [ ] C++ 关键字蓝色粗体高亮
- [ ] 注释灰色，字符串深红，预处理器绿色
- [ ] 多行注释 `/* ... */` 正确高亮
- [ ] 输入 `(` → 自动插入 `)`，光标在中间
- [ ] 输入 `{` → 自动插入 `}`，光标在中间
- [ ] 输入 `"` → 自动插入 `"`，光标在中间
- [ ] 输入 `)` 且右侧是 `)` → 光标跳过
- [ ] Enter 在 `{` 后 → 新行增加缩进
- [ ] Insert 键切换 INS/OVR，状态栏显示更新
- [ ] OVR 模式下输入字符覆盖右侧字符

---

## 阶段 5：编译与运行 **[pending]**

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
- [ ] 写一个简单 C++（如 `scanf a+b, printf a+b`），按 F9 → OutputPanel 显示正确输出
- [ ] InputPanel 内容作为 stdin 正确传入程序
- [ ] 编译错误时 OutputPanel 显示红色错误信息，状态栏显示 "Build failed"
- [ ] Runtime Error（返回码非 0）显示红色
- [ ] F5 弹出外部终端窗口，程序结束后提示"按任意键关闭"
- [ ] F7 终止正在运行的进程
- [ ] 运行超时后 OutputPanel 显示红色超时信息
- [ ] 编译超时后 OutputPanel 显示红色超时信息
- [ ] Busy 状态下按 Build/Test/Run 弹出英文提示，不启动新操作
- [ ] stderr 输出用灰色字体显示
- [ ] Tab A 运行 Test 期间切到 Tab B，切回 Tab A 后看到 Tab A 的运行结果
- [ ] 新文件按 F9 → 弹出保存对话框 → 取消保存 → 不执行编译运行

---

## 阶段 6：设置与持久化 **[pending]**

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

## 阶段 7：查找替换与收尾 **[pending]**

**目标**：所有 PRD 功能完整覆盖，细节打磨。

**实现的类**：
- FindDialog（QDialog）：非模态查找
- ReplaceDialog（QDialog）：非模态替换

**具体内容**：
- FindDialog：查找文本、大小写敏感、向上/向下 RadioButton、Find Next / Close，非模态，关闭时隐藏保留状态
- ReplaceDialog：查找文本 + 替换文本、Replace / Replace All / Close，非模态
- GotoLineDialog：使用 QInputDialog.getInt() 输入目标行号，跳转并居中显示（Ctrl+G）
- Edit 菜单完善：Undo / Redo / Find (Ctrl+F) / Replace (Ctrl+H) / Goto Line (Ctrl+G)
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
- [ ] Edit 菜单全部动作可用（Undo, Redo, Find, Replace, Goto Line）
- [ ] View 菜单 Zoom In / Zoom Out 可用
- [ ] 状态栏编码标签点击 → 弹出编码选择菜单
- [ ] Reopen with Encoding 重新加载文件内容
- [ ] Save with Encoding 以新编码保存文件
- [ ] 退出时 dirty 标签逐个弹出保存确认
- [ ] 所有快捷键与 PRD 一致
- [ ] Toolbar 按钮 tooltip 显示"动作名 (快捷键)"格式