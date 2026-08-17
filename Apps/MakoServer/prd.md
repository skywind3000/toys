# MakoServer

使用 Mako + Flask 做一个类似 PHP 的系统。使用 MakoServer 以后，用户新建动态页面或者纯 HTTP/JSON 接口，只需要在文档根目录内新增 .mako 文件即可，不用改到 Flask。

## 定位与安全边界

- 本项目定位为**本机/可信环境**使用的轻量动态页面服务，不做公网暴露场景的安全加固；
- .mako 模板本质是执行任意 Python 代码，等同本机运行脚本，使用者须知悉。

## 模板服务

- 基于 Mako / Flask，提供一套类似 .php 的网页服务；
- 用户请求 `http://localhost:5000/web/demo.mako` 的话，就会解析出相对路径，到文档根目录下寻找对应 .mako 文件并渲染返回；
- 启动后指定一个文档根目录，就能为下面的所有 .mako 脚本提供页面服务，用户写新的动态页面，新增 .mako 文件就行，不必改 Flask 端任何一行代码；
- 如果请求的是 .html / .jpg 等非 .mako 文件，直接读取二进制内容并设置对应 Content-Type 返回（静态文件服务），用 `mimetypes` 猜测类型，天然支持图片等任意二进制文件；
- 能够防止相对路径穿透到文档根目录以外；
- 防止 .mako 源码以静态文件形式泄露：扩展名判断大小写不敏感，且基于规范化后的真实路径判断（防范 Windows 下 `demo.MAKO`、尾部点 `demo.mako.`、NTFS 数据流 `demo.mako::$DATA` 等写法绕过扩展名检查、走静态分支吐出模板源码）；
- 如果请求路径不包含文件名，依次尝试追加 `index.mako`、`index.html`、`index.htm`；
- Flask 端提供 bridge 函数/对象供 .mako 脚本使用，详见下文「Bridge API」一节；
- 更新检测：用户更新 .mako 脚本后能自动检测并 reload —— 采用**请求时检查 mtime** 的方式，不引入 watchdog；
- 错误处理：.mako 脚本编译错误或运行时异常时，返回 5xx 状态码 + 错误内容页面；
- 404 处理：请求的文件不存在（含 index 兜底全部未命中）、或路径穿透检查被拒绝时，统一返回 404 状态码 + 简单文本错误页，不区分"不存在"与"被拒绝"（避免探测目录结构）；
- 编码：文本输出统一 UTF-8，第一期重点覆盖 `text/html`、`text/plain`、`application/json` 三种类型。

## Bridge API

Flask 端向 .mako 模板暴露的函数/对象，设计对标 PHP 的超全局变量与常用函数。命名空间原则：PHP 靠 `$` 前缀让变量与函数天然分域，Python 单命名空间没有这层保护，注入名分三类——

- **请求数据**：大写下划线超全局风格（`_GET` / `_SERVER` 等），几乎不会与局部变量撞名；
- **响应控制**：统一挂 `RESP` 对象（`RESP.header()` / `RESP.json()` 等），不占用全局名——尤其 `json` 由此释放给标准库，模板里 `import json` 后 `json.dumps()` 不受干扰；
- **输出**：仅 `echo` / `echoraw` 两个裸函数（高频、PHP 肌肉记忆、名字独特），另挂规范名 `RESP.write()` / `RESP.writeraw()`（`echo` / `echoraw` 只是它们的 PHP 风格别名），被模板局部变量覆盖时用规范名兜底。

### 输出

- `echo(*args)` —— 模仿 PHP 的 `echo`（含逗号分隔多参数），内部调用 Mako 的 `context.write()`，让模板代码块里可以像 PHP 一样显式输出，不必依赖 `<% %>` 块外的文本插值；
- `echoraw(bytes, content_type)` —— **短路输出**二进制内容（如动态生成图片 / 文件下载）：立即终止模板渲染，以原始字节 + 指定 Content-Type 作为响应体，跳过文本渲染假设。`echo` 只处理文本，二进制一律走 `echoraw`；
- `RESP.write(*args)` / `RESP.writeraw(*args, content_type)` —— 上述两个函数的规范名，挂在 `RESP` 对象上不受模板局部变量影响：即便 `echo` / `echoraw` 被覆盖，规范名永远可用；
- 模板中 `<% %>` 块之外的普通文本照旧直接输出，两种方式可混用；
- **输出全程缓冲**：`echo()` / 文本块写入内部缓冲，`Content-Type`、`status`、`header` 等响应元数据可在模板任意位置、最末尾设置，不存在 PHP 的 headers-already-sent 限制；模板渲染中途抛异常时丢弃已缓冲的 partial output，返回干净的 5xx 错误页。

