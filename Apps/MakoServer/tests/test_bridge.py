# -*- coding: utf-8 -*-
#======================================================================
#
# test_bridge.py - Bridge API：请求超全局 / _SERVER / RESP / _BODY / _JSON
#
#======================================================================

import os
import json


#----------------------------------------------------------------------
# _GET / _POST / _REQUEST
#----------------------------------------------------------------------

def test_get_post_separated (site, wf, client_factory):
    wf('t.mako',
       '<% echo(_GET.get("a", "-"), "|", _POST.get("b", "-")) %>')
    cli = client_factory(site)
    r = cli.post('/t.mako?a=1', data={'b': '2'})
    assert r.data == b'1|2'


def test_request_merge_post_overrides (site, wf, client_factory):
    wf('t.mako', '<% echo(_REQUEST["x"]) %>')
    cli = client_factory(site)
    r = cli.post('/t.mako?x=get', data={'x': 'post'})
    assert r.data == b'post'


def test_request_get_only (site, wf, client_factory):
    wf('t.mako', '<% echo(_REQUEST["x"]) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako?x=g').data == b'g'


def test_getlist_all_three (site, wf, client_factory):
    wf('t.mako', '<%\n'
       'echo(",".join(_GET.getlist("t")), "|",\n'
       '     ",".join(_POST.getlist("t")), "|",\n'
       '     ",".join(_REQUEST.getlist("t")))\n'
       '%>')
    cli = client_factory(site)
    r = cli.post('/t.mako?t=a&t=b', data={'t': ['c', 'd']})
    assert r.data == b'a,b|c,d|a,b,c,d'


def test_getlist_missing_empty (site, wf, client_factory):
    wf('t.mako', '<% echo(len(_GET.getlist("nope"))) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako').data == b'0'


def test_single_value_last_occurrence (site, wf, client_factory):
    # 单值 = 同名参数最后一次出现（对齐 PHP）
    wf('t.mako', '<% echo(_GET["k"]) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako?k=1&k=2&k=3').data == b'3'


def test_form_post_body_both_present (site, wf, client_factory):
    # get_data(cache=True) 先行顺序回归：form POST 下 _POST 与 _BODY 均非空
    wf('t.mako',
       '<% echo(_POST.get("k", "-"), "|", _BODY.decode("utf-8")) %>')
    cli = client_factory(site)
    r = cli.post('/t.mako', data={'k': 'v'})
    assert r.data == b'v|k=v'


#----------------------------------------------------------------------
# _SERVER
#----------------------------------------------------------------------

def test_server_basic_keys (site, wf, client_factory):
    wf('t.mako',
       '<% echo(_SERVER["REQUEST_METHOD"], "|", _SERVER["QUERY_STRING"]) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako?q=1').data == b'GET|q=1'


def test_server_http_headers (site, wf, client_factory):
    wf('t.mako', '<% echo(_SERVER.get("HTTP_AUTHORIZATION", "-")) %>')
    cli = client_factory(site)
    r = cli.get('/t.mako', headers={'Authorization': 'Bearer TOK'})
    assert r.data == b'Bearer TOK'


def test_server_content_keys_on_post (site, wf, client_factory):
    wf('t.mako',
       '<% echo(_SERVER.get("CONTENT_TYPE", "-"), "|",'
       ' _SERVER.get("CONTENT_LENGTH", "-")) %>')
    cli = client_factory(site)
    r = cli.post('/t.mako', data='xyz', content_type='text/plain')
    ct, cl = r.data.split(b'|')
    assert b'text/plain' in ct
    assert cl == b'3'


def test_server_three_forms (site, wf, client_factory):
    # SCRIPT_NAME / PATH_INFO 三形态
    wf('i.mako',
       '<% echo(_SERVER["SCRIPT_NAME"], "|", _SERVER["PATH_INFO"]) %>')
    wf('sub/index.mako',
       '<% echo(_SERVER["SCRIPT_NAME"], "|", _SERVER["PATH_INFO"]) %>')
    cli = client_factory(site)
    assert cli.get('/i.mako').data == b'/i.mako|'
    assert cli.get('/i.mako/tail').data == b'/i.mako|/tail'
    assert cli.get('/sub/').data == b'/sub/|'


