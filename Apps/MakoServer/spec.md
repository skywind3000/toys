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
| 私有接口 | 自定义字节缓冲注入依赖 `mako.runtime` 内部协议；升级 Mako 小版本须回归验证 |
| 运行形态 | ① 独立 dev server ② WSGI 入口（导出 `application`）③ CLI 渲染单个 .mako |
| 定位 | 本机/可信环境；安全检查以「可信环境下的健壮性」为准（Windows 路径陷阱），不做公网加固 |

### 0.2 PRD 待决点落定表

| # | 待决点 | 决策 |
|---|--------|------|
| 1 | 滑动超时重签触发条件 | 滑动模式：请求携带有效 session 即重签（无论脚本是否写过）；绝对模式：仅数据发生变化时重签，且时间戳继承原签发时刻 |
| 2 | CLI 下 include/inherit 基准目录 | 模板查找目录 = 被渲染脚本所在目录（HTTP 模式为 root） |
| 3 | `RESP.redirect()` 后是否终止渲染 | 不终止（对齐 PHP `header()`）；文档惯例建议其后 `return` |
| 4 | `_JSON` 解析失败行为 | 为 `None`，不报错；脚本可通过 `_BODY` 拿原文自行处理 |
| 5 | 静态文件 mimetypes 猜不出时 | `application/octet-stream`，绝不猜成 `text/html` |
| 6 | 5xx 错误页内容 | 含完整 traceback（HTML 转义）+ 请求路径；traceback 同步写 error log |
| 7 | 配置相对路径基准 | 通则：三条查找规则命中的配置文件，其中所有相对路径（含 `root`）均以**配置文件所在目录**为基准 |
| 8 | `_SERVER` 的「请求路径」键名 | `PATH_INFO`（不引入 PHP/Apache 特有的 `REQUEST_URI`） |
| 9 | `_REQUEST` 合并顺序 | GET 与 POST 合并（POST 覆盖同名 GET），不含 cookie——对齐现代 PHP `request_order="GP"` 默认 |
| 10 | `getlist` 可用范围 | `_GET` / `_POST` / `_REQUEST` 三者均支持（同一 PHPDict 实现） |
| 11 | CLI 下 `_SERVER` 内容 | 固定降级值 + `argv`，详见 6.4 |

## 1. 单文件内部布局

makoserver.py 内部代码区块（自上而下）：

| 区块 | 内容 |
|------|------|
| 头部 | 文件头注释、`__version__`、imports |
| 常量 | 默认配置、扩展名、cookie 名等 |
| 配置 | `load_config()` / 配置查找与合并 |
| 路径 | `resolve_path()` 规范化与防穿透 |
| 模板 | `TemplateStore`（自定义模板集合 + mtime 缓存） |
| 缓冲 | `BytesBuffer` |
| Bridge | `PHPDict` / `RespObject` / `make_bridge()` |
| Session | `SessionCodec`（签名/校验/密钥派生） |
| 请求 | `create_app()` / catch-all 视图 / 响应组装 |
| 日志 | error/access log 装配 |
| 入口 | `application` 导出、`main()`、`if __name__ == '__main__'` |

## 2. 配置

### 2.1 配置 schema（扁平键）

| 键 | 类型 | 默认 | 说明 |
|----|------|------|------|
| `root` | str | 必填（serve/WSGI 必须能解析出，否则启动报错退出） | 文档根目录，支持相对路径（见 2.3） |
| `port` | int | 5000 | dev server 端口 |
| `host` | str | `127.0.0.1` | dev server 监听地址 |
| `secret` | str | 空 → 派生 | session 签名密钥（UTF-8 编码） |
| `session_lifetime` | int | 3600 | session 有效期（秒） |
| `session_mode` | str | `sliding` | `sliding` / `absolute` |
| `session_cookie` | str | `MAKO_SESSION` | session cookie 名 |
| `access_log` | str | 空（不落盘） | access log 文件路径 |
| `error_log` | str | 空（stderr） | error log 文件路径 |

