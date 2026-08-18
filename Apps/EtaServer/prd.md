# EtaServer

使用 Eta + Node.js 做一个类似 PHP 的系统。使用 EtaServer 以后，用户新建动态页面或者纯 HTTP/JSON 接口，只需要在文档根目录内新增 .eta 文件即可，不用改到服务器端任何代码。

## 项目定位

EtaServer 是「文件路径即路由 + PHP 超全局 bridge」的轻量动态页面服务：指定一个文档根目录，即可为根目录下所有 .eta 脚本提供页面与接口服务，新增页面 / JSON 接口只需新增文件，零服务端代码。以 npm 包形式发布，支持 `npx -y eta-server -r root -p 5000` 一行启动；同时内置 CLI 渲染模式，可像 `php script.php` 一样直接渲染单个脚本。

## 定位与安全边界

- 本项目定位为**本机/可信环境**使用的轻量动态页面服务，不做公网暴露场景的安全加固；
- .eta 模板本质是执行任意 JavaScript 代码，等同本机运行脚本，使用者须知悉。

## 分发形态

- npm 包名 `eta-server`，`bin` 入口同名，支持 `npx -y eta-server -r ./www -p 5000` 直接启动；
- 主程序为单文件 `eta-server.js`（带 shebang，兼作 CLI 与库入口，`require` 后可编程调用 `startServer()`）；
- 除 `eta` 模板引擎外**零运行时依赖**：HTTP 服务用 Node 内置 `http`，session 用内置 `crypto` 签名 cookie 自实现，命令行解析手写。

## 模板服务

- 基于 Eta / Node.js，提供一套类似 .php 的网页服务；
- 用户请求 `http://localhost:5000/web/demo.eta` 的话，就会解析出相对路径，到文档根目录下寻找对应 .eta 文件并渲染返回；
- 启动后指定一个文档根目录，就能为下面的所有 .eta 脚本提供页面服务，用户写新的动态页面，新增 .eta 文件就行，不必改服务端任何一行代码；
- 如果请求的是非 .eta 文件，走静态文件服务：按**内置扩展名白名单**（网页 .html/.htm、文本 .txt、.css、.js、数据 .json、常见图片、.pdf、常见压缩包，完整表见 spec）返回对应 Content-Type 与原始字节；**白名单之外一律 404**，默认拒绝（fail-closed）；白名单内且存在的文件仅接受 GET/HEAD，其它谓词返回 405 Method Not Allowed（附 `Allow: GET, HEAD` 头）；.eta 脚本则全谓词渲染，`REQUEST_METHOD` 如实传递给脚本；
- 能够防止相对路径穿透到文档根目录以外；**文件系统层逃逸同样拒绝**：root 内指向外部的 symlink / junction 经 realpath 容器校验后 404；Windows 保留设备名（NUL/CON…）、NTFS 备用数据流（`$DATA`）404；尾部点/空格按 Win32 开文件语义归一；重复斜杠 308 归并（`//a` → `/a`）；
- 请求映射到目录（含 `/`）：URL 末尾无 `/` 时先 301 重定向补斜杠（对齐 Apache `DirectorySlash`），再依次尝试追加 `index.eta`、`index.html`、`index.htm`；
- 支持 PATH_INFO 尾挂机制：请求 `xxx.eta/尾挂路径`（如 `/index.eta/hello`）时渲染 `xxx.eta`，尾挂部分（`/hello`）经 `_SERVER['PATH_INFO']` 传入；静态文件不带尾挂；
- 更新检测：模板引擎关闭缓存（`cache: false`），每次请求读盘编译，改完即生效；
- 错误处理：.eta 脚本编译错误或运行时异常时，返回 500 + 错误内容页面（含转义后的错误信息与调用栈）；
- 请求体大小默认上限 64MB，超限在客户端上传完成后返回 413（排水语义，不断连）；
- **每请求隔离**：bridge 数据与 URL 解析结果均为每请求独立（不存共享可变状态），并发请求间参数不串号；
- 404 处理：文件不存在或路径穿透被拒绝时，统一返回 404，不区分「不存在」与「被拒绝」；
- 编码：文本输出统一 UTF-8。

## Bridge API

Node 端向 .eta 模板暴露的变量/函数，命名与语义对标 PHP 超全局变量。Eta 配置开启 `useWith`，模板内可**裸名访问**（`_GET.name` 而非 `it._GET.name`），`it.` 前缀写法同样有效。

### 请求（仿 PHP 超全局变量命名）

- `_REQUEST` —— 合并的请求参数字典（query 与 form post 合并，后者覆盖前者）；
- `_GET` / `_POST` —— GET 与 POST 参数字典分开访问；`_POST` 仅解析 `application/x-www-form-urlencoded`，JSON 请求体进 `_JSON`；
- `_SERVER` —— 请求环境信息字典，至少包含：`REQUEST_METHOD`、`QUERY_STRING`、`REQUEST_URI`、`SCRIPT_NAME`、`PATH_INFO`、`SCRIPT_FILENAME`、`SCRIPT_DIRNAME`、`DOCUMENT_ROOT`、`REMOTE_ADDR`、`CONTENT_TYPE`、`CONTENT_LENGTH`、`SERVER_NAME`、`SERVER_PORT`、`REQUEST_SCHEME`、`SERVER_PROTOCOL`、`REQUEST_TIME` / `REQUEST_TIME_FLOAT`、以及 `HTTP_*` 形式的客户端请求头；
- `_BODY` —— 原始请求 body（Buffer，对应 PHP 的 `php://input`）；若 Content-Type 为 JSON 则同时提供 `_JSON`（自动解析成对象，否则为 null）；请求体大小默认上限 64MB，超限返回 413；
- `_COOKIE` —— 客户端 cookie 字典（值经 percent-decode）；
- `_SESSION` —— 会话对象：基于**签名 cookie + 时间戳**，无服务端存储；cookie 固定 `Path=/; HttpOnly; SameSite=Lax`，浏览器会话 cookie（不设 Max-Age）；滑动超时（默认 30 分钟，每次响应重签刷新）；签名密钥由本机指纹（hostname + 用户名 + home 目录 + 网卡 MAC + 文档根 realpath 的 SHA256）派生，无需落盘即可同机稳定、跨机不同、**同机不同站点亦不同**；整条 cookie 超 4KB → 500（浏览器静默丢弃不如显式失败）；值仅支持 JSON 可序列化类型；数据客户端可见（只防篡改不防偷看）。