def test_server_three_forms_mounted (site, wf, client_factory):
    wf('i.mako',
       '<% echo(_SERVER["SCRIPT_NAME"], "|", _SERVER["PATH_INFO"]) %>')
    cli = client_factory(site)
    r = cli.get('/i.mako/tail', environ_overrides={'SCRIPT_NAME': '/app1'})
    assert r.data == b'/app1/i.mako|/tail'


def test_script_filename_follows_target (site, wf, client_factory):
    # SCRIPT_FILENAME 跟随实际渲染文件（尾挂 / 兜底场景）
    wf('r.mako', '<% echo(_SERVER["SCRIPT_FILENAME"]) %>')
    wf('sub/index.mako', '<% echo(_SERVER["SCRIPT_FILENAME"]) %>')
    cli = client_factory(site)
    r_real = os.path.abspath(os.path.join(str(site), 'r.mako'))
    i_real = os.path.abspath(os.path.join(str(site), 'sub', 'index.mako'))
    assert cli.get('/r.mako').data.decode('utf-8') == r_real
    assert cli.get('/r.mako/xyz').data.decode('utf-8') == r_real
    assert cli.get('/sub/').data.decode('utf-8') == i_real


def test_script_dirname_document_root (site, wf, client_factory):
    wf('sub/t.mako',
       '<% echo(_SERVER["SCRIPT_DIRNAME"], "|", _SERVER["DOCUMENT_ROOT"]) %>')
    cli = client_factory(site)
    dirname, docroot = cli.get('/sub/t.mako').data.split(b'|')
    assert dirname.decode('utf-8') == os.path.abspath(
        os.path.join(str(site), 'sub'))
    assert docroot.decode('utf-8') == os.path.realpath(str(site))


def test_request_uri_with_query (site, wf, client_factory):
    wf('t.mako', '<% echo(_SERVER["REQUEST_URI"]) %>')
    cli = client_factory(site)
    assert cli.get('/t.mako?x=1').data == b'/t.mako?x=1'
    assert cli.get('/t.mako').data == b'/t.mako'


def test_request_uri_dir_fallback (site, wf, client_factory):
    # 目录兜底场景：PATH_INFO 为空、REQUEST_URI 保留完整原始路径
    wf('sub/index.mako',
       '<% echo(_SERVER["REQUEST_URI"], "|", _SERVER["PATH_INFO"]) %>')
    cli = client_factory(site)
    assert cli.get('/sub/?z=2').data == b'/sub/?z=2|'


#----------------------------------------------------------------------
# _BODY / _JSON
#----------------------------------------------------------------------

def test_body_raw (site, wf, client_factory):
    # _BODY 是原始 bytes：二进制回显走 echoraw（echo 只接受文本）
    wf('t.mako', '<% echoraw(_BODY) %>')
    cli = client_factory(site)
    r = cli.post('/t.mako', data=b'\x00\x01RAW',
                 content_type='application/octet-stream')
    assert r.data == b'\x00\x01RAW'


def test_json_parsed (site, wf, client_factory):
    wf('t.mako', '<% echo(_JSON["a"], "|", _JSON["b"]["c"]) %>')
    cli = client_factory(site)
    r = cli.post('/t.mako', json={'a': 1, 'b': {'c': 'x'}})
    assert r.data == b'1|x'


def test_json_bad_is_none (site, wf, client_factory):
    wf('t.mako', '<% echo("NONE" if _JSON is None else "BAD") %>')
    cli = client_factory(site)
    r = cli.post('/t.mako', data='{not json',
                 content_type='application/json')
    assert r.data == b'NONE'


def test_json_non_json_content_type (site, wf, client_factory):
    wf('t.mako', '<% echo("NONE" if _JSON is None else "BAD") %>')
    cli = client_factory(site)
    r = cli.post('/t.mako', data='{"a":1}', content_type='text/plain')
    assert r.data == b'NONE'


def test_json_plus_vendor_type (site, wf, client_factory):
    # +json 子串同样触发解析
    wf('t.mako', '<% echo(_JSON["k"]) %>')
    cli = client_factory(site)
    r = cli.post('/t.mako', data='{"k":"v"}',
                 content_type='application/vnd.api+json')
    assert r.data == b'v'


def test_json_empty_body_none (site, wf, client_factory):
    wf('t.mako', '<% echo("NONE" if _JSON is None else "BAD") %>')
    cli = client_factory(site)
    r = cli.post('/t.mako', data=b'', content_type='application/json')
    assert r.data == b'NONE'


