# MakoServer

使用 Mako + Flask 做一个类似 PHP 的系统。使用 MakoServer 以后，用户新建动态页面或者纯 HTTP/JSON 接口，只需要在文档根目录内新增 .mako 文件即可，不用改到 Flask。

## 定位与安全边界

- 本项目定位为**本机/可信环境**使用的轻量动态页面服务，不做公网暴露场景的安全加固；
- .mako 模板本质是执行任意 Python 代码，等同本机运行脚本，使用者须知悉。

## 模板服务

- 基于 Mako / Flask，提供一套类似 .php 的网页服务；
- 用户请求 `http://localhost:5000/web/demo.mako` 的话，就会解析出相对路径，到文档根目录下寻找对应 .mako 文件并渲染返回；
- 启动后指定一个文档根目录，就能为下面的所有 .mako 脚本提供页面服务，用户写新的动态页面，新增 .mako 文件就行，不必改 Flask 端任何一行代码；
- 如果请求的是非 .mako 文件，走静态文件服务：按**内置扩展名白名单**（网页 .html/.htm、文本 .txt、.css、.js、数据 .json、常见图片、.pdf、常见压缩包，完整表见 spec）返回对应 Content-Type 与原始字节；**白名单之外（.py / .pyw / .pyo / .pyc / .php / .ini / .bak / .db / .log / 无扩展名等）一律 404（无论请求谓词）**，与「不存在」同响应——默认拒绝（fail-closed），源码、备份、数据库等杂物默认不可下载；白名单内且存在的文件仅接受 GET/HEAD，其它谓词返回 405 Method Not Allowed（附 `Allow: GET, HEAD` 头；判定在白名单之后，404 优先，不因 405 泄露文件存在性；.mako 脚本则全谓词渲染，`REQUEST_METHOD` 如实传递给脚本）；
- 能够防止相对路径穿透到文档根目录以外；
- 防止 .mako 源码以静态文件形式泄露：扩展名判断大小写不敏感，且基于规范化后的真实路径判断（防范 Windows 下 `demo.MAKO`、尾部点 `demo.mako.`、NTFS 数据流 `demo.mako::$DATA` 等写法绕过扩展名检查、走静态分支吐出模板源码；尾部点剥除仅 Windows 主动特判——Linux 下此类字面文件名不存在、自然 404 fail-closed，有意跨平台分裂）；
- 服务自身与配置的防回吐：makoserver.py 自身与 `makoserver.ini`（.py / .ini 均不在静态白名单，天然 404）、实际加载命中的配置文件、已配置的日志文件（后两者路径启动时记录，请求解析全程对**最终目标文件**比对——初始路径先行、PATH_INFO 回溯与 index 兜底解析出的目标终点收口，命中即 404）——比对覆盖静态分支（回吐 secret 与访客日志）与模板分支（日志 / 配置若起名 `*.mako` 会被**当模板编译执行**），回溯与兜底旁路同堵；
- 如果请求映射到目录（含 `/`）：URL 末尾无 `/` 时先 301 重定向补斜杠（对齐 Apache `DirectorySlash`，防页内相对链接错链），再依次尝试追加 `index.mako`、`index.html`、`index.htm`；
- 支持 PHP 的 PATH_INFO 尾挂机制：请求 `xxx.mako/尾挂路径`（如 `/index.mako/hello`）时渲染 `xxx.mako`，尾挂部分（`/hello`）经 `_SERVER['PATH_INFO']` 传入，脚本可据此实现漂亮 URL 路由（无需 query string）；静态文件不带尾挂（`style.css/hello` → 404）；尾挂中的 `../` 已被路径规范化先行钳制，不构成穿透；
- Flask 端提供 bridge 函数/对象供 .mako 脚本使用，详见下文「Bridge API」一节；
- 更新检测：用户更新 .mako 脚本后能自动检测并 reload —— 采用**请求时检查 mtime** 的方式，不引入 watchdog；
- 错误处理：.mako 脚本编译错误或运行时异常时，返回 5xx 状态码 + 错误内容页面；
- 404 处理：请求的文件不存在（含 index 兜底全部未命中）、或路径穿透检查被拒绝时，统一返回 404 状态码 + 简单文本错误页，不区分"不存在"与"被拒绝"（避免探测文件结构）；目录存在性可经 301（目录无斜杠）/ 404（不存在）的差异被探测——Apache 同病，可信环境接受，知悉即可；
- 编码：文本输出统一 UTF-8，第一期重点覆盖 `text/html`、`text/plain`、`application/json` 三种类型。

