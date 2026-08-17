# -*- coding: utf-8 -*-
#======================================================================
#
# test_paths.py - 路径解析：防穿透 / 大小写 / NT 特判 / 301 / 尾挂回溯
#
#======================================================================

import os
import pytest


INFO_MAKO = (
    '<% echo(_SERVER["SCRIPT_NAME"], "|", _SERVER["PATH_INFO"]) %>')
DEMO_MAKO = '<% echo("DEMO") %>'
INDEX_MAKO = '<% echo("INDEX", "|", _SERVER["PATH_INFO"]) %>'


@pytest.fixture
def cli (site, wf, client_factory):
    wf('demo.mako', DEMO_MAKO)
    wf('info.mako', INFO_MAKO)
    wf('index.mako', INDEX_MAKO)
    wf('sub/inner.mako', '<% echo("INNER") %>')
    wf('style.css', 'css-body')
    os.mkdir(os.path.join(str(site), 'dir'))
    return client_factory(site)


#----------------------------------------------------------------------
# 防穿透与拒绝
#----------------------------------------------------------------------

def test_dotdot_clamped (cli):
    # ../ 被钳制回 root 内 → 目标不存在 → 404（而非逃出 root）
    r = cli.get('/../../etc/passwd')
    assert r.status_code == 404
    assert r.data == b'404 Not Found\n'


def test_encoded_dotdot (cli):
    r = cli.get('/..%2f..%2f..%2fetc/passwd')
    assert r.status_code == 404


def test_nul_byte (cli):
    r = cli.get('/%00demo.mako')
    assert r.status_code == 404
    r = cli.get('/demo.mako%00')
    assert r.status_code == 404


def test_reject_same_body_as_not_found (cli):
    # 拒绝与不存在同响应体（防探测）
    r1 = cli.get('/..%2f..%2fx')
    r2 = cli.get('/definitely_not_exist_xyz')
    assert r1.status_code == 404 and r2.status_code == 404
    assert r1.data == r2.data


def test_root_itself_allowed (cli):
    # 请求 / 放行进入 index 兜底（不被 root 本身拒绝）
    r = cli.get('/')
    assert r.status_code == 200
    assert b'INDEX' in r.data


def test_mako_dir_is_404 (site, wf, client_factory):
    # 名为 foo.mako 的目录 → 404（非 500）
    os.mkdir(os.path.join(str(site), 'foo.mako'))
    cli = client_factory(site)
    r = cli.get('/foo.mako')
    assert r.status_code == 404
    assert r.data == b'404 Not Found\n'


#----------------------------------------------------------------------
# 大小写与平台特判
#----------------------------------------------------------------------

def test_uppercase_ext_renders (site, wf, client_factory):
    # demo.MAKO 全平台一致走模板分支（显式 lower 归一）
    wf('demo.MAKO', '<% echo("UPPER") %>')
    cli = client_factory(site)
    r = cli.get('/demo.MAKO')
    assert r.status_code == 200
    assert r.data == b'UPPER'


@pytest.mark.skipif(os.name != 'nt', reason='NTFS only')
def test_trailing_dot_windows (cli):
    # Windows 剥尾部点：demo.mako. → demo.mako 渲染
    r = cli.get('/demo.mako.')
    assert r.status_code == 200
    assert r.data == b'DEMO'


@pytest.mark.skipif(os.name == 'nt', reason='posix only')
def test_trailing_dot_linux (site, wf, client_factory):
    # Linux 下 demo.mako. 是字面文件名，不存在 → 404 fail-closed
    cli = client_factory(site)
    r = cli.get('/demo.mako.')
    assert r.status_code == 404


@pytest.mark.skipif(os.name != 'nt', reason='NTFS only')
def test_ads_data_stream (cli):
    # demo.mako::$DATA → 404（含 ':' 拒绝），防源码经数据流泄露
    r = cli.get('/demo.mako::$DATA')
    assert r.status_code == 404


@pytest.mark.skipif(os.name != 'nt', reason='Windows only')
def test_dos_device_names (cli):
    # DOS 设备名 → 404（commonpath ValueError 兜底回归，非 500）
    for name in ('/nul', '/con.txt', '/aux', '/com1.css'):
        r = cli.get(name)
        assert r.status_code == 404, name


