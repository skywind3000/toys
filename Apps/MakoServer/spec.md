# MakoServer 技术规格

对应 [prd.md](prd.md)。实现为单文件 `makoserver.py`，本文档描述其内部结构、算法与全部行为决策。

## 0. 总览与决策记录

### 0.1 基本面

| 项 | 值 |
|----|----|
| 实现文件 | 单文件 `makoserver.py`（不得改名 `mako.py`，会遮蔽 `import mako`） |
| 直接依赖 | Flask、Mako 两个第三方包，其余仅标准库 |
| 版本约束 | `Flask<4` / `Mako<1.5`；开发/验证基准 Flask 2.2.x + Mako 1.4.x |
| 语法约束 | Python 3.8（禁 walrus、`str.removeprefix` 等 3.9+ 特性），兼容 Win7 打包 |
| 私有接口 | 自定义字节缓冲注入依赖 `mako.runtime` 内部协议；升级 Mako 小版本须回归验证。Flask 同理：上界 `<4` 允许 3.x，跨主版本相对开发基准 2.2 的行为差异（`get_data` / form 缓存时序、`redirect` 编码等实测锚点）同样须回归验证 |
| 运行形态 | ① 独立 dev server ② WSGI 入口（导出 `application`）③ CLI 渲染单个 .mako |
| 定位 | 本机/可信环境；安全检查以「可信环境下的健壮性」为准（Windows 路径陷阱），不做公网加固 |

### 0.2 PRD 待决点落定表

| # | 待决点 | 决策 |
|---|--------|------|
| 1 | 滑动超时重签触发条件 | 滑动模式：请求携带有效 session 即重签（无论脚本是否写过）；绝对模式：仅数据发生变化时重签，且时间戳继承原签发时刻 |
| 2 | CLI 下 include/inherit 基准目录 | 模板查找目录 = 被渲染脚本所在目录（HTTP 模式为 root） |
| 3 | `RESP.redirect()` 后是否终止渲染 | 不终止（对齐 PHP `header()`）；文档惯例建议其后 `return` |
| 4 | `_JSON` 解析失败行为 | 为 `None`，不报错；脚本可通过 `_BODY` 拿原文自行处理 |
| 5 | 静态文件 Content-Type 兜底 | 并入 #12（弃用 mimetypes，改内置扩展名白名单，白名单外一律 404） |
| 6 | 5xx 错误页内容 | 含完整 traceback（HTML 转义）+ 请求路径；traceback 同步写 error log |
| 7 | 配置相对路径基准 | 通则：三条查找规则命中的配置文件，其中所有相对路径（含 `root`）均以**配置文件所在目录**为基准 |
| 8 | `_SERVER` 的「请求路径」键名 | `PATH_INFO`（不引入 PHP/Apache 特有的 `REQUEST_URI`）——**后被 #16 / #17 修订**：`PATH_INFO` 收窄为尾挂语义（脚本路径并入 `SCRIPT_NAME`），`REQUEST_URI` 补入，以修订后为准 |
| 9 | `_REQUEST` 合并顺序 | GET 与 POST 合并（POST 覆盖同名 GET），不含 cookie——对齐现代 PHP `request_order="GP"` 默认 |
| 10 | `getlist` 可用范围 | `_GET` / `_POST` / `_REQUEST` 三者均支持（同一 PHPDict 实现） |
| 11 | CLI 下 `_SERVER` 内容 | 固定降级值 + `argv`，详见 6.4 |
| 12 | 静态文件类型判定 | 内置扩展名白名单表（弃用 mimetypes，注册表映射不可控）；白名单外一律 404（与不存在同响应，fail-closed） |
| 13 | WSGI 零配置 root | 配置缺失时回退 makoserver.py 所在目录（`__file__` 目录，与配置查找第 2 条同锚点），单文件拷进站点目录即部署 |
| 14 | 配置文件格式 | INI（`configparser` 标准库）：单节 `[makoserver]`、`#`/`;` 行注释、手写友好；`session_lifetime` 显式 int 转换；文件名 `makoserver.ini` / `settings.ini` |
| 15 | port / host 不进配置 | 仅 dev server 用得到（WSGI 监听由宿主决定、CLI 不读配置），属进程启动参数而非站点属性——纯命令行 `-p` / `--host`，schema 不设死键 |
| 16 | 尾挂 PATH_INFO（PHP AcceptPathInfo） | 路径不存在时逐级回溯**只找文件**：命中 `.mako` → 渲染 + 尾挂作 `_SERVER['PATH_INFO']` 传入；命中非 `.mako` 文件 → 404（静态不带尾挂）；**回溯碰到存在的目录 → 404**（Apache `mod_dir` 仅对显式目录请求生效，`/dir/x` 本就 404，不兜底——审核修正，初版「转 index 兜底」非 PHP 语义）；`SCRIPT_NAME` 同步改为脚本路径部分（PHP `$_SERVER` 分工） |
| 17 | REQUEST_URI 键；回溯耗尽不上溯 | 补入 `_SERVER`（PHP 同名键同语义：编码态原文，含挂载前缀与 query）——脚本获取原始 URL 的通用途径；回溯耗尽维持 404，**不上溯**到 root 的 index.mako（PHP 原生无全兜底语义，前端控制器用显式 `/index.mako/...` 尾挂表达） |
| 18 | 目录尾斜杠 301 | 请求映射到目录且 URL 末尾无 `/`（如 `/demo`）→ `301` 重定向补斜杠（`/demo/`，保留 query）——对齐 Apache `DirectorySlash`；否则页内相对链接会按 `/` 解析全部错链 |
| 19 | session cookie 属性 | 固定 `Path=/; HttpOnly; SameSite=Lax`；**不设 Max-Age / Expires**（浏览器会话 cookie，对齐 PHP 默认 `session.cookie_lifetime=0`）——过期控制由服务端时间戳判定承担（cookie 即使被浏览器持久保留，过期后校验失败按无 session 处理） |
| 20 | OPTIONS 交给脚本 | 路由注册 `provide_automatic_options=False`——否则 Flask 默认自动应答 OPTIONS（200 + Allow 头），view 永不被调用、`REQUEST_METHOD='OPTIONS'` 传不到脚本；关闭后 OPTIONS 到达模板分支照常渲染（Apache + mod_php 同为执行脚本） |
| 21 | 模板文件访问基准 | **不 chdir**（cwd 是进程级状态，dev server / WSGI 多线程共享进程，并发请求互相切目录 = 数据竞争；PHP 敢切靠的是单请求同步 worker 模型）；补 `_SERVER['SCRIPT_FILENAME']` / `['DOCUMENT_ROOT']` / `['SCRIPT_DIRNAME']`（前两键 PHP `$_SERVER` 标配，第三键为便利键 = dirname，语义同 PHP `__DIR__`）；模板定位文件用三键拼绝对路径，裸相对路径基准为进程 cwd、行为不保证 |
| 22 | 启动校验（root 与日志路径） | dev / WSGI 启动时校验最终 root 存在且为目录，否则**报错退出**（stderr 带 root 路径与来源）——静默带病运行会 realpath 照算、全站 404，极具迷惑性；已配置的 `error_log` / `access_log` 同受启动校验（父目录存在且可写，append 模式探测打开），失败同样报错退出——否则延迟到装配 FileHandler 或首条日志才炸，WSGI 下 stderr 无人看；CLI 无 root / 日志概念不校验 |
| 23 | PathInfoNormMiddleware（实现期修正） | 实测 Werkzeug 2.2 两处行为与 spec 初版假设不符，用前置 middleware 显式兑现：① merge_slashes 仅在首次匹配失败时才触发归一 308，而本站 catch-all `<path:>` 路由首次必命中，归一永不发生——由 middleware 对含 `//` 的 PATH_INFO 发 308 归并（保留前缀与 query）；② 挂载根无斜杠（空 PATH_INFO）时 matcher 自行 308 丢 query、请求到不了视图——middleware 把空 PATH_INFO 归一成 `'/'`、原始值记 `MAKO_RAW_PATH_INFO`，由视图按 3.3 发 301（保留 query）。详见 3.1 |
| 24 | CLI stdin 渲染标记用 `-` 非 `--` | `python makoserver.py - [args...]` 从 stdin 读模板源并渲染。选**单减号**：POSIX Utility Syntax Guideline 13 规定操作数 `-` 即 stdin/stdout，cat / grep / sed / tar / curl / gcc / python / jq / pandoc / `kubectl apply -f -` / `docker build -` 全线同约定，PHP CLI 读 stdin 时 `$argv[0]` 亦为 `'-'`（本项目对标 PHP，天然契合）；`--` 被否决——它是 getopt/argparse 的**选项终止符**（POSIX Guideline 10），argparse 会吞掉首个 `--`、根本到不了位置参数，语义冲突且技术不可行。细则见 10.3 |

## 1. 单文件内部布局

makoserver.py 内部代码区块（自上而下）：

