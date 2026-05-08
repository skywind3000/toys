# OutputPanel 性能优化与重构

## 当前的问题

每次新消息到达后都要追加到 OutputPanel 对应的 document，然后靠一个 Timer 来处理滚动，性能开销大，逻辑不够严密。

## 重构目标

提升 OutputPanel 的性能，同时引入更合理的 "按需滚动" 方式：

- 新消息来的时候只有 OutputPanel 的滚动条在最下方的时候会自动滚动，因为代表用户现在想看新消息；
- 如果滚动条被用户拉到上面，代表用户想看老消息，那么新消息来的时候就只追加，不自动滚动窗口了；

每个 TAB 的 OutputPanel 引入 pinned_to_bottom 来管理这个状态。

## 具体做法

1）移除现在老的 need_scroll 计算和 timer 以及 OutputPanel 内容追加逻辑；

2）为每个 TAB 维护一个 output_buffer 列表，和一个 pinned_to_bottom 的布尔变量；

3）每次某个 TAB 的 OutputPanel 需要输出数据时只是把 `(color, text)` 追加到 output_buffer，不直接写入 Document；

4）存在一个全局 timer，在 MainWindow 初始化时创建并启动，间隔 50ms，**永不停止**。每次 tick 扫描每个 tab：

- 如果 output_buffer 有内容，就合并相邻相同 color 的条目，分批将 output_buffer flush 到该 Tab 对应的 Document 里；
- 如果是当前 TAB（对应 Document 可见），看 pinned_to_bottom 为真就把滚动条滚动到最后一行；
- 如果不是当前 TAB（对应 Document 不可见），做完 flush 就行，不滚动；
- buffer 为空且无需滚动时，本次 tick 无实际操作，开销极低；

5）如果一个非激活的 TAB 被激活（`_switch_to_tab`），检查新 tab 的 pinned_to_bottom：
   - 若为 True，把 OutputPanel 滚动条拉到最后一行；
   - 若为 False，恢复切换前保存的 `tab.output_scroll` 值（即用户离开时正在看的位置）；
   _save_widget_state 仍然在切走前保存 output_scroll（供 pinned=False 时恢复用）；

## 全局 Timer 的生命周期

- Timer 在 MainWindow.__init__ 时创建并启动，间隔 50ms
- **永远不停**，不需要 isActive() 检查，不需要 start/stop 调用
- tick 内只做有意义的操作（buffer 非空才 flush，pinned 才滚动）
- 没有操作时开销极低，50ms 一次空循环对性能无影响

## 入口点改造

所有向 OutputPanel 写入数据的地方，统一改为向对应 tab 的 output_buffer 追加 `(color, text)` 元组，不再直接调用 `_output_append` 写入 Document：

- `_on_run_stdout_ready(text)` → `tab.output_buffer.append((None, text))`
- `_on_run_stderr_ready(text)` → `tab.output_buffer.append((QColor(128,128,128), text))`
- 编译错误信息输出 → `tab.output_buffer.append((error_color, text))`
- 其他所有 `_output_append(tab.output_doc, ...)` 调用点 → 改为 `tab.output_buffer.append((color, text))`

## Buffer Flush 逻辑

Timer tick 中对每个 tab 的 flush 步骤：

1）检查 tab.output_buffer 是否为空，空则跳过；

2）合并相邻且 color 相同的条目：遍历 buffer，连续两条 color 一致则 text 拼接，减少 cursor 操作次数；

3）遍历合并后的列表，逐条用 QTextCursor 插入到 tab.output_doc，每条切换一次 QTextCharFormat；

4）清空 tab.output_buffer。

### 合并规则

仅合并**相邻**同 color 条目，不跨颜色边界：

```
(stdout, "hello")    → color=None
(stdout, " world")   → color=None   → 合并为 "hello world"
(stderr, "error")    → color=gray   → 不合并，独立段
(stdout, "done")     → color=None   → 新段，不与前面 stdout 合并
```

### 大输出保护