### 请求（仿 PHP 超全局变量命名）

命名一律大写下划线风格，避开与函数参数、requests 库等常见名字的冲突：

- `_REQUEST` —— 合并的请求参数字典（对应 PHP 的 `$_REQUEST`），支持 `getlist(name)` 获取同名多值（如 `?tag=a&tag=b`）；
- `_GET` / `_POST` —— GET 与 POST 参数字典分开访问（对应 `$_GET` / `$_POST`）；
- `_SERVER` —— 请求环境信息字典（对应 `$_SERVER`），至少包含：`REQUEST_METHOD`、`QUERY_STRING`、`SCRIPT_NAME`、请求路径、`REMOTE_ADDR`（客户端 IP）、以及 `HTTP_*` 形式的客户端请求头（如 `HTTP_AUTHORIZATION`）；
- `_BODY` —— 原始请求 body（对应 PHP 的 `php://input`）；若 Content-Type 为 JSON 则同时提供 `_JSON`（自动解析成字典，否则为 None）；
- `_COOKIE` —— 客户端 cookie 字典（对应 `$_COOKIE`）；
- `_SESSION` —— 会话字典（对应 `$_SESSION`），一期实现，方案如下：
  - 基于**签名 cookie + 时间戳**，无服务端存储，天然兼容 WSGI 多进程；
  - 时间戳在签名覆盖范围内，客户端无法篡改续命；过期判定以服务端时钟为准；
  - **两层超时独立控制**：cookie 自身的 HTTP 层过期（`RESP.setcookie()` 的 expires/max-age）与签名 session 的时间戳过期是两层，前者管浏览器是否携带，后者管服务端是否接受；
  - 支持两种超时语义（配置项切换）：绝对超时（签发时间起算）与滑动超时（每次响应重签刷新，仿 PHP 默认行为）；
  - 签名密钥优先读配置；配置缺失时由本机指纹（machine-id + 网卡 MAC 的 hash）派生，无需落盘即可同机稳定、跨机不同；
  - 预期管理：容量受 cookie 限制（约 4KB）、数据客户端可见（只防篡改不防偷看）、无法服务端主动失效（改密钥可全员掉线）；
  - 更复杂的会话需求（主动淘汰、大容量存储等）由用户脚本自行搭配 Redis 等后端实现，bridge 提供 cookie 原语即可支撑（发 HttpOnly 的 sid cookie + 自管存储），MakoServer 不内置也不感知这些依赖。

### 响应

响应控制方法统一挂 `RESP` 对象（输出类的 `RESP.write` / `RESP.writeraw` 见上文输出节）：

- `RESP.header(name, value)` / `RESP.status(code)` —— 设置响应 header、状态码（对应 PHP 的 `header()` / `http_response_code()`）；
- `RESP.redirect(url, code=302)` —— 便捷重定向（等价于 PHP 的 `header('Location: ...')`）；
- `RESP.json(data)` —— 便捷 JSON 响应（自动设置 Content-Type 并序列化）；参考 PHP 实现，**不主动退出**渲染，脚本需自行终止后续输出以防残留文本污染 body（Mako 模板顶层 `<% %>` 块内 `return` 即可终止渲染）；
- `RESP.setcookie(name, value, ...)` —— 设置 cookie（对应 PHP 的 `setcookie()`）。

### 第二期扩展（暂不实现）

- `_FILES` —— 文件上传（对应 PHP 的 `$_FILES` / `move_uploaded_file`）。

### 说明

- 跨请求持久化不提供内置支持，脚本自己读写文件即可（本机可信环境）；
- CLI 模式下 bridge 的降级语义见「运行方式」一节，`echo()` 在 CLI 下照常输出（随渲染结果写入 stdout）；`_SESSION` 读取为空、写入随 cookie 设置一同 no-op。

## 路径解析