| 区块 | 内容 |
|------|------|
| 头部 | 文件头注释、`__version__`、imports |
| 常量 | 默认配置、扩展名、cookie 名等 |
| 配置 | `load_config()` / 配置查找与合并 |
| 路径 | `resolve_path()` 规范化与防穿透 |
| 中间件 | `PathInfoNormMiddleware`（斜杠归一/308）/ `AccessLogMiddleware` |
| 模板 | `TemplateStore`（自定义模板集合 + mtime 缓存） |
| 缓冲 | `BytesBuffer` |
| Bridge | `PHPDict` / `RespObject` / `make_bridge()` |
| Session | `SessionCodec`（签名/校验/密钥派生） |
| 请求 | `create_app()` / catch-all 视图 / 响应组装 |
| 日志 | error/access log 装配 |
| 入口 | `application` 导出、`main()`、`if __name__ == '__main__'` |

## 2. 配置

### 2.1 配置 schema（`[makoserver]` 节内扁平键）

| 键 | 类型 | 默认 | 说明 |
|----|------|------|------|
| `root` | str | 见 2.4 回退链 | 文档根目录，支持相对路径（见 2.3）；三种模式均有回退，无需必填 |
| `secret` | str | 空 → 派生 | session 签名密钥（UTF-8 编码） |
| `session_lifetime` | int | 3600 | session 有效期（秒） |
| `session_mode` | str | `sliding` | `sliding` / `absolute` |
| `session_cookie` | str | `MAKO_SESSION` | session cookie 名 |
| `access_log` | str | 空（不落盘） | access log 文件路径 |
| `error_log` | str | 空（stderr） | error log 文件路径 |

未知键忽略不报错（向前兼容）；若未知键与已知键拼写相近（如 `session_lifetim`），向 stderr 打一条 warning（非阻塞，防拼写错被静默吞掉回落默认值）——「相近」**钉死为 `difflib.get_close_matches(name, 已知键列表, n=1, cutoff=0.8)` 非空即 warn**（实现唯一、无裁量空间；无相近匹配的未知键静默忽略）。配置文件格式为 **INI**（`configparser`，标准库）：单节 `[makoserver]`，键值均为字符串，支持 `#` / `;` 行注释；**构造 `ConfigParser(interpolation=None)`**——默认的 `BasicInterpolation` 会对 `%` 做插值展开，含 `%` 的值（如手写 secret）直接抛 `InterpolationSyntaxError`，必须显式关闭；`session_lifetime` 读出后显式 `int()` 转换。值按 configparser 语义 strip 首尾空白（secret 勿带首尾空格）。配置非法（缺 `[makoserver]` 节、解析错、int 转换失败）按用途分级处理——WSGI/serve 启动时直接报错退出（带文件路径，configparser 异常自带行号）；仅 CLI 渲染模式不读配置、不受影响。

`port` / `host` **不进配置文件**（决策 #15）：它们只对 dev server 一个模式生效（WSGI 监听由宿主决定、CLI 不读配置），属进程启动参数而非站点属性，纯命令行 `-p` / `--host` 提供（见 10.1）。

### 2.2 查找顺序（WSGI / serve 模式，命中即用、不逐层合并）

1. dev server 命令行 `--conf FILE`（仅 `__main__` 模式存在；CLI 渲染模式下该参数被忽略）；
2. 环境变量 `MAKOSERVER_CONF` 指定的路径（文件不存在 = 未命中，继续下寻）；
3. 入口脚本（`makoserver.py`）同目录下 `makoserver.ini`；
4. `~/.config/makoserver/settings.ini`。

serve 模式下第 2 条的「入口脚本同目录」即 makoserver.py 所在目录。

### 2.3 相对路径通则

配置文件中所有相对路径（`root`、`access_log`、`error_log`）均以**该配置文件所在目录**为基准 `os.path.join(conf_dir, value)` 后再取 abspath。命令行传入的路径不做此变换（按 shell 语义走 cwd）。

### 2.4 优先级与 root 回退链

- CLI 渲染：不读配置，无 root 概念（模板基准 = 脚本所在目录，见 4.3）；
- dev server：`-r/--root` > 配置文件 `root` > **当前工作目录**（对齐 `php -S` 默认 docroot = cwd 的行为；默认 host=127.0.0.1 仅监听回环，暴露面可控）；
- **root 存在性启动校验**（决策 #22）：dev / WSGI 启动时校验最终确定的 root 存在且为目录（`os.path.isdir`）——不存在或非目录 → **报错退出**（stderr 带 root 路径与来源，如 `root=/nonexistent (from config)`），不静默带病运行（否则 realpath 照算、全站 404，极具迷惑性）；CLI 无 root 概念不校验。回退链默认值（cwd）同样过此校验，路径统一。已配置的 `error_log` / `access_log` 同受启动校验（父目录存在且可写——探测方式：以 append 模式试开一次即关；失败报错退出，同「报错退出优于带病运行」哲学，否则延迟到装配 FileHandler 或首条日志才炸、WSGI 下 stderr 无人看）；
- WSGI：配置文件 `root` > **makoserver.py 所在目录**（`__file__` 取 abspath 后 dirname；不回退 cwd——WSGI 进程的工作目录不可靠，如 mod_wsgi 常为 `/`）。零配置即拷即用：单文件放进站点目录就能跑；
- 其余键（`secret` / `session_*` / `access_log` / `error_log`）：仅配置文件 > 内置默认（无命令行对应参数）；
- `port` / `host` 为**纯命令行参数**（默认 5000 / `127.0.0.1`），不进配置文件——作用域分界：进程启动参数走命令行，站点与部署属性走配置文件；WSGI 模式监听由宿主决定，配置该键本就无效。

## 3. 请求处理流水线

### 3.1 路由

Flask app 仅注册两条路由（catch-all，禁用 static 路由）：

- `/` → `view('')`
- `/<path:url_path>` → `view(url_path)`

两条路由 methods 同集放开全谓词（GET / HEAD / POST / PUT / DELETE / PATCH / OPTIONS）且 **`provide_automatic_options=False`**——Flask 默认对 OPTIONS 自动应答（200 + Allow 头），view 永不被调用、`REQUEST_METHOD='OPTIONS'` 传不到脚本（Apache + mod_php 对 OPTIONS 是执行脚本，关闭后行为对齐）；`POST /` 等根路径请求同样到达模板，不出现 Flask 默认 405。HEAD 由 Werkzeug 自动处理 body 剥离。

WSGI 挂载前缀（SCRIPT_NAME）由 Flask/Werkzeug 自动剥除，view 收到的即 URL 尾部。全谓词的作用域：POST / PUT / DELETE / PATCH 到达**模板分支**时正常渲染，`_SERVER['REQUEST_METHOD']` 如实传递（REST 风格 API 由 .mako 脚本自行处理）；**静态分支不接受非 GET/HEAD**（405，见 3.5）。

**Werkzeug 前置行为声明与 PathInfoNormMiddleware**：spec 初版假设 `merge_slashes=True` 由 Werkzeug 在路由层自动发 **308** 归并重定向——**实测不成立**：Werkzeug 2.2 的 merge_slashes 仅在**首次匹配失败**时才重试归并（matcher 源码 `if self.merge_slashes and rv is None`），而本站 catch-all `<path:url_path>` 路由首次即可匹配任何带斜杠的路径（`//a` 直接命中、url_path 含双斜杠），归一重定向永不触发、view 直接拿到 `//a` 形态的路径（缓存键与 `REQUEST_URI` 呈现不一致）。故本框架用前置 **PathInfoNormMiddleware**（包裹于 `app.wsgi_app` 最内层、路由之前）显式兑现两件事：① `PATH_INFO` 含连续斜杠 → **308** 归并重定向到合并后路径（`SCRIPT_NAME` 前缀 + query 保留），对齐 spec 声明的行为；② 空/无前导斜杠的 `PATH_INFO` 归一成 `'/'`——Werkzeug 2.2 的 matcher 对空 `PATH_INFO`（挂载根无斜杠请求）会自行 308 到 `script_root + '/'` 且**丢失 query**、请求到不了视图，归一后由视图按 3.3 规则发 301（保留 query）；归一前的原始值记入 `MAKO_RAW_PATH_INFO` 供视图判定。故「全部路径逻辑在 resolve_path 收口」指 **middleware 归一之后**的路径。

**Location 的编码收口（解码舞步）**：凡以 **environ 原值**（`SCRIPT_NAME` / `PATH_INFO`）拼 Location 的分支——middleware 的 308 归并、3.3 的挂载根 301——拼好后必须先做 PEP 3333 解码舞步 `value.encode('latin-1').decode('utf-8', 'replace')` 还原为 UTF-8 文本，再交 `redirect()`。environ 字符串是 latin-1 承载形态（PEP 3333，UTF-8 原始字节逐字节映射），直接交 `redirect()` 会被 iri_to_uri 按 UTF-8 重新百分号编码，非 ASCII 路径的 Location 即成乱码（`%C3%A4%C2%B8%C2%AD` 而非 `%E4%B8%AD`），浏览器跟随后恒 404；经 `request.path` / `request.script_root` 取值的分支（3.3 普通目录 301）Werkzeug 内部已做同样还原，无需重复。还原对纯 ASCII 路径是恒等变换；值本身非 latin-1 可表示（测试直接注入真实字符串的场景）时原样返回。

