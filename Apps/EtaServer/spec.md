# EtaServer 技术规格

Eta 模板引擎 + Node.js 内置 HTTP 的 PHP 风格动态页面服务：文件路径即路由，指定一个文档根目录即可服务其下全部 .eta 脚本；另内置 CLI 渲染模式（类 `php script.php`）。单文件实现，运行时依赖仅 `eta`，以 npm 包形式发布支持 `npx` 一行启动。

## 架构

```
CLI (parseArgs)
  ├─ 无位置参数 → startServer(root, port, host)   # HTTP 模式，唯一公开启动 API
  │    └─ http.createServer → handleRequest  # 每请求
  │         ├─ URL 解析 / 路径规范化 / 防穿透（请求态 parsed 逐层传参，
  │         │    ctx 仅存启动期不可变配置，决策 #14）
  │         ├─ 模板分支  → renderTemplate(parsed, ...)
  │         │    ├─ readBody（64MB 上限，超限排水后 413，决策 #14）
  │         │    ├─ 组装 bridge 数据（_GET/_POST/_SERVER/.../RESP/require）
  │         │    ├─ fs.readFileSync + eta.renderStringAsync()
  │         │    └─ 装配响应头（RESP 记录 + session 重签）→ writeHead/end
  │         ├─ 目录分支  → 301 补斜杠 → index.eta / index.html / index.htm
  │         │    （兜底候选逐个 realpath 校验，决策 #12）
  │         └─ 静态分支  → 白名单扩展名 → GET/HEAD 校验 → stream pipe
  └─ 首个位置参数 → renderCli(script, args)   # CLI 渲染模式（决策 #11）
       ├─ script='-' 时从 stdin 读源（base 目录 = cwd）
       ├─ bridge 降级（固定 _SERVER + argv，空 _GET/_POST/_SESSION 等）
       └─ renderStringAsync 后按 body 优先级写 stdout，异常 exit 1
```

单文件 `eta-server.js`（约 950 行），运行时依赖仅 `eta`。

## 关键决策

### 决策 #1：用 `renderStringAsync` 而非 Eta 的文件加载 API

Eta v3 实例没有 `renderFile`（v2 旧 API），`render` / `renderAsync` 的文件解析对绝对路径处理有 bug（会把 `views` 前缀二次拼接，Windows 下实测报 `Could not find template: demo\demo\api.eta`）。因此**服务端自己 `fs.readFileSync` 读源文件，再调 `renderStringAsync(src, data)`**：

- 绕开 Eta 文件解析的全部怪异行为；
- 每次请求读盘，mtime 热更新天然成立（无需 eta 的 cache 机制，`cache: false` 只是保险）；
- 模板内 `include("./header")` 仍由 Eta 解析（Eta v3 模板函数名为 `include`，非 v2 的 `includeFile`；renderStringAsync 编译时未传 filepath，故相对 `views`（HTTP 模式即文档根、CLI 模式即脚本所在目录/cwd，见决策 #11）解析），与「相对当前模板目录」的常见模板引擎语义有差异（见已知限制）。

### 决策 #2：Eta 配置

```js
new Eta({ views: root, cache: false, useWith: true, autoTrim: false })
```

- `useWith: true` —— 模板内裸名访问 bridge 变量（`_GET.name` 而非 `it._GET.name`），`it.` 前缀写法同时有效，最大化 PHP 手感；
- `autoTrim: false` —— Eta 默认吞掉标签紧邻的换行（`<%= x %>\n` 后的 `\n` 被吃），按「源码忠实保留」原则关闭；文本模板的响应体逐字节忠实于源文件；
- `cache: false` —— 配合决策 #1，每次请求编译。模板量大的场景有性能代价，可信环境接受。

### 决策 #3：`require` 锚定模板目录

模板不是模块（`new Function` 体），默认无 `require` / `import`。bridge 注入：

```js
require: createRequire(scriptAbs)
```

- 相对说明符以 .eta 文件所在目录为基准；
- 裸说明符沿目录向上搜索 `node_modules`；
- 与「同目录 .js 文件」的 Node 原生行为一致；
- ESM 静态 `import` 语法不可用（非模块作用域），需要时用 `await import()` 动态形式；
- **模板内可 require `.ts` 文件**：Node 22.18+ 内置类型剥离（无需任何依赖），因此「模板 JS 薄壳 + 逻辑下沉 .ts 库文件」是推荐分工；限制：仅可擦除语法（enum / namespace / 参数属性会报错）。模板代码块本身不经过类型剥离（`new Function` 编译路径），故 `<% %>` 内仍只能写 JS；`engines.node >= 22.18` 即为此特性而设。

