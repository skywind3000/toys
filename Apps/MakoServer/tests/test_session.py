# -*- coding: utf-8 -*-
#======================================================================
#
# test_session.py - session：签发/校验/超时语义/容量/独占
#
#======================================================================

import time
import base64
import inspect
import pytest


def _set_cookie (cli, name, value):
    """test client 塞 cookie，兼容 Werkzeug 两代签名：
    >=2.3 为 set_cookie(key, value)，旧版为 (server_name, key, value)。"""
    params = list(inspect.signature(cli.set_cookie).parameters)
    if params and params[0] == 'server_name':
        cli.set_cookie('localhost', name, value)
    else:
        cli.set_cookie(name, value)


INI = '''[makoserver]
secret = test-secret-key
session_lifetime = 3600
session_mode = {mode}
{extra}'''


@pytest.fixture
def mkapp (site, mako_mod, tmp_path):
    """构建 app：mkapp(mode='sliding', extra='', extra_keys={}) → (app, client)"""
    def _mk (mode='sliding', extra=''):
        conf = tmp_path / 'makoserver.ini'
        conf.write_text(INI.format(mode=mode, extra=extra), encoding='utf-8')
        app = mako_mod.create_app(root=str(site), conf_file=str(conf))
        return app, app.test_client()
    return _mk


def _cookie_of (resp, name='MAKO_SESSION'):
    for item in resp.headers.get_all('Set-Cookie'):
        if item.startswith(name + '='):
            return item.split(';', 1)[0][len(name) + 1:]
    return None


def test_roundtrip (site, wf, mkapp):
    wf('w.mako', '<% _SESSION["u"] = "sky" %><% echo("W") %>')
    wf('r.mako', '<% echo(_SESSION.get("u", "-")) %>')
    app, cli = mkapp()
    r1 = cli.get('/w.mako')
    value = _cookie_of(r1)
    assert value is not None
    _set_cookie(cli, 'MAKO_SESSION', value)
    r2 = cli.get('/r.mako')
    assert r2.data == b'sky'


def test_cookie_attributes (site, wf, mkapp):
    wf('w.mako', '<% _SESSION["u"] = 1 %>')
    app, cli = mkapp()
    r = cli.get('/w.mako')
    sc = r.headers['Set-Cookie']
    assert 'Path=/' in sc
    assert 'HttpOnly' in sc
    assert 'SameSite=Lax' in sc
    # 浏览器会话 cookie：不设 Max-Age / Expires
    assert 'Max-Age' not in sc
    assert 'Expires' not in sc


def test_tamper_data_rejected (site, wf, mkapp):
    wf('w.mako', '<% _SESSION["u"] = 1 %>')
    wf('r.mako', '<% echo(_SESSION.get("u", "-")) %>')
    app, cli = mkapp()
    value = _cookie_of(cli.get('/w.mako'))
    data_b64, ts, sig = value.split('.')
    # 篡改 data（换成 {"u":2} 的 b64）
    evil = base64.urlsafe_b64encode(b'{"u":2}').rstrip(b'=').decode()
    forged = '%s.%s.%s' % (evil, ts, sig)
    _set_cookie(cli, 'MAKO_SESSION', forged)
    r = cli.get('/r.mako')
    assert r.data == b'-'


def test_tamper_ts_rejected (site, wf, mkapp):
    wf('w.mako', '<% _SESSION["u"] = 1 %>')
    wf('r.mako', '<% echo(_SESSION.get("u", "-")) %>')
    app, cli = mkapp()
    value = _cookie_of(cli.get('/w.mako'))
    data_b64, ts, sig = value.split('.')
    forged = '%s.%s.%s' % (data_b64, str(int(ts) - 99999), sig)
    _set_cookie(cli, 'MAKO_SESSION', forged)
    r = cli.get('/r.mako')
    assert r.data == b'-'


def test_tamper_sig_rejected (site, wf, mkapp):
    wf('w.mako', '<% _SESSION["u"] = 1 %>')
    wf('r.mako', '<% echo(_SESSION.get("u", "-")) %>')
    app, cli = mkapp()
    value = _cookie_of(cli.get('/w.mako'))
    data_b64, ts, sig = value.split('.')
    forged = '%s.%s.%s' % (data_b64, ts, '0' * len(sig))
    _set_cookie(cli, 'MAKO_SESSION', forged)
    r = cli.get('/r.mako')
    assert r.data == b'-'


