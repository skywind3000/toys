# CodeRunner

PyQt5 开发的 C++ 代码运行器，面向信奥学生。核心特色：右侧 Input/Output 面板，点 Test 即把 Input 内容作 stdin 传入程序，Output 面板实时显示 stdout/stderr，内循环效率远高于 Dev-C++ 手动粘贴模式。

整个软件界面使用英文。UI 使用 Fusion 主题，Toolbar 使用自绘彩色图标（纯图标无文字）。

整个程序源代码只有一个文件 Apps/CodeRunner/CodeRunner.py，测试放到 Apps/CodeRunner/tests 下面。

## 用户画像

用户是参加 C++ 信奥的小学生/初中生，用此工具做题（Online Judge）。OJ 题目有样例输入/输出，传统用 Dev-C++ 时每次运行都要弹终端窗口、手动拷贝粘贴测试数据，内循环效率太低。CodeRunner 的 Input 面板让用户粘贴样例输入后每次点 Test 即可，省去重复拷贝粘贴。

## 设计选择

追求简洁，不做过度功能，避免沦为另一个 CPEditor。刻意省略：

- **不做多组测试数据**：不支持一个 InputPanel 里设置多组 input/expected output 并批量测试
- **不做期望输出对比**：不提供 Expected Output 面板和 diff 功能
- **不做编译错误跳转**：点击编译错误不跳转到对应行号，学生应学会自己看行号定位
- **不做暗色主题**：工程量大，暂不排入近期迭代
- **不做 Smart Select（Ctrl+B 扩展选区）**：优先级最低，后续迭代考虑
- **不做 Ctrl+Left/Right 按单词跳转**：QTextEdit 默认可能已支持部分行为，需验证后再决定
- **不做代码补全和错误 linting**：违反"简洁 OJ 工具"定位

## 界面框架

从上到下五个区域：MenuBar、Toolbar、TabBar、MainArea、StatusLine。窗口默认大小 1000x650。CodeEditor 与右侧面板默认 1:1 左右分割，可拖动调整。

```
╔═════════════════════════════════════════════════════════════════════════╗
║ File   Edit   Run   View   Help                                         ║
║─────────────────────────────────────────────────────────────────────────║
║ ➕ New  💾 Save  📁 Open  |  ▶ Run  🧪 Test  ⏹ Stop  ⚙ Settings       ║
║─────────────────────────────────────────────────────────────────────────║
║ [📄 test.cpp] [📄 hello.cpp]                                            ║
╠═══════════════════════════════════╦═════════════════════════════════════╣
║ 1  #include <stdio.h>             ║ INPUT                               ║
║ 2  #include <stdlib.h>            ║ 233 666                             ║
║ 3  using namespace std;           ║                                     ║
║ 4  int main() {                   ║─────────────────────────────────────║
║ 5      int a, b;                  ║ OUTPUT                              ║
║ 6      scanf("%d %d", &a, &b);    ║ 899                                 ║
║ 7      printf("%d", a + b);       ║ --------                            ║
║ 8      return 0;                  ║ exit with code 0 in 0.015s, 1.2MB   ║
║ 9  }                              ║                                     ║
╠═══════════════════════════════════╩═════════════════════════════════════╣
║ Build successful                         Ln 4/120, Col 12 | GBK | INS   ║
╚═════════════════════════════════════════════════════════════════════════╝
```

### MenuBar

窗口顶部菜单栏：File、Edit、Run、View、Help。所有动作均可通过菜单触发。

### Toolbar

菜单栏下方，7 个按钮：New、Save、Open | Run、Test、Stop | Settings。自绘彩色图标（无文字），悬停 tooltip 格式 "动作名 (快捷键)"。

### TabBar

每打开/新建一个文件占用一个标签页。新建文件显示 "untitled1"、"untitled2"（递增编号）。新文件和已修改文件显示 unsaved 标记。Alt+1~9 切换到第 1~9 个标签，Alt+0 切换到第 10 个。关闭最后一个标签后进入空标签状态（编辑区为空），不会自动新建空白标签。首次启动也是空标签状态。