### 决策 #4：`<%= %>` 默认转义（Eta 原生 autoEscape）

`<%= %>` 输出经 HTML 转义（`"` → `&quot;` 等），原样输出用 `<%~ %>`。这是安全导向的默认选择（区别于「原样输出 + 手动 escape」方向），模板写 JSON/纯文本时用 `<%~ %>`。bridge 同时提供 `escape()` 函数供显式转义。

### 决策 #5：session 自实现，零依赖

签名 cookie 方案全自实现，不引 express-session：

- cookie 名 `etasess`，值 = `base64url(payload) + '.' + base64url(HMAC-SHA256(secret, payload))`；
- payload = `{ d: 会话数据, e: 过期时间戳 }`，时间戳在签名覆盖范围内；
- `timingSafeEqual` 比对签名，长度不等先行拒绝；
- 滑动超时 30 分钟（`SESSION_TTL`），会话非空时每次响应重签刷新；
- 会话为空但请求携带 cookie 时下发 `Max-Age=0` 清除；
- 密钥派生：`SHA256('eta-server|hostname|username|homedir|全部非零MAC排序后逗号连接|realpath(root)')`，不落盘、同机稳定、跨机不同、**同机不同 root 亦不同**（决策 #13）。MAC 混入**全部**网卡而非首个：枚举顺序无跨重启保证且可能选中虚拟网卡，只取首个会在网卡顺序变化时静默失效全部 session（review 修正）；`os.userInfo()` / `networkInterfaces()` 均带 try 兜底；
- cookie 属性固定 `Path=/; HttpOnly; SameSite=Lax`，不设 Max-Age（浏览器会话 cookie）。

### 决策 #6：输出模型——渲染返回后才发响应

Eta 渲染是纯函数（返回完整字符串），天然没有 headers-already-sent 问题：`RESP.header()` / `status()` 只是往 `resp.headers` 数组里记，渲染完成后统一装配。响应体优先级：

1. `resp.binary !== null`（`RESP.writeraw` 触碰过）→ 二进制缓冲，短路文本；
2. `resp.text !== null`（`RESP.json()` 调过）→ JSON 字符串；
3. 否则渲染出的 html。

`RESP.json()` 不主动终止渲染，脚本用顶层 `return` 自行退出（Eta 模板代码块在函数体内，`return` 可用，demo/api.eta 即此写法）。

### 决策 #7：路由与静态文件语义

- 路径规范化：`decodeURIComponent(pathname)` 失败 → 404；`\0` → 404；`path.resolve(root, '.' + pathname)` 后前缀校验，越界 → 404（与「不存在」同响应，fail-closed）；
- PATH_INFO：`lower.indexOf('.eta/')` 切分脚本与尾挂（取第一个命中），尾挂随 `_SERVER.PATH_INFO` 传入；
- 目录：无尾斜杠 301 补（`Location` 保留 query string），再依次 `index.eta`（走模板管线）/ `index.html` / `index.htm`；
- 静态白名单见 `STATIC_TYPES`（38 种：网页 / 文本 / 数据 / 图片 / 字体 / 音视频 / wasm / 压缩包，`.js`/`.mjs` 为 `text/javascript`），白名单外 404；存在但谓词非 GET/HEAD → 405 + `Allow: GET, HEAD`（白名单优先，404 不因 405 泄露存在性）；
- 服务器自身文件（`SELF_PATH`）命中即 404，防止 docroot 恰好是包目录时回吐源码。

### 决策 #8：零依赖原则

HTTP 用 `node:http`、session 用 `node:crypto`、CLI 手写解析——除 `eta` 外无运行时依赖。目标：`npx -y eta-server` 冷启动快、供应链面小、发包无争议。

### 决策 #11：CLI 渲染模式（php 风格单脚本渲染）

```
eta-server [options] script [args...]
  script    被渲染脚本路径（不限 .eta 扩展名，对齐 php foo.txt 照跑；
            文件不存在 → stderr 报错 exit 1）；传 `-` 时从 stdin 读源渲染
  args...   脚本名之后的一切参数不解析、原样透传，
            脚本经 _SERVER.argv 读取，argv[0] = script 自身（对齐 PHP $argv）
```