### 3.2 路径解析算法（resolve_path）

输入：URL 尾部 `url_path`（已 URL 解码）。步骤：

1. **POSIX 规范化**：`rel = posixpath.normpath('/' + url_path).lstrip('/')`，得到如 `demo/demo.mako`。前置 `/` 使 normpath 将越界 `..` **钳制回根**（`/../../etc` → `/etc`，rel 永不含头部 `..`）——注意这是钳制而非拒绝，逃逸防护实际由第 4 步 commonpath 收口承担（实测 normpath 不会让 `..` 残留，实现勿依赖本步做拒绝）。本步同时记录 `trailing = url_path.endswith('/')`（原始请求是否带尾斜杠——normpath 会吃掉它，后端分支判定需要，见 3.3 静态分支与 6.4 PATH_INFO 形态）；
2. **空字节拒绝**（全平台）：URL 解码后 `'\x00' in rel` → 拒绝（404）——`\x00` 进入 `os.stat` / `open` 会抛 `ValueError`（非 OSError），不拦会变 500；
3. **NTFS 特判**（`os.name == 'nt'` 下）：
   - `rel` 含 `:`（盘符 / `::$DATA` 数据流）→ 拒绝；
   - Windows 会剥掉路径段末尾的 `.` 与空格，此处对 `rel` 整体 `rstrip(' .')`（等效作用于末段 basename）后再做后续判断——防 `demo.mako.` 绕过；中间段的点/空格交由文件系统自身语义，不额外模拟。**特判仅限 Windows 系、有意跨平台分裂**：Linux 文件系统无剥尾点语义，`demo.mako.` 是字面文件名、通常不存在 → 走不存在分支 404（回溯不救——父段即 root 目录），天然 fail-closed，无需也不模拟剥点——与 lower() 归一的全平台一致是两条哲学：前者靠平台语义天然兜底即可，后者平台大小写语义互斥（NTFS 不敏感 / ext4 敏感）必须显式归一；
4. **拼合与真实路径收口**：`full = os.path.join(root, rel)`；`real = os.path.realpath(full)`、`root_real = os.path.realpath(root)`；`os.path.commonpath([real, root_real])` **包 try/except ValueError → 拒绝（404）**——commonpath 对两路径**不同盘符 / UNC / 设备命名空间**时不返回不等、直接抛 `ValueError("Paths don't have the same drive")`（文档化行为），未捕获会变 500。两类同族陷阱由此一条兜底吃掉：① root 内 junction / 符号链接指向另一盘符（realpath 忠实解析出他盘路径，本指望 commonpath 拒绝，跨盘时它自己先炸）；② DOS 设备名请求（`/nul`、`/con.txt`、`/aux`、`/com1.css`——Windows 路径归一可解析成设备路径形态）。异常路径与不等路径同走 404（3.2 step6 同体原则）。`commonpath != root_real`（逃出 root）→ 拒绝。`real == root_real`（请求 `/` 本身）**放行**，进入 3.3 目录分支走 index 兜底，不得拒绝。realpath 一并覆盖符号链接 / junction 指出 root 的场景；
5. **敏感路径屏蔽**：`real` 命中运行时屏蔽集合（实际加载的配置文件路径、已配置的 access_log / error_log 路径，见 3.5 规则 4）→ 404。本步对**初始 real** 先行比对（快速路径，拦住直接请求）；由于尾挂回溯 / index 兜底会解析出**与初始 real 不同的目标文件**，屏蔽比对的总则是「**最终解析到的目标文件在打开 / 渲染前必须过屏蔽集合**」（回溯命中父文件、兜底命中 index.* 时各自比对，见 3.3）——静态分支（回吐 secret / 日志）与模板分支（把日志 / 配置**当模板编译执行**，`error_log` 起名 `log.mako` 即成 RCE）一体防护；
6. **拒绝即 404**：与「文件不存在」同响应（见 3.6），不区分。

realpath 结果缓存每请求重算（不做跨请求缓存，量小无所谓，避免缓存失效漏洞）。

### 3.3 分支判定（在规范化后的 basename 上）

对步骤 4 的 `real`：`name = os.path.basename(real).lower()`

- `name.endswith('.mako')` **且 `os.path.isfile(real)`** → **模板分支**（见 3.4）。`endswith` 不带 isfile 的旧写法会把**名为 `foo.mako` 的目录**送进模板分支，`open()` 抛 `IsADirectoryError` → 500，故加 isfile 收口。请求 `/demo.mako/`（`trailing`、无尾挂）→ 照常渲染，`PATH_INFO = '/'`（尾斜杠本身算尾挂，对齐 Apache/mod_php 语义，见 6.4）——与静态侧同理，**仅初始 real 直接命中时适用**，index 兜底命中的 `index.mako` 豁免（`PATH_INFO = ''`，见 6.4 表）；
- `name.endswith('.mako')` 但**不是文件**（目录或不存在）→ 404（不进回溯——`/nonexist.mako/x` 回溯到 `nonexist.mako` 亦非文件、再到 root 是目录，结果同为 404，规则闭合。其中名为 `foo.mako` 的**目录**有意不做目录处理、不走 301 / index 兜底：目录名以 `.mako` 结尾系病态命名，若按目录处理则兜底 `foo.mako/index.*` 命中后 `SCRIPT_NAME` 以 `.mako` 结尾、与「.mako 后缀 = 可执行模板文件」的直觉契约冲突，简单一致的选择是一律 404）；
- `os.path.isfile(real)` → **静态分支**（.mako 已被上面拦截，不会以静态形式吐出源码。**原始请求带尾斜杠（`trailing`）→ 404**：文件非目录，对齐 Apache「文件路径带尾斜杠 404」，与「静态不带尾挂」（`style.css/hello` → 404）精神一致——不查则 normpath 吃掉斜杠后照常 200，与尾挂 404 行为分裂。**trailing 规则仅作用于「初始 real 直接命中文件」的场景**：index 兜底目标（`/dir/` → `dir/index.html`）经目录分支「按对应分支处理」进入本分支，**豁免 trailing 判定**——目录请求的 trailing 恒为真，不豁免则所有落到 index.html / index.htm 的兜底全部 404，与 3.5 规则 3、test_http 的 405 预期直接冲突）；
- `os.path.isdir(real)` → **目录请求**，按序两查：
  - **挂载根无斜杠**（前置边角）：**原始** `PATH_INFO` 为空（`''`）且 `SCRIPT_NAME` 非空（挂载根如 `/app1`）→ **301** 到 `SCRIPT_NAME + '/'`（+ query；`SCRIPT_NAME` 是 environ 原值，拼 Location 前须过 3.1 的解码舞步还原）。判定用 environ 的 `MAKO_RAW_PATH_INFO`（PathInfoNormMiddleware 归一前记录的原始值，见 3.1）——中间件已把空 `PATH_INFO` 归一成 `'/'` 使请求能到达视图，直接看 environ `PATH_INFO` 恒非空、判定失灵。必须本步先行拦截：Werkzeug 的 `request.path` 会把空 `PATH_INFO` **归一成 `'/'`**（源码 `raw_path.lstrip("/") and "/" + ... or "/"`），`endswith('/')` 判定失灵、静默走 index 兜底 → 页面挂在无斜杠 URL `/app1` 下，页内相对链接全按 `/` 解析错链——正是 301 补斜杠（决策 #18）要防的事故；
  - 其余：看 URL 尾部有无 `/`（`request.path.endswith('/')`；`request.path` 为解码态，`%2F` 会被解码成 `/` 而直接按带斜杠处理——边角行为，声明接受）——无（如 `/demo`）→ **301** 重定向，`Location = request.script_root + request.path + '/'`（QUERY_STRING 非空时才追加 `?query`，空 query 不挂裸 `?`）。**必须拼 `script_root`**：Werkzeug `Request.path` 只派生自 `PATH_INFO`、**不含**挂载前缀（前缀在 `request.script_root`，即 environ `SCRIPT_NAME`）——曾误判「request.path 天然含前缀」，系 test client 默认 `SCRIPT_NAME=''`、全路径进了 `PATH_INFO` 所致，测不出两者分离；真实挂载（`WSGIScriptAlias /app1`）下只拼 path 会得到 `/demo/` 而非 `/app1/demo/`、301 跳出应用。`request.path` 是解码态，但 **Werkzeug `redirect()` 会对 Location 自动重新百分号编码**（中文目录名实测无碍）——实现者勿自行 `quote`，防双重编码。有尾斜杠（如 `/demo/`、`/`）→ **index 兜底**：依次试 `<real>/index.mako`、`<real>/index.html`、`<real>/index.htm`（存在即按对应分支处理；**命中文件先 `os.path.realpath` 归一再过屏蔽集合比对**——`index.*` 本身可能是指向被屏蔽文件的符号链接，未解析直接比对即旁路，命中 → 404），全不中 → 404；
