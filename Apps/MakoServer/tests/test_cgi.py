# -*- coding: utf-8 -*-
#======================================================================
#
# test_cgi.py - 普通 CGI 运行模式（mod_cgi cgi-bin / Action 映射）
#
# 通过子进程模拟 CGI 环境（GATEWAY_INTERFACE 等 RFC 3875 变量），
# 验证 makoserver.py 直接执行时自动进入 CGI 模式、零配置文档根
# 回退 DOCUMENT_ROOT、以及配置链优先生效。
#
#======================================================================

import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MAKO = os.path.join(os.path.dirname(HERE), 'makoserver.py')


def make_env (tmp_path, root, path_info, method='GET', query='',
              extra=None):
    """构造隔离的 CGI 环境：HOME 指向假目录（防 ~/.config 泄漏），
    清掉 MAKOSERVER_CONF，root 经 DOCUMENT_ROOT 传入。"""
    home = tmp_path / 'fakehome'
    home.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.pop('MAKOSERVER_CONF', None)
    env['HOME'] = str(home)
    env['USERPROFILE'] = str(home)
    env.update({
        'GATEWAY_INTERFACE': 'CGI/1.1',
        'REQUEST_METHOD': method,
        'SCRIPT_NAME': '/cgi-bin/makoserver.py',
        'PATH_INFO': path_info,
        'QUERY_STRING': query,
        'SERVER_NAME': 'localhost',
        'SERVER_PORT': '80',
        'SERVER_PROTOCOL': 'HTTP/1.0',
        'DOCUMENT_ROOT': str(root),
    })
    if extra:
        env.update(extra)
    return env


def run_cgi (env, data=None, cwd=None):
    return subprocess.run([sys.executable, MAKO], env=env,
                          capture_output=True, input=data, cwd=cwd)


def parse_response (raw):
    """拆 CGI 输出：(status, headers dict, body bytes)。
    CGIHandler 仅在非 200 时输出 Status: 行。"""
    head, _, body = raw.partition(b'\r\n\r\n')
    status = 200
    headers = {}
    for line in head.split(b'\r\n'):
        if not line:
            continue
        name, _, value = line.partition(b':')
        name = name.strip().decode('latin-1').lower()
        value = value.strip().decode('latin-1')
        if name == 'status':
            status = int(value.split()[0])
        else:
            headers.setdefault(name, []).append(value)
    return status, headers, body


def test_render_template (tmp_path):
    site = tmp_path / 'site'
    site.mkdir()
    (site / 'index.mako').write_text(
        '<% echo("cgi-ok") %>', encoding='utf-8')
    env = make_env(tmp_path, site, '/index.mako')
    r = run_cgi(env, cwd=str(site))
    assert r.returncode == 0
    status, headers, body = parse_response(r.stdout)
    assert status == 200
    assert body == b'cgi-ok'
    assert headers['content-type'][0].startswith('text/html')


def test_zero_config_root_is_document_root (tmp_path):
    # 无任何配置文件：DOCUMENT_ROOT 即文档根
    site = tmp_path / 'site'
    site.mkdir()
    (site / 'sub' ).mkdir()
    (site / 'sub' / 'page.mako').write_text(
        '<% echo(_SERVER["DOCUMENT_ROOT"]) %>', encoding='utf-8')
    env = make_env(tmp_path, site, '/sub/page.mako')
    r = run_cgi(env)
    assert r.returncode == 0
    _, _, body = parse_response(r.stdout)
    assert body.decode('utf-8') == str(site)


def test_get_params (tmp_path):
    site = tmp_path / 'site'
    site.mkdir()
    (site / 'q.mako').write_text(
        '<% echo(_GET["a"], "|", _GET["b"]) %>', encoding='utf-8')
    env = make_env(tmp_path, site, '/q.mako', query='a=1&b=2')
    r = run_cgi(env)
    _, _, body = parse_response(r.stdout)
    assert body == b'1|2'


def test_post_form (tmp_path):
    site = tmp_path / 'site'
    site.mkdir()
    (site / 'p.mako').write_text(
        '<% echo(_SERVER["REQUEST_METHOD"], "|", _POST["x"]) %>',
        encoding='utf-8')
    env = make_env(tmp_path, site, '/p.mako', method='POST', extra={
        'CONTENT_TYPE': 'application/x-www-form-urlencoded',
        'CONTENT_LENGTH': '4',
    })
    r = run_cgi(env, data=b'x=77')
    _, _, body = parse_response(r.stdout)
    assert body == b'POST|77'