- **模式判定**：parseArgs 遇首个非选项位置参数即进 CLI 模式，其后一律 break（脚本名后的参数即使形如 `-p` 也原样透传，argparse REMAINDER 同语义）；无位置参数才进 HTTP 服务模式。位置参数出现在 `-r` / `-p` / `-H` 之前或之后均可（选项照常吃掉各自的值）；
- **stdin 渲染**（`script` = `-`）：`fs.readFileSync(0)` 读 stdin 全量字节按 UTF-8 解码（BOM 容忍，与文件加载一致；Node 的 readFileSync 读 fd 0 对管道 / 文件 / 交互终端均工作）；`views` / include / require 基准 = **cwd**（无脚本文件时的唯一自然锚点）；`_SERVER.SCRIPT_NAME` / `SCRIPT_FILENAME` = `'-'`、`SCRIPT_DIRNAME` = cwd、`argv[0]` = `'-'`（PHP CLI 读 stdin 时同为 `'-'`）；require 锚点用 `createRequire(path.join(cwd, 'stdin.js'))`（createRequire 只取路径形状做解析基准，文件无需存在）；
- **bridge 降级**：`_SERVER` 固定降级值——REQUEST_METHOD=GET、QUERY_STRING/PATH_INFO/CONTENT_TYPE/CONTENT_LENGTH/REMOTE_ADDR/SERVER_NAME/SERVER_PORT 空串、REQUEST_TIME / REQUEST_TIME_FLOAT 渲染开始时刻、argv 透传；**不设** REQUEST_URI / DOCUMENT_ROOT / REQUEST_SCHEME / HTTP_*（CLI 无 URL / root / scheme 概念，PHP CLI 亦无）；`_GET`/`_POST`/`_REQUEST`/`_COOKIE` 空对象、`_SESSION` 空对象（写无副作用，CLI 不发 cookie）、`_BODY` 空 Buffer、`_JSON` null；
- **RESP**：照常注入，header/status/redirect/setcookie 仅记录不产生副作用（渲染返回后无任何响应装配）；writeraw / json 参与 body 选择（优先级同 HTTP：binary > text > 渲染文本），属输出而非响应控制，不受 no-op 规则影响；
- **include / require 基准**：文件渲染 = 脚本所在目录（Eta 实例 `views` = 该目录；require 锚定脚本绝对路径，决策 #3 同规则）；stdin 渲染 = cwd；
- **输出**：渲染成功后按 body 优先级写 `process.stdout`（原始字节，二进制安全）。渲染异常 → stack 写 stderr、exit 1，stdout 零输出（Eta 纯函数渲染天然无 partial output，无需额外防护）；文件不存在 → `eta-server: no such file: X`、exit 1；
- **不实现 PHP exit() flush 语义**：Eta 渲染是纯函数，输出仅在渲染完整返回后一次性产出，无法在中途 flush 已缓冲内容；脚本中途停止输出用顶层 `return`（模板代码块在函数体内），强行 `process.exit(code)` 会丢弃全部已生成输出直接退出（Node 语义，不设防、不兜底）；
- **不读任何配置**（本无配置文件机制）；`-r` / `-p` / `-H` 在 CLI 模式静默接受但不产生作用（PHP 式宽容）；
- `renderCli(script, args)` 一并导出（module.exports），供测试 / 编程调用。

### 决策 #12：路径加固（realpath 容器校验 + Windows 特判）

字符串前缀检查只挡得住文本层穿透，挡不住文件系统层的逃逸，故补齐一整套加固：