未知键忽略不报错（向前兼容）。配置文件为非法 JSON：按用途分级处理——WSGI/serve 启动时直接报错退出（带文件路径与行号）；仅 CLI 渲染模式不读配置、不受影响。

### 2.2 查找顺序（WSGI / serve 模式，命中即用、不逐层合并）

1. 环境变量 `MAKOSERVER_CONF` 指定的路径（文件不存在 = 未命中，继续下寻）；
2. 入口脚本（`makoserver.py`）同目录下 `makoserver.json`；
3. `~/.config/makoserver/settings.json`。

serve 模式下第 2 条的「入口脚本同目录」即 makoserver.py 所在目录。

### 2.3 相对路径通则

配置文件中所有相对路径（`root`、`access_log`、`error_log`）均以**该配置文件所在目录**为基准 `os.path.join(conf_dir, value)` 后再取 abspath。命令行传入的路径不做此变换（按 shell 语义走 cwd）。

### 2.4 优先级

命令行参数 > 配置文件 > 内置默认。CLI 渲染模式不读配置。

## 3. 请求处理流水线

### 3.1 路由

Flask app 仅注册两条路由（catch-all，禁用 static 路由）：

- `GET/HEAD /` → `view('')`
- `GET/HEAD/POST/... /<path:url_path>` → `view(url_path)`（methods 放开全谓词；HEAD 由 Werkzeug 自动处理 body 剥离）

WSGI 挂载前缀（SCRIPT_NAME）由 Flask/Werkzeug 自动剥除，view 收到的即 URL 尾部。非 GET/POST 谓词到达模板时 `_SERVER['REQUEST_METHOD']` 如实反映。

### 3.2 路径解析算法（resolve_path）

输入：URL 尾部 `url_path`（已 URL 解码）。步骤：

1. **POSIX 规范化**：`rel = posixpath.normpath('/' + url_path).lstrip('/')`，得到如 `demo/demo.mako`；任何 `..` 在 normpath 后仍残留于头部（即逃出 root）→ 拒绝；
2. **NTFS 特判**（`os.name == 'nt'` 下）：
   - `rel` 含 `:`（盘符 / `::$DATA` 数据流）→ 拒绝；
   - `rel` 每个路径段的结尾 `.` 与空格视为被文件系统剥掉（Windows 语义），对 `rel.rstrip(' .')` 后的形态做后续判断——防 `demo.mako.` 绕过；
3. **拼合与真实路径收口**：`full = os.path.join(root, rel)`；`real = os.path.realpath(full)`、`root_real = os.path.realpath(root)`；`os.path.commonpath([real, root_real]) != root_real`（或 real == root_real，即指向 root 本身）→ 拒绝。realpath 一并覆盖符号链接 / junction 指出 root 的场景；
4. **拒绝即 404**：与「文件不存在」同响应（见 3.6），不区分。

realpath 结果缓存每请求重算（不做跨请求缓存，量小无所谓，避免缓存失效漏洞）。

### 3.3 分支判定（在规范化后的 basename 上）

对步骤 3 的 `real`：`name = os.path.basename(os.path.normcase(real))`

- `name.endswith('.mako')` → **模板分支**（即使文件不存在也走此分支：渲染时自然 404/500，见 3.4）；
- `os.path.isfile(real)` → **静态分支**（.mako 已被上一条拦截，不会以静态形式吐出源码；大小写变体 `demo.MAKO` 经 normcase 同样落入模板分支）；
- `os.path.isdir(real)` 或 `real` 不存在 → **index 兜底**：依次试 `<real>/index.mako`、`<real>/index.html`、`<real>/index.htm`（存在即按对应分支处理），全不中 → 404。

### 3.4 模板分支

1. `store.get(rel)`：mtime 检查命中缓存或重新加载编译（见 4）；
2. 文件不存在 → 404；
3. 编译/渲染任何异常（含 include/inherit 目标缺失）→ 500（见 9.1）；
4. 渲染成功 → 按 8 组装响应。

### 3.5 静态分支

