# MakoServer Guestbook Demo

一个用 `.mako` 模板写的小留言板，演示 MakoServer 的 PHP 风格桥接能力。

## 运行

在 `Apps/MakoServer/` 目录下：

```
python makoserver.py -r demo -p 8000
```

浏览器打开 <http://127.0.0.1:8000/index.mako>。

## 文件

| 文件 | 说明 |
|------|------|
| `index.mako` | 留言列表 + 表单 + debug 面板 |
| `post.mako` | POST 处理：校验、落盘、发 cookie、redirect（PRG） |
| `header.mako` / `footer.mako` | 公共布局（`<%include>` 演示） |
| `common/siteutil.py` | 站点本地辅助模块（root 在 sys.path，`<%! %>` 直接 import，spec 决策 #26） |
| `style.css` | 静态文件（白名单分支演示） |
| `data/messages.json` | 留言存储（运行时自动创建，勿手工编辑） |

## 功能点对照

- **GET 参数** — 翻页 `?page=N`；`?debug=1` 打开请求透视面板（打印 `_GET` / `_REQUEST` / `_COOKIE` / `_SESSION` / `_SERVER`，含 `getlist` 多值展示：`?debug=1&foo=bar&foo=baz`）
- **POST 参数** — `post.mako` 读 `name` / `message`，校验失败时输入经 session 带回表单
- **Cookie** — 发帖成功后 `RESP.setcookie('gb_name', ...)` 记住名字 30 天，下次自动回填
- **Session** — 访问计数器（`_SESSION['visits']`）+ 一次性 flash 消息（POST→redirect→GET 显示后消失）
- **PRG 模式** — `post.mako` 处理完 `RESP.redirect('index.mako')` + `return`
- **模板定位** — 数据文件用 `_SERVER['SCRIPT_DIRNAME']` 拼绝对路径（spec 决策 #21）
- **站点模块 import** — `index.mako` 的 `<%! %>` 块 `from common.siteutil import tagline`（root 尾部追加进 sys.path，spec 决策 #26；注意 .py 修改后需重启，不像 .mako 有 mtime 热重载）
- **HTML 转义** — 所有用户输入经 `escape()` 输出（可发 `<script>alert(1)</script>` 验证）

## curl 冒烟测试

```
# GET + query
curl -s "http://127.0.0.1:8000/index.mako?page=1&debug=1"

# POST（看 Set-Cookie 与 302）
curl -si -d "name=Alice&message=hello" http://127.0.0.1:8000/post.mako

# 带 cookie 回访
curl -s -b "gb_name=Alice" http://127.0.0.1:8000/index.mako
```