### CodeEditor

MainArea 左侧的代码编辑区域。功能列表：

- **C++ 语法高亮**：关键字、预处理器、字符串、注释、数字、运算符；多行注释跟踪
- **行号显示**：左侧行号区域，宽度随最大行号位数动态调整
- **当前行高亮**：浅黄色背景标记光标所在行
- **括号匹配高亮**：配对括号浅蓝色背景（仅在非注释、非字符串上下文中生效）
- **自动缩进**：Enter 保留当前行前导空白；行末 `{` 时增加一级缩进；光标在 `{` 和 `}` 之间时插入两行
- **Smart Backspace**：Space 缩进模式下，光标在缩进整数倍边界且左侧全是空格时，一次删除 indent_size 个空格
- **Tab 键**：无选区 → 插入 `\t`（indent_style='tab'）或 indent_size 个空格（indent_style='space'）；有选区 → 对选中行增加一级缩进
- **Shift+Tab**：有选区 → 对选中行减少一级缩进；无选区 → 对当前行减少一级缩进
- **Ctrl+/ 注释/取消注释**：Toggle `//`，空行视为未注释，全部已注释则移除
- **Ctrl+D 复制当前行**：不替换剪贴板
- **Ctrl+Shift+K 删除当前行**：删除光标所在行或选中行
- **Alt+Up/Down 上下移动当前行**：调换代码行顺序
- **括号补全**（Settings 中可开关，默认启用）：
  - 输入开符号 → 自动插入闭符号，光标置中间
  - **闭符号跳过**：输入闭符号时光标右侧恰好同一符号则跳过
  - **对删除**：删除开符号时右侧紧邻闭符号一并删除
  - **上下文感知**：注释或字符串内的括号不触发自动补全
  - `#include <` → 自动插入 `>`，光标置中间
  - `/*` → 自动补 `*/`，光标置中间
- **改写模式**：Insert 键切换 INS/OVR，OVR 模式宽光标、输入替换右侧字符
- **Zoom**：Ctrl++ 放大、Ctrl+- 缩小（最小 6pt）。Zoom 是偏移量（非绝对字号），修改编辑器字体 Settings 时所有标签 zoom 重置为 0，修改非字体相关 Settings 时 zoom 保留。会话级不持久化
- **右键菜单**：Undo、Redo、Cut、Copy、Paste、Comment/Uncomment、Indent、Unindent、Duplicate Line、Delete Line

缩进风格和宽度可在 Settings 中配置（Tab/Space，宽度 2-16，默认 Tab + 4）。

### InputPanel

MainArea 右上的输入面板，固定 "INPUT" 标签，下方文本编辑区。粘贴 OJ 样例输入。支持 Tab 键插入制表符。**内容是 per-tab 的**，切换标签时随之切换，退出时持久化保存，重启后恢复。

### OutputPanel

MainArea 右下的输出面板，固定 "OUTPUT" 标签，下方只读文本区。显示程序输出，不同内容类型用不同颜色区分：stdout 默认色、stderr 灰色、正常退出/Build 成功灰色、编译错误/Runtime Error/超时/崩溃红色。**内容是 per-tab 的**，切换标签时随之切换，关闭标签时清除，不做持久化。

**自动滚动**：新输出默认自动滚到底部；用户向上翻看时暂停自动滚动；END 键恢复自动滚动。每次 Test/Build 清空后重新开启自动滚动。

**退出状态行**：运行结果行（正常退出、Runtime Error、Timeout 等）前追加换行，确保不接在程序输出末尾。正常退出显示 "exit with code N in X.XXXs"；如安装了 psutil 则附加内存占用（如 ", 1.2MB"）。

**双击跳转**：双击编译错误/警告行（格式 `filename:line:col: error/warning: ...` 或 `filename:line: error/warning: ...`）时，光标跳转到 CodeEditor 对应行列位置并聚焦编辑器。非错误行双击行为不变（QTextEdit 默认选词）。

