# -*- coding: utf-8 -*-
#======================================================================
#
# test_index.py - 目录 index 兜底
#
#======================================================================

import os


def test_index_order_mako_first (site, wf, client_factory):
    wf('index.mako', '<% echo("M") %>')
    wf('index.html', 'H')
    wf('index.htm', 'T')
    cli = client_factory(site)
    assert cli.get('/').data == b'M'


def test_index_order_html_second (site, wf, client_factory):
    wf('index.html', 'H')
    wf('index.htm', 'T')
    cli = client_factory(site)
    r = cli.get('/')
    assert r.data == b'H'
    assert r.content_type == 'text/html; charset=utf-8'


def test_index_order_htm_last (site, wf, client_factory):
    wf('index.htm', 'T')
    cli = client_factory(site)
    assert cli.get('/').data == b'T'


def test_index_all_missing_404 (site, client_factory):
    cli = client_factory(site)
    r = cli.get('/')
    assert r.status_code == 404
    assert r.data == b'404 Not Found\n'


def test_subdir_index (site, wf, client_factory):
    wf('sub/index.mako', '<% echo("SUB") %>')
    cli = client_factory(site)
    r = cli.get('/sub/')
    assert r.status_code == 200
    assert r.data == b'SUB'


def test_dir_index_html_exempts_trailing (site, wf, client_factory):
    # /dir/（有 index.html）→ 200：index 兜底豁免 trailing 判定回归
    wf('dir/index.html', 'DIRH')
    cli = client_factory(site)
    r = cli.get('/dir/')
    assert r.status_code == 200
    assert r.data == b'DIRH'


def test_dir_index_htm_exempts_trailing (site, wf, client_factory):
    wf('dir/index.htm', 'DIRT')
    cli = client_factory(site)
    r = cli.get('/dir/')
    assert r.status_code == 200
    assert r.data == b'DIRT'


def test_root_request_path_keys (site, wf, client_factory):
    # index 兜底渲染时 SCRIPT_NAME = 挂载前缀 + '/'，PATH_INFO=''
    wf('index.mako',
       '<% echo(_SERVER["SCRIPT_NAME"], "|", _SERVER["PATH_INFO"]) %>')
    cli = client_factory(site)
    assert cli.get('/').data == b'/|'


def test_subdir_fallback_script_keys (site, wf, client_factory):
    # SCRIPT_FILENAME 跟随实际渲染的 index.mako
    wf('sub/index.mako', '<% echo(_SERVER["SCRIPT_FILENAME"]) %>')
    cli = client_factory(site)
    r = cli.get('/sub/')
    expect = os.path.abspath(os.path.join(str(site), 'sub', 'index.mako'))
    assert r.data.decode('utf-8') == expect