1. `mimetypes.guess_type(real)`：猜中 → 该类型；猜不中 → `application/octet-stream`；
2. **不加 charset**（静态文件可能是任意编码的老页面，强加 UTF-8 会误导浏览器）；
3. 读文件字节为 body；读失败（权限/占用）→ 500；
4. 支持 `If-Modified-Since` / 304？一期不做，一律 200 全量返回（本机场景带宽免费）。

### 3.6 404 响应

`text/plain; charset=utf-8`，body `404 Not Found\n`。

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
| CLI 渲染 | 被渲染脚本所在目录 |

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

`template.render(context, **bridge_names)` 或经 5.2 的 Context 构造注入。注入名固定为下表 11 个，未注入名在模板中引用时按 Mako 默认 NameError 报 500：

| 注入名 | 类型 | 构造 |
|--------|------|------|
| `echo` | function | 见 6.2 |
| `_REQUEST` | PHPDict | GET+POST 合并 |
| `_GET` | PHPDict | `request.args` |
| `_POST` | PHPDict | `request.form` |
| `_SERVER` | dict | 见 6.4 |
| `_BODY` | bytes | `request.get_data()` |
| `_JSON` | dict/None | 见 6.5 |
| `_COOKIE` | dict | `request.cookies` 普通 dict |
| `_SESSION` | dict | 见 7 |
| `RESP` | RespObject | 见 6.6 |

（`RESP.write` 是 RespObject 属性 = `echo` 同一函数对象。）

### 6.2 echo(*args)

逐参数顺序写入 buffer：`None` → 跳过（空串，对齐 PHP `echo null`）；`str` → `buffer.write(str)`（UTF-8 即时编码）；`bytes/bytearray/memoryview` → `buffer.write(bytes(...))`；其它 → `buffer.write(str(x))`。多参数按序全部输出后返回（无返回值）。

### 6.3 PHPDict

`dict` 子类。构造自 Flask MultiDict：**单值 = 同名参数最后一次出现**（对齐 PHP），`getlist(name)` 返回全部出现的列表（无则 `[]`）。`_REQUEST` 合并：先放 GET 全部，再放 POST（后者覆盖同名单值）；`getlist` 返回 GET+POST 全部同名值（GET 在前）。

### 6.4 _SERVER 键集

HTTP 模式（自 WSGI environ 透传 + 提炼）：

`REQUEST_METHOD`、`QUERY_STRING`、`SCRIPT_NAME`、`PATH_INFO`、`CONTENT_TYPE`、`CONTENT_LENGTH`、`REMOTE_ADDR`、`SERVER_NAME`、`SERVER_PORT`、`REQUEST_SCHEME`（自 `wsgi.url_scheme`），以及全部 `HTTP_*` 头（environ 原名透传）。

CLI 模式（降级值）：

| 键 | 值 |
|----|----|
| `REQUEST_METHOD` | `'GET'` |
| `QUERY_STRING` | `''` |
| `SCRIPT_NAME` | 脚本绝对路径 |
| `PATH_INFO` | `''` |
| `REMOTE_ADDR` / `SERVER_NAME` / `SERVER_PORT` / `CONTENT_TYPE` / `CONTENT_LENGTH` | `''` |
| `argv` | `sys.argv`（对齐 PHP CLI SAPI） |

### 6.5 _BODY / _JSON

`_BODY` 为原始 body bytes（CLI 恒 `b''`）。`_JSON`：Content-Type 字符串包含子串 `json`（覆盖 `application/json`、`+json`、`text/json`）时 `json.loads(_BODY)`，**解析失败 → None**；不含 json → None。body 为空也 → None。

### 6.6 RespObject 方法

| 方法 | 行为（HTTP 模式） | CLI 模式 |
|------|--------------------|-----------|
| `write(*args)` | = `echo` | 同 echo（正常输出） |
| `header(name, value)` | 记入待发 headers，后设覆盖先设；`Content-Type` 经此设置时完全覆盖默认值 | no-op |
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

校验：split 成三段（多段/缺段 → 无效）→ `hmac.compare_digest` 常量时间比签 → `now - ts` 按模式判过期。任一步失败视为**无 session**（`_SESSION` 为空 dict），不报错。

