# CodeRunner

这是一个 PyQt5 开发的代码运行器，方便信奥学生进行 C++ 代码的编写和运行，不同于普通编辑器 / IDE，除了代码编辑区外，最重要的是右边有一个 Input 面板和一个 Output 面板，点 Test 后会把 Input 面板的东西设置成程序的 stdin，并且把程序的 stdout/stderr 显示到 Output 面板，如果有编译错误，会自动显示在 Output 面板。

整个软件界面使用英文。

整个程序源代码只有一个文件 Apps/CodeRunner/CodeRunner.py 即可，全部写在里面，测试放到 Apps/CodeRunner/tests 下面。

## 设计选择

本工具追求简洁，不做过度功能，避免沦为另一个 CPEditor。以下是刻意省略的设计：

- **不做多组测试数据**：不支持在一个 InputPanel 里设置多组 input/expected output 并批量测试，用户只需粘贴一组输入、点 Test、看输出，够用就好
- **不做期望输出对比**：不提供 Expected Output 面板和 diff 功能，用户自行比对输出是否正确，保持界面简单
- **不做编译错误跳转**：点击编译错误信息不会跳转到编辑器对应行号，学生应学会自己看错误行号并定位，这是基本能力

## 用户画像

用户都是参加 C++ 信奥的小学生/初中生，会使用这个软件来做题（Online Judge），OJ 题目一般都是有一些样例数据输入，然后有输出，传统学生用 Dev-C++ 时比较麻烦的是每次运行程序，弹出 cmd 黑色终端窗口，等待输入时，又要去题目那里把输入拷贝，并粘贴到终端窗口里，然后观察输出，这个 Inner Loop 效率太低了。

所以右边设计了输入面板，用户只需要把题目的样例输入贴到 InputPanel 里面，然后修改了程序，每次点 Test 后，就会把 InputPanel 里的内容通过 stdin 传递给程序，然后把程序输出显示到 OutputPanel，这样就不用像 Dev-C++ 那样，每次运行都要麻烦的把测试数据粘贴到终端窗口了。

## 界面框架

从上到下分别是：MenuBar，Toolbar，Tabbar，MainArea 四个区域。窗口默认大小 1000x650，CodeEditor 与右侧面板默认按 1:1 左右分割，中间可拖动调整。

```
╔═════════════════════════════════════════════════════════════════════════╗
║ File   Edit   Run   View                                                ║
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
╚═══════════════════════════════════╩═════════════════════════════════════╝
```

### MenuBar

窗口顶部的菜单栏，包含 File、Edit、Run、View 四个菜单，所有动作均可通过菜单触发（详见 Actions 章节）。

### Toolbar

菜单栏下方的工具栏，放置常用动作的按钮：New、Save、Open、Run、Test、Stop、Settings（详见 Actions 章节）。每个按钮鼠标悬停时显示 tooltip，格式为"动作名 (快捷键)"，例如 "Test (F9)"。

### Tabbar

工具栏下方的标签栏，每打开或新建一个源代码文件，会占用一个独立的 TAB 页，以文件名命名，新建的文件显示为 "untitled1"、"untitled2"（递增编号）。新建的文件内部带有"新文件"标志，表示该文件从未保存到磁盘；打开已存在的文件则没有此标志。新建文件预填充模板内容后同样视为拥有未保存更改，标签名显示 unsaved 标记（如 `*untitled1*`），与空白新文件的行为一致。文件名右边会显示是否有未保存的更改，基本行为参考标准的多文档文本编辑器。

可以通过 Alt+数字键快速切换标签（详见 Actions 章节中的 Switch Tab）：Alt+1 切换到第一个标签，Alt+2 第二个，依此类推，Alt+0 切换到第十个标签。

### CodeEditor

MainArea 左侧的代码编辑区域，用于编写 C++ 代码。支持：

- C++ 语法高亮
- 自动缩进
- 括号补全（可选）
- 显示行号
- Tab 键插入 Tab 制表符（非空格），Tab 制表符默认 4 个字符宽度，与 Dev-C++ 行为一致
- 字体大小可通过 Zoom In / Zoom Out 临时调整（详见 Actions 章节）。Zoom 调整的字号仅在当前会话有效，不会写入 Settings，重启软件后恢复为 Settings 中配置的字号

### InputPanel

MainArea 右上的输入面板，用户在此粘贴 OJ 题目的样例输入。点击 Test 时，面板内容将作为程序的标准输入传递（详见 Actions 节中的 Test）。**InputPanel 的内容是 per-tab 的，切换标签时输入内容随之切换，退出时随标签页一起持久化保存，重启后恢复。**

### OutputPanel

MainArea 右下的输出面板，用于显示：

- Test 运行后程序的标准输出（stdout）使用默认字体颜色，标准错误（stderr）使用灰色字体区分显示；每次 Test 替换 OutputPanel 的全部内容，不追加
- 编译错误信息（以**红色字体**显示），正常程序输出使用默认字体颜色
- Build 的编译结果