### 模块加载

- `require(spec)` —— 按模板文件所在目录锚定的 Node `require`（`module.createRequire(scriptPath)`）：相对说明符以 .eta 文件目录为基准，裸说明符沿目录向上搜索 `node_modules`，与「同目录的 .js 文件」行为一致；
- ESM 静态 `import` 语法不可用（模板编译为 `new Function` 体，非模块），需要 ESM 时用 `await import()` 动态形式；
- **模板代码块只能写 JS，但业务逻辑可用 TypeScript**：模板里直接 `require('./lib/util.ts')` 即可，由 Node 22.18+ 内置类型剥离支持，零额外依赖；仅限可擦除语法（类型注解 / interface / type / 泛型可用，enum / namespace / 参数属性不可用）；模板保持薄壳，重逻辑下沉到 .ts 库文件。

### 输出与响应

- 模板普通文本与 `<%= %>` 插值照旧直接输出，**输出全程缓冲**，`RESP.header()` / `status()` 可在模板任意位置调用，不存在 headers-already-sent 限制；
- `<%= %>` 默认 HTML 转义（Eta `autoEscape`），原样输出用 `<%~ %>`；
- `escape(value)` —— HTML 转义函数（对标 `htmlspecialchars`，返回转义后字符串）；`RESP.escape` 为同一函数；
- `RESP.status(code)` / `RESP.header(name, value)` —— 设置状态码 / 响应头（status 非 100–999 整数 → 500）；
- `RESP.redirect(url, code=302)` —— 便捷重定向；
- `RESP.json(data)` —— 便捷 JSON 响应（自动设置 Content-Type 并序列化；**不主动退出**渲染，脚本需自行终止后续输出）；
- `RESP.setcookie(name, value, opts)` —— 设置 cookie，值默认 percent-encode 下发；**与 session cookie 同名（`etasess`）的条目丢弃不下发**（session 机制独占该名字，stderr 留 warning）；
- `RESP.writeraw(buf)` —— 二进制输出通道：追加 bytes，一旦使用即短路全部文本输出（模板文本与插值整体丢弃）；writeraw 不负责设置 Content-Type，需自行 `RESP.header()`；
- 默认 Content-Type：脚本未显式设置时为 `text/html; charset=utf-8`。

### 暂不实现（二期规划）

- `_FILES` —— 文件上传（multipart 解析）；
- 配置文件（ini / json）与日志文件；
- 绝对超时 / 自定义 session TTL 的 CLI 参数。

## CLI

```
eta-server -r <root> -p <port> [-H <host>]        # HTTP 服务模式
eta-server [options] script [args...]              # CLI 渲染模式
eta-server [options] - [args...]                   # 从 stdin 读脚本渲染
```

- `-r / --root`：文档根目录，默认当前目录（仅 HTTP 模式有效）；
- `-p / --port`：端口，默认 5000（仅 HTTP 模式有效）；
- `-H / --host`：监听地址，默认 127.0.0.1（仅 HTTP 模式有效）；
- `-h / --help`：帮助。

启动时打印横幅（版本、root 绝对路径、访问 URL）；端口占用（EADDRINUSE）给出友好报错。

### CLI 渲染模式

出现第一个非选项位置参数时进入 CLI 渲染模式，类似 `php script.php`：渲染单个脚本、结果写 stdout 后退出。规则（对齐 PHP CLI 习惯）：

- 脚本路径**不限扩展名**；文件不存在 → stderr 报错、退出码 1；
- `script` 为 `-` 时从 **stdin** 读取模板源渲染（POSIX 约定）；
- 脚本名之后的一切参数**不解析、原样透传**，脚本经 `_SERVER.argv` 读取，`argv[0]` = 脚本自身（stdin 时为 `'-'`）；
- include / require 基准目录 = 脚本所在目录（stdin 渲染为 cwd）；
- `_SERVER` 降级为固定值（REQUEST_METHOD=GET 等，不设 REQUEST_URI / DOCUMENT_ROOT / HTTP_*），bridge 其余成员降级（空 _GET/_POST/_COOKIE/_SESSION、空 _BODY）；RESP 的 header/status/redirect/setcookie 仅记录、无副作用；
- 输出体优先级与 HTTP 模式一致：writeraw 二进制短路 > RESP.json() > 渲染文本；
- 渲染异常 → 错误栈写 stderr、退出码 1，stdout 不输出任何内容；
- `-r` / `-p` / `-H` 等选项出现在脚本名之前照常接受但不产生任何作用（PHP 式宽容）。
