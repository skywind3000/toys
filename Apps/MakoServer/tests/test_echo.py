# -*- coding: utf-8 -*-
#======================================================================
#
# test_echo.py - echo 文本类型矩阵、RESP.write 兜底与 writeraw/echoraw
#
#======================================================================


def test_echo_str (site, wf, client_factory):
    wf('t.mako', '<% echo("abc") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'abc'


def test_echo_bytes_typeerror_500 (site, wf, client_factory):
    # echo 只接受文本：bytes → TypeError → 500，错误信息指向 writeraw
    wf('t.mako', '<% echo(b"\\x00\\x01BIN") %>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.status_code == 500
    assert b'echo() accepts text only' in r.data


def test_echo_bytearray_typeerror_500 (site, wf, client_factory):
    wf('t.mako', '<% echo(bytearray(b"BA")) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').status_code == 500


def test_echo_memoryview_typeerror_500 (site, wf, client_factory):
    wf('t.mako', '<% echo(memoryview(b"MV")) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').status_code == 500


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
    wf('t.mako', '<% echo("a", None, "b", "c") %>')
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


#----------------------------------------------------------------------
# RESP.writeraw / echoraw：独立二进制缓冲与短路
#----------------------------------------------------------------------

def test_echoraw_binary_body (site, wf, client_factory):
    wf('t.mako', '<% echoraw(b"\\x89PNG\\r\\n\\x1a\\n") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'\x89PNG\r\n\x1a\n'


def test_echoraw_append_mode (site, wf, client_factory):
    # 多次调用 / 多参数按序追加到同一二进制缓冲
    wf('t.mako', '<% echoraw(b"\\x00", b"\\x01") %>'
                 '<% echoraw(bytearray(b"\\x02"), memoryview(b"\\x03")) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'\x00\x01\x02\x03'


def test_echoraw_short_circuits_text (site, wf, client_factory):
    # 一旦使用 writeraw，模板文本块与 echo 输出整体被短路
    wf('t.mako', 'HEAD<% echo("TEXT") %><% echoraw(b"RAW") %>TAIL\n')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'RAW'


def test_echoraw_eof_newline_not_polluting (site, wf, client_factory):
    # 精确二进制脚本无需关心编辑器 EOF 换行（短路兑现，非 rstrip）
    wf('bin.mako', '<% echoraw(b"\\x89PNG") %>\n\n   \n')
    cli = client_factory(site)
    assert cli.get('/bin.mako').data == b'\x89PNG'


def test_echoraw_does_not_set_content_type (site, wf, client_factory):
    # writeraw 不负责 Content-Type：未显式设置时仍是默认 text/html
    wf('t.mako', '<% echoraw(b"RAW") %>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.content_type == 'text/html; charset=utf-8'
    assert r.data == b'RAW'


def test_echoraw_manual_content_type (site, wf, client_factory):
    wf('t.mako', '<%\nRESP.header("Content-Type", "image/png")\n'
       'echoraw(b"\\x89PNG")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.content_type == 'image/png'
    assert r.data == b'\x89PNG'


def test_echoraw_headers_status_still_apply (site, wf, client_factory):
    # 短路只作用于 body：status / 自定义 header / cookie 照常下发
    wf('t.mako', '<%\nRESP.status(418)\nRESP.header("X-Raw", "1")\n'
       'RESP.setcookie("c", "v")\nechoraw(b"RAW")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.status_code == 418
    assert r.headers['X-Raw'] == '1'
    assert 'c=v' in r.headers['Set-Cookie']
    assert r.data == b'RAW'


def test_echoraw_empty_call_short_circuits (site, wf, client_factory):
    # 零参数调用也触发短路：文本输出被丢弃、body 为空
    wf('t.mako', 'TEXT<% echoraw() %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b''


def test_writeraw_alias_same (site, wf, client_factory):
    # echoraw 与 RESP.writeraw 是同一方法（绑定方法相等）
    wf('t.mako', '<% echo("T" if echoraw == RESP.writeraw else "F") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'T'


def test_resp_writeraw_fallback_when_shadowed (site, wf, client_factory):
    # echoraw 被局部变量覆盖后，规范名 RESP.writeraw 兜底
    wf('t.mako', '<%\n echoraw = 123\n%><% RESP.writeraw(b"OK") %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'OK'


def test_writeraw_str_typeerror_500 (site, wf, client_factory):
    # writeraw 只接受 bytes-like：str → TypeError → 500
    wf('t.mako', '<% echoraw("text") %>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.status_code == 500
    assert b'writeraw() accepts bytes-like only' in r.data