### 7.2 密钥派生（本机指纹）

`secret` 配置非空 → 直接用（UTF-8 编码）。否则由本机指纹派生，算法借鉴 `C:\Share\vim\lib\credential.py` 的 `__generate_host_uuid()`（多分量收集、逐项容错、一次性散列、模块级缓存）：

**分量收集**（components 列表，逐项独立 try/except，失败/缺失即跳过该项、不中断）：

1. 固定域分离盐 `'MAKOSERVER-HOST-KEY'`（对应原函数的 `SHADOW_CODE`）；
2. `socket.gethostname()`；
3. Windows：`wmic csproduct get uuid`（主板硬件 UUID）；wmic 不可用（Win11 24H2 起已移除）→ 回退 winreg 读 `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`；
4. Linux：`/etc/machine-id`，次选 `/var/lib/dbus/machine-id`，再备 `/sys/class/dmi/id/product_uuid`；
5. `platform.processor()`；
6. MAC（条件采集）：先判 WSL——`/proc/version` 含 `microsoft`/`wsl` 则跳过（WSL 的 MAC 每次重启漂移，不稳定）；否则 `uuid.getnode()`，且 `((mac >> 40) & 0x01) == 0` 才采信（bit40 为本地管理位，=1 表示随机/本地 MAC，不稳定，跳过）。

**拼接散列**：`secret = sha256(':'.join(components).encode('utf-8', 'ignore')).digest()`——与原函数相同的 `':'` 拼接 + sha256；原函数将 hexdigest 切片为 UUID 形状返回，MakoServer 不需要，直接取 32 字节 digest 作 HMAC-SHA256 密钥。

**缓存**：模块级计算一次后缓存（对应原函数 `fetch_uuid()` 的 memoize 做法）。

效果与原函数一致：多分量容错（单一来源读取失败或漂移不影响整体稳定）、同机稳定、跨机不同、无需落盘。

### 7.3 签发 / 重签 / 过期规则表

请求开始时载入有效数据并做快照（`snapshot = copy of loaded data`）。渲染结束后按 `now_dict` 与快照比对（不等 = 脚本写过）：

| 场景 | absolute | sliding |
|------|----------|---------|
| 带有效 session，未改数据 | 不发 Set-Cookie | 重签：ts = now，重发 |
| 带有效 session，改了数据 | 重签：**ts 继承原 ts**（绝对窗口不重置） | 重签：ts = now |
| 无 session，dict 非空 | 签发：ts = now | 签发：ts = now |
| 无 session，dict 为空 | 不发 | 不发 |
| 校验失败 / 过期 | `_SESSION` = 空 dict，按「无 session」行处理 | 同左 |

（清空 `_SESSION` 属「改了数据」：absolute 下重签空数据 ts 继承，sliding 下 ts=now。）

### 7.4 容量上限

组装 Set-Cookie 前检查完整 cookie 串长度 > 3800 字节 → 抛 `SessionTooLarge` → 500 错误页（错误信息说明 4KB 限制）。

### 7.5 CLI 模式

`_SESSION` 恒为空 dict；对它的写无任何副作用（不发 cookie）。

## 8. 响应组装（HTTP 模式）

渲染成功后：

1. body = `buffer.getvalue()`；
2. status = RESP 记录的 code（未设 → 200）；
3. Content-Type：RESP 显式设置值 > 默认 `text/html; charset=utf-8`；
4. 其余 RESP headers 逐个加入（后设覆盖先设；同名 Set-Cookie 多条并存）；
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

## 10. 运行形态

### 10.1 独立 dev server

```
python makoserver.py [--root DIR] [--port N] [--host H]
```

读配置（2.2）→ 命令行覆盖（2.4）→ `app.run(host, port, threaded=True)`。并发 = Werkzeug dev server 线程模型，不追求生产级。

### 10.2 WSGI 入口

模块级 `application = create_app(...)`：import 时完成配置查找与 app 构造（每进程一次，无跨进程状态，天然多进程兼容）。Apache `WSGIScriptAlias /app1 /path/to/makoserver.py` 即用。

