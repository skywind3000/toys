# -*- coding: utf-8 -*-
#======================================================================
#
# test_template.py - 模板加载：渲染 / mtime reload / 尾部截断 / BOM / include
#
#======================================================================

import os


def test_basic_render (site, wf, client_factory):
    wf('t.mako', 'hello <% echo("world") %>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.status_code == 200
    assert r.content_type == 'text/html; charset=utf-8'
    assert r.data == b'hello world'


def test_mtime_reload (site, wf, client_factory):
    path = wf('t.mako', '<% echo("V1") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'V1'
    # 改写内容（长度变化）并显式推后 mtime，强制跨文件系统时间精度
    with open(path, 'w', encoding='utf-8') as fp:
        fp.write('<% echo("VERSION2") %>')
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 8))
    assert cli.get('/t.mako').data == b'VERSION2'


def test_size_change_reload (site, wf, client_factory):
    path = wf('t.mako', '<% echo("AAA") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'AAA'
    with open(path, 'w', encoding='utf-8') as fp:
        fp.write('<% echo("BBBBBBBB") %>')
    os.utime(path, ns=(0, 0))     # mtime 故意不动，size 变也应 reload
    assert cli.get('/t.mako').data == b'BBBBBBBB'


def test_trailing_whitespace_truncated (site, wf, client_factory):
    # 整文件单一代码块 + 二进制输出：%> 后的尾部空白不属于输出
    wf('bin.mako', '<% echo(b"\\x89PNG\\r\\n\\x1a\\n") %>\n\n   \n')
    cli = client_factory(site)
    r = cli.get('/bin.mako')
    assert r.data == b'\x89PNG\r\n\x1a\n'


def test_text_template_trailing_newline_truncated (site, wf, client_factory):
    wf('t.mako', 'hello\n\n\n')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'hello'


def test_bom_file (site, wfb, client_factory):
    # Windows 记事本 BOM 兼容
    wfb('bom.mako', b'\xef\xbb\xbf<% echo("BOM") %>')
    cli = client_factory(site)
    assert cli.get('/bom.mako').data == b'BOM'


def test_include_relative (site, wf, client_factory):
    # include 相对解析基准 = 被包含者所在目录（HTTP 模式即 root 下的相对）
    wf('sub/page.mako', '[<%include file="inc.mako"/>]')
    wf('sub/inc.mako', 'INC')
    cli = client_factory(site)
    assert cli.get('/sub/page.mako').data == b'[INC]'


def test_include_from_root (site, wf, client_factory):
    wf('page.mako', '[<%include file="/header.mako"/>]')
    wf('header.mako', 'HEAD')
    cli = client_factory(site)
    assert cli.get('/page.mako').data == b'[HEAD]'


def test_inherit (site, wf, client_factory):
    wf('base.mako', 'BASE[${self.body()}]')
    wf('child.mako', '<%inherit file="base.mako"/>CHILD')
    cli = client_factory(site)
    assert cli.get('/child.mako').data == b'BASE[CHILD]'


def test_include_missing_500 (site, wf, client_factory):
    wf('t.mako', '<%include file="no_such.mako"/>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.status_code == 500


def test_compile_error_500 (site, wf, client_factory):
    wf('bad.mako', '<% this is not python >>> %>')
    cli = client_factory(site)
    r = cli.get('/bad.mako')
    assert r.status_code == 500
    assert b'500 Internal Server Error' in r.data


def test_runtime_error_discards_partial (site, wf, client_factory):
    # 渲染中途抛异常：丢弃 partial output，返回干净 500
    wf('t.mako', 'PARTIAL<% raise RuntimeError("stop") %>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.status_code == 500
    assert b'PARTIAL' not in r.data
    assert b'stop' in r.data      # traceback 含异常信息