- `real` 不存在 → **尾挂回溯**（PATH_INFO 机制，对齐 PHP `AcceptPathInfo`）：**在 `real`（realpath 产物）链上**逐级去掉末段向上，**只找文件**（不得在未解析链接的 `full` / `rel` 拼合路径上判定——注意两条链上 `isfile` 的存在性判定结果并无差异，**必须用 real 链的理由是屏蔽比对要拿真实路径**：realpath 已把符号链接解析掉，`link.mako` → `log.mako` 的软链在 real 链上天然是 `root/log.mako`、与屏蔽集合（存 realpath）正确比对；full 链上参与比对的 `root/link.mako` 不在集合而其真实目标在，比对放行、`open()` 时才被 OS 重定向到被屏蔽文件，旁路即成）——
  - 父路径是**存在的文件**且 `.mako` → **先过屏蔽集合比对**（real 链上的路径天然是真实路径，直接比对；防 `/log.mako/hello` 经回溯绕过初始 real 比对、旁路执行被屏蔽日志），通过则渲染该文件，被去掉的部分（含前导 `/`）作为 `_SERVER['PATH_INFO']` 传入——原始请求带尾斜杠时以 `trailing` 补回（`/index.mako/hello` → `PATH_INFO = '/hello'`；`/index.mako/hello/` → `PATH_INFO = '/hello/'`，对齐 Apache/mod_php——不补则 normpath 吃掉尾斜杠、原文丢失）；
  - 父路径是存在的文件但**非 .mako** → 404（静态文件不带尾挂，PHP 同语义，`style.css/hello` → 404）；
  - 父路径是**存在的目录** → 404（**不兜底**：Apache `mod_dir` 仅对显式目录请求生效，`/dir/x`（x 不存在）本就是 404）；
  - 父路径仍不存在 → 继续向上；回溯链耗尽（含到达 root）→ 404。root 是目录、按目录规则同样归 404，两条终止条件自然闭合，无「永不 404」漏洞。

  原第三分支「不存在 → index 兜底」系死逻辑（路径不存在则其下 index.* 更不可能存在），由回溯取代。尾挂仅为传入脚本的字符串（URL 解码、规范化后的残余），不参与文件查找，无需额外防穿透（`..` 已在 3.2 step1 被钳制）。

大小写归一用显式 `lower()` 而非 `os.path.normcase`——后者仅 Windows 转小写，Linux / 容器下恒等，会造成 `demo.MAKO` 在 Windows 走模板分支、在 Linux 走静态分支 404 的跨平台分裂；显式 `lower()` 保证「扩展名判断大小写不敏感」在所有平台行为一致（Linux 下磁盘真有 `demo.MAKO` 文件时同样渲染）。

### 3.4 模板分支

1. `store.get(脚本相对路径)`：mtime 检查命中缓存或重新加载编译（见 4）。**脚本相对路径** = 普通请求时即 3.2 的 `rel`；尾挂回溯 / index 兜底场景为**实际渲染目标**（回溯命中的父文件、`<real>/index.mako`）相对 root 的路径——不得传原始 `rel`（否则缓存键挂错、加载的文件也不对，见 3.3）；
2. 主模板文件不存在已在 3.3 判定层拦截（404，不进本分支）；本条仅作防御性兜底；
3. 编译/渲染任何异常（含 include/inherit 目标缺失）→ 500（见 9.1）；
4. 渲染成功 → 按 8 组装响应。

### 3.5 静态分支（扩展名白名单）

判定在规范化后的 basename 上（3.3 已 lower 归一，各平台大小写变体统一）。内置白名单表（模块级 dict 常量，**弃用 mimetypes 模块**——其映射来自系统注册表，装软件即变，不可控）：

| 类别 | 扩展名 | Content-Type |
|------|--------|--------------|
| 网页 | `.html` / `.htm` | `text/html; charset=utf-8` |
| 文本 | `.txt` | `text/plain; charset=utf-8` |
| 样式 | `.css` | `text/css; charset=utf-8` |
| 脚本 | `.js` | `application/javascript` |
| 数据 | `.json` | `application/json`（无 charset，与 RESP.json 一致，RFC 8259） |
| 图片 | `.png` / `.jpg` `.jpeg` / `.gif` / `.svg` / `.ico` / `.webp` | `image/png` / `image/jpeg` / `image/gif` / `image/svg+xml` / `image/x-icon` / `image/webp` |
| 文档 | `.pdf` | `application/pdf` |
| 压缩 | `.zip` / `.rar` / `.7z` / `.tar` / `.gz` `.tgz` / `.xz` | `application/zip` / `application/vnd.rar` / `application/x-7z-compressed` / `application/x-tar` / `application/gzip` / `application/x-xz` |

规则：

1. 扩展名在白名单 → 按表设 Content-Type，读文件字节原样为 body（不转码；二进制类无 charset，文本类声明 utf-8——与 PRD「文本输出统一 UTF-8」契约对齐）；
2. **白名单外一律 404**（`.py` / `.pyw` / `.pyo` / `.pyc` / `.php` / `.ini` / `.bak` / `.db` / `.log` / 无扩展名 / ...），与「不存在」同响应体（3.6，防探测原则）——fail-closed：源码、备份、数据库等杂物默认不可下载（makoserver.py 自身即被此条挡住）；
3. **谓词限制**：静态分支仅接受 GET / HEAD；其它谓词（POST / PUT / DELETE / PATCH）命中**白名单内且存在**的文件 → `405 Method Not Allowed`（附 `Allow: GET, HEAD`）。判定顺序在白名单之后——白名单外路径无论谓词一律 404（保持与「不存在」同体，不因 405 泄露文件存在性）。index 兜底落到 `index.html` / `index.htm` 时同受此限（`index.mako` 属模板分支，照常全谓词渲染）；
4. **运行时敏感路径屏蔽**：比对对象是**最终解析到的目标文件路径**——初始 real（3.2 step5 先行比对，快速路径）、尾挂回溯命中的父文件（real 链上操作、天然真实路径，见 3.3）、index 兜底命中的 index.*（**realpath 归一后比对**，见 3.3），打开 / 渲染前收口，静态与模板两分支一体防护；比对双方均以 realpath 归一（集合存 realpath，比对前对目标也 realpath），防 root 内指向被屏蔽文件的符号链接旁路。屏蔽集合 =「实际加载的配置文件路径」+「已配置的 error_log / access_log 路径」（启动时构建）。`.ini` 本就不在静态白名单（`makoserver.ini` / `settings.ini` 天然 404），但 `MAKOSERVER_CONF` 可指向任意文件名（含 `secret.json` 等白名单类型），日志路径亦可起名 `access.txt` / **`log.mako`**——后者若不屏蔽，模板分支会把日志**当模板编译执行**（内容变可执行代码，兼泄露与 RCE；仅比对初始 real 挡不住 `/log.mako/hello` 的回溯旁路与 `/sub/` 的兜底旁路）。include / inherit 系模板作者自身行为、不经请求路由，不在屏蔽范围（与 PHP `include` 同理，信任边界内）；
5. 读文件失败（权限/占用）→ 500；
6. `If-Modified-Since` / 304 一期不做，一律 200 全量返回（本机场景带宽免费）。

### 3.6 404 / 405 响应

- 404：`text/plain; charset=utf-8`，body `404 Not Found\n`；
- 405：`text/plain; charset=utf-8`，body `405 Method Not Allowed\n`，附 `Allow: GET, HEAD`（静态分支谓词限制，3.5 规则 3）——与 404 同极简风格，无 HTML。

## 4. 模板加载（TemplateStore）

自定义模板集合（不使用 `mako.lookup.TemplateLookup`，因其文件读取路径无 rstrip 钩子），实现 `get_template(uri)` 与 `adjust_uri(uri, relativeto)` 两协议，供 `Template(text=..., lookup=store)` 的 include/inherit 解析。

### 4.1 加载与编译

1. `path = os.path.join(base_dir, *uri.split('/'))`；
2. 读源码：`open(path, 'r', encoding='utf-8-sig')`（兼容 Windows 记事本 BOM）；
3. **尾部空白截断**：`text = text.rstrip()`（PRD 契约：文件末尾空白永远不属于输出内容；rstrip 默认字符集含空格/tab/\r/\n/\f\v，覆盖所有加载路径——主模板、include、inherit、CLI 脚本一致）；
4. `Template(text=text, lookup=self, input_encoding='utf-8')`，纯内存编译（无 `module_directory`）。

### 4.2 mtime 缓存与 reload

