# quickrun.py 技术规格

## 1. 功能概述

`quickrun.py` 是一个命令行工具，用于从源代码注释中提取并执行预定义的命令。开发者可以在源文件注释里以特定格式写入构建/运行命令，随后通过命令行直接调用，无需额外编写 `Makefile` 或脚本。

## 2. 命令定义语法

在源文件注释中，使用如下格式定义命令：

```cpp
// @command(build): gcc $(FILENAME) -o $(FILENOEXT).exe
// @command(run): $(FILENOEXT).exe
```

语法规则：

- 以 `@command` 开头，后接括号中的命令名。
- 命令名后可带 `/target` 表示仅在指定平台生效，例如 `@command(run/win32)`。
- 冒号 `:` 后是实际要执行的命令字符串。
- 命令字符串中可使用 `$(VAR)` 形式的变量占位符。
- 同一文件中可定义多个命令，命令名不区分输入顺序，最终按名称排序展示。

## 3. 支持语言

根据文件扩展名选择注释提取器：

| 扩展名 | 语言 | 注释风格 |
|--------|------|----------|
| `.c`, `.cc`, `.cxx`, `.cpp`, `.h`, `.hpp`, `.hh` | C/C++ | `//`, `/* */` |
| `.cs` | C# | `//`, `/* */` |
| `.java`, `.js`, `.ts`, `.as` | Java / JavaScript / TypeScript / ActionScript | `//`, `/* */` |
| `.go` | Go | `//`, `/* */` |
| `.py` | Python | `#`, `"""`, `'''` |

Python  extractor 会额外处理带前缀的三引号字符串，例如 `r"""..."""`、`f'...'`、`b"..."` 等。

## 4. 可用变量

`configure` 类在初始化时会构建环境变量表，所有值均为字符串。命令字符串中按下表写法直接引用即可，替换发生在执行前；不支持 `$NAME`、`%NAME%` 等其它写法。

| 写法 | 说明 |
|--------|------|
| `$(FILENAME)` | 源文件名（含扩展名） |
| `$(FILEPATH)` | 源文件绝对路径 |
| `$(FILEDIR)` | 源文件所在目录绝对路径 |
| `$(FILEEXT)` | 源文件扩展名（小写） |
| `$(FILENOEXT)` | 源文件名（不含扩展名） |
| `$(PATHNOEXT)` | 源文件绝对路径（不含扩展名） |
| `$(ROOT)` | 项目根目录绝对路径 |
| `$(DIRNAME)` | 源文件所在目录名 |
| `$(PRONAME)` | 项目根目录名 |
| `$(TARGET)` | 当前目标平台，默认 `sys.platform`，可通过 `-t` 修改 |

## 5. 项目根目录探测

初始化 `configure` 时，从源文件所在目录向上查找标记文件/目录，以确定项目根目录：

- 默认标记：`.git`、`.svn`、`.hg`、`.project`、`.root`
- 可通过环境变量 `QUICKRUN_MARKERS` 覆盖，多个标记用逗号分隔，例如：
  ```powershell
  $env:QUICKRUN_MARKERS = '.git,.project'
  ```
- 标记支持通配符 `*`、`?`、`[`，匹配任意一个存在项即视为根目录。
- 若未找到且 `fallback=True`，则返回源文件所在目录。

## 6. 命令行接口

```text
usage: python quickrun.py [options] <filename> [command]
```

选项：

| 选项 | 说明 |
|------|------|
| `-h`, `--help` | 显示帮助信息 |
| `-t {name}`, `--target={name}` | 指定目标平台 |
| `-l`, `--list` | 列出文件中定义的所有命令 |

行为：

- `-h` / `--help` 不需要提供文件名，优先级最高，显示帮助后即退出。
- 若只提供文件名或带 `-l`，则列出可用命令并退出。
- 若提供文件名和命令名，则执行对应命令。
- 命令通过 `subprocess.run(..., shell=True)` 在源文件所在目录执行。
- 程序退出码等于被执行命令的退出码；若命令不存在则返回 `1`。

## 7. 执行流程

1. 解析命令行参数；若请求帮助则直接输出帮助信息。
2. 创建 `configure` 实例，初始化环境变量并探测项目根目录。
3. 调用 `load()`：读取源文件文本，提取注释，解析所有 `@command(...)` 定义。
4. 若未指定具体命令，调用 `list()` 输出命令列表。
5. 若指定命令，调用 `quickrun(name)`：先替换变量，再通过 `system()` 执行，并将其返回码作为程序退出码。

## 8. 示例

### C++ 源文件 `main.cpp`

```cpp
// @command(build): g++ $(FILENAME) -o $(FILENOEXT).exe
// @command(run): $(FILENOEXT).exe
// @command(clean/win32): del $(FILENOEXT).exe
// @command(clean/linux): rm -f $(FILENOEXT)

#include <iostream>
int main() {
    std::cout << "Hello, quickrun!" << std::endl;
    return 0;
}
```

### 命令行调用

```powershell
# 列出命令
python Script\quickrun.py main.cpp

# 编译
python Script\quickrun.py main.cpp build

# 运行（Windows）
python Script\quickrun.py main.cpp run

# 清理（仅在 TARGET 为 linux 时生效）
python Script\quickrun.py -t linux main.cpp clean
```

## 9. 内部模块说明

- `tokenize(code, specs, eof)`：基于正则的简易词法分析器，返回 `(name, value, line, column)` 生成器。
- `extract_cpp_comments(code)` / `extract_python_comments(code)`：分别提取 C 风格与 Python 风格注释。
- `getopt(argv, shortopts)`：自定义命令行参数解析器，支持 `-opt value` 与 `--opt=value` 形式。
- `tabulify(rows, style)`：用于格式化命令列表输出。
- `configure` 类：核心配置与执行入口。
- `main(argv)`：命令行入口。

## 10. 依赖与兼容性

- 仅依赖 Python 标准库：`sys`, `os`, `re`, `subprocess`, `pprint`。
- 兼容 Python 3.8+，未使用 3.9+ 特有语法。
