# EtaServer 技术规格

`Apps/MakoServer`（Python/Mako/Flask）的 JavaScript 对标实现：Eta 模板引擎 + Node.js 内置 HTTP，文件路径即路由的 PHP 风格动态页面服务，以 npm 包形式发布支持 `npx` 一行启动。

## 架构

```
CLI (parseArgs)
  └─ startServer(root, port, host)          # 唯一公开 API（module.exports）
       └─ http.createServer → handleRequest  # 每请求
            ├─ URL 解析 / 路径规范化 / 防穿透
            ├─ 模板分支  → renderTemplate()
            │    ├─ readBody（64MB 上限，超限 413）
            │    ├─ 组装 bridge 数据（_GET/_POST/_SERVER/.../RESP/require）
            │    ├─ fs.readFileSync + eta.renderStringAsync()
            │    └─ 装配响应头（RESP 记录 + session 重签）→ writeHead/end
            ├─ 目录分支  → 301 补斜杠 → index.eta / index.html / index.htm
            └─ 静态分支  → 白名单扩展名 → GET/HEAD 校验 → stream pipe
```

单文件 `eta-server.js`（约 600 行），运行时依赖仅 `eta`。

## 关键决策

### 决策 #1：用 `renderStringAsync` 而非 Eta 的文件加载 API

Eta v3 实例没有 `renderFile`（v2 旧 API），`render` / `renderAsync` 的文件解析对绝对路径处理有 bug（会把 `views` 前缀二次拼接，Windows 下实测报 `Could not find template: demo\demo\api.eta`）。因此**服务端自己 `fs.readFileSync` 读源文件，再调 `renderStringAsync(src, data)`**：

- 绕开 Eta 文件解析的全部怪异行为；
- 每次请求读盘，mtime 热更新天然成立（无需 eta 的 cache 机制，`cache: false` 只是保险）；
- 模板内 `includeFile("./header")` 仍由 Eta 解析，基准目录为 `views`（即文档根），与 Mako 的 include 相对当前模板目录的语义有差异，文档注明即可。

### 决策 #2：Eta 配置

```js
new Eta({ views: root, cache: false, useWith: true, autoTrim: false })
```

- `useWith: true` —— 模板内裸名访问 bridge 变量（`_GET.name` 而非 `it._GET.name`），`it.` 前缀写法同时有效，最大化 PHP 手感；
- `autoTrim: false` —— Eta 默认吞掉标签紧邻的换行（`<%= x %>\n` 后的 `\n` 被吃），对标 MakoServer「源码忠实保留」原则关闭；文本模板的响应体逐字节忠实于源文件；
- `cache: false` —— 配合决策 #1，每次请求编译。模板量大的场景有性能代价，可信环境接受。

### 决策 #3：`require` 锚定模板目录

模板不是模块（`new Function` 体），默认无 `require` / `import`。bridge 注入：

```js
require: createRequire(scriptAbs)
```

- 相对说明符以 .eta 文件所在目录为基准；
- 裸说明符沿目录向上搜索 `node_modules`；
- 与「同目录 .js 文件」的 Node 原生行为一致；
- ESM 静态 `import` 语法不可用（非模块作用域），需要时用 `await import()` 动态形式。

### 决策 #4：`<%= %>` 默认转义（Eta 原生 autoEscape）

`<%= %>` 输出经 HTML 转义（`"` → `&quot;` 等），原样输出用 `<%~ %>`。与 MakoServer 的 `${}` 不转义 + 手动 `escape()` 的方向相反——Eta 选择安全默认，模板写 JSON/纯文本时用 `<%~ %>`。bridge 同时提供 `escape()` 函数供显式转义。

### 决策 #5：session 自实现，零依赖

对标 MakoServer 的签名 cookie 方案，不引 express-session：

- cookie 名 `etasess`，值 = `base64url(payload) + '.' + base64url(HMAC-SHA256(secret, payload))`；
- payload = `{ d: 会话数据, e: 过期时间戳 }`，时间戳在签名覆盖范围内；
- `timingSafeEqual` 比对签名，长度不等先行拒绝；
- 滑动超时 30 分钟（`SESSION_TTL`），会话非空时每次响应重签刷新；
- 会话为空但请求携带 cookie 时下发 `Max-Age=0` 清除；
- 密钥派生：`SHA256('eta-server|hostname|username|homedir|首个非零MAC')`，不落盘、同机稳定、跨机不同；`os.userInfo()` / `networkInterfaces()` 均带 try 兜底；
- cookie 属性固定 `Path=/; HttpOnly; SameSite=Lax`，不设 Max-Age（浏览器会话 cookie）。

### 决策 #6：输出模型——渲染返回后才发响应

Eta 渲染是纯函数（返回完整字符串），天然没有 headers-already-sent 问题：`RESP.header()` / `status()` 只是往 `resp.headers` 数组里记，渲染完成后统一装配。响应体优先级：

1. `resp.binary !== null`（`RESP.writeraw` 触碰过）→ 二进制缓冲，短路文本；
2. `resp.text !== null`（`RESP.json()` 调过）→ JSON 字符串；
3. 否则渲染出的 html。