#----------------------------------------------------------------------
# _COOKIE
#----------------------------------------------------------------------

def test_cookie_dict (site, wf, client_factory):
    wf('t.mako', '<% echo(_COOKIE.get("ck", "-")) %>')
    cli = client_factory(site)
    # 兼容 Werkzeug 两代 test client set_cookie 签名
    import inspect
    params = list(inspect.signature(cli.set_cookie).parameters)
    if params and params[0] == 'server_name':
        cli.set_cookie('localhost', 'ck', 'vv')
    else:
        cli.set_cookie('ck', 'vv')
    r = cli.get('/t.mako')
    assert r.data == b'vv'


#----------------------------------------------------------------------
# RESP
#----------------------------------------------------------------------

def test_resp_header_overwrite (site, wf, client_factory):
    wf('t.mako', '<%\nRESP.header("X-One", "a")\nRESP.header("X-One", "b")\n'
       'echo("x")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.headers.get_all('X-One') == ['b']


def test_resp_header_setcookie_appends (site, wf, client_factory):
    # RESP.header('Set-Cookie') 连设两次逐条追加（原始逃生舱）
    wf('t.mako', '<%\nRESP.header("Set-Cookie", "a=1")\n'
       'RESP.header("Set-Cookie", "b=2")\necho("x")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.headers.get_all('Set-Cookie') == ['a=1', 'b=2']


def test_resp_status (site, wf, client_factory):
    wf('t.mako', '<% RESP.status(201) %><% echo("created") %>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.status_code == 201
    assert r.data == b'created'


def test_redirect_not_terminating (site, wf, client_factory):
    # redirect 不终止渲染：后续 echo 仍污染 body（对齐 PHP，行为断言）
    wf('t.mako', '<%\nRESP.redirect("/target")\necho("LEFTOVER")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.status_code == 302
    assert r.headers['Location'] == '/target'
    assert r.data == b'LEFTOVER'


def test_redirect_custom_code (site, wf, client_factory):
    wf('t.mako', '<% RESP.redirect("/t", code=301) %>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.status_code == 301
    assert r.headers['Location'] == '/t'


def test_json_not_terminating (site, wf, client_factory):
    wf('t.mako', '<%\nRESP.json({"a": 1})\necho("AFTER")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.content_type == 'application/json'
    assert r.data == b'{"a":1}AFTER'


def test_json_unicode (site, wf, client_factory):
    wf('t.mako', '<% RESP.json({"中文": "值"}) %>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    # ensure_ascii=False：原文 UTF-8 直出
    assert r.data == json.dumps({'中文': '值'}, ensure_ascii=False,
                                separators=(',', ':')).encode('utf-8')


def test_setcookie_full (site, wf, client_factory):
    wf('t.mako', '<%\nRESP.setcookie("ck", "cv", max_age=60, path="/p", '
       'httponly=True, samesite="Lax")\necho("x")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    sc = r.headers['Set-Cookie']
    assert sc.startswith('ck=cv')
    assert 'Max-Age=60' in sc
    assert 'Path=/p' in sc
    assert 'HttpOnly' in sc
    assert 'SameSite=Lax' in sc


def test_setcookie_same_name_overwrite (site, wf, client_factory):
    wf('t.mako', '<%\nRESP.setcookie("ck", "v1")\nRESP.setcookie("ck", "v2")\n'
       'echo("x")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    assert r.headers.get_all('Set-Cookie') == ['ck=v2; Path=/']


def test_setcookie_expires_timestamp (site, wf, client_factory):
    # expires 数值时间戳 → IMF-fixdate 格式（UTC）
    wf('t.mako', '<%\nRESP.setcookie("ck", "cv", expires=0)\necho("x")\n%>')
    cli = client_factory(site)
    r = cli.get('/t.mako')
    sc = r.headers['Set-Cookie']
    assert 'Expires=Thu, 01 Jan 1970 00:00:00 GMT' in sc


def test_post_root_reaches_template (site, wf, client_factory):
    # POST / 到达根路径模板，不出现 Flask 默认 405
    wf('index.mako', '<% echo("M=", _SERVER["REQUEST_METHOD"]) %>')
    cli = client_factory(site)
    r = cli.post('/')
    assert r.status_code == 200
    assert r.data == b'M=POST'
