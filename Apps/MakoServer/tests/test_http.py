# -*- coding: utf-8 -*-
#======================================================================
#
# test_http.py - 端到端（Flask test client）：头/状态/错误页/日志
#
#======================================================================

import os
import time


def test_default_content_type (site, wf, client_factory):
    wf('t.mako', '<% echo("x") %>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.content_type == 'text/html; charset=utf-8'


def test_explicit_content_type (site, wf, client_factory):
    wf('t.mako', '<%\nRESP.header("Content-Type", "image/png")\n'
       'echoraw(b"\\x89PNG")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.content_type == 'image/png'
    assert r.data == b'\x89PNG'


def test_status_and_headers (site, wf, client_factory):
    wf('t.mako', '<%\nRESP.status(418)\nRESP.header("X-Tea", "pot")\n'
       'echo("short")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.status_code == 418
    assert r.headers['X-Tea'] == 'pot'


def test_setcookie_roundtrip (site, wf, client_factory):
    wf('set.mako', '<%\nRESP.setcookie("pref", "dark")\necho("S")\n%>')
    wf('get.mako', '<% echo(_COOKIE.get("pref", "-")) %>')
    cli = client_factory(site)
    r1 = cli.get('/set.mako')
    assert 'pref=dark' in r1.headers['Set-Cookie']
    r2 = cli.get('/get.mako', headers={'Cookie': 'pref=dark'})
    assert r2.data == b'dark'


def test_404_plain_text (site, client_factory):
    cli = client_factory(site)
    r = cli.get('/nope.mako')
    assert r.status_code == 404
    assert r.content_type == 'text/plain; charset=utf-8'
    assert r.data == b'404 Not Found\n'


def test_500_traceback_escaped (site, wf, client_factory):
    # 500 页含转义后的 traceback 与请求路径；<script> 注入路径被转义
    wf('err.mako', '<% raise RuntimeError("boom") %>')
    cli = client_factory(site)
    r = cli.get('/err.mako/%3Cscript%3Ealert(1)%3C/script%3E')
    assert r.status_code == 500
    assert r.content_type == 'text/html; charset=utf-8'
    assert b'<h1>500 Internal Server Error</h1>' in r.data
    # 注入串以转义形式出现，原始 <script> 标签不得出现
    assert b'&lt;script&gt;' in r.data
    assert b'<script>' not in r.data
    assert b'boom' in r.data


def test_500_path_echoed_escaped (site, wf, client_factory):
    wf('err.mako', '<% raise RuntimeError("x") %>')
    cli = client_factory(site)
    r = cli.get('/err.mako')
    assert b'/err.mako' in r.data


def test_all_methods_render (site, wf, client_factory):
    # PUT / DELETE / PATCH / POST / OPTIONS 均到达脚本，method 如实传递
    wf('t.mako', '<% echo(_SERVER["REQUEST_METHOD"]) %>')
    cli = client_factory(site)
    for m in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'):
        r = cli.open('/t.mako', method=m)
        assert r.status_code == 200, m
        assert r.data == m.encode('ascii'), m


def test_options_not_auto_answered (site, wf, client_factory):
    # provide_automatic_options=False 回归：OPTIONS 不返回 Flask 自动 Allow
    wf('t.mako', '<% echo("SCRIPT") %>')
    cli = client_factory(site)
    r = cli.open('/t.mako', method='OPTIONS')
    assert r.status_code == 200
    assert r.data == b'SCRIPT'
    assert 'Allow' not in r.headers


def test_head_static_empty_body (site, wf, client_factory):
    wf('a.txt', 'hello-world')
    cli = client_factory(site)
    r = cli.head('/a.txt')
    assert r.status_code == 200
    assert r.data == b''


def test_index_html_put_405 (site, wf, client_factory):
    # index 兜底落 index.html 时 PUT → 405
    wf('sub/index.html', 'H')
    cli = client_factory(site)
    r = cli.open('/sub/', method='PUT')
    assert r.status_code == 405
    assert r.headers['Allow'] == 'GET, HEAD'


def test_index_mako_put_renders (site, wf, client_factory):
    # index 兜底落 index.mako 时 PUT 照常渲染（全谓词）
    wf('sub/index.mako', '<% echo("M=", _SERVER["REQUEST_METHOD"]) %>')
    cli = client_factory(site)
    r = cli.open('/sub/', method='PUT')
    assert r.status_code == 200
    assert r.data == b'M=PUT'


def test_binary_download_headers (site, wf, client_factory):
    # 二进制输出脚本显式指定类型 + 自定义 header（echoraw 短路文本）
    wf('dl.mako', '<%\nRESP.header("Content-Type", "application/octet-stream")\n'
       'RESP.header("Content-Disposition", "attachment; filename=x.bin")\n'
       'echoraw(b"\\x00\\x01\\x02")\n%>')
    cli = client_factory(site)
    r = cli.get('/dl.mako')
    assert r.content_type == 'application/octet-stream'
    assert r.headers['Content-Disposition'] == 'attachment; filename=x.bin'
    assert r.data == b'\x00\x01\x02'


def test_access_log_written (site, wf, app_factory, tmp_path):
    wf('t.mako', '<% echo("x") %>')
    logfile = tmp_path / 'access.log'
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\naccess_log = %s\n' % (
        str(site).replace('\\', '/'),
        str(logfile).replace('\\', '/')), encoding='utf-8')
    app = app_factory(conf_file=str(conf))
    cli = app.test_client()
    cli.get('/t.mako?a=1')
    cli.get('/nope')
    time.sleep(0.01)
    lines = logfile.read_text(encoding='utf-8').strip().splitlines()
    assert len(lines) == 2
    assert '/t.mako?a=1' in lines[0]
    assert ' 200 ' in lines[0]
    assert '/nope' in lines[1]
    assert ' 404 ' in lines[1]


def test_error_log_written (site, wf, app_factory, tmp_path):
    wf('err.mako', '<% raise RuntimeError("logged-boom") %>')
    logfile = tmp_path / 'error.log'
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\nerror_log = %s\n' % (
        str(site).replace('\\', '/'),
        str(logfile).replace('\\', '/')), encoding='utf-8')
    app = app_factory(conf_file=str(conf))
    cli = app.test_client()
    r = cli.get('/err.mako')
    assert r.status_code == 500
    text = logfile.read_text(encoding='utf-8')
    assert 'logged-boom' in text
    assert 'Traceback' in text


