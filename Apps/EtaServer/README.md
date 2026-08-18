# EtaServer

PHP 风格的 `.eta` 动态页面服务器：**文件路径即路由**，往文档根目录丢一个 `.eta` 文件就是一个页面，不用写任何服务端代码。是 `Apps/MakoServer`（Python 版）的 JavaScript 对标实现。

需求见 [prd.md](prd.md)，实现细节与决策见 [spec.md](spec.md)。

## 快速开始

```bash
# 发布后（npm 包名 eta-server）
npx -y eta-server -r ./www -p 5000

# 本仓库直接跑
cd Apps/EtaServer
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

## 测试

```bash
npm test    # 需 Node 18+
```
