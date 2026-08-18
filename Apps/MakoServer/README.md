# MakoServer

**MakoServer** 是一个类似 PHP 的动态页面服务：基于 Mako + Flask，指定一个文档根目录（root），目录下所有 `.mako` 文件就像 `.php` 一样按请求即时渲染，新增页面只需新增文件，不用改任何服务端代码。

- 单文件实现（`makoserver.py`），第三方依赖仅 Flask、Mako 两个，拷走单文件即可部署；
- 内置 PHP 风格超全局变量（`_GET` / `_POST` / `_SESSION` / ...）、`echo()` / `echoraw()` / `escape()`、`RESP` 响应控制对象；
- 三种运行模式：独立 dev server、WSGI 应用（mod_wsgi / gunicorn / uWSGI）、CLI 渲染（像 `php xxx.php`）；另支持普通 CGI 脚本作为兜底部署形态（免 mod_wsgi）；
- 零配置即拷即用：把 `makoserver.py` 放进站点目录作为 WSGI 入口，文档根目录就是它所在的目录。

> **定位与安全边界**：本项目定位为**本机 / 可信环境**使用的轻量动态页面服务，不做公网暴露场景的安全加固。`.mako` 模板本质是执行任意 Python 代码，等同在本机运行脚本，使用者须知悉。完整设计见 [prd.md](prd.md) 与 [spec.md](spec.md)。

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [编写 .mako 页面](#编写-mako-页面)
- [Bridge API](#bridge-api)
- [URL 与路径解析](#url-与路径解析)
- [会话（_SESSION）](#会话_session)
- [配置文件](#配置文件)
- [CLI 渲染模式](#cli-渲染模式)
- [部署](#部署)
  - [零配置单文件部署](#零配置单文件部署)
  - [Debian 13 + Apache mod_wsgi](#debian-13--apache-mod_wsgi)
  - [nginx + gunicorn + supervisor](#nginx--gunicorn--supervisor)
  - [普通 CGI（兜底模式）](#普通-cgi兜底模式)
- [常见问题](#常见问题)

## 安装

依赖只有两个（Python ≥ 3.8）：

```bash
pip install flask mako
```

Debian/Ubuntu 可以直接装系统包（MakoServer 对 Mako 1.3.x / 1.4.x、Flask 2.x / 3.x 均兼容）：

```bash
sudo apt install python3-flask python3-mako
```

## 快速开始

建一个站点目录，随便放个 `index.mako`：

```html
<!doctype html>
<title>hello</title>
<h1>Hello, ${_GET.get('name', 'world')}!</h1>
<p>现在是 ${escape(str(__import__('time').time()))}</p>
```

启动 dev server：

```bash
python makoserver.py -r ./site            # 默认监听 127.0.0.1:5000
python makoserver.py -r ./site -p 8080    # 指定端口
python makoserver.py -r ./site --host 0.0.0.0   # 局域网可访问
```

浏览器打开 `http://127.0.0.1:5000/` 即可。修改 `.mako` 文件后**无需重启**，下一个请求自动重新编译（按 mtime + 文件大小检测）。

dev server 模式下的命令行参数：

| 参数 | 说明 | 默认 |
|---|---|---|
| `-r / --root DIR` | 文档根目录（最高优先级） | 配置文件 `root`，再缺省为 cwd |
| `-p / --port N` | 监听端口 | 5000 |
| `--host ADDR` | 绑定地址 | 127.0.0.1 |
| `--conf FILE` | 指定配置文件（最高优先级） | 走搜索链 |

## 编写 .mako 页面

`.mako` 就是标准 Mako 模板，同时注入了一组 PHP 风格的名字：

```html
<%!
# 模块块：模板加载时执行一次。只放 import 和纯函数，
# 不要在这里引用 echo / _GET / RESP 等注入名！
import time
def fmt(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))
%>
<%
# 渲染块：每个请求执行一次，注入名在这里可用
name = _GET.get('name', 'guest')
count = int(_SESSION.get('count', 0)) + 1
_SESSION['count'] = count
%>
<!doctype html>
<html>
<body>
  <h1>Hello, ${escape(name)}</h1>
  <p>你是第 ${count} 次访问</p>
  <p>${fmt(time.time())}</p>
</body>
</html>
```

一条硬性规则：**注入名（`echo` / `escape` / `_GET` / `_SESSION` / `RESP` 等）只存在于渲染作用域**，`<%! %>` 模块块里引用它们编译不报错、运行时才抛 `NameError`。`<%! %>` 里只放 import 与纯函数；需要注入名的辅助函数放 `<% %>` 里，或把注入名作为参数显式传入。

根目录下的 `.py` 辅助模块可以直接 import（启动时根目录被追加到 `sys.path` 尾部，py3 命名空间包，无需 `__init__.py`）：

```
root/common/siteutil.py   →   <%! from common.siteutil import tagline %>
```

注意 `.py` 模块常驻 `sys.modules`，**编辑后需重启服务**（与 `.mako` 的热重载不同），适合放 DB / Redis 客户端等长生命周期单例。

## Bridge API

### 输出

| 名字 | 说明 |
|---|---|
| `echo(*args)` | 显式文本输出，参数 `str()` 后写入文本缓冲；`None` 输出空串；**bytes 抛 TypeError**——二进制内容走 `echoraw()` |
| `RESP.write(*args)` | `echo` 的规范名（同一函数对象），`echo` 被局部变量覆盖时用它兜底 |
| `echoraw(*args)` | 二进制输出：只接受 bytes / bytearray / memoryview，**追加**到独立二进制缓冲；**一旦调用即短路全部文本输出**，响应体只剩二进制内容。不代设 Content-Type，需自行 `RESP.header('Content-Type', ...)` |
| `RESP.writeraw(*args)` | `echoraw` 的规范名，覆盖时兜底 |
| `escape(value)` | 对标 PHP `htmlspecialchars`：`str()` 后转义 `& < > " '`，**返回字符串**（不输出）。`${}` 插值输出用户数据时务必用它 |
| `RESP.escape(value)` | `escape` 的规范名 |

`<% %>` 块外的普通文本照常直接输出，以上方式可混用。**输出全程缓冲**，`RESP.header()` / `RESP.status()` 可以在模板任意位置调用，没有 PHP 的 headers-already-sent 限制；渲染中途抛异常会丢弃已缓冲内容返回干净的 5xx 错误页。

### 请求（仿 PHP 超全局变量）

| 名字 | 对应 PHP | 说明 |
|---|---|---|
| `_GET` | `$_GET` | GET 参数字典；`_GET.getlist(name)` 取同名多值 |
| `_POST` | `$_POST` | POST 参数字典 |
| `_REQUEST` | `$_REQUEST` | GET + POST 合并（POST 覆盖同名 GET） |
| `_SERVER` | `$_SERVER` | 见下表 |
| `_BODY` | `php://input` | 原始请求体（bytes） |
| `_JSON` | — | Content-Type 含 json 时自动解析为 dict，否则 None |
| `_COOKIE` | `$_COOKIE` | cookie 字典 |
| `_SESSION` | `$_SESSION` | 会话字典，可读写，见[会话](#会话_session)一节 |

`_SERVER` 包含：`REQUEST_METHOD`、`QUERY_STRING`、`SCRIPT_NAME`（脚本路径）、`PATH_INFO`（尾挂路径，见下）、`REQUEST_URI`（原始请求 URI）、`SCRIPT_FILENAME`（脚本绝对路径）、`SCRIPT_DIRNAME`（脚本目录，语义同 PHP `__DIR__`）、`DOCUMENT_ROOT`、`REMOTE_ADDR`、`CONTENT_TYPE` / `CONTENT_LENGTH`、`SERVER_NAME` / `SERVER_PORT` / `REQUEST_SCHEME`、以及所有 `HTTP_*` 请求头（如 `HTTP_AUTHORIZATION`）。

模板内访问文件**不要依赖进程 cwd**（随启动方式漂移），用 `SCRIPT_DIRNAME` / `DOCUMENT_ROOT` 拼绝对路径。

### 响应（RESP 对象）

| 方法 | 说明 |
|---|---|
| `RESP.header(name, value)` | 设置响应头（同名覆盖；`Set-Cookie` 追加） |
| `RESP.status(code)` | 设置状态码 |
| `RESP.redirect(url, code=302)` | 重定向 |
| `RESP.json(data)` | JSON 响应（自动设 Content-Type）；**不主动退出**，需要时在 `<% %>` 块内 `return` 终止渲染 |
| `RESP.setcookie(name, value, *, max_age=None, expires=None, path='/', domain=None, secure=False, httponly=False, samesite=None)` | 设置 cookie，参数语义同 PHP `setcookie()`；值默认 percent-encode（`_COOKIE` 读取侧自动解码），原样下发用 `RESP.header('Set-Cookie', ...)`（= `setrawcookie()`） |
| `RESP.write(*args)` / `RESP.writeraw(*args)` / `RESP.escape(value)` | 见输出节 |

默认 Content-Type 为 `text/html; charset=utf-8`；输出二进制（动态图片 / 下载等）用 `echoraw()` 并以 `RESP.header('Content-Type', ...)` 显式指定类型（`echoraw` 不代设）。

## URL 与路径解析

假设 root 为 `/home/data/mako`，挂载在 `/app1`（WSGI）或直接服务（dev server）：

| 请求 | 行为 |
|---|---|
| `/demo.mako` | 渲染 `root/demo.mako` |
| `/app1/demo.mako` | 同上（WSGI 挂载前缀自动剥除） |
| `/demo.mako/hello/world` | **PATH_INFO 尾挂**：渲染 `demo.mako`，尾挂部分进 `_SERVER['PATH_INFO']`（`/hello/world`），可实现漂亮 URL 路由 |
| `/sub/` | 依次找 `index.mako` → `index.html` → `index.htm` |
| `/sub`（无尾斜杠） | 301 补斜杠到 `/sub/`（对齐 Apache DirectorySlash） |
| `/style.css` | 静态文件按内置白名单原样返回 |
| `/secret.py`、`/backup.bak`、无扩展名文件 | **一律 404**（fail-closed，无论谓词） |

要点：

- **静态白名单**（白名单外全 404）：`.html` `.htm` `.txt` `.csv` `.md` `.css` `.js` `.mjs` `.json` `.map` `.xml`、图片（`.png` `.jpg` `.jpeg` `.gif` `.svg` `.ico` `.webp` `.avif` `.bmp`）、字体（`.woff` `.woff2` `.ttf` `.otf` `.eot`）、音视频（`.mp3` `.ogg` `.wav` `.mp4` `.webm`）、`.wasm` `.pdf`、压缩包（`.zip` `.rar` `.7z` `.tar` `.gz` `.tgz` `.xz`）；可用配置键 `static_types` 按站点扩展/覆盖（`ext=mime` 逗号分隔）；
- `.mako` 支持全部 HTTP 方法（`REQUEST_METHOD` 如实传递）；静态文件仅 GET/HEAD，其它谓词 405；
- 防路径穿透、防 `.mako` 源码泄露、防配置文件 / 日志文件回吐均已内置；
- 源文件按原文编译，末尾空白**不截断**——文本响应忠实保留源文件的尾部换行；二进制脚本用 `echoraw()` 短路文本输出，EOF 换行自然不会污染。

## 会话（_SESSION）

- 基于**签名 cookie + 时间戳**，无服务端存储，天然兼容 WSGI 多进程；
- 直接读写 `_SESSION` 字典即可，改动在响应时自动回写（签名防篡改，**不防偷看**，勿存敏感明文）；
- 容量受 cookie 限制（约 4KB，超限返回 500）；值必须是 JSON 可序列化类型；
- cookie 名默认 `MAKO_SESSION`（可配置），脚本 `RESP.setcookie()` 使用同名会被丢弃并告警；
- 超时语义两种（配置项 `session_mode`）：`sliding`（每次响应重签，仿 PHP 默认）/ `absolute`（签发时间起算）；
- 签名密钥优先读配置 `secret`；未配置时由本机指纹派生（同机稳定、跨机不同）。多机负载均衡或容器重建场景**务必显式配置 secret**。

## 配置文件

单节 INI 格式（`#` / `;` 注释），节名固定 `[makoserver]`：

```ini
[makoserver]
root = /home/data/mako          # 文档根目录
secret = s3cr3t-key             # _SESSION 签名密钥（缺省=本机指纹派生）
session_lifetime = 3600         # 会话超时秒数
session_mode = sliding          # sliding / absolute
session_cookie = MAKO_SESSION   # 会话 cookie 名
max_body = 67108864             # 请求体上限（字节），默认 64MB，<=0 不限制
static_types = woff3=font/woff3 # 可选，静态白名单扩展（ext=mime 逗号分隔）
access_log = /var/log/makoserver/access.log   # 可选，缺省不落盘
error_log  = /var/log/makoserver/error.log    # 可选，缺省写 stderr
```

配置文件搜索顺序（先命中先用）：

1. dev server 的 `--conf FILE` 参数；
2. 环境变量 `MAKOSERVER_CONF`；
3. **makoserver.py（WSGI 入口脚本）同目录的 `makoserver.ini`**；
4. `~/.config/makoserver/settings.ini`。

配置中的相对路径以**配置文件所在目录**为基准解析。日志文件路径不建议指向文档根目录（框架会对其做运行时 404 屏蔽，但放 root 外更整洁），也不内置日志轮转，请自行搭配 logrotate。

## CLI 渲染模式

像 `php script.php` 一样渲染单个脚本，结果原始字节写 stdout：

```bash
python makoserver.py script.mako [args...]
echo '<% echo(6 * 7) %>' | python makoserver.py -
```

- 脚本名传 `-` 时从 stdin 读模板源（POSIX 约定），`<%include>` 基准为 cwd；
- 脚本名后的参数原样传入 `_SERVER['argv']`（`argv[0]` 为脚本自身）；
- CLI 模式不读配置文件；bridge 降级语义对齐 PHP CLI：请求字典为空、`REQUEST_METHOD` 为 GET、`RESP.header/status/setcookie` 静默 no-op，`echo` / `echoraw` 照常工作（`echoraw` 同样短路文本、stdout 输出原始字节）——同一个 `.mako` 脚本 HTTP 和 CLI 两种模式都能跑。

## 部署

### 零配置单文件部署

`makoserver.py` 导出模块级 `application` 对象，本身就是 WSGI 入口。把 `makoserver.py` 拷进站点目录（或**建一个软链接**，如 `wsgistart.py`），零配置下文档根目录就是该文件（软链接）所在目录；需要配置就在旁边放一个 `makoserver.ini`。

```bash
mkdir -p /srv/www/mysite
cd /srv/www/mysite
ln -s /opt/makoserver/makoserver.py wsgistart.py
# 站点文件直接放这里即可
```

### Debian 13 + Apache mod_wsgi

全部走系统包，不需要 venv 也不需要 sudo pip：

```bash
sudo apt install apache2 libapache2-mod-wsgi-py3 python3-flask python3-mako
```

Apache 站点配置（`/etc/apache2/sites-available/mysite.conf`）：

```apache
<VirtualHost *:80>
    ServerName mysite.local

    # daemon mode + 独立进程组；python-home 仅当使用 venv 时需要，
    # 用系统包时省略 python-home 即可
    WSGIDaemonProcess mysite processes=2 threads=15 \
        python-path=/srv/www/mysite
    WSGIProcessGroup mysite

    # 入口指向站点目录里的 makoserver.py（或其软链接 wsgistart.py）
    WSGIScriptAlias / /srv/www/mysite/wsgistart.py

    <Directory /srv/www/mysite>
        Require all granted
    </Directory>

    ErrorLog ${APACHE_LOG_DIR}/mysite-error.log
    CustomLog ${APACHE_LOG_DIR}/mysite-access.log combined
</VirtualHost>
```

```bash
sudo a2ensite mysite
sudo systemctl reload apache2
```

要点：

- **使用 daemon mode**（`WSGIDaemonProcess` + `WSGIProcessGroup`）：venv 场景下这是唯一选择（embedded 模式不支持按应用指定 `python-home`）；系统包场景下 embedded 虽能跑，daemon 仍是官方推荐形态——独立进程组、多站点互不串 `sys.path`，且改代码后 touch 入口文件即可热重载，无需重启 Apache。若改用 venv，加 `python-home=/path/to/venv`（venv 基底 Python 版本必须和 mod_wsgi 编译的版本一致，Debian 系统包对得上）；
- `makoserver.py` 自身、`makoserver.ini`、配置文件、日志文件均不会被 HTTP 回吐（内置 404 屏蔽），但仍建议把配置和日志放 root 外；
- access log 默认由 Apache 记录，MakoServer 不重复记录；错误信息走 Apache ErrorLog。

### nginx + gunicorn + supervisor

适合不想装 Apache 的场景。Debian 13 可以全用系统包：

```bash
sudo apt install gunicorn python3-flask python3-mako supervisor
```

**supervisor 配置**（`/etc/supervisor/conf.d/mysite.conf`）：

```ini
[program:mysite]
command=/usr/bin/gunicorn makoserver:application
    --bind 127.0.0.1:8000
    --workers 2 --threads 8
    --timeout 60
    --max-requests 1000 --max-requests-jitter 100
    --chdir /srv/www/mysite
directory=/srv/www/mysite
user=www-data
autostart=true
autorestart=true
stderr_logfile=/var/log/mysite/gunicorn-error.log
stdout_logfile=/var/log/mysite/gunicorn-access.log
```

> supervisor 的 ini 不支持反斜杠续行，实际写成一个长行，或确认你的 supervisor 版本支持折行。

**nginx 配置**（`/etc/nginx/sites-available/mysite`）：

```nginx
server {
    listen 80;
    server_name mysite.local;

    # 最简：全部转发。makoserver 自带静态白名单服务，
    # nginx 无需区分静态 / 动态（PATH_INFO 尾挂 URL 也自然正确）
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        client_max_body_size 16m;
    }
}
```

makoserver 自己处理静态文件（白名单内原样返回、白名单外 404），所以 nginx 侧**不建议**做 `try_files` 静态分流——会破坏 PATH_INFO 尾挂语义，也绕过 fail-closed 白名单。nginx 在这里的价值是 TLS、限流、缓冲慢客户端。

```bash
sudo ln -s /etc/nginx/sites-available/mysite /etc/nginx/sites-enabled/
sudo supervisorctl reread && sudo supervisorctl update
sudo systemctl reload nginx
```

也可以用 systemd unit 代替 supervisor（gunicorn 自带 daemonize 能力有限，systemd 写法与常见 Flask 部署一致），二选一即可。

### 普通 CGI（兜底模式）

连 mod_wsgi 都懒得装（或装不上）的机器，makoserver.py 可以直接当普通 CGI 脚本跑（Apache mod_cgi / mod_cgid），CGI 环境自动检测，零配置时文档根回退服务器提供的 `DOCUMENT_ROOT`。需要启用 `mod_cgi` / `mod_cgid` 并给目录加 `Options +ExecCGI`（cgi-bin 目录默认已有）。

**形态一：cgi-bin 放置**

把 `makoserver.py` 拷进 `/var/www/cgi-bin/`，请求 URL 为 `/cgi-bin/makoserver.py/index.mako`。能用，但 URL 丑，且静态文件请求也全部经 Python 进程处理。

**形态二（推荐）：Action 映射**

```apache
AddHandler mako-script .mako
Action mako-script /cgi-bin/makoserver.py
```

URL 保持 `/web/demo.mako` 原样（Apache 自动以 `PATH_INFO=/web/demo.mako` 调脚本），`.css` / `.png` 等静态文件由 Apache 直接服务，根本不进 Python——这是 PHP 时代 `Action application/x-httpd-php /cgi-bin/php` 的经典配法。

站点配置示例：

```apache
<VirtualHost *:80>
    ServerName mysite.local
    DocumentRoot /srv/www/mysite

    <Directory /srv/www/mysite>
        Require all granted
        AddHandler mako-script .mako
    </Directory>

    # makoserver.py 放 cgi-bin（或任何可执行位置）
    ScriptAlias /cgi-bin/ /var/www/cgi-bin/
    Action mako-script /cgi-bin/makoserver.py
</VirtualHost>
```

注意：

- **每请求冷启动一个 Python 进程**（约 100~300ms），内网低频场景够用，别指望生产性能；要进程常驻请用 mod_wsgi daemon 或 gunicorn；
- 配置搜索链与 WSGI 模式相同（`MAKOSERVER_CONF` > 脚本同目录 `makoserver.ini` > `~/.config/makoserver/settings.ini`），配置里的 `root` 优先于 `DOCUMENT_ROOT`；
- 不引入 FastCGI：flup 多年无人维护，进程常驻需求由 mod_wsgi daemon 承接。

### 进程健壮性建议

- gunicorn `--max-requests` 定期回收 worker、`--timeout` 杀死死循环脚本（MakoServer 自身不回收进程）；
- mod_wsgi 对应参数：`WSGIDaemonProcess ... maximum-requests=1000 request-timeout=60`。

## 常见问题

**Q: 修改 `.mako` 要重启吗？**
不用，按 mtime + 文件大小热重载。但 `<%! %>` 里 import 的 `.py` 辅助模块常驻内存，改它们要重启。

**Q: 模板里 `import json` 会不会和 bridge 冲突？**
不会。JSON 响应挂在 `RESP.json()` 上，`json` 这个名字完整保留给标准库。

**Q: 能跑在公网吗？**
定位是本机 / 可信环境，不做公网安全加固；`.mako` 可执行任意 Python，暴露公网等于开放代码执行。确要对外，请自行在前面加认证代理等防线，并阅读 [hardening.md](hardening.md)。

**Q: 上传文件？**
`_FILES` 属二期功能暂未实现；当前可通过 `_BODY` 自行处理 multipart，或改用前端 base64 + `_JSON` 传。

**Q: 依赖版本有要求吗？**
Python ≥ 3.8；`Flask<4`、`Mako<1.5`（初版开发基准 Flask 2.2.x；当前验证环境 Flask 3.1.x + Werkzeug 3.1.x + Mako 1.4.x 全量测试通过，另验证 Debian 系统包 Mako 1.3.2 / 1.3.9 兼容；升级依赖建议回归测试）。

## 相关文档

- [prd.md](prd.md) — 产品需求文档（完整行为定义）
- [spec.md](spec.md) — 技术规格文档（实现决策与取舍）
- [hardening.md](hardening.md) — 安全边界说明
- `demo/` — 示例站点（`python makoserver.py -r demo` 即可体验）
- `tests/` — pytest 测试套件（`python -m pytest tests/`）