## Bridge API

Flask 端向 .mako 模板暴露的函数/对象，设计对标 PHP 的超全局变量与常用函数。命名空间原则：PHP 靠 `$` 前缀让变量与函数天然分域，Python 单命名空间没有这层保护，注入名分三类——

- **请求数据**：大写下划线超全局风格（`_GET` / `_SERVER` 等），几乎不会与局部变量撞名；
- **响应控制**：统一挂 `RESP` 对象（`RESP.header()` / `RESP.json()` 等），不占用全局名——尤其 `json` 由此释放给标准库，模板里 `import json` 后 `json.dumps()` 不受干扰；
- **输出/工具**：裸函数两个——`echo`（输出，高频、PHP 肌肉记忆、名字独特）与 `escape`（HTML 转义，对标 `htmlspecialchars`），分别另挂规范名 `RESP.write()` / `RESP.escape()`（同为同一函数对象），被模板局部变量覆盖时用规范名兜底。

### 输出

- `echo(*args)` —— 模仿 PHP 的 `echo`（含逗号分隔多参数），内部调用 Mako 的 `context.write()`，让模板代码块里可以像 PHP 一样显式输出，不必依赖 `<% %>` 块外的文本插值。输出缓冲只有一个，统一存 bytes：参数是 bytes（含 bytearray）时直接追加，`None` 输出空串（对齐 PHP 的 `echo null`），其它类型先 `str()` 再即时 UTF-8 编码追加——因此二进制内容（动态生成图片 / 文件下载等）直接 `echo(字节串)` 即可，无需单独的 raw 接口；
- `RESP.write(*args)` —— `echo` 的规范名，挂在 `RESP` 对象上不受模板局部变量影响：即便 `echo` 被覆盖，规范名永远可用；
- `escape(value)` —— 对标 PHP 的 `htmlspecialchars`：先 `str()`（整数 / 浮点 / None / 任意对象先字符串化）再转义 `& < > " '`（`quote=True`），**返回转义后的字符串**（纯转换，不写输出缓冲）；`${}` 插值输出变量时用它防注入；
- `RESP.escape(value)` —— `escape` 的规范名（同一函数对象），被模板局部变量覆盖时兜底；CLI 模式照常可用（纯函数不受响应控制 no-op 规则影响）；
- 模板中 `<% %>` 块之外的普通文本照旧直接输出，以上方式可混用；
- **输出全程缓冲**：`echo()` / 文本块写入内部缓冲，`Content-Type`、`status`、`header` 等响应元数据可在模板任意位置、最末尾设置，不存在 PHP 的 headers-already-sent 限制；模板渲染中途抛异常时丢弃已缓冲的 partial output，返回干净的 5xx 错误页；缓冲在实现上以自定义 Mako buffer 兑现（`write(str)` 即时 UTF-8 编码追加、`write(bytes)` 直通），不依赖 Mako 默认的文本 buffer；
- **源码末尾空白截断**：读取 .mako 源文件后、编译前，统一删除源码末尾空白（空格 / tab / 换行）——文件末尾空白永远不属于输出内容。由此写精确二进制脚本（整文件单一 `<% %>` 块、二进制经 `echo(bytes)` 输出）时无需关心编辑器的 EOF 换行，`%>` 后的尾部空白不会污染输出；普通文本模板也获得统一行为（响应体末尾不保留源文件的尾部换行）。

### 请求（仿 PHP 超全局变量命名）

命名一律大写下划线风格，避开与函数参数、requests 库等常见名字的冲突：