**OutputPanel 的内容是 per-tab 的，切换标签时输出内容随之切换，标签关闭时内容一起清除，不做持久化保存。** InputPanel 和 OutputPanel 属于各自标签页的内容容器的一部分，如果在 Tab A 运行 Test 期间用户切换到 Tab B，Tab B 显示自己的 Input/Output 内容；Tab A 的运行结果完成后写入 Tab A 所拥有的 OutputPanel，用户切换回 Tab A 时即可看到。

InputPanel 和 OutputPanel 默认上下平分，中间有可拖动的分割条，用户可以自由调整两个面板的比例。

## Actions

所有用户可触发的动作汇总如下，每个动作可通过菜单、工具栏按钮、快捷键等方式触发：

| 动作 | 说明 | 菜单位置 | 工具栏 | 快捷键 |
|------|------|----------|--------|--------|
| New | 新建文件（预填充模板内容） | File > New | 是 | Ctrl+N |
| Open | 打开文件 | File > Open | 是 | Ctrl+O |
| Save | 保存当前文件 | File > Save | 是 | Ctrl+S |
| Save As | 另存为 | File > Save As | 否 | Ctrl+Shift+S |
| Settings | 打开设置面板 | File > Settings | 是 | - |
| Build | 强制编译当前文件 | Run > Build | 否 | Ctrl+B |
| Test | 编译并用 InputPanel 测试 | Run > Test | 是 | F9 |
| Run | 编译并弹终端窗口交互运行 | Run > Run | 是 | F5 |
| Stop | 终止当前运行的进程 | Run > Stop | 是 | F7 |
| Undo | 撤销编辑 | Edit > Undo | 否 | Ctrl+Z |
| Redo | 重做编辑 | Edit > Redo | 否 | Ctrl+Y |
| Find | 查找文本 | Edit > Find | 否 | Ctrl+F |
| Replace | 替换文本 | Edit > Replace | 否 | Ctrl+H |
| Goto Line | 跳转到指定行号 | Edit > Goto Line | 否 | Ctrl+G |
| Zoom In | 放大字体 | View > Zoom In | 否 | Ctrl++ |
| Zoom Out | 缩小字体 | View > Zoom Out | 否 | Ctrl+- |
| Switch Tab | 切换到第 N 个标签页 | - | 否 | Alt+1 ~ Alt+0 |
| Close Tab | 关闭当前标签页 | File > Close | 否 | Ctrl+W |

编译产物（`.exe`）放在源文件同目录下，文件名与源文件同名（如 `test.cpp` 编译为 `test.exe`），与 Dev-C++ 单文件模式行为一致。Run/Test 运行编译产物时，工作目录（working directory）设置为编译产物所在的目录。

### New（新建文件）

新建文件时，编辑器预填充模板内容（而非空白文档），模板内容可在 Settings 中配置（详见设置章节的"新建模板"项）。默认模板为：

```cpp
#include <iostream>
#include <cstdio>
using namespace std;
int main() {
    return 0;
}
```

学生做题时几乎每次都要写这个骨架，预填充模板让新建即可开始写逻辑，无需手动重复输入。如果需要空白文件，直接 Ctrl+A 全选删除即可。

### Test（主要工作流）

点击 Test 时：先保存文件（如果有更改；如果当前文件带有"新文件"标志则弹出保存对话框让用户选择文件名和路径，用户取消保存则终止后续流程），然后判断是否需要重新编译——需要重新编译的条件为：可执行文件不存在、可执行文件比源文件旧、或编译产物比上次修改编译参数的时间旧。如果编译出错就在 OutputPanel 显示错误信息，然后结束；如果编译正常，就从 InputPanel 里面取得输入内容，作为启动程序的标准输入，然后捕获标准输出（stdout 使用默认字体颜色）和标准错误（stderr 使用灰色字体颜色，与 stdout 区分显示）、返回码和运行耗时显示到 OutputPanel。每次 Test 替换 OutputPanel 的全部内容，不追加上次输出。返回码非 0 时显示为 Runtime Error。如果运行超时，则终止进程并在 OutputPanel 末尾以**红色字体**显示 "Timeout after xx seconds"。正常运行结束后，在输出内容下方显示退出码、运行耗时（如 "exit with code 0 in 0.015s"）；如果系统安装了 `psutil` 库则额外显示内存占用（如 "exit with code 0 in 0.015s, 1.2MB"），未安装 `psutil` 时不显示内存信息。

运行过程中 Test 和 Run 按钮保持可用，但如果用户点击则提示"程序正在运行，请等待运行结束或 Stop 后再使用"。

### Run（交互式运行）

点击 Run 时：先保存文件（如果有更改；如果当前文件带有"新文件"标志则弹出保存对话框让用户选择文件名和路径，用户取消保存则终止后续流程），然后判断是否需要重新编译（同 Test 的判断逻辑），如果编译出错就在 OutputPanel 显示错误信息，然后结束；如果编译正常，就弹出一个系统终端窗口运行程序，程序结束后提示"按任意键关闭"，用户可在终端窗口中手动输入数据进行交互。**弹出终端窗口后，CodeRunner 不再跟踪该进程的运行状态，视为本次 Run 已完成**，用户可以立即进行下一次 Test 或 Run。Stop 按钮不影响通过 Run 弹出的外部终端进程。

