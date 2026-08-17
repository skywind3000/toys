# -*- coding: utf-8 -*-
from mako import runtime
from mako.template import Template


class BytesBuffer:
    def __init__(self):
        self.data = bytearray()

    def write(self, s):
        if isinstance(s, str):
            s = s.encode('utf-8')
        self.data.extend(s)

    def truncate(self):
        self.data = bytearray()

    def getvalue(self):
        return bytes(self.data)


def render_bytes(tpl, **kw):
    buf = BytesBuffer()
    ctx = runtime.Context(buf, **kw)
    ctx._outputting_as_unicode = False
    ctx._set_with_template(tpl)
    runtime._render_context(tpl, tpl.callable_, ctx)
    return buf.getvalue()


# 1) 文本与二进制混排
t1 = Template('hello <% context.write(b"-BIN-") %> world')
print('mixed :', repr(render_bytes(t1)))

# 2) 纯二进制（PNG 头），%> 后无尾部换行
src = b'<% context.write(b"\\x89PNG\\r\\n\\x1a\\n") %>'
t2 = Template(src.decode('ascii'))
print('exact :', repr(render_bytes(t2)))

# 3) 纯二进制但 %> 后带尾部换行（编辑器常见）
t3 = Template(src.decode('ascii') + '\n')
print('tailNL:', repr(render_bytes(t3)))

# 4) 中文文本 UTF-8 编码
t4 = Template('中文 ${"测试"}')
print('utf8  :', repr(render_bytes(t4)))