- `_REQUEST` —— 合并的请求参数字典（对应 PHP 的 `$_REQUEST`），支持 `getlist(name)` 获取同名多值（如 `?tag=a&tag=b`）；
- `_GET` / `_POST` —— GET 与 POST 参数字典分开访问（对应 `$_GET` / `$_POST`）；
- `_SERVER` —— 请求环境信息字典（对应 `$_SERVER`），至少包含：`REQUEST_METHOD`、`QUERY_STRING`、`SCRIPT_NAME`（脚本路径）、`PATH_INFO`（尾挂路径，PHP 语义分工：脚本路径在 `SCRIPT_NAME`、尾挂在 `PATH_INFO`，无尾挂时为空串）、`REQUEST_URI`（原始请求 URI 原文含 query，编码态不受解码 / 规范化影响）、`SCRIPT_FILENAME`（实际渲染脚本的绝对路径，尾挂 / 兜底场景跟随最终渲染目标）、`SCRIPT_DIRNAME`（脚本所在目录，语义同 PHP 的 `__DIR__`）、`DOCUMENT_ROOT`（文档根绝对路径）——模板内文件访问**勿依赖**进程 cwd（随启动方式漂移、多线程共享不保证），定位文件用此三键拼绝对路径（PHP web「cwd = 脚本目录」因线程安全不可 chdir，以显式拼路径等价兑现）、`REMOTE_ADDR`（客户端 IP）、`CONTENT_TYPE` / `CONTENT_LENGTH`（请求体类型与长度，POST 场景高频）、`SERVER_NAME` / `SERVER_PORT` / `REQUEST_SCHEME`（服务端地址信息）、以及 `HTTP_*` 形式的客户端请求头（如 `HTTP_AUTHORIZATION`）；
- `_BODY` —— 原始请求 body（对应 PHP 的 `php://input`）；若 Content-Type 为 JSON 则同时提供 `_JSON`（自动解析成字典，否则为 None）；
- `_COOKIE` —— 客户端 cookie 字典（对应 `$_COOKIE`）；
- `_SESSION` —— 会话字典（对应 `$_SESSION`），一期实现，方案如下：
  - 基于**签名 cookie + 时间戳**，无服务端存储，天然兼容 WSGI 多进程；
  - session cookie 固定 `Path=/; HttpOnly; SameSite=Lax`，不设 Max-Age / Expires（浏览器会话 cookie，对齐 PHP 默认 `session.cookie_lifetime=0`）；过期控制由服务端时间戳判定独立承担；
  - 时间戳在签名覆盖范围内，客户端无法篡改续命；过期判定以服务端时钟为准；
  - **两层超时独立控制**：cookie 自身的 HTTP 层过期（`RESP.setcookie()` 的 expires/max-age）与签名 session 的时间戳过期是两层，前者管浏览器是否携带，后者管服务端是否接受；
  - 支持两种超时语义（配置项切换）：绝对超时（签发时间起算）与滑动超时（每次响应重签刷新，仿 PHP 默认行为）；
  - 签名密钥优先读配置；配置缺失时由本机指纹（machine-id + 网卡 MAC 的 hash）派生，无需落盘即可同机稳定、跨机不同；
  - 预期管理：容量受 cookie 限制（约 4KB，超限抛 500 错误页、错误信息说明容量限制）、值仅支持 JSON 可序列化类型（datetime / 自定义对象等写入时同样 500 报错）、数据客户端可见（只防篡改不防偷看）、无法服务端主动失效（改密钥可全员掉线）；
  - 更复杂的会话需求（主动淘汰、大容量存储等）由用户脚本自行搭配 Redis 等后端实现，bridge 提供 cookie 原语即可支撑（发 HttpOnly 的 sid cookie + 自管存储），MakoServer 不内置也不感知这些依赖。

### 响应

响应控制方法统一挂 `RESP` 对象（输出类的 `RESP.write` 见上文输出节）：

- `RESP.header(name, value)` / `RESP.status(code)` —— 设置响应 header、状态码（对应 PHP 的 `header()` / `http_response_code()`）；
- `RESP.redirect(url, code=302)` —— 便捷重定向（等价于 PHP 的 `header('Location: ...')`）；
- `RESP.json(data)` —— 便捷 JSON 响应（自动设置 Content-Type 并序列化）；参考 PHP 实现，**不主动退出**渲染，脚本需自行终止后续输出以防残留文本污染 body（Mako 模板顶层 `<% %>` 块内 `return` 即可终止渲染）；
- `RESP.setcookie(name, value, ...)` —— 设置 cookie（对应 PHP 的 `setcookie()`）；
- 默认 Content-Type：脚本未显式设置时为 `text/html; charset=utf-8`（对齐 PHP 默认行为），二进制输出脚本（动态图片 / 下载等）需用 `RESP.header()` 显式指定类型。

### 第二期扩展（暂不实现）

- `_FILES` —— 文件上传（对应 PHP 的 `$_FILES` / `move_uploaded_file`）。

### 说明

