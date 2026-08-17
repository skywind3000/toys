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


def test_escape_html_chars (site, wf, client_factory):
    # < > & " ' 全转义（quote=True）
    wf('t.mako', """<% echo(escape("<a href='x'>&")) %>""")
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'&lt;a href=&#x27;x&#x27;&gt;&amp;'


def test_escape_number_first_str (site, wf, client_factory):
    # 整数/浮点先 str() 再转义
    wf('t.mako', '<% echo(escape(42), "|", escape(1.5), "|", escape(None)) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'42|1.5|None'


def test_escape_returns_not_writes (site, wf, client_factory):
    # escape 是纯转换：返回值用于插值，本身不写输出
    wf('t.mako', '[${escape("<b>")}]')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'[&lt;b&gt;]'


def test_resp_escape_same_function (site, wf, client_factory):
    # RESP.escape 与注入的 escape 同一函数对象
    wf('t.mako', '<% echo("T" if RESP.escape is escape else "F") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'T'


def test_resp_escape_shadow_fallback (site, wf, client_factory):
    # escape 被局部变量覆盖时，规范名 RESP.escape 兜底
    wf('t.mako', '<%\n escape = 123\n%><% echo(RESP.escape("<x>")) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'&lt;x&gt;'