缓存表 `{uri: (path, mtime_ns, size, template)}`。每次 `get_template` 时 `os.stat` 比对 mtime_ns 或 size 变化即重编译——满足「请求时检查 mtime」的 PRD 要求，不引入 watchdog。编译动作置于 `threading.Lock` 内（dev server 多线程并发首访）。

### 4.3 include/inherit 相对路径基准

| 模式 | `base_dir` |
|------|-----------|
| HTTP（serve / WSGI） | root |
| CLI 渲染 | 被渲染脚本所在目录（stdin 渲染时为 cwd，见 10.3） |

`adjust_uri`：`posixpath.join(posixpath.dirname(filenm), uri)` 归一化后返回，Mako 用其回调 `get_template`。

## 5. 字节缓冲（BytesBuffer）

### 5.1 协议

| 方法 | 行为 |
|------|------|
| `write(x)` | `str` → `x.encode('utf-8')` 追加；`bytes/bytearray/memoryview` → `bytes(x)` 追加；其它类型不允许进入（由 echo 层先行转换） |
| `getvalue()` | `b''.join(chunks)` → bytes |

内部为 chunk 列表（避免 bytes 不可变的反复拷贝）。

### 5.2 与 Mako 的集成

渲染时构造 `mako.runtime.Context`，其 buffer 换为本实现（实现 Mako buffer 的 `write`/`getvalue` 协议）。Mako 生成代码对模板文本块调用 `context.write(str)`——由 `write(str)` 分支即时编码；bridge 的 `echo` 直接向同一 buffer 写（bytes 分支直通）。**该集成面依赖 `mako.runtime` 内部协议（Context/Buffer 构造），属 PRD 已声明的私有接口依赖，Mako 升级须回归验证。**

### 5.3 异常丢弃

渲染抛异常时不使用 partial buffer，直接进入 500 流程。

## 6. Bridge

### 6.1 注入机制

`template.render(context, **bridge_names)` 或经 5.2 的 Context 构造注入。注入名固定为下表 11 个，未注入名在模板中引用时按 Mako 默认 NameError 报 500。

**构造顺序（必须遵守）**：先 `_BODY = request.get_data(cache=True)`，再构造 `_GET` / `_POST`（读 `request.args` / `request.form`）。顺序颠倒（先 form 后 get_data）会让 body 读到 `b''`——Werkzeug 的表单解析直接消费底层流，`get_data` 晚于 form 则无流可读（Flask 2.2 实测）；`get_data(cache=True)` 先行缓存后，form 解析从缓存回填、两者兼得。

| 注入名 | 类型 | 构造 |
|--------|------|------|
| `echo` | function | 见 6.2 |
| `escape` | function | 见 6.2（HTML 转义，返回字符串） |
| `_REQUEST` | PHPDict | GET+POST 合并 |
| `_BODY` | bytes | `request.get_data(cache=True)`（**最先构造**，见上构造顺序） |
| `_GET` | PHPDict | `request.args` |
| `_POST` | PHPDict | `request.form` |
| `_SERVER` | dict | 见 6.4 |
| `_JSON` | dict/None | 见 6.5 |
| `_COOKIE` | dict | `request.cookies` 普通 dict |
| `_SESSION` | dict | 见 7 |
| `RESP` | RespObject | 见 6.6 |

（`RESP.write` 是 RespObject 属性 = `echo` 同一函数对象；`RESP.escape` 同理 = `escape` 同一函数对象。）

### 6.2 echo(*args) / escape(value)

**echo**：逐参数顺序写入 buffer：`None` → 跳过（空串，对齐 PHP `echo null`）；`str` → `buffer.write(str)`（UTF-8 即时编码）；`bytes/bytearray/memoryview` → `buffer.write(bytes(...))`；其它 → `buffer.write(str(x))`。多参数按序全部输出后返回（无返回值）。

**escape**：对标 PHP `htmlspecialchars` —— 先 `str(value)`（整数 / 浮点 / None / 任意对象先字符串化），再 `html.escape(..., quote=True)` 转义 `& < > " '`，**返回转义后的字符串**；`str()` 失败返回 `'(unprintable)'`。纯转换函数：不写 buffer、不碰响应，故不受 CLI 响应控制 no-op 规则影响，两模式行为一致；`RESP.escape` 为同一函数对象（规范名兜底）。

### 6.3 PHPDict

`dict` 子类。构造自 Flask MultiDict：**单值 = 同名参数最后一次出现**（对齐 PHP），`getlist(name)` 返回全部出现的列表（无则 `[]`）。`_REQUEST` 合并：先放 GET 全部，再放 POST（后者覆盖同名单值）；`getlist` 返回 GET+POST 全部同名值（GET 在前）。

### 6.4 _SERVER 键集

HTTP 模式（自 WSGI environ 透传 + 提炼）：

`REQUEST_METHOD`、`QUERY_STRING`、`CONTENT_TYPE`、`CONTENT_LENGTH`、`REMOTE_ADDR`、`SERVER_NAME`、`SERVER_PORT`、`REQUEST_SCHEME`（自 `wsgi.url_scheme`），以及全部 `HTTP_*` 头（environ 原名透传）。

`REQUEST_URI` = 原始请求 URI（**编码态原文**，含挂载前缀与 query，如 `'/app1/register/hello?x=1'`；无 query 时无 `?`）。WSGI environ 无此标准键（CGI/FPM 才有），取值三级：`environ['REQUEST_URI']`（mod_wsgi / uWSGI 原生提供，但无 `RAW_URI`）> `environ['RAW_URI']`（Werkzeug 注入）> 拼接兜底 `environ 的 SCRIPT_NAME + PATH_INFO + query`（即覆写构造**前**的 environ 原值；「原始」易误读为编码态原文，实为 PEP 3333 解码态）——兜底产出为**解码态近似值**（PEP 3333 的 environ `PATH_INFO` 已解码，`%2F`→`/`、`%41`→`A` 等无法还原原文），仅当前两级均缺失的宿主上使用，明示近似。用途：脚本获取原始请求 URL 的通用途径——编码态原文不受解码 / 规范化影响，query 一并可得（WordPress permalink、CodeIgniter 的 REQUEST_URI 模式均依赖同名键做路由）。CLI 模式不设此键（PHP CLI 亦无）。

`SCRIPT_NAME` / `PATH_INFO` 按分支判定结果**覆写构造**（PHP `$_SERVER` 语义，非 environ 原样透传——脚本路径永远在 `SCRIPT_NAME`，尾挂在 `PATH_INFO`）：

| 场景 | SCRIPT_NAME | PATH_INFO |
|------|-------------|-----------|
| 普通请求（`/demo.mako`，无尾挂） | 挂载前缀 + `/demo.mako` | `''` |
| 尾挂请求（`/index.mako/hello`） | 挂载前缀 + `/index.mako` | `'/hello'` |
| index 兜底渲染（`/dir/` → `dir/index.mako`） | 挂载前缀 + `/dir/` | `''` |

（挂载前缀即 environ 原始 SCRIPT_NAME，如 `/app1`，无挂载时为空串。`/demo.mako/`（尾斜杠、无尾挂）属普通请求形态但 `PATH_INFO = '/'` 而非空串——尾斜杠本身算尾挂，对齐 Apache/mod_php，见 3.3。）

`SCRIPT_FILENAME` / `DOCUMENT_ROOT` / `SCRIPT_DIRNAME`（决策 #21，模板定位文件的正路）：

| 键 | 值 |
|----|----|
| `SCRIPT_FILENAME` | 最终渲染目标的**绝对路径**（PHP 同名键；跟随实际渲染的文件——含尾挂回溯命中的父文件、index 兜底命中的 index.*，而非初始请求路径） |
| `DOCUMENT_ROOT` | root 的绝对路径（realpath 归一） |
| `SCRIPT_DIRNAME` | `os.path.dirname(SCRIPT_FILENAME)`（便利键，PHP 无同名超全局，语义同其 `__DIR__` 魔法常量） |

**模板内文件访问契约**：模板里 `open()` 等相对路径的基准是**服务进程 cwd**（dev server = 启动时 shell 目录、WSGI = 宿主 cwd），随启动方式漂移且多线程共享，**勿依赖**；定位文件用 `os.path.join(_SERVER['SCRIPT_DIRNAME'], ...)`（自身目录）或 `_SERVER['DOCUMENT_ROOT']`（站点根）拼绝对路径。PHP web「cwd = 脚本目录」的行为因线程安全不可 chdir，改以显式拼路径等价兑现。

三键（连同整个 `_SERVER`）**仅存在于模板渲染上下文**——静态分支、301、404 等无模板执行的场景不构造 `_SERVER`（PHP 的 `$_SERVER` 亦只存在于其脚本内，同语义）。

CLI 模式（降级值）：