- **realpath 容器校验**：stat 命中后 `fs.realpathSync` 解析真实位置，与 `realpathSync(root)`（startServer 时一次性算好存 `ctx.rootReal`）做包含校验，不在容器内 → 404。**root 内指向外部的 symlink / Windows junction 一律 404**（模板分支与静态/目录分支同规则）；容器内的链接照常服务（扩展名按 realpath 判定）；
- **Windows 保留设备名**：路径段匹配 `^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$`（不区分大小写、带不带扩展名）→ 404（仅 win32）；
- **NTFS 备用数据流**：路径段含 `:`（`foo.txt::$DATA` / `foo:bar`）→ 404（仅 win32；`%3A` 解码后同样命中）；
- **尾部点/空格归一**：Win32 开文件时静默丢弃尾部 `.` / 空格（`demo.eta.` 实际打开 `demo.eta`），故在扩展名判定前先对解码后 pathname 做 `replace(/[. ]+$/, '')`，保证扩展名决策与文件系统实际行为一致（POSIX 不做，同名文件真不存在 → 404）；
- **重复斜杠 308 归并**：`//a///b` → 308 `/a/b`（Location 保留 query string）。先在**原始 URL** 上检查（`new URL('//a')` 会把前导 `//` 当协议相对误析主机），再对解码后 pathname 查一次（覆盖 `%2f` 编码的斜杠）；
- **index 兜底候选逐个校验**（review 补漏）：目录本身过了容器校验，但 `index.eta` / `index.html` / `index.htm` 可能是目录内指向 root 外的链接，故逐候选过 `realInside`，逃逸即 404（fail-closed，不回退下一候选）；
- **Location 编码**：解码态 pathname 拼 Location（目录 301、解码层 308）时逐段 `encodeURIComponent`（非 ASCII / 空格不裸写进头）；原始 URL 层 308 与 query string 保持原文；
- Windows `%5c`（反斜杠）解码后成为路径分隔符：`path.resolve` 归一后照走文本层包含校验与 realpath 容器校验，逃逸同样 404，无额外分支（影响仅限容器内语义，记此备忘）；
- 原有规则不变：`\0` 拒绝、`path.resolve(root, '.' + pathname)` 后文本层包含校验、SELF_PATH 屏蔽。

### 决策 #13：session 加固（4KB 上限 + 密钥混 root + 名称独占）

三项 session 健壮性机制：

- **4KB 上限**（`SESSION_COOKIE_LIMIT = 4096`）：重签时校验整条 Set-Cookie 字节长（`Buffer.byteLength`），超限 → 500（错误页含 "about 4KB" 字样）。浏览器对超大 cookie 静默丢弃，不如显式失败；
- **密钥混入 root**：`deriveSecret(rootDir)` 的 seed 追加 `realpathSync(root)`——同机不同文档根的站点密钥不同，A 站 session cookie 投 B 站验签失败按无 session 处理；CLI 模式不用 session 不参与；函数一并导出供测试；
- **session cookie 名独占**：`RESP.setcookie('etasess', ...)` 与框架 session 同名，该条丢弃不下发并向 stderr 打 warning（下发两条同名 Set-Cookie 的浏览器取舍未定义）；`RESP.header('Set-Cookie', ...)` 原始通道不做名称检查（原始逃生舱，信任模板作者，同名冲突后果自负）。

### 决策 #14：每请求状态隔离（review 后的结构性修正）

外部 review 实证发现并修复的三类问题：

- **`ctx.parsed` 跨请求串号**（最严重）：原实现把本次请求的 URL 解析结果写进所有请求共享的 `ctx`，而 `renderTemplate` 在 `await readBody()` 之后才读它——两次 await 之间任何第二个请求到达都会覆盖前者。实测 8MB POST 并发探针下 80 个请求 71 个 `_GET`/`QUERY_STRING` 串号。修正：**`ctx` 只留启动期不可变配置**（root/rootReal/host/port/secret/eta），请求态（`parsed`）改为参数逐层传入 `renderTemplate`；架构图中 `ctx.parsed` 字段删除；
- **413 交付语义**：原实现超限立即 `req.destroy()`，客户端只能收到 ECONNRESET 永远看不到 413（PRD 承诺「超限返回 413」落空）。修正：超限后**继续排水**（丢弃后续 chunk，内存有界），客户端上传完毕后正常回 413，连接可复用（body 已消费完）；代价是响应在上传完成后才到达（同 Werkzeug 行为）；
- **原型键污染**：`_GET` / `_POST` / `_REQUEST` / `_COOKIE` / form 解析结果一律 `Object.create(null)`（`?__proto__=x` / `?constructor=x` 只作普通数据键，不影响字典行为）。

另有一组小修正同批落地：`RESP.status()` 存原始值不 coercing（原 `Number(code) || 200` 会把 `status('abc')`/`status(0)` 静默归 200），校验提前到渲染刚结束时（非法 code 不再浪费 session 重签）；端口参数校验收紧为 1–65535 整数（原 `Number()` 后判空，浮点/负数/越界都能通过）；`startServer` 的 `error` 监听在 listen 成功后摘除（避免后续 server 级错误 reject 已 settle 的 Promise）。