**OutputPanel 完整消息列表**：

| 场景 | 消息 | 颜色 |
|------|------|------|
| 正常退出 (code 0) | exit with code 0 in X.XXXs, XMB | 灰色 |
| Runtime Error (code ≠ 0) | Runtime Error (exit code N) | 红色 |
| Runtime Error + crash detail | Runtime Error: detail (exit code N) | 红色 |
| 程序崩溃 | Program crashed: detail (exit code N) | 红色 |
| 用户 Stop 运行 | Process stopped in X.XXXs | 灰色 |
| 运行超时 | Timeout after Xs | 红色 |
| 程序启动失败 | Failed to start program + Error: detail | 红色 |
| Build 成功 | Build OK in X.XXXs | 灰色 |
| 编译错误 | error messages | 红色 |
| 用户 Stop 编译 | Compilation stopped in X.XXXs | 灰色 |
| 编译超时 | Compilation timeout after Xs (ran X.XXXs) | 红色 |
| 编译器启动失败 | Failed to start compiler 'path' + Error: detail + Please check Settings... | 红色 |
| 终端启动失败 | Failed to launch terminal | 红色 |

crash detail 包含 Windows NTSTATUS 码可读描述（如 "DLL not found"、"Access violation"）。

InputPanel 和 OutputPanel 默认上下 1:1 平分，中间可拖动分割条。

### StatusLine

窗口底部状态栏，两部分：

- **左侧 (Message)**：操作提示信息，如 "Build successful"、"Build failed with 3 error(s)"、"Program exited with code 0"、"Runtime Error"、"Timeout after 10 seconds"。触发新操作时更新，平时保持上一条消息。
- **右侧 (Cursor/Encoding/Mode)**：`Ln {当前行}/{总行数}, Col {列号} | {编码} | {模式}`（如 `Ln 4/120, Col 12 | GBK | INS`）。行号列号从 1 开始，随光标实时更新。模式 INS/OVR 通过 Insert 键切换。点击编码标签弹出编码菜单。

## Actions

所有用户动作汇总：