- **模板辅助函数的作用域约定**：Mako 模板有两层 Python 作用域——`<%! %>` 是模块级（模板加载时执行一次）、`<% %>` / `${ }` 是渲染体（每请求执行一次）。bridge 注入的 11 个名字（`echo` / `escape` / `_GET` / `_SESSION` / `RESP` 等）只存在于渲染作用域，`<%! %>` 里的函数引用它们会在**运行时首次被调用时**才报 NameError（编译不报错，极具迷惑性）。约定：`<%! %>` 里只放 import 与纯函数（参数进、结果出，不碰注入名）；要用注入名的辅助函数放 `<% %>` 里，或把注入名作为参数显式传入；
- 跨请求持久化不提供内置支持，脚本自己读写文件即可（本机可信环境）；
- CLI 模式下 bridge 的降级语义见「运行方式」一节，`echo()` 在 CLI 下照常输出（渲染结果以原始字节写入 stdout 的 `sys.stdout.buffer`，保证二进制内容不损坏）；`_SESSION` 读取为空、写入随 cookie 设置一同 no-op。

### 注入名作用域（模板编写约定）

桥接注入名（`echo` / `escape` / `_GET` / `_SESSION` / `RESP` 等）是**每请求**经渲染调用传入的，只存在于模板的**渲染体作用域**（`<% %>` 块与 `${}` 插值），**不在模板模块的 globals 里**。由此产生一条硬性编写规则：

- `<%! %>`（模块块，模板加载时执行一次）里**只放 import 与纯函数**——参数进、结果出，绝不引用任何注入名；
- 需要访问注入名的辅助函数一律定义在 `<% %>` 块内（每请求定义，闭包捕获注入名）；
- 确需在 `<%! %>` 定义工具函数又想转义时，显式把 `escape` 作为参数传入，或改用标准库 `import html` + `html.escape(..., quote=True)`（语义等价）。

违反时的失败形态：编译正常通过（注入名是合法标识符），**运行时**函数被调用才抛 `NameError`——且若该函数只在特定分支（如 `?debug=1`）被调用，平时页面一切正常，极具迷惑性。

### 站点本地模块 import

HTTP 模式（dev server / WSGI）启动时，文档根目录会被追加进 `sys.path` 尾部，因此模板可以在 `<%! %>` 模块块里直接 import 根目录下的 .py 辅助模块（点分路径，py3 命名空间包，无需 `__init__.py`），例如 `root/common/siteutil.py` → `from common.siteutil import tagline`。两点预期：追加在尾部，标准库与已安装包永远优先，root 下同名文件无法遮蔽标准库；导入的 .py 常驻 `sys.modules`，**编辑后需重启服务才生效**（与 .mako 的 mtime 热重载不同），适合放 DB / Redis 客户端等长生命周期单例。CLI 模式无文档根概念不参与；`.py` 不在静态白名单，辅助模块放根目录内不会经 HTTP 泄露。

## 路径解析

- 程序与配置中统一用 **root** 指代文档根目录；
- makoserver.py 可直接作为 WSGI 入口使用（文件导出 `application` 函数），无需另写入口脚本；
- **WSGI 挂载场景**：假设 Apache 配置了 `WSGIScriptAlias /app1 /path/to/makoserver.py`，且配置中 root 为 `/home/data/mako`。用户请求 `http://192.168.1.11/app1/demo/demo.mako` 时，`/app1` 挂载前缀由 WSGI 环境（SCRIPT_NAME）提供并被剥除，剩余部分 `demo/demo.mako` 拼到 root 上，解析为模板文件 `/home/data/mako/demo/demo.mako`；
- **独立 Flask 模式**：同一 root 下，请求 `http://localhost:5000/demo/demo.mako` 没有挂载前缀，直接解析为 `/home/data/mako/demo/demo.mako`——两种模式下相同的 URL 尾部对应同一个模板文件，方便本机开发与 WSGI 部署行为一致；
- **index 兜底**：仍以 WSGI 场景为例，用户请求 `http://192.168.1.11/app1/` 时，在 root（`/home/data/mako`）下依次寻找 `index.mako`、`index.html`、`index.htm`，哪个存在就渲染/返回哪个，全部不存在则 404；请求 `/app1`（挂载根无尾斜杠）时先 301 补斜杠到 `/app1/` 再兜底（防页内相对链接错链，与目录补斜杠同理）。

## 配置文件

