# -*- coding: utf-8 -*-
#======================================================================
#
# test_static.py - 静态分支：白名单 / 谓词 / 敏感屏蔽
#
#======================================================================

import os
import pytest


MATRIX = {
    'a.html': 'text/html; charset=utf-8',
    'a.htm': 'text/html; charset=utf-8',
    'a.txt': 'text/plain; charset=utf-8',
    'a.css': 'text/css; charset=utf-8',
    'a.js': 'text/javascript; charset=utf-8',
    'a.mjs': 'text/javascript; charset=utf-8',
    'a.json': 'application/json',
    'a.map': 'application/json',
    'a.xml': 'application/xml',
    'a.csv': 'text/csv; charset=utf-8',
    'a.md': 'text/markdown; charset=utf-8',
    'a.png': 'image/png',
    'a.jpg': 'image/jpeg',
    'a.jpeg': 'image/jpeg',
    'a.gif': 'image/gif',
    'a.svg': 'image/svg+xml',
    'a.ico': 'image/x-icon',
    'a.webp': 'image/webp',
    'a.avif': 'image/avif',
    'a.bmp': 'image/bmp',
    'a.woff': 'font/woff',
    'a.woff2': 'font/woff2',
    'a.ttf': 'font/ttf',
    'a.otf': 'font/otf',
    'a.eot': 'application/vnd.ms-fontobject',
    'a.mp3': 'audio/mpeg',
    'a.ogg': 'audio/ogg',
    'a.wav': 'audio/wav',
    'a.mp4': 'video/mp4',
    'a.webm': 'video/webm',
    'a.wasm': 'application/wasm',
    'a.pdf': 'application/pdf',
    'a.zip': 'application/zip',
    'a.rar': 'application/vnd.rar',
    'a.7z': 'application/x-7z-compressed',
    'a.tar': 'application/x-tar',
    'a.gz': 'application/gzip',
    'a.tgz': 'application/gzip',
    'a.xz': 'application/x-xz',
}


def test_whitelist_matrix (site, wfb, client_factory):
    for fn, ctype in MATRIX.items():
        wfb(fn, b'PAYLOAD-' + fn.encode('ascii'))
    cli = client_factory(site)
    for fn, ctype in MATRIX.items():
        r = cli.get('/' + fn)
        assert r.status_code == 200, fn
        assert r.content_type == ctype, fn
        assert r.data == b'PAYLOAD-' + fn.encode('ascii'), fn


def test_whitelist_outside_404 (site, wf, client_factory):
    for fn in ('s.py', 's.pyw', 's.pyo', 's.pyc', 's.php', 's.ini',
               's.bak', 's.db', 's.log', 'noext'):
        wf(fn, 'print(1)')
    cli = client_factory(site)
    for fn in ('s.py', 's.pyw', 's.pyo', 's.pyc', 's.php', 's.ini',
               's.bak', 's.db', 's.log', 'noext'):
        r = cli.get('/' + fn)
        assert r.status_code == 404, fn
        assert r.data == b'404 Not Found\n', fn


def test_method_not_allowed (site, wf, client_factory):
    wf('a.txt', 'hello')
    cli = client_factory(site)
    for m in ('POST', 'PUT', 'DELETE', 'PATCH'):
        r = cli.open('/a.txt', method=m)
        assert r.status_code == 405, m
        assert r.headers['Allow'] == 'GET, HEAD', m
        assert r.data == b'405 Method Not Allowed\n', m


def test_method_outside_whitelist_still_404 (site, wf, client_factory):
    # 白名单外路径无论谓词一律 404（不因 405 泄露存在性）
    wf('s.py', 'x')
    cli = client_factory(site)
    r = cli.open('/s.py', method='PUT')
    assert r.status_code == 404


def test_get_head_ok (site, wf, client_factory):
    wf('a.txt', 'hello')
    cli = client_factory(site)
    assert cli.get('/a.txt').data == b'hello'
    r = cli.head('/a.txt')
    assert r.status_code == 200
    assert r.data == b''


def test_uppercase_ext_normalized (site, wfb, client_factory):
    wfb('IMG.PNG', b'\x89PNG')
    cli = client_factory(site)
    r = cli.get('/IMG.PNG')
    assert r.status_code == 200
    assert r.content_type == 'image/png'


def test_makoserver_py_itself_404 (site, wf, client_factory):
    # makoserver.py 拷进 root 也不可得（.py 不在白名单）
    wf('makoserver.py', 'print("source")')
    cli = client_factory(site)
    r = cli.get('/makoserver.py')
    assert r.status_code == 404


def test_binary_bytes_intact (site, wfb, client_factory):
    data = bytes(range(256)) * 4
    wfb('pic.png', data)
    cli = client_factory(site)
    assert cli.get('/pic.png').data == data


#----------------------------------------------------------------------
# 敏感路径屏蔽
#----------------------------------------------------------------------