| 动作 | 说明 | 菜单 | 工具栏 | 快捷键 |
|------|------|------|--------|--------|
| New | 新建文件（预填充模板，光标定位到 main() 第一个 `{` 后的行缩进位置） | File > New | 是 | Ctrl+N |
| Open | 打开文件（已打开的文件切换到对应标签而非新建） | File > Open | 是 | Ctrl+O |
| Save | 保存当前文件 | File > Save | 是 | Ctrl+S |
| Save As | 另存为 | File > Save As | 否 | Ctrl+Shift+S |
| Settings | 打开设置面板 | File > Settings | 是 | - |
| Build | 强制编译当前文件 | Run > Build | 否 | Ctrl+B |
| Test | 编译并用 InputPanel 测试 | Run > Test | 是 | F9 |
| Run | 编译并弹终端窗口交互运行 | Run > Run | 是 | F5 |
| Stop | 终止当前运行的进程 | Run > Stop | 是 | F7 |
| Undo | 撤销 | Edit > Undo | 否 | Ctrl+Z |
| Redo | 重做 | Edit > Redo | 否 | Ctrl+Y |
| Cut | 剪切 | Edit > Cut | 否 | Ctrl+X |
| Copy | 复制 | Edit > Copy | 否 | Ctrl+C |
| Paste | 粘贴 | Edit > Paste | 否 | Ctrl+V |
| Find | 查找文本 | Edit > Find | 否 | Ctrl+F |
| Replace | 替换文本 | Edit > Replace | 否 | Ctrl+H |
| Goto Line | 跳转到指定行号 | Edit > Goto Line | 否 | Ctrl+G |
| Comment/Uncomment | 注释/取消注释 | Edit > Comment/Uncomment | 否 | Ctrl+/ |
| Indent | 选中行增加缩进 | Edit > Indent | 否 | Ctrl+] / Tab(有选区) |
| Unindent | 选中行减少缩进 | Edit > Unindent | 否 | Ctrl+[ / Shift+Tab |
| Duplicate Line | 复制当前行/选中行 | Edit > Duplicate Line | 否 | Ctrl+D |
| Delete Line | 删除当前行/选中行 | Edit > Delete Line | 否 | Ctrl+Shift+K |
| Move Line Up | 当前行/选中行上移 | Edit > Move Line Up | 否 | Alt+Up |
| Move Line Down | 当前行/选中行下移 | Edit > Move Line Down | 否 | Alt+Down |
| Zoom In | 放大字体 | View > Zoom In | 否 | Ctrl++ |
| Zoom Out | 缩小字体 | View > Zoom Out | 否 | Ctrl+- |
| Switch Tab | 切换到第 N 个标签 | - | 否 | Alt+1~Alt+0 |
| Close Tab | 关闭当前标签 | File > Close | 否 | Ctrl+W |
| About | 显示关于信息 | Help > About | 否 | - |

编译产物放在源文件同目录下，文件名与源文件同名（如 test.cpp → test.exe）。编译时 cwd 设为源文件所在目录，传给编译器的源文件名和 -o 目标使用相对路径（纯文件名），使 gcc 报错信息简短（如 `hello.cpp:3:5: error: ...` 而非绝对路径）。Run/Test 运行时工作目录为编译产物所在目录。

## 核心工作流

### New（新建文件）

新建文件预填充模板内容（可在 Settings 中配置），默认模板为基础 C++ 骩架。光标自动定位到 main() 第一个 `{` 后的行缩进位置，用户可直接开始写逻辑。

### Test（F9）

保存文件（新文件弹保存对话框，取消则终止） → 判断是否需要重编译（exe 不存在、过期、编译参数变更等） → 编译失败则 OutputPanel 显示错误信息并结束 → 编译成功则用 InputPanel 内容作 stdin 运行程序 → OutputPanel 显示 stdout（默认色）+ stderr（灰色）+ 退出状态行。每次 Test 替换 OutputPanel 全部内容。

### Run（F5）

保存文件 → 判断是否需要重编译 → 编译失败则 OutputPanel 显示错误并结束 → 编译成功则弹出系统终端窗口运行程序，程序结束后提示 "按任意键关闭"。弹出终端后 CodeRunner 不再跟踪该进程，Stop 不影响外部终端进程。

### Build（Ctrl+B）

保存文件 → 强制重新编译 → OutputPanel 显示 "Build OK in X.XXXs"（灰色）或编译错误（红色）。

### Stop（F7）

终止当前编译/运行进程。Build/Test/Run 互斥——当前操作完成或被 Stop 前，点击 Build/Test/Run 弹提示 "A process is currently running. Please wait or press Stop before starting a new operation."（按钮保持可点击，不禁用灰显）。

运行超时默认 10 秒（可在 Settings 中更改），编译超时默认 20 秒（可在 Settings 中更改），超时后终止进程并在 OutputPanel 显示红色超时信息。

## 设置

配置保存在 `~/.config/coderunner/settings.json`。模态 Dialog，OK 保存/Cancel 丢弃，三页 Tab 结构。

### Compiler 页

- **编译器路径**：默认 PATH 中的 gcc。提供 Browse... 按钮和 Auto Detect 按钮（自动搜索常见安装路径）
- **编译参数**：额外编译选项（如 `-std=c++14 -O2`），默认留空。变更后触发所有标签重编译
- **环境变量**：key/value 表格编辑，值支持 `$VAR_NAME` 语法引用已有环境变量，为覆盖模式
- **运行超时**：1-300 秒，默认 10
- **编译超时**：1-300 秒，默认 20

### Editor 页

- **编辑器字体与字号**：monospace 字体选择器 + 字号（默认 Consolas/11，Windows 优先 Consolas，macOS 优先 Menlo）
- **IO 面板字体与字号**：独立于编辑器配置
- **括号补全**：QCheckBox，默认启用
- **缩进风格**：Tab / Space，默认 Tab
- **Tab 宽度 / 缩进步长**：2-16，默认 4
- **Word Wrap**：QCheckBox，默认关闭

### Template 页

- **模板文本编辑器**：QPlainTextEdit，Tab 宽度实时跟随 Tab Width 设置，Enter 自动缩进
- **Reset to Default** 按钮：恢复默认 C++ 骩架模板

## 编码策略

**核心原则：用户不需要关心编码，CodeRunner 自动处理一切。**

### 自动检测

打开文件时自动检测编码（UTF-8 BOM → 严格 UTF-8 验证 → 系统编码），不做概率检测。新建文件默认 UTF-8，保存时 UTF-8 不加 BOM。

### 编辑器显示

状态栏右侧显示当前文件编码（如 `UTF-8`、`GBK`），用户可知晓编码状态。

### 编译标志

根据文件编码自动添加 g++ 编译标志，确保程序运行时 I/O 使用平台编码（Windows 为 GBK），无需用户手动配置。

### 运行时 I/O

Test 模式下 InputPanel → stdin 转换为平台编码，stdout/stderr → OutputPanel 从平台编码转换显示，中文正常显示。Run 模式弹出外部终端，使用系统编码无需额外转换。

### 编码相关用户操作

- **状态栏编码标签可点击** → 弹出编码菜单：
  - **Reopen with Encoding**：用指定编码重新解读当前文件。**新文件（untitled）不可 Reopen**。有未保存更改时弹 Save/Discard/Cancel 确认
  - **Save with Encoding**：用指定编码保存当前文件。新文件先弹 Save As 对话框选路径。**注意：Save with Encoding 不清理行尾空白**（与普通 Save 行为不同）
  - 可选编码：UTF-8、GBK、GB18030、Big5、Shift_JIS、EUC-JP、EUC-KR、ISO-8859-1、ISO-8859-2、Windows-1252、Windows-1251

### 保存文件

保存时使用原始编码写回。自动清理行尾空白。GBK 文件保存含非 GBK 字符时弹警告不崩溃。Save As 失败时 rollback 为新/未保存状态。

## 文件操作

- **重复文件检测**：Open 或拖放打开已打开的文件时，切换到对应标签而非新建标签
- **文件拖放**：支持 `.cpp/.c/.cc/.cxx/.h/.hpp/.hh` 文件直接拖到窗口打开
- **最近文件列表**：File > Recent Files 子菜单，最多 10 条按时间倒序。点击已删除文件提示 "File not found" 并移除
- **关闭标签**：有未保存更改时弹 Save/Discard/Cancel 确认
- **文件对话框起始目录**：上次使用目录（持久化保存）；如目录已不存在则回退到用户主目录

## 查找和替换

- **Find (Ctrl+F)**：非模态对话框，大小写敏感选项，向上/向下方向，wrap-around 搜索（到末尾/开头时从头/尾继续）。未找到时标题栏显示 "Not found"。Close 时隐藏保留状态
- **Replace (Ctrl+H)**：非模态对话框，增加替换文本 + Replace/Replace All 按钮。Replace All 完成后标题栏显示替换数量。Close 时隐藏保留状态
- **Goto Line (Ctrl+G)**：输入行号（1~总行数），光标跳转到目标行首并居中滚动

## 窗口状态持久化

窗口以下状态退出时自动保存到 `~/.cache/coderunner/window.json`，下次启动恢复：

- 窗口大小和位置（恢复时 clamp 到屏幕可见区域）
- 左右分割条和上下分割条位置
- 文件对话框上次目录
- 打开的标签页列表（已保存文件重新打开，untitled 标签恢复编辑器+Input 内容，Output 清空）
- 最近文件列表

## 其他行为

其他诸如退出时逐个确认保存文件等行为，参考标准多文档文本编辑器。