def test_symlink_out_of_root (site, wf, client_factory, tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    secret = outside / 'secret.txt'
    secret.write_text('TOP-SECRET', encoding='utf-8')
    link = os.path.join(str(site), 'link.txt')
    try:
        os.symlink(str(secret), link)
    except OSError:
        pytest.skip('symlink not permitted on this platform')
    cli = client_factory(site)
    r = cli.get('/link.txt')
    assert r.status_code == 404


#----------------------------------------------------------------------
# 目录 301 补斜杠
#----------------------------------------------------------------------

def test_dir_no_slash_301 (cli):
    r = cli.get('/dir')
    assert r.status_code == 301
    assert r.headers['Location'].endswith('/dir/')


def test_dir_no_slash_301_keeps_query (cli):
    r = cli.get('/dir?a=1&b=2')
    assert r.status_code == 301
    loc = r.headers['Location']
    assert '/dir/?' in loc
    assert 'a=1' in loc and 'b=2' in loc


def test_dir_with_slash_fallback (cli):
    r = cli.get('/dir/')
    assert r.status_code == 404     # dir 下无 index.* → 404
    r = cli.get('/')
    assert r.status_code == 200


def test_mount_dir_301_has_prefix (cli):
    # WSGI 挂载场景：Location 必须含挂载前缀，不跳出应用
    r = cli.get('/dir', environ_overrides={'SCRIPT_NAME': '/app1'})
    assert r.status_code == 301
    loc = r.headers['Location']
    assert '/app1/dir/' in loc


def test_mount_root_no_slash_301 (cli):
    # 挂载根无斜杠（environ PATH_INFO=''）→ 301 补斜杠
    r = cli.get('/', environ_overrides={'SCRIPT_NAME': '/app1',
                                        'PATH_INFO': ''})
    assert r.status_code == 301
    assert r.headers['Location'].endswith('/app1/')


def test_mount_root_no_slash_keeps_query (cli):
    r = cli.get('/', environ_overrides={'SCRIPT_NAME': '/app1',
                                        'PATH_INFO': '',
                                        'QUERY_STRING': 'x=9'})
    assert r.status_code == 301
    assert r.headers['Location'].endswith('/app1/?x=9')


def test_merge_slashes_308 (cli):
    # 重复斜杠 → 308 归并（spec 3.1 前置归一）
    r = cli.get('/', environ_overrides={'PATH_INFO': '//demo.mako'})
    assert r.status_code == 308
    assert r.headers['Location'].endswith('/demo.mako')


def test_merge_slashes_keeps_query (cli):
    r = cli.get('/', environ_overrides={'PATH_INFO': '//a///b',
                                        'QUERY_STRING': 'q=1'})
    assert r.status_code == 308
    loc = r.headers['Location']
    assert '/a/b' in loc and 'q=1' in loc


def test_merge_slashes_308_non_ascii (cli):
    # 非 ASCII 路径：真实 WSGI 服务器按 PEP 3333 以 latin-1 承载
    # UTF-8 字节，Location 须还原后再重编码（解码舞步回归）
    raw = '//中文/a.txt'.encode('utf-8').decode('latin-1')
    r = cli.get('/', environ_overrides={'PATH_INFO': raw})
    assert r.status_code == 308
    assert r.headers['Location'].endswith('/%E4%B8%AD%E6%96%87/a.txt')


def test_mount_root_301_non_ascii_prefix (cli):
    # 挂载前缀含非 ASCII：301 Location 同受解码舞步保护
    raw_sn = '/应用'.encode('utf-8').decode('latin-1')
    r = cli.get('/', environ_overrides={'SCRIPT_NAME': raw_sn,
                                        'PATH_INFO': ''})
    assert r.status_code == 301
    assert r.headers['Location'].endswith('/%E5%BA%94%E7%94%A8/')


#----------------------------------------------------------------------
# 裸尾斜杠
#----------------------------------------------------------------------

def test_static_trailing_slash_404 (cli):
    r = cli.get('/style.css/')
    assert r.status_code == 404


def test_mako_trailing_slash_renders (cli):
    # /demo.mako/ → 照常渲染，PATH_INFO='/'
    r = cli.get('/info.mako/')
    assert r.status_code == 200
    assert r.data == b'/info.mako|/'


#----------------------------------------------------------------------
# 尾挂回溯（PATH_INFO）
#----------------------------------------------------------------------

def test_walkback_renders_mako (cli):
    r = cli.get('/index.mako/hello')
    assert r.status_code == 200
    assert r.data == b'INDEX|/hello'


def test_walkback_trailing_restored (cli):
    # 原始请求带尾斜杠时 PATH_INFO 补回尾斜杠
    r = cli.get('/index.mako/hello/')
    assert r.status_code == 200
    assert r.data == b'INDEX|/hello/'


def test_walkback_deep (cli):
    r = cli.get('/index.mako/a/b/c')
    assert r.status_code == 200
    assert r.data == b'INDEX|/a/b/c'


def test_walkback_static_404 (cli):
    # 静态文件不带尾挂
    r = cli.get('/style.css/hello')
    assert r.status_code == 404


def test_walkback_exhausted_404 (cli):
    r = cli.get('/a/b/c')
    assert r.status_code == 404


def test_walkback_dir_404 (cli):
    # 回溯碰到存在的目录 → 404（不兜底 index）
    r = cli.get('/dir/x')
    assert r.status_code == 404
    r = cli.get('/dir/x/y/z')
    assert r.status_code == 404


def test_walkback_nonexist_mako_404 (cli):
    # /nonexist.mako/x：回溯到 nonexist.mako 亦非文件 → 404
    r = cli.get('/nonexist.mako/x')
    assert r.status_code == 404
