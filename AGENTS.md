# 项目说明

PyQt5 桌面小工具集合。Library 目录放可复用的 PyQt5 组件库，Apps 目录放独立的小应用，每个应用一个文件夹。

## 目录结构

```
Library/
  AnchorLayout/          # C# 风格的 Anchor/Dock 布局组件
    AnchorLayout.py      # 主库文件（单文件）
    demo_anchor1.py      # 演示脚本
    demo_anchor2.py      # 演示脚本
    demo_docking.py      # 演示脚本
    cpp/                 # C++/Qt 参考实现

Apps/
  CodeRunner/            # 信奥 C++ 代码运行器
    prd.md               # 产品需求文档
    spec.md              # 技术规格文档（迭代时补写）
    CodeRunner.py        # 主程序（单文件）
    tests/               # 测试脚本
```

## 技术规格

- **Python 3.8 + PyQt5** — 为了兼容 Windows 7 打包，不得使用 3.9+ 的语法特性（如 walrus operator `:=`、`str.removeprefix()` 等）
- **DPI 缩放** — 必须感知桌面 DPI 缩放比例，运行时按比例调整字体和布局尺寸，高分屏下不可太小。使用 `QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)` 或手动计算 DPI factor 并乘以所有固定尺寸值
- **依赖最小化** — 只依赖 PyQt5，不引入第三方 GUI 框架

## Library 编码规范

- **单文件库** — 每个库的完整实现放在一个 `.py` 文件中（如 `AnchorLayout.py`），不拆分模块
- **伴生演示** — 提供 `demo_*.py` 演示脚本，可直接 `python demo_xxx.py` 运行验证
- **文件头格式**：
  ```python
  #! /usr/bin/env python
  # -*- coding: utf-8 -*-
  #======================================================================
  #
  # FileName.py - 简短描述
  #
  # Created by skywind on YYYY/MM/DD
  # Last Modified: YYYY/MM/DD HH:MM:SS
  #
  #======================================================================
  ```
- **返回值风格** — 成功返回 `0`，失败返回 `-1` / `-2`（C 习惯），不抛异常用于内部控制流
- **私有方法** — 双下划线前缀 `__method_name` 表示私有
- **无外部依赖** — Library 组件只依赖 PyQt5，不依赖其他 Library 组件或第三方包

## Apps 编码规范

- **单文件主程序** — 每个应用的主程序写在单个 `.py` 文件中（如 `CodeRunner.py`），所有类和逻辑集中于此
- **文档驱动** — 每个 App 必须有 `prd.md`（产品需求）和 `spec.md`（技术规格）。迭代前先阅读这两个文档，修改代码后必须同步更新文档
- **测试位置** — 测试脚本放在 `Apps/<AppName>/tests/` 目录下
- **UI 语言** — 遵循 `prd.md` 中的规定（如 CodeRunner 要求英文 UI），未规定时默认中文
- **配置存储** — 应用配置保存在 `~/.config/<appname>/settings.json`

## Agent 工作流

迭代某个 App 时：

1. 读取 `Apps/<AppName>/prd.md` 和 `spec.md`，理解当前需求和技术方案
2. 如果 `spec.md` 不存在，根据 `prd.md` 和已有代码先补写 `spec.md`
3. 按文档实现或修改代码
4. 修改完成后，同步更新 `prd.md` 和 `spec.md` 使文档与代码一致
5. 编写或更新对应的测试

迭代某个 Library 时：

1. 读取库的 `.py` 文件和演示脚本，理解现有接口和用法
2. 修改库代码
3. 更新或补充演示脚本，确保能直接运行验证功能
4. 如有 C++ 参考实现（`cpp/` 目录），保持 Python 和 C++ 版本的接口一致性

## 编码风格

- 函数/方法定义时参数括号前有空格：`def method (self, arg)`（作者习惯）
- 类型注解使用紧凑格式：`arg:QWidget` 而非 `arg: QWidget`（与现有代码一致）
- 字符串优先用单引号，多行/含单引号时用双引号
- 注释用中文或英文均可，保持与周围代码一致