| 键 | 值 |
|----|----|
| `REQUEST_METHOD` | `'GET'` |
| `QUERY_STRING` | `''` |
| `SCRIPT_NAME` | 脚本绝对路径（stdin 渲染时为 `'-'`） |
| `SCRIPT_FILENAME` | 脚本绝对路径（= `SCRIPT_NAME`，对齐 PHP CLI 的同名键；stdin 渲染时为 `'-'`） |
| `SCRIPT_DIRNAME` | 脚本所在目录（stdin 渲染时为 cwd） |
| `PATH_INFO` | `''` |
| `REMOTE_ADDR` / `SERVER_NAME` / `SERVER_PORT` / `CONTENT_TYPE` / `CONTENT_LENGTH` | `''` |
| `argv` | `[脚本路径] + 其余命令行参数`（argv[0] = 被渲染脚本自身，stdin 渲染时为 `'-'`——对齐 PHP CLI `$argv`） |

（`DOCUMENT_ROOT` / `REQUEST_URI` / `REQUEST_SCHEME` 不设——CLI 模式无 root / URL / scheme 概念，PHP CLI 亦无此三键。）

### 6.5 _BODY / _JSON

`_BODY` 为原始 body bytes（CLI 恒 `b''`）。一期不设 `MAX_CONTENT_LENGTH`，body 全量读入内存（可信环境定位，公网上限见 hardening.md）。`_JSON`：Content-Type 字符串包含子串 `json`（覆盖 `application/json`、`+json`、`text/json`）时 `json.loads(_BODY)`，**解析失败 → None**；不含 json → None。body 为空也 → None。

### 6.6 RespObject 方法

| 方法 | 行为（HTTP 模式） | CLI 模式 |
|------|--------------------|-----------|
| `write(*args)` | = `echo` | 同 echo（正常输出） |
| `escape(value)` | = `escape` 同一函数对象（见 6.2），返回转义串 | 照常可用（纯函数） |
| `header(name, value)` | 记入待发 headers，后设覆盖先设；例外：`Set-Cookie` **追加不覆盖**（对齐 PHP `header('Set-Cookie: ...')` 可多次调用逐条下发，见 8）；`Content-Type` 经此设置时完全覆盖默认值 | no-op |
| `status(code)` | 记入状态码，后设覆盖 | no-op |
| `redirect(url, code=302)` | `header('Location', url)` + `status(code)`，**不终止渲染** | no-op |
| `json(data)` | `header('Content-Type', 'application/json')` + `buffer.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))`，**不终止渲染**（脚本自行 `return`） | Content-Type 丢弃，序列化文本照常写 buffer |
| `setcookie(name, value='', *, max_age=None, expires=None, path='/', domain=None, secure=False, httponly=False, samesite=None)` | 记入待发 cookies，同名后设覆盖 | no-op |

`json.dumps` 抛 TypeError（不可序列化对象）→ 渲染异常 → 500。`application/json` 不附加 charset（RFC 8259 默认 UTF-8）。

## 7. Session

### 7.1 Cookie 格式与签名

```
MAKO_SESSION={data_b64}.{ts}.{sig}
data_b64 = urlsafe_b64encode(json.dumps(data, ensure_ascii=False, separators=(',',':')).encode('utf-8')).rstrip(b'=')
ts      = 十进制秒级时间戳（签发时刻）
sig     = hmac_sha256(secret, data_b64 + b'.' + ts).hexdigest()
```

校验：split 成三段（多段/缺段 → 无效）→ `hmac.compare_digest` 常量时间比签 → 过期判定 `now - ts >= lifetime`（到点即过期，等号含入，sliding/absolute 同式）。任一步失败视为**无 session**（`_SESSION` 为空 dict），不报错。

解码注意：`data_b64` 签发时去掉了 `=` padding，校验通过后须补回 `data_b64 + b'=' * (-len(data_b64) % 4)` 再 `urlsafe_b64decode`——否则直接 `binascii.Error: Incorrect padding`（必踩实现坑）。

**Cookie 属性**（决策 #19）：session cookie 固定 `Path=/; HttpOnly; SameSite=Lax`，**不设 Max-Age / Expires**——浏览器会话 cookie，对齐 PHP 默认 `session.cookie_lifetime=0`；过期控制完全由服务端时间戳判定承担（cookie 即使被浏览器或插件持久保留，过期后校验失败按无 session 处理，两层各自独立）。HttpOnly 防页面 XSS 偷 cookie，SameSite=Lax 提供基础 CSRF 缓解（均现代默认做法；PHP 同名 ini 默认偏松是历史包袱，新项目不继承）。

### 7.2 密钥派生（本机指纹）

`secret` 配置非空 → 直接用（UTF-8 编码）。否则由本机指纹派生，算法要点：多分量收集、逐项容错、一次性散列、模块级缓存（下文内联完整描述，自包含）：

**分量收集**（components 列表，逐项独立 try/except，失败/缺失即跳过该项、不中断）：

1. 固定域分离盐 `'MAKOSERVER-HOST-KEY'`（防不同用途的指纹散列直接互相复用）；
2. `socket.gethostname()`；
3. Windows：`wmic csproduct get uuid`（主板硬件 UUID）；wmic 不可用（Win11 24H2 起已移除）→ 回退 winreg 读 `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`；
4. Linux：`/etc/machine-id`，次选 `/var/lib/dbus/machine-id`，再备 `/sys/class/dmi/id/product_uuid`；
5. `platform.processor()`；
6. MAC（条件采集）：先判 WSL——`/proc/version` 含 `microsoft`/`wsl` 则跳过（WSL 的 MAC 每次重启漂移，不稳定）；否则 `uuid.getnode()`，且 `((mac >> 40) & 0x01) == 0` 才采信（bit40 为本地管理位，=1 表示随机/本地 MAC，不稳定，跳过）。

**拼接散列**：`secret = sha256(':'.join(components).encode('utf-8', 'ignore')).digest()`——`':'` 拼接分隔 + sha256，直接取 32 字节 digest 作 HMAC-SHA256 密钥（不整形为 UUID 形状，无必要）。

**缓存**：模块级计算一次后缓存（memoize，进程生命周期内不重算——运行中分量漂移不影响已派生密钥）。

效果：多分量容错（单一来源读取失败或漂移不影响整体稳定）、同机稳定、跨机不同、无需落盘。极端退化警示：若全部分量采集失败（无 hostname、无 machine-id、无 MAC 的异常环境），secret 退化为固定常量、跨机相同——可信环境可接受，知悉即可。

### 7.3 签发 / 重签 / 过期规则表

请求开始时载入有效数据并做**规范化快照**：`snapshot = json.dumps(data, sort_keys=True, separators=(',', ':'))`——快照与比对基准均为**规范化 JSON 串**而非 dict copy。浅拷贝有隐蔽坑：`_SESSION['cart'].append(x)` 这类嵌套原地修改后，快照与现值内层是同一对象、`==` 恒真，absolute 模式判「未改」不重签、修改静默丢失，sliding 模式却因「有效即重签」把它存下——两种模式对同一段脚本行为分裂，最难排查。JSON 串一举解决深比较与 dict 键序两个问题。渲染结束后以同样参数序列化 `now_dict` 与快照**比串**，不等 = 脚本写过（检出含嵌套层级的原地修改、增删键、整体重绑定）：

| 场景 | absolute | sliding |
|------|----------|---------|
| 带有效 session，未改数据 | 不发 Set-Cookie | 重签：ts = now，重发 |
| 带有效 session，改了数据 | 重签：**ts 继承原 ts**（绝对窗口不重置） | 重签：ts = now |
| 无 session，dict 非空 | 签发：ts = now | 签发：ts = now |
| 无 session，dict 为空 | 不发 | 不发 |
| 校验失败 / 过期 | `_SESSION` = 空 dict，按「无 session」行处理 | 同左 |

（清空 `_SESSION` 属「改了数据」：absolute 下重签空数据 ts 继承，sliding 下 ts=now。）

变更检测基于框架持有 dict 的快照比对，覆盖**原地修改**（`_SESSION['k'] = v` / `.update()` / `.clear()` / `del`，**含嵌套层级**——`_SESSION['cart'].append(x)` 等，深比较由上述规范化 JSON 串快照保证）；模板中 `_SESSION = {...}` 属局部名重绑定，框架侧对象不变，判为「未写」、修改丢失——Python 语义使然（与 PHP `$_SESSION` 可整体重赋值不同），模板代码须原地增删改。

### 7.4 容量上限与序列化失败

- 组装 Set-Cookie 前检查完整 cookie 串长度 > 3800 字节 → 抛 `SessionTooLarge` → 500 错误页（错误信息说明 4KB 限制）；
- session 值不可 JSON 序列化（datetime / set / 自定义对象等）→ 序列化抛 `TypeError` → **同语义 500** 错误页（错误信息说明 session 仅支持 JSON 类型）——与 `SessionTooLarge` 同阶段（渲染成功后的响应组装）、同性质（脚本写了存不进 cookie 的东西），归一类处理。