def test_garbage_cookie_rejected (site, wf, mkapp):
    wf('r.mako', '<% echo(_SESSION.get("u", "-")) %>')
    app, cli = mkapp()
    for garbage in ('', 'abc', 'a.b', 'a.b.c.d', 'xx.yy.zz'):
        _set_cookie(cli, 'MAKO_SESSION', garbage)
        r = cli.get('/r.mako')
        assert r.data == b'-', garbage


def test_padding_restored (mako_mod):
    # base64 去 padding 后补 '=' 再解码：各种长度均往返
    codec = mako_mod.SessionCodec(b'k', 3600, 'sliding', 'X')
    for i in range(1, 20):
        data = {'k': 'v' * i}
        value = codec.encode(data, 1000000)
        assert codec.decode(value, now=1000001) == (data, 1000000)


def test_expiry_boundary (mako_mod):
    # now - ts == lifetime 即过期（等号含入）
    codec = mako_mod.SessionCodec(b'k', 100, 'sliding', 'X')
    value = codec.encode({'a': 1}, 1000)
    assert codec.decode(value, now=1099) is not None
    assert codec.decode(value, now=1100) is None


def test_absolute_expired_rejected (site, wf, mkapp):
    wf('r.mako', '<% echo(_SESSION.get("u", "-")) %>')
    app, cli = mkapp(mode='absolute')
    codec = app.mako_server.codec
    old = int(time.time()) - 7200      # 超过 lifetime=3600
    value = codec.encode({'u': 'old'}, old)
    _set_cookie(cli, 'MAKO_SESSION', value)
    r = cli.get('/r.mako')
    assert r.data == b'-'


def test_absolute_ts_inherited (site, wf, mkapp):
    # absolute：改数据重签时 ts 继承原签发时刻
    wf('w.mako', '<% _SESSION["u"] = _SESSION.get("u", 0) + 1 %>')
    app, cli = mkapp(mode='absolute')
    codec = app.mako_server.codec
    old_ts = int(time.time()) - 100
    value = codec.encode({'u': 1}, old_ts)
    _set_cookie(cli, 'MAKO_SESSION', value)
    r = cli.get('/w.mako')
    new_value = _cookie_of(r)
    assert new_value is not None
    assert new_value.split('.')[1] == str(old_ts)


def test_absolute_unchanged_no_cookie (site, wf, mkapp):
    # absolute：带有效 session 未改数据 → 不发 Set-Cookie
    wf('r.mako', '<% echo(_SESSION.get("u", "-")) %>')
    app, cli = mkapp(mode='absolute')
    codec = app.mako_server.codec
    value = codec.encode({'u': 1}, int(time.time()))
    _set_cookie(cli, 'MAKO_SESSION', value)
    r = cli.get('/r.mako')
    assert r.data == b'1'
    assert _cookie_of(r) is None


def test_sliding_resign_without_write (site, wf, mkapp):
    # sliding：无写入也重签（ts 刷新）
    wf('r.mako', '<% echo(_SESSION.get("u", "-")) %>')
    app, cli = mkapp(mode='sliding')
    codec = app.mako_server.codec
    old_ts = int(time.time()) - 500
    value = codec.encode({'u': 1}, old_ts)
    _set_cookie(cli, 'MAKO_SESSION', value)
    r = cli.get('/r.mako')
    new_value = _cookie_of(r)
    assert new_value is not None
    assert int(new_value.split('.')[1]) > old_ts


def test_no_session_empty_no_cookie (site, wf, mkapp):
    # 无 session 且 dict 为空 → 不发
    wf('t.mako', '<% echo("x") %>')
    app, cli = mkapp()
    r = cli.get('/t.mako')
    assert _cookie_of(r) is None


