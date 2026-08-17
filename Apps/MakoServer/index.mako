<%!
import os
import sys
import time
import socket
import platform
import datetime
%>\
<%
#
# makoinfo() - 类似 phpinfo() 的 MakoServer 信息页
#
# 注意：不 import makoserver 本身（WSGI 模式下重复执行模块级 bootstrap），
# 版本号经 echo.__globals__（注入函数所在模块命名空间）读取，两种模式通用。
#
import html as _h
import flask as _flask
import mako as _mako
import werkzeug as _wz

_g = echo.__globals__
_ms_version = _g.get('__version__', '?')
_srv = _SERVER

def _esc (v):
    try:
        return _h.escape(str(v), quote=True)
    except Exception:
        return '(unprintable)'

def _kv_rows (pairs):
    out = []
    for k, v in pairs:
        out.append('<tr><td class="e">%s</td><td class="v">%s</td></tr>'
                   % (_esc(k), _esc(v)))
    if not out:
        out.append('<tr><td class="e" colspan="2">(empty)</td></tr>')
    return '\n'.join(out)

_now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
%>\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>makoinfo()</title>
<style>
body {background:#fff; color:#222; margin:0; padding:0;
      font-family:Verdana,Arial,Helvetica,sans-serif; font-size:12px;}
.banner {background:#666699; color:#fff; padding:10px 18px;}
.banner h1 {margin:0; font-size:22px; font-weight:bold;}
.banner span {color:#ccccff;}
.wrap {padding:8px 18px 40px 18px;}
h2 {background:#9999cc; color:#fff; font-size:14px; padding:4px 10px;
    margin:26px 0 0 0;}
table {border-collapse:collapse; width:920px; margin:0 0 2px 0;}
td {border:1px solid #9999cc; padding:3px 8px; vertical-align:top;}
td.e {background:#ccccff; font-weight:bold; width:300px;}
td.v {background:#f8f8ff; word-break:break-all; white-space:pre-wrap;}
td.h {background:#666699; color:#fff; font-weight:bold;}
p.foot {color:#888; margin-top:30px;}
a {color:#666699;}
</style>
</head>
<body>
<div class="banner">
<h1>makoinfo() <span>- MakoServer ${_esc(_ms_version)}</span></h1>
</div>
<div class="wrap">

<h2>System</h2>
<table>
<tr><td class="e">MakoServer Version</td><td class="v">${_esc(_ms_version)}</td></tr>
<tr><td class="e">Python Version</td><td class="v">${_esc(sys.version.replace(chr(10), ' '))}</td></tr>
<tr><td class="e">Python Executable</td><td class="v">${_esc(sys.executable)}</td></tr>
<tr><td class="e">Platform</td><td class="v">${_esc(platform.platform())}</td></tr>
<tr><td class="e">OS / Architecture</td><td class="v">${_esc(os.name)} / ${_esc(platform.machine())}</td></tr>
<tr><td class="e">Hostname</td><td class="v">${_esc(socket.gethostname())}</td></tr>
<tr><td class="e">Process ID</td><td class="v">${_esc(os.getpid())}</td></tr>
<tr><td class="e">Current Working Directory</td><td class="v">${_esc(os.getcwd())}</td></tr>
<tr><td class="e">Server Time</td><td class="v">${_esc(_now)}</td></tr>
</table>

<h2>Frameworks &amp; Dependencies</h2>
<table>
<tr><td class="e">Flask</td><td class="v">${_esc(_flask.__version__)}</td></tr>
<tr><td class="e">Werkzeug</td><td class="v">${_esc(_wz.__version__)}</td></tr>
<tr><td class="e">Mako</td><td class="v">${_esc(_mako.__version__)}</td></tr>
</table>

<h2>This Request (_SERVER)</h2>
<table>
${_kv_rows(sorted(_srv.items()))}
</table>

<h2>Request Parameters</h2>
<table>
<tr><td class="h" colspan="2">_GET</td></tr>
${_kv_rows([(k, ', '.join(_GET.getlist(k))) for k in sorted(_GET.keys())])}
<tr><td class="h" colspan="2">_POST</td></tr>
${_kv_rows([(k, ', '.join(_POST.getlist(k))) for k in sorted(_POST.keys())])}
<tr><td class="h" colspan="2">_REQUEST (GET + POST)</td></tr>
${_kv_rows([(k, ', '.join(_REQUEST.getlist(k))) for k in sorted(_REQUEST.keys())])}
<tr><td class="h" colspan="2">_COOKIE</td></tr>
${_kv_rows(sorted(_COOKIE.items()))}
</table>

<h2>Session (_SESSION)</h2>
<table>
${_kv_rows(sorted(_SESSION.items()))}
</table>

<h2>Environment Variables (os.environ)</h2>
<table>
${_kv_rows(sorted(os.environ.items()))}
</table>

<h2>Paths</h2>
<table>
<tr><td class="e">DOCUMENT_ROOT</td><td class="v">${_esc(_srv.get('DOCUMENT_ROOT', '-'))}</td></tr>
<tr><td class="e">SCRIPT_FILENAME</td><td class="v">${_esc(_srv.get('SCRIPT_FILENAME', '-'))}</td></tr>
<tr><td class="e">SCRIPT_DIRNAME</td><td class="v">${_esc(_srv.get('SCRIPT_DIRNAME', '-'))}</td></tr>
<tr><td class="e">sys.path</td><td class="v">${_esc(chr(10).join(sys.path))}</td></tr>
</table>

<h2>Bridge API (injected names)</h2>
<table>
<tr><td class="h">Name</td><td class="h">Description</td></tr>
<tr><td class="e">echo(*args)</td><td class="v">PHP 式输出：str 即时 UTF-8 编码、bytes 直通、None 输出空串</td></tr>
<tr><td class="e">RESP.header(name, value)</td><td class="v">设置响应头（Set-Cookie 追加、其余覆盖）</td></tr>
<tr><td class="e">RESP.status(code)</td><td class="v">设置响应状态码</td></tr>
<tr><td class="e">RESP.redirect(url, code=302)</td><td class="v">便捷重定向（不终止渲染，脚本自行 return）</td></tr>
<tr><td class="e">RESP.json(data)</td><td class="v">JSON 响应（Content-Type: application/json，不终止渲染）</td></tr>
<tr><td class="e">RESP.setcookie(...)</td><td class="v">设置 cookie（对应 PHP setcookie）</td></tr>
<tr><td class="e">RESP.write(*args)</td><td class="v">echo 的规范名，被局部变量覆盖时兜底</td></tr>
<tr><td class="e">_GET / _POST / _REQUEST</td><td class="v">请求参数（PHPDict，支持 getlist 取同名多值；_REQUEST 为 GET+POST 合并，POST 覆盖）</td></tr>
<tr><td class="e">_SERVER</td><td class="v">请求环境（REQUEST_METHOD / SCRIPT_NAME / PATH_INFO / REQUEST_URI / SCRIPT_FILENAME / SCRIPT_DIRNAME / DOCUMENT_ROOT / HTTP_* 等）</td></tr>
<tr><td class="e">_BODY / _JSON</td><td class="v">原始请求体 bytes；Content-Type 含 json 时自动解析（失败为 None）</td></tr>
<tr><td class="e">_COOKIE</td><td class="v">客户端 cookie 字典</td></tr>
<tr><td class="e">_SESSION</td><td class="v">会话字典（签名 cookie + 时间戳，无服务端存储；原地增删改，勿整体重绑定）</td></tr>
</table>

<p class="foot">
makoinfo() - generated at ${_esc(_now)} by MakoServer ${_esc(_ms_version)}
(Flask ${_esc(_flask.__version__)} / Werkzeug ${_esc(_wz.__version__)} / Mako ${_esc(_mako.__version__)})
</p>

</div>
</body>
</html>