## Bridge API 清单

| 名字 | 类型 | 说明 |
|---|---|---|
| `_GET` / `_POST` / `_REQUEST` | object | query / form-urlencoded / 二者合并（后覆盖前） |
| `_SERVER` | object | 见下 |
| `_COOKIE` | object | percent-decode 后的 cookie 字典 |
| `_SESSION` | object | 签名 cookie session（决策 #5），整条 cookie 超 4KB → 500（决策 #13） |
| `_BODY` | Buffer | 原始请求体（对标 `php://input`） |
| `_JSON` | object/null | Content-Type 含 `json` 子串（覆盖 `application/json`、`application/*+json`、`text/json`）时自动解析，解析失败 / 非 json → null |
| `RESP` | object | `status/header/redirect/setcookie/json/writeraw/escape`（status 存原始值、渲染后校验：非 100–999 整数 → 500，决策 #14；setcookie 与 session 同名 → 丢弃，决策 #13） |
| `escape(v)` | function | HTML 转义（`& < > " '`），返回字符串；`RESP.escape` 为同一函数 |
| `require(spec)` | function | 锚定模板目录的 Node require（决策 #3） |

`_SERVER` 键：`REQUEST_METHOD`、`QUERY_STRING`（原始请求行截取，编码态原文）、`REQUEST_URI`（req.url 原文）、`SCRIPT_NAME`、`PATH_INFO`、`SCRIPT_FILENAME`、`SCRIPT_DIRNAME`、`DOCUMENT_ROOT`、`REMOTE_ADDR`、`CONTENT_TYPE`、`CONTENT_LENGTH`、`SERVER_NAME`、`SERVER_PORT`、`REQUEST_SCHEME`（恒 `http`）、`SERVER_PROTOCOL`（`HTTP/` + req.httpVersion）、`REQUEST_TIME` / `REQUEST_TIME_FLOAT`（请求开始时刻，HTTP 与 CLI 两模式均设）、以及 `HTTP_*` 请求头（大写、`-`→`_`）。

## 错误页

统一 `errorPage(code, title, detail)`：等宽字体 + `<pre>` 转义详情；500 附完整 stack。渲染中途抛异常即整体转 500（无 partial output，Eta 纯函数渲染天然满足）。`res.headersSent` 后出错直接 `res.destroy()`。

## 测试

- `tests/test_server.js`：spawn 子进程起服务（端口 5177），fetch 断言 HTTP 模式；
- `tests/test_cli.js`：spawnSync 断言 CLI 渲染模式（决策 #11）：文件渲染字节精确、argv 透传（argv[0]=脚本自身、脚本后含 `-H` 等形如选项的参数原样透传）、降级 `_SERVER` 键集与空 bridge、不限扩展名（.txt 照渲染）、文件不存在 / 渲染异常 exit 1 且 stdout 干净、include 基准=脚本目录、require 锚定脚本目录、writeraw / json 短路、RESP 响应控制 no-op、BOM 容忍、尾部换行保留、选项在脚本名前照常接受；stdin（`-`）渲染、三键降级（SCRIPT_NAME/FILENAME='-'、SCRIPT_DIRNAME=cwd）、argv[0]='-'、include/require 基准=cwd、异常 exit 1、BOM 容忍。

HTTP 模式断言 41 项：