def test_pretty_url_path_info (tmp_path):
    # /t.mako/hello 尾挂：渲染 t.mako，PATH_INFO=/hello
    site = tmp_path / 'site'
    site.mkdir()
    (site / 't.mako').write_text(
        '<% echo(_SERVER["PATH_INFO"]) %>', encoding='utf-8')
    env = make_env(tmp_path, site, '/t.mako/hello')
    r = run_cgi(env)
    _, _, body = parse_response(r.stdout)
    assert body == b'/hello'


def test_static_whitelist (tmp_path):
    site = tmp_path / 'site'
    site.mkdir()
    (site / 'style.css').write_text('body{}', encoding='utf-8')
    env = make_env(tmp_path, site, '/style.css')
    r = run_cgi(env)
    status, headers, body = parse_response(r.stdout)
    assert status == 200
    assert headers['content-type'][0].startswith('text/css')
    assert body == b'body{}'


def test_outside_whitelist_404 (tmp_path):
    site = tmp_path / 'site'
    site.mkdir()
    (site / 'secret.py').write_text('print(1)', encoding='utf-8')
    env = make_env(tmp_path, site, '/secret.py')
    r = run_cgi(env)
    status, _, _ = parse_response(r.stdout)
    assert status == 404


def test_not_found_404 (tmp_path):
    site = tmp_path / 'site'
    site.mkdir()
    env = make_env(tmp_path, site, '/no-such.mako')
    r = run_cgi(env)
    status, _, _ = parse_response(r.stdout)
    assert status == 404


def test_config_overrides_document_root (tmp_path):
    # 配置 root 优先于 DOCUMENT_ROOT
    site = tmp_path / 'site'
    site.mkdir()
    real = tmp_path / 'realroot'
    real.mkdir()
    (real / 'c.mako').write_text(
        '<% echo("from-real-root") %>', encoding='utf-8')
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\n' % str(real),
                    encoding='utf-8')
    env = make_env(tmp_path, site, '/c.mako',
                   extra={'MAKOSERVER_CONF': str(conf)})
    r = run_cgi(env)
    status, _, body = parse_response(r.stdout)
    assert status == 200
    assert body == b'from-real-root'


def test_secondary_detection_without_gateway (tmp_path):
    # 无 GATEWAY_INTERFACE，靠 REQUEST_METHOD + SCRIPT_FILENAME
    # 兜底判定
    site = tmp_path / 'site'
    site.mkdir()
    (site / 'index.mako').write_text(
        '<% echo("fallback-detect") %>', encoding='utf-8')
    env = make_env(tmp_path, site, '/index.mako')
    env.pop('GATEWAY_INTERFACE')
    env['SCRIPT_FILENAME'] = '/var/www/cgi-bin/makoserver.py'
    r = run_cgi(env)
    _, _, body = parse_response(r.stdout)
    assert body == b'fallback-detect'


def test_cli_render_not_hijacked (tmp_path):
    # CLI 渲染模式不受 CGI 检测影响（shell 环境无 CGI 标志）
    script = tmp_path / 't.mako'
    script.write_text('<% echo("plain-cli") %>', encoding='utf-8')
    env = dict(os.environ)
    env.pop('GATEWAY_INTERFACE', None)
    env.pop('REQUEST_METHOD', None)
    r = subprocess.run([sys.executable, MAKO, str(script)],
                       capture_output=True, env=env)
    assert r.returncode == 0
    assert r.stdout == b'plain-cli'


def test_cgi_env_with_argv_not_hijacked (tmp_path):
    # argv 守卫：环境里泄漏 CGI 标志但命令行带位置参数 →
    # 仍走 CLI 渲染，不被 CGI 分支劫持（决策 #40）
    script = tmp_path / 't.mako'
    script.write_text('<% echo("argv-wins") %>', encoding='utf-8')
    env = dict(os.environ)
    env['GATEWAY_INTERFACE'] = 'CGI/1.1'
    env['REQUEST_METHOD'] = 'GET'
    env['SCRIPT_FILENAME'] = str(script)
    r = subprocess.run([sys.executable, MAKO, str(script)],
                       capture_output=True, env=env)
    assert r.returncode == 0
    assert r.stdout == b'argv-wins'      # 无 CGI 头，纯渲染结果
