# EtaServer

PHP 风格的 `.eta` 动态页面服务器：**文件路径即路由**，往文档根目录丢一个 `.eta` 文件就是一个页面，不用写任何服务端代码。

需求见 [prd.md](prd.md)，实现细节与决策见 [spec.md](spec.md)。

## 快速开始

```bash
# 发布后（npm 包名 eta-server）
npx -y eta-server -r ./www -p 5000

# 本仓库直接跑（clone 后进仓库根目录）
npm install
node eta-server.js -r demo -p 5000
# 打开 http://127.0.0.1:5000/
```

## 写个页面

文档根目录内新建 `hello.eta`：

```html
<%
const name = _GET.name || 'world'
_SESSION.count = (_SESSION.count || 0) + 1
%>
<h1>Hello, <%= name %>!</h1>
<p>第 <%= _SESSION.count %> 次访问</p>
```

请求 `http://localhost:5000/hello.eta?name=skywind` 即得页面。`_GET` / `_POST` / `_SESSION` / `_SERVER` / `_COOKIE` / `RESP` / `require` 等 bridge 变量裸名可用（详见 prd.md Bridge API 一节）。

## 命令行渲染（CLI 模式）

像 `php script.php` 一样直接渲染单个脚本，结果写 stdout：

```bash
node eta-server.js demo/hello.eta            # 渲染文件
node eta-server.js script.eta one two --x    # 额外参数经 _SERVER.argv 透传
echo 'hi <%~ _SERVER.argv[0] %>' | node eta-server.js -   # 从 stdin 读脚本
```

规则（对齐 PHP CLI 习惯）：脚本不限扩展名；`-` 代表 stdin；脚本名后的一切参数原样透传（`argv[0]` = 脚本自身）；include / require 以脚本所在目录为基准（stdin 时为 cwd）；渲染异常报错到 stderr、退出码 1。详见 spec.md 决策 #11。

## 测试

```bash
npm test    # 测试本体需 Node 18+（fetch）；模板内 require(.ts) 特性需 22.18+，见 package.json engines
```