### 7.5 CLI 模式

`_SESSION` 恒为空 dict；对它的写无任何副作用（不发 cookie）。

## 8. 响应组装（HTTP 模式）

渲染成功后：

1. body = `buffer.getvalue()`；
2. status = RESP 记录的 code（未设 → 200）；
3. Content-Type：RESP 显式设置值 > 默认 `text/html; charset=utf-8`；
4. 其余 RESP headers 逐个加入（后设覆盖先设；**Set-Cookie 例外**——`RESP.header` 设置的逐条追加、`RESP.setcookie` 按 cookie name 后设覆盖、session 的 Set-Cookie 独立追加，三者并存下发。**session cookie 名独占**：脚本 `RESP.setcookie('MAKO_SESSION', ...)` 与框架 session 机制同名时**该条丢弃、不下发**，并向 error log 打 warning——下发两条同名 Set-Cookie 的浏览器取舍行为未定义；session 机制对该名字独占管理（`Path/HttpOnly/SameSite` 固定属性不容脚本覆盖；清 session 走服务端过期或清空数据，删浏览器 cookie 无意义）。**独占检查只覆盖 `setcookie` 通道**：`RESP.header('Set-Cookie', 'MAKO_SESSION=...')` 属**原始逃生舱**——逐条追加、不解析 cookie 名、不做名字检查，同名冲突后果自负（信任模板作者哲学，与 include 豁免屏蔽同理））；
5. session 规则（7.3）决定是否追加 Set-Cookie；
6. 组装 `flask.Response(body, status, headers)` 返回。

redirect 场景：脚本设了 302 + Location 但 body 已有内容 → 照发（对齐 PHP，303 语义由脚本自己保证，`return` 防污染）。

## 9. 错误处理

### 9.1 500（模板编译/渲染异常、静态读失败、SessionTooLarge 等）

- body：极简 HTML 页：`<h1>500 Internal Server Error</h1>` + 请求路径 + `<pre>`traceback`</pre>`，全部经 `html.escape` 转义；
- Content-Type：`text/html; charset=utf-8`；
- traceback 原文写 error log（见 11）；
- 不回显任何用户输入参数（路径是唯一回显且已转义）。

### 9.2 404

见 3.6。

### 9.3 CLI 异常

traceback 写 stderr，`sys.exit(1)`；stdout 不输出 partial 内容。

### 9.4 隔离边界（脚本 vs 宿主进程）

.mako **不在沙箱中运行**（PRD 定位：等同本机运行脚本）。隔离程度分两层：

- **已隔离**：Python 异常（编译错 / 运行错 / 脚本主动 raise）→ 500 页面，进程无恙；每请求的 bridge / buffer / session 均为一次性对象，脚本对其的污染不跨请求；partial buffer 渲染异常即丢弃；
- **不设防**：进程级故障真实影响 makoserver——`os._exit()`、C 扩展段错误直接杀死进程；死循环请求挂起且一期无超时（GIL 调度下其他请求仍可服务，但该请求永不返回）；内存泄漏累加在宿主进程；模板亦可经 `echo.__globals__` 等路径触达模块全局（无沙箱的应有之义，信任边界靠「可信环境」定位承担）；
- 进程级健壮性交部署层兜底：WSGI 多进程（gunicorn prefork）+ `--max-requests` 定期回收 + `--timeout` 杀死死循环（与 hardening.md「两层账」一致）；一期 dev server 单进程形态不提供。

## 10. 运行形态与模式判定

### 10.0 模式判定（互斥三分支）

1. `__name__ != '__main__'`（被 import：mod_wsgi / gunicorn / uWSGI）→ **WSGI 模式**，模块级构建 `application`；
2. `__main__` 且存在首个非选项位置参数 → **CLI 渲染模式**，该参数即脚本路径（**不限制 .mako 扩展名**，对齐 `php foo.txt` 照跑的习惯；文件不存在 → stderr 报错 exit 1；**单独一个 `-` 亦属位置参数**（argparse 对裸 `-` 按位置参数处理）→ stdin 渲染，见 10.3 与决策 #24）；
3. `__main__` 且无位置参数 → **dev server 模式**。

「检测 WSGI 环境」以 import 语义判定（`__name__`），不依赖环境变量——gunicorn / uWSGI 不设统一标志，mod_wsgi import 时请求 environ 尚不存在。

### 10.1 独立 dev server

```
python makoserver.py [options]
  -r, --root DIR      文档根目录（最高优先级，回退链见 2.4）
  -p, --port N        端口，默认 5000（纯命令行，不读配置）
  --host ADDR         监听地址，默认 127.0.0.1（纯命令行，不读配置）
  --conf FILE         指定配置文件（等价 MAKOSERVER_CONF，优先于三级查找）
  --version           打印 __version__ 退出
  -h, --help          argparse 自带
```

读配置（2.2，`--conf` 最先）→ 命令行覆盖与 root 三级回退（2.4，最终回退 cwd）→ `app.run(host, port, threaded=True)`。并发 = Werkzeug dev server 线程模型，不追求生产级。

### 10.2 WSGI 入口

模块级 `application = create_app(...)`：import 时完成配置查找与 app 构造（每进程一次，无跨进程状态，天然多进程兼容）；root 见 2.4（配置缺失时回退本文件所在目录，零配置即拷即用）。Apache `WSGIScriptAlias /app1 /path/to/makoserver.py` 即用。

### 10.3 CLI 渲染

```
python makoserver.py [options] script [args...]
  script    被渲染脚本路径（不限 .mako 扩展名，文件不存在 → stderr 报错 exit 1）；
            传 `-` 时从 stdin 读取模板源渲染（POSIX 约定，决策 #24）
  args...   脚本名之后的一切参数不解析、原样透传（argparse REMAINDER），
            脚本经 _SERVER['argv'] 读取，argv[0] = script 自身（对齐 PHP $argv）
```

- 不读配置文件（`--conf` / `-r` / `-p` / `--host` 在此模式静默忽略，PHP 式宽容。「静默忽略」= argparse 照常解析接受（如 `makoserver.py -r dir script.mako` 中 `dir` 作为 `-r` 的值被吞、`script.mako` 仍为位置参数）但**不产生任何副作用**——不读配置、不设 root；非报错，亦不逐参数剔除）；`TemplateStore.base_dir` = 脚本所在目录（4.3）；
- **stdin 渲染**（`script` = `-`，决策 #24）：从 `sys.stdin.buffer` 读原始字节，按 `utf-8-sig` 解码（BOM 容忍，与文件加载一致；解码失败 → stderr 报错 exit 1），源码同样做尾部空白截断（rstrip，与 4.1 契约一致）后以 `Template(text=..., uri='<stdin>', lookup=store)` 纯内存编译；`TemplateStore.base_dir` = **cwd**（无脚本文件时 include/inherit 的唯一自然锚点）；`_SERVER` 三键降级：`SCRIPT_NAME` / `SCRIPT_FILENAME` = `'-'`、`SCRIPT_DIRNAME` = cwd；`argv[0]` = `'-'`（PHP CLI 读 stdin 时同为 `'-'`），其余参数照常透传（`makoserver.py - a b` → `argv = ['-', 'a', 'b']`）；
- bridge 按 6.4/6.6 CLI 列降级；
- 成功：`sys.stdout.buffer.write(body)`（原始字节，二进制安全）；
- 失败：见 9.3。

模式判定与扩展名规则见 10.0。

## 11. 日志

| 通道 | 默认 | 配置后 |
|------|------|--------|
| error log | stderr | `error_log` 文件；自实现 `_AppendFileHandler`（每条日志即时 append 打开写入，不长期持有句柄——避免 Windows 下持续锁文件影响清理/滚动；本机场景写入量小，开销可忽略；UTF-8） |
| access log | 不落盘（dev 走 Werkzeug 控制台自带输出；WSGI 交宿主） | `access_log` 文件；middleware 包裹 app 记录，**dev server 与 WSGI 两模式同样生效**（装配于 app 本身，与运行形态无关；dev 下与 Werkzeug 控制台输出并存） |

- error log 内容：5xx traceback、启动错误、模板编译错误；格式 `%(asctime)s %(levelname)s %(message)s`；
- access log 行格式：`{iso_time} {remote_addr} {method} {path} {status} {bytes}`（状态码与字节数自 WSGI 响应回读）；
- 滚动由使用者自行管理（logrotate / 容器收集），框架不内置；
- 日志文件路径若配置进 root 内：框架已对该路径做运行时 404 屏蔽（3.5 规则 4——初始 real、回溯、兜底终点全收口，旁路同堵），直接回吐被堵；放 root 外仅更整洁、连比对都省。

## 12. 测试计划（tests/，pytest）