def test_zero_config_module_dir (mako_mod):
    # WSGI 零配置：root 回退 makoserver.py 所在目录
    app = mako_mod.create_app(default_root=mako_mod.MODULE_DIR)
    assert app.mako_server.root == os.path.abspath(mako_mod.MODULE_DIR)


def test_concurrent_apps_isolated (site, tmp_path, mako_mod, wf):
    # 同进程多个 app 实例互不串扰（logger / store 独立）
    wf('t.mako', '<% echo("A") %>')
    site_b = tmp_path / 'site_b'
    site_b.mkdir()
    (site_b / 't.mako').write_text('<% echo("B") %>', encoding='utf-8')
    app_a = mako_mod.create_app(root=str(site))
    app_b = mako_mod.create_app(root=str(site_b))
    assert app_a.test_client().get('/t.mako').data == b'A'
    assert app_b.test_client().get('/t.mako').data == b'B'


#----------------------------------------------------------------------
# setcookie 值编码（决策 #31）与请求体上限（决策 #32）
#----------------------------------------------------------------------

def test_setcookie_value_percent_encoded (site, wf, client_factory):
    # 含 ; , = 空格的值 percent-encode 下发，不被 cookie 语法截断
    wf('t.mako', '<%\nRESP.setcookie("k", "a;b,c=d e")\necho("S")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert 'k=a%3Bb%2Cc%3Dd%20e' in r.headers['Set-Cookie']


def test_setcookie_roundtrip_special_chars (site, wf, client_factory):
    # 写侧编码 + _COOKIE 读侧解码，特殊字符值往返闭合
    wf('r.mako', '<% echo(_COOKIE.get("k", "-")) %>')
    cli = client_factory(site)
    # Werkzeug >=2.3 的 test client 丢弃手工 Cookie 头（jar 接管），
    # 用 set_cookie 原样塞入编码后的值
    import inspect
    params = list(inspect.signature(cli.set_cookie).parameters)
    if params and params[0] == 'server_name':
        cli.set_cookie('localhost', 'k', 'a%3Bb%2Cc%3Dd%20e')
    else:
        cli.set_cookie('k', 'a%3Bb%2Cc%3Dd%20e')
    r = cli.get('/r.mako')
    assert r.data == 'a;b,c=d e'.encode('utf-8')


def test_setcookie_raw_channel_untouched (site, wf, client_factory):
    # RESP.header('Set-Cookie') 原样逃生舱（= PHP setrawcookie）不做编码
    wf('t.mako', '<%\nRESP.header("Set-Cookie", "raw=a;b; Path=/")\necho("S")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert 'raw=a;b; Path=/' in r.headers.get_all('Set-Cookie')


def test_setcookie_space_and_plus_form (site, wf, client_factory):
    # 与 PHP urlencode 的字节分歧钉死（决策 #31）：空格 → %20（非 +），
    # 字面 + → %2B——输出永远没有裸 +，PHP 惯用的读侧
    # replace(/\+/g,' ') 加固对本框架恒为 no-op
    wf('t.mako', '<%\nRESP.setcookie("k", "a+b c")\necho("S")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert 'k=a%2Bb%20c' in r.headers['Set-Cookie']


def test_max_body_default_64mb (site, app_factory):
    # 默认上限 64MB 存在（映射 Flask MAX_CONTENT_LENGTH）
    app = app_factory(root=str(site))
    assert app.config['MAX_CONTENT_LENGTH'] == 67108864


def test_max_body_413 (site, wf, app_factory, tmp_path):
    # POST 超过配置的 max_body → 413
    wf('t.mako', '<% echo(len(_BODY)) %>')
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\nmax_body = 1000\n' % (
        str(site).replace('\\', '/')), encoding='utf-8')
    cli = app_factory(conf_file=str(conf)).test_client()
    ok = cli.post('/t.mako', data=b'x' * 500)
    assert ok.status_code == 200 and ok.data == b'500'
    r = cli.post('/t.mako', data=b'x' * 2000)
    assert r.status_code == 413


def test_max_body_zero_unlimited (site, wf, app_factory, tmp_path):
    # max_body <= 0 解除限制
    wf('t.mako', '<% echo(len(_BODY)) %>')
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\nmax_body = 0\n' % (
        str(site).replace('\\', '/')), encoding='utf-8')
    app = app_factory(conf_file=str(conf))
    assert app.config['MAX_CONTENT_LENGTH'] is None
    r = app.test_client().post('/t.mako', data=b'x' * 2000)
    assert r.status_code == 200 and r.data == b'2000'
