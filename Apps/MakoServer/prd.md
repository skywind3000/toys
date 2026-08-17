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
- 在 Flask 端提供一系列 bridge 函数/对象，供 .mako 脚本使用：
  - 设置返回的 header、返回码；
  - 读取请求参数（类似 PHP 的 `$_ARGS` 字典）、请求方法（GET/POST）、请求 body；
  - 读写 cookie；
  - （可选/后续扩展）`response.raw(bytes, content_type)` 接口，让脚本直接返回二进制内容（如动态生成图片），跳过模板渲染的文本假设；
- 更新检测：用户更新 .mako 脚本后能自动检测并 reload —— 采用**请求时检查 mtime** 的方式，不引入 watchdog；
- 错误处理：.mako 脚本编译错误或运行时异常时，返回 5xx 状态码 + 错误内容页面；
- 404 处理：请求的文件不存在（含 index 兜底全部未命中）、或路径穿透检查被拒绝时，统一返回 404 状态码 + 简单文本错误页，不区分"不存在"与"被拒绝"（避免探测目录结构）；
- 编码：文本输出统一 UTF-8，第一期重点覆盖 `text/html`、`text/plain`、`application/json` 三种类型。

## 配置文件

- 全局默认配置（默认端口、默认文档根目录等）：`~/.config/makoserver/settings.json`；
- 命令行参数优先级高于配置文件：单独运行时命令行指定的根目录、端口等覆盖配置文件中的同名项；
- WSGI 模式下按以下顺序查找配置文件，命中即用：
  1. 环境变量 `MAKOSERVER_CONF` 指定的路径；
  2. WSGI 入口脚本同目录下的 `makoserver.json`；
  3. 兜底 `~/.config/makoserver/settings.json`。
- 若希望"配置随站点目录走，一个目录拷走就能跑"，做法是把 WSGI 入口脚本和 `makoserver.json` 一起放进站点目录（利用第 2 条规则），配置中的相对路径以配置文件所在目录为基准解析。

## 运行方式

- 这个 MakoServer 可以单独运行，指定一个根目录和端口就能启动一个 HTTP Server 提供页面服务；
- 这个 MakoServer 也可以按 WSGI 的模式运行，它会寻找配置文件，从里面解析出根目录；
- 还可以单独传入一个 .mako 脚本，就像命令行运行 `php xxx.php` 那样渲染出来，结果写到 stdout；
- CLI 模式下 bridge 对象参考 PHP CLI 的降级语义：请求参数字典为空、请求方法为 `GET`、请求 body 为空、cookie 读取为空；设置 header/返回码/cookie 的调用静默无效（no-op），不报错——保证同一个 .mako 脚本在 HTTP 和 CLI 两种模式下都能运行。

## 非功能需求

- 并发模型：第一期使用 Flask 自带 dev server 即可，不追求生产级并发能力；
- 日志：请求日志走 Flask/Werkzeug 默认输出即可。