### 10.3 CLI 渲染

```
python makoserver.py script.mako [args...]
```

- 不读配置文件；`TemplateStore.base_dir` = 脚本所在目录（4.3）；
- bridge 按 6.4/6.6 CLI 列降级；
- 成功：`sys.stdout.buffer.write(body)`（原始字节，二进制安全）；
- 失败：见 9.3。

参数判定：首个位置参数存在且不是选项 → CLI 渲染模式；无位置参数 → dev server 模式。

## 11. 日志

| 通道 | 默认 | 配置后 |
|------|------|--------|
| error log | stderr | `error_log` 文件；logging `FileHandler`（append，UTF-8） |
| access log | 不落盘（dev 走 Werkzeug 控制台自带输出；WSGI 交宿主） | `access_log` 文件；WSGI middleware 包裹 app 记录 |

- error log 内容：5xx traceback、启动错误、模板编译错误；格式 `%(asctime)s %(levelname)s %(message)s`；
- access log 行格式：`{iso_time} {remote_addr} {method} {path} {status} {bytes}`（状态码与字节数自 WSGI 响应回读）；
- 滚动由使用者自行管理（logrotate / 容器收集），框架不内置；
- 日志文件路径若配置进 root 内，属使用者选择，框架不阻止但 PRD 已警示回吐风险。

## 12. 测试计划（tests/，pytest）

| 文件 | 覆盖点 |
|------|--------|
| `test_config.py` | 三级查找命中即用；`MAKOSERVER_CONF` 不存在继续下寻；相对路径基准（root/log 路径均相对配置文件目录）；CLI 覆盖优先级；非法 JSON 报错 |
| `test_paths.py` | `../` 逃逸、绝对路径注入、`..%2f` 解码后穿透、尾部点 `demo.mako.`、`demo.MAKO`、`demo.mako::$DATA`（Windows）、realpath 符号链接出 root；拒绝与不存在同 404 响应体 |
| `test_index.py` | 目录请求三级兜底顺序；全部未命中 404；root 请求 `/` |
| `test_static.py` | html/jpg/png Content-Type；未知扩展 → octet-stream；字节原样；无 charset |
| `test_template.py` | 基本渲染；mtime 变更后 reload；源码尾部空白截断（单块二进制脚本 `%>` 后空白/EOF 换行不污染）；BOM 文件；include/inherit 相对解析（HTTP 与 CLI 两基准） |
| `test_echo.py` | echo 类型矩阵：str/bytes/bytearray/None/int/混合多参；RESP.write 同一函数；echo 被局部变量覆盖后 RESP.write 兜底 |
| `test_bridge.py` | `_GET`/`_POST` 分离；`_REQUEST` 覆盖序（POST 压 GET）；getlist 三处可用；`_SERVER` 键集与 HTTP_*；`_BODY`；`_JSON` 含 json/坏 JSON/非 JSON；RESP.header/status 后设覆盖；redirect/json 不终止渲染（后续 echo 仍污染 body，行为断言）；json 中文 ensure_ascii=False |
| `test_session.py` | 签发/回带往返；篡改 data/ts/签名 → 空 dict；absolute 到期拒绝、改数据 ts 继承；sliding 无写入也重签、重签刷新 ts；过期边界（now-ts == lifetime）；4KB 超限 500；secret 配置覆盖派生；派生密钥模块级缓存（两次调用同值） |
| `test_cli.py` | stdout 字节精确比对（含二进制输出）；降级 `_SERVER`/空参数/no-op RESP；`argv` 传入；include 基准 = 脚本目录；异常 exit 1 |
| `test_http.py` | 端到端（Flask test client）：默认 Content-Type；显式覆盖；Set-Cookie 下发与回带；404 文本；500 traceback 转义（`<script>` 注入路径转义断言） |

## 13. 明确不做（一期）

- `_FILES` 上传、限速、安全响应头、错误页脱敏开关（公网加固见 hardening.md）；
- 静态文件 304/Range；
- 日志轮转、多 app 多 root 路由；
- watchdog 及任何第三方依赖。