| 文件 | 覆盖点 |
|------|--------|
| `test_config.py` | 四级查找命中即用（`--conf` > `MAKOSERVER_CONF` > 同目录 ini > settings.ini）；`--conf`/`MAKOSERVER_CONF` 文件不存在继续下寻；相对路径基准（root/log 路径均相对配置文件目录）；`-r` 覆盖配置 `root`；配置含 `port` 键被忽略（不报错）；非法 INI 报错（缺 `[makoserver]` 节 / 解析错 / `session_lifetime` 非整数）；**含 `%` 的 secret 正常读出（interpolation=None 回归，不抛 InterpolationSyntaxError）**；注释行与未知键忽略；dev server root 三级回退（-r > 配置 > cwd）；WSGI 零配置回退 makoserver.py 所在目录；**root 不存在 / 非目录 → 启动报错退出（stderr 含 root 路径与来源；决策 #22）**；**`error_log` / `access_log` 父目录不存在 / 不可写 → 启动报错退出（append 探测失败；决策 #22 同哲学）** |
| `test_paths.py` | `../` 逃逸（钳制后落 root 内 404）、绝对路径注入、`..%2f` 解码后穿透、尾部点 `demo.mako.`、`demo.MAKO` 跨平台一致走模板分支（lower 归一，非 normcase）、`demo.mako::$DATA`（Windows）、realpath 符号链接出 root、**跨盘符 junction 与 DOS 设备名（`/nul`、`/con.txt`，Windows）→ 404（commonpath ValueError 兜底回归，非 500）**；**`%00` 空字节 → 404（非 500）**；**名为 `foo.mako` 的目录 → 404（非 500）**；拒绝与不存在同 404 响应体；请求 `/` 放行进 index 兜底（不被 root 本身拒绝）；**目录无尾斜杠（`/demo`，demo 为目录）→ 301 + Location `/demo/`（query 保留）；WSGI 挂载场景 Location 含前缀——`environ_overrides={'SCRIPT_NAME': '/app1'}` 构造（test client 默认 SCRIPT_NAME=''、测不出 script_root/path 分离），`/app1/demo` → `/app1/demo/` 不跳出应用；挂载根无斜杠（`/app1`，environ PATH_INFO=''）→ 301 `/app1/`（Werkzeug 空 PATH_INFO 归一 '/' 的静默兜底回归）；带斜杠 `/demo/` 照常兜底**；**裸尾斜杠：`/style.css/` → 404、`/demo.mako/` → 渲染 + `PATH_INFO='/'`、`/index.mako/hello/` → 渲染 + `PATH_INFO='/hello/'`（回溯场景 trailing 补回尾斜杠）**；**`//a` → 308（PathInfoNormMiddleware 归一，决策 #23）**；尾挂回溯：`index.mako/hello` 渲染 index.mako + `PATH_INFO='/hello'`、`style.css/hello` → 404、`a/b/c` 全不存在逐级回溯耗尽 404、**`dir/x`（dir 为目录、x 不存在）→ 404（不兜底 dir/index.*，对齐 Apache mod_dir）**；**非 ASCII 路径 308 归并 / 非 ASCII 挂载前缀 301 的 Location 百分号编码正确（latin-1 解码舞步回归，见 3.1）** |
| `test_index.py` | 目录请求三级兜底顺序；全部未命中 404；root 请求 `/`；**`/dir/`（有 index.html）→ 200（index 兜底豁免 trailing 判定回归——不豁免则目录请求恒 404）** |
| `test_static.py` | 白名单矩阵逐扩展名断言 Content-Type（html/htm/txt/css/js/json/png/jpg/gif/svg/ico/webp/pdf/zip/xz/...）；白名单外 404（.py/.pyc/.php/.ini/.bak/.db/.log/无扩展名）；非 GET/HEAD（PUT/DELETE）命中白名单内文件 → 405 + `Allow: GET, HEAD`，白名单外路径 PUT 仍 404；扩展名大写归一（`.PNG` → image/png）；makoserver.py 自身 404；命中的配置文件路径 404；已配置日志路径 404（**含起名 `log.mako` 的模板分支场景：直接请求、尾挂 `/log.mako/hello` 回溯、`/sub/` 兜底命中被屏蔽 `sub/index.mako`——三条路径全 404，旁路全堵**）；**root 内 `link.mako` 符号链接指向 `log.mako` → 直接请求与尾挂请求均 404（real 链比对回归：full 链上链接路径不在集合、真实目标在，real 链已解析为真实路径直接命中）**；图片/压缩字节原样；404 与不存在响应体一致 |
| `test_template.py` | 基本渲染；mtime 变更后 reload；源码尾部空白截断（单块二进制脚本 `%>` 后空白/EOF 换行不污染）；BOM 文件；include/inherit 相对解析（HTTP 与 CLI 两基准） |
| `test_echo.py` | echo 类型矩阵：str/bytes/bytearray/None/int/混合多参；RESP.write 同一函数；echo 被局部变量覆盖后 RESP.write 兜底；**escape：HTML 五字符全转义（quote=True）、整数/浮点先 str() 再转义、纯返回值不写缓冲、RESP.escape 同一函数对象与覆盖兜底、CLI 照常可用** |
| `test_bridge.py` | `_GET`/`_POST` 分离；`_REQUEST` 覆盖序（POST 压 GET）；getlist 三处可用；**form-encoded POST 同时断言 `_POST` 与 `_BODY` 均非空（get_data(cache=True) 先行顺序回归）**；`_SERVER` 键集与 HTTP_*；`SCRIPT_NAME`/`PATH_INFO` 三形态（普通请求 / 尾挂请求 / index 兜底渲染）；`SCRIPT_FILENAME`/`SCRIPT_DIRNAME`/`DOCUMENT_ROOT` 三键（尾挂与兜底场景下 `SCRIPT_FILENAME` 跟随**实际渲染文件**而非初始请求路径）；`REQUEST_URI` 含 query / 无 query / 目录兜底场景（此时 `PATH_INFO` 为空、`REQUEST_URI` 保留完整原始路径）；`_BODY`；`_JSON` 含 json/坏 JSON/非 JSON；RESP.header/status 后设覆盖；`RESP.header('Set-Cookie')` 连设两次逐条追加；`POST /` 到达根路径模板；redirect/json 不终止渲染（后续 echo 仍污染 body，行为断言）；json 中文 ensure_ascii=False；setcookie `expires` 数值时间戳 → IMF-fixdate（UTC）格式断言 |
| `test_session.py` | 签发/回带往返；**Set-Cookie 属性断言（`Path=/`、`HttpOnly`、`SameSite=Lax`、无 Max-Age/Expires）**；篡改 data/ts/签名 → 空 dict；base64 去 padding 后补 `=` 再解码；absolute 到期拒绝、改数据 ts 继承；sliding 无写入也重签、重签刷新 ts；过期边界（now-ts == lifetime 即过期，等号含入）；原地修改检出（**含嵌套层级：`_SESSION['cart'].append(x)` 判「已写」重签——规范化 JSON 串深比较回归，absolute 模式防嵌套修改静默丢失**）/ `_SESSION = {...}` 重绑定判「未写」；4KB 超限 500；**值不可 JSON 序列化（datetime 等）→ 500（错误信息说明仅支持 JSON 类型）**；**`RESP.setcookie('MAKO_SESSION', ...)` 同名 → 丢弃不下发 + error log warning（session cookie 名独占回归）**；secret 配置覆盖派生；派生密钥模块级缓存（两次调用同值） |
| `test_cli.py` | stdout 字节精确比对（含二进制输出）；降级 `_SERVER`/空参数/no-op RESP；`argv` 透传（argv[0]=脚本自身、脚本后参数含 `--` 前缀原样透传）；include 基准 = 脚本目录；非 .mako 扩展名照渲染；脚本不存在 exit 1；渲染异常 exit 1；**stdin 渲染（`-`，决策 #24）：基本渲染、argv[0]='-' 与三键降级（SCRIPT_NAME/FILENAME='-'、SCRIPT_DIRNAME=cwd）、include 基准 = cwd、尾部空白截断、BOM 容忍、渲染异常 exit 1** |
| `test_http.py` | 端到端（Flask test client）：默认 Content-Type；显式覆盖；Set-Cookie 下发与回带；404 文本；500 traceback 转义（`<script>` 注入路径转义断言）；PUT/DELETE 请求 .mako 正常渲染且 `_SERVER['REQUEST_METHOD']` 如实传递；**OPTIONS 请求 .mako 到达脚本渲染（`REQUEST_METHOD='OPTIONS'`，非 Flask 自动 Allow 应答——provide_automatic_options=False 回归）**；index 兜底落 index.html 时 PUT → 405、落 index.mako 时 PUT 照常渲染 |

## 13. 明确不做（一期）

- `_FILES` 上传、限速、请求体大小上限（`MAX_CONTENT_LENGTH`，一期 body 全量进内存）、安全响应头、错误页脱敏开关（公网加固见 hardening.md）；
- 静态文件 304/Range；
- 日志轮转、多 app 多 root 路由；
- watchdog 及任何第三方依赖。
