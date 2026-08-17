# -*- coding: utf-8 -*-
#======================================================================
#
# test_cli.py - CLI 渲染模式（python makoserver.py script [args...]）
#
#======================================================================

import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
MAKO = os.path.join(os.path.dirname(HERE), 'makoserver.py')


def run_cli (args, cwd=None, data=None):
    return subprocess.run([sys.executable, MAKO] + list(args),
                          capture_output=True, cwd=cwd, input=data)


def test_stdout_bytes_exact (tmp_path):
    # 二进制输出字节精确（含 PNG 头），%> 后 EOF 换行不污染
    script = tmp_path / 'bin.mako'
    script.write_text(
        '<% echo(b"\\x89PNG\\r\\n\\x1a\\n") %>\n', encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.returncode == 0
    assert r.stdout == b'\x89PNG\r\n\x1a\n'


def test_text_output (tmp_path):
    script = tmp_path / 't.mako'
    script.write_text('<% echo("hello ", 1 + 1) %>', encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.returncode == 0
    assert r.stdout == b'hello 2'


def test_degraded_server (tmp_path):
    # 降级 _SERVER：GET / 空参数 / 空 REMOTE_ADDR
    script = tmp_path / 't.mako'
    script.write_text(
        '<% s = _SERVER %>'
        '<% echo(s["REQUEST_METHOD"], "|", s["QUERY_STRING"], "|", '
        's["REMOTE_ADDR"], "|", s["PATH_INFO"]) %>', encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.stdout == b'GET|||'


def test_degraded_empty_request_dicts (tmp_path):
    script = tmp_path / 't.mako'
    script.write_text(
        '<% echo(len(_GET), len(_POST), len(_REQUEST), len(_COOKIE), '
        'len(_BODY), _JSON is None) %>', encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.stdout == b'00000True'


def test_resp_noop (tmp_path):
    # CLI 下 RESP.header/status/setcookie/redirect 静默无效，不报错
    script = tmp_path / 't.mako'
    script.write_text(
        '<%\nRESP.header("X-A", "1")\nRESP.status(500)\n'
        'RESP.setcookie("c", "v")\nRESP.redirect("/x")\n%>'
        '<% echo("ALIVE") %>', encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.returncode == 0
    assert r.stdout == b'ALIVE'


def test_resp_json_cli (tmp_path):
    # CLI 下 RESP.json：Content-Type 丢弃、序列化文本照常输出
    script = tmp_path / 't.mako'
    script.write_text('<% RESP.json({"a": 1}) %>', encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.stdout == b'{"a":1}'


def test_argv_passthrough (tmp_path):
    # argv[0] = 脚本自身，其后参数（含 -- 前缀）原样透传
    script = tmp_path / 't.mako'
    script.write_text(
        '<% echo(";".join(_SERVER["argv"])) %>', encoding='utf-8')
    r = run_cli([str(script), 'one', '--flag', '-x'], cwd=str(tmp_path))
    expect = ';'.join([str(script), 'one', '--flag', '-x'])
    assert r.stdout.decode('utf-8') == expect


def test_script_keys (tmp_path):
    # SCRIPT_NAME / SCRIPT_FILENAME = 脚本绝对路径，SCRIPT_DIRNAME = 目录
    script = tmp_path / 't.mako'
    script.write_text(
        '<% s = _SERVER %>'
        '<% echo(s["SCRIPT_NAME"] == s["SCRIPT_FILENAME"], "|", '
        's["SCRIPT_DIRNAME"]) %>', encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    name, dirname = r.stdout.split(b'|')
    assert name == b'True'
    assert dirname.decode('utf-8') == os.path.dirname(os.path.abspath(str(script)))


def test_include_base_is_script_dir (tmp_path):
    # include 基准 = 被渲染脚本所在目录（与 cwd 无关）
    sub = tmp_path / 'sub'
    sub.mkdir()
    (sub / 'inc.mako').write_text('INC', encoding='utf-8')
    script = sub / 'main.mako'
    script.write_text('[<%include file="inc.mako"/>]', encoding='utf-8')
    other = tmp_path / 'other'
    other.mkdir()
    r = run_cli([str(script)], cwd=str(other))
    assert r.returncode == 0
    assert r.stdout == b'[INC]'


def test_non_mako_extension (tmp_path):
    # 不限 .mako 扩展名（对齐 php foo.txt 照跑）
    script = tmp_path / 'page.txt'
    script.write_text('<% echo("TXT") %>', encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.returncode == 0
    assert r.stdout == b'TXT'


def test_script_not_found (tmp_path):
    r = run_cli([str(tmp_path / 'no_such.mako')], cwd=str(tmp_path))
    assert r.returncode == 1
    assert b'no such file' in r.stderr
    assert r.stdout == b''


def test_render_exception_exit1 (tmp_path):
    # 渲染异常：exit 1，stderr 有 traceback，stdout 不输出 partial
    script = tmp_path / 't.mako'
    script.write_text('PARTIAL<% raise RuntimeError("boom") %>',
                      encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.returncode == 1
    assert r.stdout == b''
    assert b'Traceback' in r.stderr
    assert b'boom' in r.stderr


def test_session_noop_cli (tmp_path):
    # CLI 下 _SESSION 读取为空、写入无副作用（不发 cookie、不报错）
    script = tmp_path / 't.mako'
    script.write_text(
        '<% _SESSION["x"] = 1 %><% echo(_SESSION["x"]) %>',
        encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.returncode == 0
    assert r.stdout == b'1'


def test_cli_ignores_options_after_script (tmp_path):
    # -r / -p 等被脚本参数吞掉（REMAINDER 透传）
    script = tmp_path / 't.mako'
    script.write_text('<% echo(len(_SERVER["argv"])) %>', encoding='utf-8')
    r = run_cli([str(script), '-r', 'somewhere'], cwd=str(tmp_path))
    assert r.returncode == 0
    assert r.stdout == b'3'      # [script, '-r', 'somewhere']


def test_echo_none_and_bytes_cli (tmp_path):
    script = tmp_path / 't.mako'
    script.write_text('<% echo(None, b"B", "A") %>', encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.stdout == b'BA'


def test_escape_cli (tmp_path):
    # CLI 模式 escape / RESP.escape 照常可用（纯函数不受 no-op 影响）
    script = tmp_path / 't.mako'
    script.write_text('<% echo(escape("<b>"), "|", RESP.escape(42)) %>',
                      encoding='utf-8')
    r = run_cli([str(script)], cwd=str(tmp_path))
    assert r.returncode == 0
    assert r.stdout == b'&lt;b&gt;|42'


#----------------------------------------------------------------------
# stdin 渲染（script = '-'，POSIX 约定）
#----------------------------------------------------------------------

def test_stdin_render (tmp_path):
    r = run_cli(['-'], cwd=str(tmp_path), data=b'<% echo("IN", 6 * 7) %>')
    assert r.returncode == 0
    assert r.stdout == b'IN42'


def test_stdin_argv_and_script_keys (tmp_path):
    # argv[0]='-'（对齐 PHP CLI stdin），SCRIPT_NAME/FILENAME='-'，
    # SCRIPT_DIRNAME=cwd
    tpl = ('<% s = _SERVER %>'
           '<% echo(";".join(s["argv"]), "|", s["SCRIPT_NAME"], "|", '
           's["SCRIPT_FILENAME"], "|", s["SCRIPT_DIRNAME"]) %>')
    r = run_cli(['-', 'one', '--flag'], cwd=str(tmp_path),
                data=tpl.encode('utf-8'))
    assert r.returncode == 0
    argv, name, filename, dirname = r.stdout.decode('utf-8').split('|')
    assert argv == '-;one;--flag'
    assert name == '-' and filename == '-'
    assert os.path.normcase(dirname) == os.path.normcase(str(tmp_path))


def test_stdin_include_base_is_cwd (tmp_path):
    # stdin 模式 include 基准 = cwd
    (tmp_path / 'inc.mako').write_text('INC', encoding='utf-8')
    r = run_cli(['-'], cwd=str(tmp_path),
                data=b'[<%include file="inc.mako"/>]')
    assert r.returncode == 0
    assert r.stdout == b'[INC]'


def test_stdin_trailing_whitespace_stripped (tmp_path):
    # 尾部空白截断契约与文件加载一致
    r = run_cli(['-'], cwd=str(tmp_path),
                data=b'<% echo(b"\\x89PNG") %>\n\n  \n')
    assert r.returncode == 0
    assert r.stdout == b'\x89PNG'


def test_stdin_bom_tolerated (tmp_path):
    # utf-8-sig：BOM 前缀不进输出
    r = run_cli(['-'], cwd=str(tmp_path),
                data=b'\xef\xbb\xbf<% echo("BOM-OK") %>')
    assert r.returncode == 0
    assert r.stdout == b'BOM-OK'


def test_stdin_render_exception_exit1 (tmp_path):
    r = run_cli(['-'], cwd=str(tmp_path),
                data=b'PARTIAL<% raise RuntimeError("boom") %>')
    assert r.returncode == 1
    assert r.stdout == b''
    assert b'Traceback' in r.stderr and b'boom' in r.stderr