- 程序与配置中统一用 **root** 指代文档根目录；
- makoserver.py 可直接作为 WSGI 入口使用（文件导出 `application` 函数），无需另写入口脚本；
- **WSGI 挂载场景**：假设 Apache 配置了 `WSGIScriptAlias /app1 /path/to/makoserver.py`，且配置中 root 为 `/home/data/mako`。用户请求 `http://192.168.1.11/app1/demo/demo.mako` 时，`/app1` 挂载前缀由 WSGI 环境（SCRIPT_NAME）提供并被剥除，剩余部分 `demo/demo.mako` 拼到 root 上，解析为模板文件 `/home/data/mako/demo/demo.mako`；
- **独立 Flask 模式**：同一 root 下，请求 `http://localhost:5000/demo/demo.mako` 没有挂载前缀，直接解析为 `/home/data/mako/demo/demo.mako`——两种模式下相同的 URL 尾部对应同一个模板文件，方便本机开发与 WSGI 部署行为一致；
- **index 兜底**：仍以 WSGI 场景为例，用户请求 `http://192.168.1.11/app1`（或 `/app1/`）时，在 root（`/home/data/mako`）下依次寻找 `index.mako`、`index.html`、`index.htm`，哪个存在就渲染/返回哪个，全部不存在则 404。

## 配置文件

- 全局默认配置（默认端口、默认文档根目录等）：`~/.config/makoserver/settings.json`；`_SESSION` 的签名密钥（secret）可在此显式配置覆盖，未配置时按本机指纹派生（详见「Bridge API」一节）；
- 可选键 `access_log` / `error_log`：值为文件路径，配置后请求日志 / 错误日志分别写入对应文件；不配置时的默认流向：access log 不落盘、error log 走 stderr（详见「非功能需求」日志一节）。日志文件路径不得默认指向文档根目录，避免被静态分支回吐泄露；
- 命令行参数优先级高于配置文件：单独运行时命令行指定的根目录、端口等覆盖配置文件中的同名项；
- WSGI 模式下按以下顺序查找配置文件，命中即用：
  1. 环境变量 `MAKOSERVER_CONF` 指定的路径；
  2. WSGI 入口脚本同目录下的 `makoserver.json`；
  3. 兜底 `~/.config/makoserver/settings.json`。
- 若希望"配置随站点目录走，一个目录拷走就能跑"，做法是把 WSGI 入口脚本和 `makoserver.json` 一起放进站点目录（利用第 2 条规则），配置中的相对路径以配置文件所在目录为基准解析。

## 运行方式

- 整个 MakoServer 自身代码只有 `makoserver.py` 一个文件，第三方依赖仅 Flask、Mako 两个，除此之外不依赖任何第三方库，拷走单文件就能部署；
- 这个 MakoServer 可以单独运行，指定一个根目录和端口就能启动一个 HTTP Server 提供页面服务；
- 这个 MakoServer 也可以按 WSGI 的模式运行，它会寻找配置文件，从里面解析出根目录；
- 还可以单独传入一个 .mako 脚本，就像命令行运行 `php xxx.php` 那样渲染出来，结果写到 stdout；
- CLI 模式下 bridge 对象参考 PHP CLI 的降级语义：请求参数字典为空、请求方法为 `GET`、请求 body 为空、cookie 读取为空；`RESP.header()` / `RESP.status()` / `RESP.setcookie()` 等响应控制调用静默无效（no-op），不报错——保证同一个 .mako 脚本在 HTTP 和 CLI 两种模式下都能运行。

## 非功能需求

- 并发模型：第一期使用 Flask 自带 dev server 即可，不追求生产级并发能力；
- 依赖版本：受 Python 3.8 地板约束，`Flask<3.1` / `Mako<1.3`（部署时可钉版本上界，避免未来主版本破坏性改动影响 MakoServer）；
- 模板编译：一律在内存中进行，`module_directory` 不启用，确保文档根目录可只读挂载且不产生 `__pycache__` / `.pyc` 污染（`module_directory` 会落盘编译后 `.py` 并经 import 系统写 `__pycache__`，既破坏只读 root 又可能被静态分支回吐编译后源码）；
- 日志：
  - access log 默认不落盘：独立 dev 模式走 Werkzeug 控制台默认输出，WSGI 模式交由宿主（Apache `access_log` / gunicorn `--access-logfile`）负责，MakoServer 不重复记录；配置了 `access_log` 文件路径后由 MakoServer 主动记录请求日志（含 WSGI 模式，此时与宿主日志并存，是否双写由使用者取舍）；
  - error log（含 5xx traceback）默认写 stderr；可由配置项 `error_log` 指定文件覆盖，`access_log` 同理可选；
  - 配置了文件路径即由使用者自行管理滚动（logrotate / 容器日志收集），框架不内置日志轮转；
  - 日志文件路径不得默认写入文档根目录——否则会被静态分支当作文件回吐，泄露访客 IP / 探测路径 / 服务端 traceback。
