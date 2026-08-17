# -*- coding: utf-8 -*-
#======================================================================
#
# test_echo.py - echo 类型矩阵与 RESP.write 兜底
#
#======================================================================


def test_echo_str (site, wf, client_factory):
    wf('t.mako', '<% echo("abc") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'abc'


def test_echo_bytes (site, wf, client_factory):
    wf('t.mako', '<% echo(b"\\x00\\x01BIN") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'\x00\x01BIN'


def test_echo_bytearray (site, wf, client_factory):
    wf('t.mako', '<% echo(bytearray(b"BA")) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'BA'


def test_echo_memoryview (site, wf, client_factory):
    wf('t.mako', '<% echo(memoryview(b"MV")) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'MV'


def test_echo_none_outputs_nothing (site, wf, client_factory):
    # 对齐 PHP echo null → 空串
    wf('t.mako', '<% echo(None) %>|')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'|'


def test_echo_other_types_str (site, wf, client_factory):
    wf('t.mako', '<% echo(42, 1.5, [1, 2]) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'421.5[1, 2]'


def test_echo_multi_args (site, wf, client_factory):
    wf('t.mako', '<% echo("a", b"b", None, "c") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'abc'


def test_echo_utf8 (site, wf, client_factory):
    wf('t.mako', '<% echo("中文") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == '中文'.encode('utf-8')


def test_resp_write_same (site, wf, client_factory):
    wf('t.mako', '<% RESP.write("RW") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'RW'


def test_resp_write_fallback_when_echo_shadowed (site, wf, client_factory):
    # echo 被模板局部变量覆盖后，规范名 RESP.write 兜底仍可用
    wf('t.mako', '<%\n echo = 123\n%><% RESP.write("OK") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'OK'


def test_mixed_text_and_echo (site, wf, client_factory):
    # 普通文本块与 echo 可混用
    wf('t.mako', 'A<% echo("B") %>C')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'ABC'