如果 output_buffer 积累的文本总量超过 64KB，或条目数超过 200，立即执行一次 flush，不等下一个 tick。防止高频输出场景下 buffer 膨胀。flush 完成后，如果该 tab 是当前 tab 且 pinned_to_bottom = True，立即执行一次程序性滚动到底部。

### 交互式程序的即时 flush

用户提交 stdin 输入（按 Enter）时，立即触发一次当前 tab 的 buffer flush，不等 tick。保证交互式程序的 prompt 能尽快显示，用户不会在看不到提示的情况下输入。flush 完成后同样检查 pinned_to_bottom，若为 True 则立即滚动到底部。

## 状态管理

每个 Tab 的 pinned_to_bottom 变量的状态管理：

1）初始化新建 Tab 或清空 OutputPanel 时，设置 pinned_to_bottom = True；

2）用户将滚动条往上拉（离开最后一行），设置 pinned_to_bottom = False，代表用户想看老内容；

3）用户将滚动条拉回最后一行，设置 pinned_to_bottom = True，代表用户又想看新内容了；

4）滚动条是否在最后一行的判断有 3-4 像素的误差冗余，考虑 DPI 换算问题；

5）**程序启动时**（进入 compiling / running 状态），重置 pinned_to_bottom = True，代表用户此时想看新输出；

6）**用户按 End 键**，设置 pinned_to_bottom = True 并立即滚动到底部。
   OutputPanel 已 override `keyPressEvent`，捕获 `Qt.Key_End`：先调用 `super().keyPressEvent(event)` 让光标移到行末，再额外将 scrollbar 滚到 maximum() 并设置 pinned_to_bottom = True。注意不用 `Ctrl+End`（Qt 标准"文档末尾"快捷键），因为直觉上按 End 就是"回到最新输出"。

### 区分用户滚动与程序滚动

Timer tick 中的程序性滚动（setValue 到 maximum）也会触发 scrollbar 的 valueChanged 信号。为避免误判，引入 `__programmatic_scroll` 布尔标志：

- Timer tick 执行程序性滚动前，设置 `__programmatic_scroll = True`
- 滚动完成后（同一 tick 内），设置 `__programmatic_scroll = False`
- `_on_output_scroll_changed` 检测 scrollbar 变化时：
  - 若 `__programmatic_scroll` 为 True → 忽略，不改变 pinned 状态
  - 否则正常判断：不在底部 → pinned = False；在底部 → pinned = True

## Tab Data 字段变更

TabData 新增字段，移除旧字段：

| 字段 | 变化 | 说明 |
|------|------|------|
| `_need_scroll` | **移除** | 由 `pinned_to_bottom` 替代 |
| `pinned_to_bottom` | **新增**，初始 True | 是否自动跟随到最新输出 |
| `output_buffer` | **新增**，初始 `[]` | `(color, text)` 元组列表 |
| `output_scroll` | 保留 | 供 pinned=False 时切回 tab 恢复位置 |

`_scroll_output_timer`（MainWindow 上）：改为永不停止的全局 timer，连接到新的 `_on_flush_timer`。

## 入口点清单（需逐一改造）

所有需要修改的调用点（当前代码中 `_need_scroll = True` + `_output_append` 的组合），共约 15 处，均在 `FlowController.on_compile_finished` / `on_run_finished`、`clear_and_start_compile`、`start_test_run`、`MainWindow._on_run_stdout_ready`、`_on_run_stderr_ready`、`OutputPanel.keyPressEvent`、以及若干 `scroll_requested.emit(tab)` 触发路径中。

改造规则：
- `_output_clear(tab.output_doc)` + `tab._need_scroll = True` → `tab.output_buffer.clear()` + `_output_clear(tab.output_doc)` + `tab.pinned_to_bottom = True`
- `_output_append(tab.output_doc, text, color)` → `tab.output_buffer.append((color, text))`
- `self.scroll_requested.emit(tab)` + 对应的 `_on_flow_scroll_requested` → 可移除，滚动由 timer tick 统一负责
- `tab._need_scroll = True` 的独立赋值（不伴随 clear/append）→ `tab.pinned_to_bottom = True`