`RESP.json()` 不主动终止渲染（对标 MakoServer 决策），脚本用顶层 `return` 自行退出（Eta 模板代码块在函数体内，`return` 可用，demo/api.eta 即此写法）。

### 决策 #7：路由与静态语义照抄 MakoServer

- 路径规范化：`decodeURIComponent(pathname)` 失败 → 404；`\0` → 404；`path.resolve(root, '.' + pathname)` 后前缀校验，越界 → 404（与「不存在」同响应，fail-closed）；
- PATH_INFO：`lower.indexOf('.eta/')` 切分脚本与尾挂（取第一个命中），尾挂随 `_SERVER.PATH_INFO` 传入；
- 目录：无尾斜杠 301 补（`Location` 保留 query string），再依次 `index.eta`（走模板管线）/ `index.html` / `index.htm`；
- 静态白名单见 `STATIC_TYPES`（约 20 种），白名单外 404；存在但谓词非 GET/HEAD → 405 + `Allow: GET, HEAD`（白名单优先，404 不因 405 泄露存在性）；
- 服务器自身文件（`SELF_PATH`）命中即 404，防止 docroot 恰好是包目录时回吐源码。

### 决策 #8：零依赖原则

HTTP 用 `node:http`、session 用 `node:crypto`、CLI 手写解析——除 `eta` 外无运行时依赖。目标：`npx -y eta-server` 冷启动快、供应链面小、发包无争议。

## Bridge API 清单

| 名字 | 类型 | 说明 |
|---|---|---|
| `_GET` / `_POST` / `_REQUEST` | object | query / form-urlencoded / 二者合并（后覆盖前） |
| `_SERVER` | object | 见下 |
| `_COOKIE` | object | percent-decode 后的 cookie 字典 |
| `_SESSION` | object | 签名 cookie session（决策 #5） |
| `_BODY` | Buffer | 原始请求体（对标 `php://input`） |
| `_JSON` | object/null | Content-Type 为 JSON 时自动解析 |
| `RESP` | object | `status/header/redirect/setcookie/json/writeraw` |
| `escape(v)` | function | HTML 转义（`& < > " '`），返回字符串 |
| `require(spec)` | function | 锚定模板目录的 Node require（决策 #3） |

`_SERVER` 键：`REQUEST_METHOD`、`QUERY_STRING`（原始请求行截取，编码态原文）、`REQUEST_URI`（req.url 原文）、`SCRIPT_NAME`、`PATH_INFO`、`SCRIPT_FILENAME`、`SCRIPT_DIRNAME`、`DOCUMENT_ROOT`、`REMOTE_ADDR`、`CONTENT_TYPE`、`CONTENT_LENGTH`、`SERVER_NAME`、`SERVER_PORT`、`REQUEST_SCHEME`（恒 `http`）、以及 `HTTP_*` 请求头（大写、`-`→`_`）。

## 错误页

统一 `errorPage(code, title, detail)`：等宽字体 + `<pre>` 转义详情；500 附完整 stack。渲染中途抛异常即整体转 500（无 partial output，Eta 纯函数渲染天然满足）。`res.headersSent` 后出错直接 `res.destroy()`。

## 测试

`tests/test_server.js`：spawn 子进程起服务（端口 5177），fetch 断言 18 项：

- 渲染：index.eta、`/` 兜底、query 参数；
- 目录：301 补斜杠、index.html 兜底；
- 静态：Content-Type、405、白名单外 404；
- 安全：404、`../` 穿透 404；
- PATH_INFO 尾挂（`<%~ %>` 原样输出 JSON 数组）；
- API：GET echo、form POST、JSON body；
- session：三级链式 cookie 计数 1→2→3、篡改签名拒绝（count 归 1）；
- require：demo 页渲染；
- 500：broken.eta（引用未定义函数）。

跑法：`npm test`（Node 18+，用全局 fetch）。

## 已知限制

- 无 HTTPS（本机定位，反代自理）；
- 无 multipart 解析（`_FILES` 二期，请求体原样进 `_BODY`）；
- 无配置文件/日志；session TTL 硬编码 30 分钟；
- 模板 include 相对 `views`（文档根）而非模板自身目录；
- 无 Windows 路径大小写 / 尾部点 / NTFS 数据流的特判（MakoServer 有）——Node `fs` 语义下 `.ETA` 大小写分支已覆盖（扩展名判断 lowercase），尾部点与数据流场景由静态白名单 fail-closed 兜底，未逐项验收；
- `RESP.write()` 是显式抛错的占位（提示用模板文本输出），与 MakoServer 的 `RESP.write` 语义不同，勿按 PHP 习惯迁移。

## 发布

```
npm publish          # bin: eta-server -> ./eta-server.js
npx -y eta-server -r ./www -p 5000
```

未发布前可用 `npm link` 或 `npx github:<user>/toys`（bin 指向仓库内路径时 npx 需包根，建议单独建仓发布）。