- 全局默认配置（默认文档根目录、session 相关等）：`~/.config/makoserver/settings.ini`；配置文件格式为 INI（`configparser`，单节 `[makoserver]`，支持 `#` / `;` 行注释）；`_SESSION` 的签名密钥（secret）可在此显式配置覆盖，未配置时按本机指纹派生（详见「Bridge API」一节）；
- 可选键 `access_log` / `error_log`：值为文件路径，配置后请求日志 / 错误日志分别写入对应文件；不配置时的默认流向：access log 不落盘、error log 走 stderr（详见「非功能需求」日志一节）。日志文件路径不建议指向文档根目录；即使指向，框架也会对该路径做运行时 404 屏蔽（见「模板服务」防回吐一条），不会回吐泄露；
- 命令行参数：`-r` 指定的根目录覆盖配置文件中的 `root`；`-p` / `--host` 为纯命令行参数（端口、监听地址属进程启动属性，只对 dev server 有意义，不进配置文件——WSGI 模式监听由宿主决定，CLI 模式不读配置）；
- WSGI 模式下按以下顺序查找配置文件，命中即用：
  1. 环境变量 `MAKOSERVER_CONF` 指定的路径；
  2. WSGI 入口脚本同目录下的 `makoserver.ini`；
  3. 兜底 `~/.config/makoserver/settings.ini`。
  独立 dev server 模式在此之上另有命令行 `--conf FILE` 最高优先（CLI 渲染模式不读配置、忽略该参数）。
- 若希望"配置随站点目录走，一个目录拷走就能跑"，做法是把 WSGI 入口脚本和 `makoserver.ini` 一起放进站点目录（利用第 2 条规则），配置中的相对路径以配置文件所在目录为基准解析；
- 更简的**零配置形态**：把 makoserver.py 单独拷进站点目录即可——找不到任何配置文件时，WSGI 模式以 makoserver.py 自身所在目录为文档根目录（与第 2 条查找规则同一锚点），需要改端口 / 密钥等再补 `makoserver.ini`。

## 运行方式

- 整个 MakoServer 自身代码只有 `makoserver.py` 一个文件，第三方依赖仅 Flask、Mako 两个，除此之外不依赖任何第三方库，拷走单文件就能部署；
- 这个 MakoServer 可以单独运行，指定一个根目录和端口就能启动一个 HTTP Server 提供页面服务；
- 这个 MakoServer 也可以按 WSGI 的模式运行，它会寻找配置文件，从里面解析出根目录；找不到配置文件时，以 makoserver.py 自身所在目录为文档根目录（零配置即拷即用）；
- 还可以单独传入一个 .mako 脚本，就像命令行运行 `php xxx.php` 那样渲染出来，结果写到 stdout；脚本名传 `-` 时从标准输入读取模板源渲染（POSIX 约定，`echo '<% echo(42) %>' | python makoserver.py -`，与 `cat` / `python -` / `jq` 等工具同习惯；PHP CLI 读 stdin 时 `$argv[0]` 亦为 `'-'`），include 基准为当前工作目录；
- CLI 模式下 bridge 对象参考 PHP CLI 的降级语义：请求参数字典为空、请求方法为 `GET`、请求 body 为空、cookie 读取为空；`RESP.header()` / `RESP.status()` / `RESP.setcookie()` 等响应控制调用静默无效（no-op），不报错——保证同一个 .mako 脚本在 HTTP 和 CLI 两种模式下都能运行。

## 非功能需求

- 并发模型：第一期使用 Flask 自带 dev server 即可，不追求生产级并发能力；
- 依赖版本：受 Python 3.8 地板约束，`Flask<4` / `Mako<1.5`（部署时可钉版本上界，避免未来主版本破坏性改动影响 MakoServer）；开发/验证基准为 Flask 2.2.x + Mako 1.4.x，其中自定义字节缓冲注入用到 `mako.runtime` 私有接口，升级 Mako 小版本时需回归验证；
- 模板编译：一律在内存中进行，`module_directory` 不启用，确保文档根目录可只读挂载且不产生 `__pycache__` / `.pyc` 污染（`module_directory` 会落盘编译后 `.py` 并经 import 系统写 `__pycache__`，既破坏只读 root 又可能被静态分支回吐编译后源码）；
- 日志：
  - access log 默认不落盘：独立 dev 模式走 Werkzeug 控制台默认输出，WSGI 模式交由宿主（Apache `access_log` / gunicorn `--access-logfile`）负责，MakoServer 不重复记录；配置了 `access_log` 文件路径后由 MakoServer 主动记录请求日志（含 WSGI 模式，此时与宿主日志并存，是否双写由使用者取舍）；
  - error log（含 5xx traceback）默认写 stderr；可由配置项 `error_log` 指定文件覆盖，`access_log` 同理可选；
  - 配置了文件路径即由使用者自行管理滚动（logrotate / 容器日志收集），框架不内置日志轮转；
  - 日志文件路径不建议写入文档根目录——框架虽对已配置的日志路径做运行时 404 屏蔽（见「模板服务」防回吐一条），放 root 外仍更整洁；