def test_loaded_config_blocked (site, wf, client_factory):
    # 命中的配置文件（起名白名单类型）→ 404
    wf('conf.json', '[makoserver]\nroot = .\n')
    conf = os.path.join(str(site), 'conf.json')
    cli = client_factory(site, conf_file=conf)
    r = cli.get('/conf.json')
    assert r.status_code == 404


def test_config_log_blocked (site, wf, client_factory, tmp_path):
    # 已配置的日志文件（白名单名）→ 404
    wf('access.txt', '')
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\naccess_log = %s\n' % (
        str(site).replace('\\', '/'),
        os.path.join(str(site), 'access.txt').replace('\\', '/')),
        encoding='utf-8')
    cli = client_factory(site, conf_file=str(conf))
    r = cli.get('/access.txt')
    assert r.status_code == 404


def test_log_mako_direct_blocked (site, client_factory, tmp_path):
    # error_log 起名 log.mako：直接请求 404（不被当模板执行）
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\nerror_log = %s\n' % (
        str(site).replace('\\', '/'),
        os.path.join(str(site), 'log.mako').replace('\\', '/')),
        encoding='utf-8')
    cli = client_factory(site, conf_file=str(conf))
    r = cli.get('/log.mako')
    assert r.status_code == 404


def test_log_mako_walkback_blocked (site, client_factory, tmp_path):
    # 尾挂回溯旁路同堵：/log.mako/hello → 404
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\nerror_log = %s\n' % (
        str(site).replace('\\', '/'),
        os.path.join(str(site), 'log.mako').replace('\\', '/')),
        encoding='utf-8')
    cli = client_factory(site, conf_file=str(conf))
    r = cli.get('/log.mako/hello')
    assert r.status_code == 404


def test_log_mako_index_fallback_blocked (site, wf, client_factory, tmp_path):
    # 兜底旁路同堵：sub/index.mako 符号链接指向被屏蔽的 log.mako
    wf('sub/dummy.txt', 'x')
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\nerror_log = %s\n' % (
        str(site).replace('\\', '/'),
        os.path.join(str(site), 'log.mako').replace('\\', '/')),
        encoding='utf-8')
    cli = client_factory(site, conf_file=str(conf))
    link = os.path.join(str(site), 'sub', 'index.mako')
    target = os.path.join(str(site), 'log.mako')
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip('symlink not permitted on this platform')
    r = cli.get('/sub/')
    assert r.status_code == 404


def test_symlink_to_blocked_mako (site, client_factory, tmp_path):
    # link.mako → log.mako（被屏蔽）：直接请求与尾挂请求均 404
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\nerror_log = %s\n' % (
        str(site).replace('\\', '/'),
        os.path.join(str(site), 'log.mako').replace('\\', '/')),
        encoding='utf-8')
    cli = client_factory(site, conf_file=str(conf))
    link = os.path.join(str(site), 'link.mako')
    target = os.path.join(str(site), 'log.mako')
    try:
        os.symlink(target, link)
    except OSError:
        pytest.skip('symlink not permitted on this platform')
    assert cli.get('/link.mako').status_code == 404
    assert cli.get('/link.mako/hello').status_code == 404


def test_not_blocked_mako_renders (site, wf, client_factory, tmp_path):
    # 对照组：未被屏蔽的 .mako 照常渲染
    wf('ok.mako', '<% echo("OK") %>')
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\nerror_log = %s\n' % (
        str(site).replace('\\', '/'),
        os.path.join(str(site), 'log.mako').replace('\\', '/')),
        encoding='utf-8')
    cli = client_factory(site, conf_file=str(conf))
    r = cli.get('/ok.mako')
    assert r.status_code == 200
    assert r.data == b'OK'


#----------------------------------------------------------------------
# static_types 配置键（决策 #39）
#----------------------------------------------------------------------

def test_static_types_config_extends (site, wfb, client_factory, tmp_path):
    # 自定义扩展名进白名单；点号可省、大小写不敏感；可覆盖内置映射
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\n'
                    'static_types = dat=application/x-dat, '
                    '.TXT=text/x-override\n' % (
                        str(site).replace('\\', '/')), encoding='utf-8')
    wfb('a.dat', b'DAT-BYTES')
    wfb('a.txt', b'TXT')
    cli = client_factory(site, conf_file=str(conf))
    r = cli.get('/a.dat')
    assert r.status_code == 200
    assert r.content_type == 'application/x-dat'
    assert r.data == b'DAT-BYTES'
    # 覆盖内置 .txt 映射
    assert cli.get('/a.txt').content_type == 'text/x-override'


def test_static_types_not_configured_404 (site, wfb, client_factory):
    # 对照组：未配置时自定义扩展名仍 404（fail-closed 不变）
    wfb('a.dat', b'X')
    cli = client_factory(site)
    assert cli.get('/a.dat').status_code == 404
