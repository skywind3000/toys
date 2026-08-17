# MakoServer 外网暴露加固备查

前提：PRD 定位是本机/可信环境。本文档仅作为"假如有一天要暴露公网"时的检查清单备查，**不改变 PRD 定位**。

核心认知：.mako = 任意 Python 执行。加固分两层——**MakoServer 代码自己负责的**，和**部署环境负责的**。就像 PHP 管不了目录权限 777、Flask 管不了前面有没有 nginx，两层的账要分开算。

---

## 一、MakoServer 代码层面要做的（暴露公网时）

这些是 makoserver.py 自己的事，属于代码行为：

1. **5xx 错误页脱敏**：公网模式下错误页只返回简短文本，不吐 traceback（traceback 记入日志）；用环境变量或配置项切换 debug 模式，本机调试仍可看完整栈；
2. **符号链接防护**：路径规范化时用 `realpath`，解析后的真实路径必须仍在文档根目录内——防止根目录内放一个符号链接指出去（PRD 现有的"规范化真实路径"检查要覆盖到符号链接场景）；
3. **请求体大小上限**：设置 Flask 的 `MAX_CONTENT_LENGTH`（如 1MB），防大 body 打爆内存；
4. **安全响应头**：统一追加 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`（或可配置的 CSP）、`Cache-Control: no-store`（对动态 .mako 响应）;
5. **cookie 属性**：bridge 写 cookie 时默认带 `HttpOnly`、`SameSite=Lax`，公网（HTTPS）下带 `Secure`，脚本可显式覆盖；
6. **Content-Type 纪律**：静态文件类型猜不出来时兜底 `application/octet-stream`，绝不猜成 `text/html`（防浏览器把未知文件当 HTML 渲染出 XSS）；
7. **日志不反射注入**：错误页不回显用户输入的原始路径/参数（回显即 XSS 温床），日志里记原始值没问题；
8. **可选：内置限速**：按 IP 的简单令牌桶（防裸跑无前置反代时被 CC）。有 nginx 时这条可不做。

以上 8 条就是暴露公网时 makoserver.py 需要增加/调整的全部代码工作，其余都是部署的事。

## 二、部署环境层面的（不是 MakoServer 代码的事，但要提醒使用者）

类比：PHP 管不了目录权限，Flask 管不了反代——但文档里提醒一句使用者总是好的：

1. **写权限控制（最重要）**：文档根目录对运行进程只读，任何能写 .mako 的途径（上传、Web 编辑器、开放 FTP）都等于交出服务器；
2. **前置反代**：nginx/Caddy 终结 HTTPS、防 Slowloris、限流限 body，Flask/gunicorn 只监听 127.0.0.1；
3. **运行账号最小权限**：专用低权限账号、无 shell，容器化最佳（只读挂载文档根 + 限 CPU/内存）；
4. **请求超时**：gunicorn timeout 兜底死循环脚本；
5. **限制出网**：服务器出站只开必要端口，防 RCE 后当跳板；
6. **认证/组网**：非公开内容走 IP 白名单、Basic Auth，或干脆 WireGuard/Tailscale 组网把公网访问降级回可信网络（最省事的方案）；
7. **日志与监控**：access log 全量留存，404 高频探测、5xx 突增要告警。

## 三、务实结论

- 真公网暴露：第一节的 8 条代码改动 + 第二节的部署清单，缺一不可；
- 只想在外网访问自己的小服务：**Tailscale/WireGuard 组网**是性价比最高的答案，第一节一条都不用做；
- 第二节的工作量远大于 MakoServer 本身，暴露公网前请三思是否值得。