- 渲染：index.eta、`/` 兜底、query 参数；
- 目录：301 补斜杠、index.html 兜底、**逃逸 index 候选逐个 404（含旁有合法 index.html 仍 fail-closed）**；
- 静态：Content-Type、405、白名单外 404、扩容类型矩阵（csv/md/js/webm 逐类型断言，`.js` = text/javascript）；
- 安全：404、`../` 穿透 404、**realpath 逃逸（junction/symlink 出 root → 404，模板与静态两路）、容器内 symlink 照常服务、DOS 设备名、NTFS ADS、尾部点平台分岐、重复斜杠 308（裸 `//` 与 `%2f` 编码两路）**；
- PATH_INFO 尾挂（`<%~ %>` 原样输出 JSON 数组）；
- API：GET echo、form POST、JSON body、**+json Content-Type 进 `_JSON`**、**超 64MB body 客户端实测收到 413**；
- bridge：**HTTP `_SERVER` 含 SERVER_PROTOCOL / REQUEST_TIME(_FLOAT)**、**原型键（`__proto__`/`constructor`/`hasOwnProperty`）只作普通数据键**；
- **并发：8×4MB POST 与 40 个 tag GET 重叠窗口，逐请求断言 `_GET` 不串号（决策 #14，对旧 `ctx.parsed` 实现有判别力，已实证还原复测）**；
- session：三级链式 cookie 计数 1→2→3、篡改签名拒绝（count 归 1）、**超 4KB → 500、deriveSecret 混 root 单元断言、setcookie 同名独占（不下发 + 仅框架一条）**；
- RESP：**status(9999) / status(0) / status('abc') → 500、RESP.escape 与 escape() 等价**；
- require：demo 页渲染；
- 500：broken.eta（引用未定义函数）。

跑法：`npm test`（测试本体需 Node 18+（全局 fetch）；`engines.node >= 22.18` 是模板内 `require(.ts)` 类型剥离特性的要求，纯测试场景 npm 对 engines 警告不阻断；依次跑 test_server.js 与 test_cli.js）。

### 决策 #9：模板 JS + 逻辑 TS 的分工，零依赖

模板代码块经 `new Function` 编译，不经过模块加载器，Node 类型剥离帮不上忙，故 `<% %>` 内只能写 JS。但注入的 `require` 支持直接加载 `.ts`（Node 22.18+ 内置类型剥离，实测通过），分工与 PHP 生态一致：模板保持薄壳，重逻辑下沉 `lib/*.ts`。仅支持可擦除语法（enum / namespace / 参数属性不可用）。不引 ts-node / tsx / typescript，`dependencies` 保持只有 `eta`；`engines.node` 相应提到 `>=22.18`。

### 决策 #10：模板内网络请求 —— 顶层 await + 内置 fetch

服务器为单进程单线程（Node 默认模型），但异步 I/O 不阻塞事件循环：`renderStringAsync` 把模板编译为 async function 体，代码块内可直接顶层 `await`，配合 Node 内置 `fetch`（零依赖）请求其他 URL；等待期间其它请求照常处理（demo/fetchdemo.eta 在模板里 await fetch 本服务自己的 hello.eta，若事件循环被阻塞此页必死锁——渲染成功即为非阻塞实证）。约定：外部 URL 必加 `AbortController` 超时保护，否则吊死的外部服务会把该请求的响应永远挂住；fetch 失败走模板内错误分支而非 500。另有一条通用陷阱记入 demo 注释：**代码块的注释里勿书写标签字面量**，Eta 解析器是纯文本扫描，注释内出现 `<%` 会误判标签边界、整块代码被当字符串（实测踩过，错误表现为后续块 ReferenceError）。

## 已知限制

- 无 HTTPS（本机定位，反代自理）；
- 无 multipart 解析（`_FILES` 二期，请求体原样进 `_BODY`）；
- 无配置文件/日志；session TTL 硬编码 30 分钟、仅 sliding 模式、cookie 名固定（可配置 TTL / 超时模式 / cookie 名留待配置文件二期）；
- **无资源护栏**：64MB body 上限为单请求值，不限并发连接数，总内存无上界；无请求级超时（slow-body 客户端可无限挂连接）——本机可信定位接受，公网部署须反代层兜底；
- 413 响应在客户端上传完成后才送达（超限后排水而非断连，决策 #14）；
- `_GET` / `_POST` / `_REQUEST` 为普通对象，同名参数多值后覆盖前（无 `getlist` 风格的多值访问 API）；
- 模板 include 相对 `views`（HTTP 模式为文档根、CLI 模式为脚本所在目录 / cwd）而非模板自身目录；
- CLI 模式无 PHP exit() 的 flush-then-exit 语义（Eta 纯函数渲染无中途 flush 途径，决策 #11）；
- `RESP.write()` 是显式抛错的占位（提示用模板文本输出），勿按 PHP `echo` 习惯使用。

## 发布

```
npm publish          # bin: eta-server -> ./eta-server.js
npx -y eta-server -r ./www -p 5000
```

未发布前可用 `npm link` 本地试用；仓库独立后直接 `npm publish` 即可。