### Build（仅编译）

Build 不在工具栏上，仅通过菜单或快捷键触发。点击后：先保存文件（如果有更改；如果当前文件带有"新文件"标志则弹出保存对话框让用户选择文件名和路径，用户取消保存则终止后续流程），然后强制重新编译，将编译结果（成功或错误信息）显示到 OutputPanel。

### Stop

如果一次 Test 过程没结束，则不能开启下一次，Test 和 Run 按钮保持可用，点击时提示"程序正在运行，请等待运行结束或 Stop 后再使用"。按 Stop（F7）终止当前进程。运行过程有时间限制，默认 10 秒，可以在设置里更改。超时后终止进程，并在 OutputPanel 末尾以红色字体显示 "Timeout after xx seconds"。编译过程也有超时限制，默认 20 秒，可以在设置里更改。

## 设置

软件配置保存在 `~/.config/coderunner/settings.json` 文件中，通过 Settings 动作打开设置对话框（详见 Actions 章节）。设置面板为独立弹出的模态 Dialog，底部有 OK 和 Cancel 按钮，点击 OK 保存更改，Cancel 放弃更改。主要设置项包括：

- **编译器路径**：g++ 编译器的路径（默认使用 PATH 中的 g++）。设置面板中提供"Auto Detect"按钮，可自动检测系统中常见安装路径下的 g++ 编译器（如 MinGW、TDM-GCC、Dev-C++ 自带 MinGW 等）
- **编译参数**：额外的编译选项（如 `-std=c++14`、`-O2` 等），修改编译参数后会触发重新编译（编译产物比上次修改编译参数的时间旧则重编译）
- **环境变量**：编译器运行和程序运行的预设环境变量，以 key/value 表格形式编辑。值中支持 `$VAR_NAME` 语法引用已有环境变量（包括 Windows 平台，统一使用 `$PATH` 而非 `%PATH%`）。设置的环境变量为覆盖模式，即直接替换系统中同名环境变量的值
- **运行超时时间**：程序运行的最大时间限制（默认 10 秒）
- **编译超时时间**：编译过程的最大时间限制（默认 20 秒）
- **字体与字号**：代码编辑器及 IO 面板的默认字体和字号
- **新建模板**：新建文件时预填充的模板内容，默认为基础 C++ 骨架（含 `#include`、`using namespace std`、`int main()`），用户可自定义模板文本

## 文件操作

- 支持文件拖放：用户可以将 `.cpp` / `.c` 文件直接拖到窗口中打开
- 支持最近文件列表：通过 File 菜单中的 Recent Files 子菜单访问，最多记录 10 个文件，按打开时间倒序排列。如果文件已被删除或移动，菜单项仍然显示，点击后提示"文件不存在"
- 关闭标签页时，如果文件有未保存的更改，弹出对话框提醒用户保存（Save / Don't Save / Cancel）

## 编码策略

- Windows 平台：文件编码、程序输入输出均跟随系统编码（中文环境即 GBK）。InputPanel 和 OutputPanel 内部使用 Unicode，向程序传递 stdin 时转换为系统编码，从程序读取 stdout 时从系统编码转换为 Unicode 显示
- 非 Windows 平台：全部使用 UTF-8，无需额外编码转换
- 编译时默认自动加入 `-fexec-charset` 参数以匹配平台编码（Windows 默认 GBK，其他平台默认 UTF-8），无需用户手动配置

## 查找和替换

Find 和 Replace 使用弹出式对话框，UI 风格参考 Windows 10 记事本和 Dev-C++。Find 对话框支持向上/向下搜索和大小写敏感选项；Replace 对话框在 Find 基础上增加替换和全部替换功能。

## 窗口状态持久化

窗口的以下状态信息保存在 `~/.cache/CodeRunner/window.json` 中，退出程序时自动保存，下次启动时恢复：

- 窗口大小和位置
- CodeEditor 与右侧面板的左右分割条位置
- InputPanel 与 OutputPanel 的上下分割条位置
- 文件对话框的上次目录（见下方说明）
- 之前打开的标签页列表及其状态（见下方说明）

### 会话恢复

重启程序时，恢复上次退出时打开的所有标签页，包括：

- 已保存的文件：重新打开对应文件
- 带有"新文件"标志且未保存的标签页：恢复编辑器内容和 InputPanel 内容，标签名仍为上次显示的名称（如 `untitled3`），"新文件"标志保留
- InputPanel 内容随标签页一起恢复
- OutputPanel 内容不做持久化，重启后为空

### 文件对话框上次目录

打开文件（Open）、保存（Save 对带有"新文件"标志的文件弹出的对话框）和另存为（Save As）时，文件对话框的初始目录为上次使用文件对话框时所在的目录，该路径记录在 `~/.cache/CodeRunner/window.json` 中。如果没有记录项（首次使用），默认打开用户主目录（Windows 下为 `%USERPROFILE%`，其他平台为 `$HOME`）。

## 其他行为

其他诸如退出时提醒保存文件之类的行为，参考标准多文档编辑器。
