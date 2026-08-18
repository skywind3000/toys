# -*- coding: utf-8 -*-
#======================================================================
#
# test_buffer.py - 公开 API 渲染路径与文本/二进制双缓冲单元测试
#
# 渲染只用 Mako 公开 API（Context + render_context，官方文档
# "using the Context programmatically" 模式），文本缓冲为 StringIO，
# 二进制走 RESP.writeraw/echoraw 独立缓冲。
#
#======================================================================

import io

import pytest
from mako.template import Template
from mako.runtime import Context


def render (mako_mod, source):
    """用与 makoserver 相同的公开 API 路径渲染模板源。

    返回 (文本输出, (raw_used, raw_bytes))。
    """
    buf = io.StringIO()
    echo = mako_mod.make_echo(buf)
    resp = mako_mod.RespObject(echo, cli=True)
    bridge = {'echo': echo, 'echoraw': resp.writeraw, 'RESP': resp}
    tpl = Template(source)
    ctx = Context(buf, **bridge)
    tpl.render_context(ctx)
    return buf.getvalue(), resp.collect_raw()


def test_text_and_echo_interleave (mako_mod):
    # 文本块与 echo 顺序交错，共享同一文本缓冲
    text, _ = render(mako_mod, 'A<% echo("B") %>C')
    assert text == 'ABC'


def test_text_utf8 (mako_mod):
    text, _ = render(mako_mod, '中文 ${"测试"}')
    assert text == '中文 测试'


def test_trailing_newline_preserved (mako_mod):
    # 文本模式不做 rstrip：模板源尾部换行忠实保留
    text, _ = render(mako_mod, 'hello\n')
    assert text == 'hello\n'


def test_echo_bytes_typeerror (mako_mod):
    # echo 只接受文本：bytes-like 抛 TypeError
    with pytest.raises(TypeError):
        render(mako_mod, '<% echo(b"BIN") %>')


def test_writeraw_appends_and_flags (mako_mod):
    # writeraw 追加模式写独立二进制缓冲，一旦调用即置 raw 标志
    text, (used, raw) = render(
        mako_mod, 'TXT<% echoraw(b"\\x00", b"\\x01") %>'
                  '<% echoraw(bytearray(b"\\x02"), memoryview(b"\\x03")) %>')
    assert used is True
    assert raw == b'\x00\x01\x02\x03'
    # 文本缓冲照常写入（短路发生在组装阶段，渲染期不报错）
    assert text == 'TXT'


def test_writeraw_str_typeerror (mako_mod):
    # writeraw 只接受 bytes-like：str 抛 TypeError
    with pytest.raises(TypeError):
        render(mako_mod, '<% echoraw("text") %>')


def test_writeraw_empty_call_sets_flag (mako_mod):
    # 零参数调用同样触发短路标志
    _, (used, raw) = render(mako_mod, 'TXT<% echoraw() %>')
    assert used is True
    assert raw == b''


def test_no_writeraw_flag_unset (mako_mod):
    _, (used, raw) = render(mako_mod, 'TXT')
    assert used is False
    assert raw == b''