def test_nested_mutation_detected (site, wf, mkapp):
    # 嵌套原地修改检出：absolute 模式下 _SESSION['cart'].append 判「已写」
    wf('w.mako', '<% _SESSION["cart"].append(9) %>')
    app, cli = mkapp(mode='absolute')
    codec = app.mako_server.codec
    value = codec.encode({'cart': [1]}, int(time.time()))
    _set_cookie(cli, 'MAKO_SESSION', value)
    r = cli.get('/w.mako')
    new_value = _cookie_of(r)
    assert new_value is not None
    # 新数据包含 9
    data, ts = codec.decode(new_value)
    assert data == {'cart': [1, 9]}


def test_rebind_not_detected (site, wf, mkapp):
    # _SESSION = {...} 重绑定判「未写」：absolute 下不重签
    wf('w.mako', '<%\n_SESSION = {"x": 1}\n%>')
    app, cli = mkapp(mode='absolute')
    codec = app.mako_server.codec
    value = codec.encode({'u': 1}, int(time.time()))
    _set_cookie(cli, 'MAKO_SESSION', value)
    r = cli.get('/w.mako')
    assert _cookie_of(r) is None


def test_clear_session_resigned (site, wf, mkapp):
    # 清空 _SESSION 属「改了数据」：sliding 下重签空数据
    wf('w.mako', '<% _SESSION.clear() %>')
    app, cli = mkapp(mode='sliding')
    codec = app.mako_server.codec
    value = codec.encode({'u': 1}, int(time.time()))
    _set_cookie(cli, 'MAKO_SESSION', value)
    r = cli.get('/w.mako')
    new_value = _cookie_of(r)
    assert new_value is not None
    data, ts = codec.decode(new_value)
    assert data == {}


def test_session_too_large_500 (site, wf, mkapp):
    wf('w.mako', '<% _SESSION["k"] = "x" * 5000 %>')
    _, cli = mkapp()
    r = cli.get('/w.mako')
    assert r.status_code == 500
    assert b'cookie capacity limit' in r.data


def test_session_non_serializable_500 (site, wf, mkapp):
    wf('w.mako', '<%\nimport datetime\n_SESSION["d"] = datetime.datetime.now()\n%>')
    _, cli = mkapp()
    r = cli.get('/w.mako')
    assert r.status_code == 500
    assert b'JSON serializable' in r.data


def test_session_cookie_name_reserved (site, wf, mkapp, tmp_path):
    # 脚本 setcookie 同名 → 丢弃不下发 + error log warning
    errlog = tmp_path / 'err.log'
    app, cli = mkapp(extra='error_log = %s' % str(errlog).replace('\\', '/'))
    wf('w.mako', '<%\nRESP.setcookie("MAKO_SESSION", "evil")\n'
       '_SESSION["a"] = 1\n%>')
    r = cli.get('/w.mako')
    cookies = r.headers.get_all('Set-Cookie')
    mako_cookies = [c for c in cookies if c.startswith('MAKO_SESSION=')]
    assert len(mako_cookies) == 1
    assert 'evil' not in mako_cookies[0]
    log_text = errlog.read_text(encoding='utf-8')
    assert 'conflicts' in log_text


def test_secret_config_overrides_derive (site, mako_mod, tmp_path):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nsecret = my-own-key\n', encoding='utf-8')
    app = mako_mod.create_app(root=str(site), conf_file=str(conf))
    assert app.mako_server.codec.secret == b'my-own-key'


def test_derived_secret_cached (mako_mod, monkeypatch):
    monkeypatch.setattr(mako_mod, '_HOST_SECRET', None)
    a = mako_mod.derive_host_secret()
    b = mako_mod.derive_host_secret()
    assert a is b
    assert isinstance(a, bytes) and len(a) == 32


def test_custom_cookie_name (site, wf, mako_mod, tmp_path):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nsecret = s\nsession_cookie = MYSESS\n',
                    encoding='utf-8')
    wf('w.mako', '<% _SESSION["u"] = 1 %>')
    wf('r.mako', '<% echo(_SESSION.get("u", "-")) %>')
    app = mako_mod.create_app(root=str(site), conf_file=str(conf))
    cli = app.test_client()
    r1 = cli.get('/w.mako')
    value = _cookie_of(r1, name='MYSESS')
    assert value is not None
    _set_cookie(cli, 'MYSESS', value)
    r2 = cli.get('/r.mako')
    assert r2.data == b'1'
