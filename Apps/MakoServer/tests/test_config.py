# -*- coding: utf-8 -*-
#======================================================================
#
# test_config.py - 配置查找 / 加载 / 启动校验 测试
#
#======================================================================

import os
import pytest

APPDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


#----------------------------------------------------------------------
# 配置加载（load_config）
#----------------------------------------------------------------------

def test_load_basic (tmp_path, mako_mod):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('\n'.join([
        '[makoserver]',
        '# a comment',
        '; another comment',
        'root = ./www',
        'session_lifetime = 600',
        'session_mode = absolute',
        'session_cookie = MYSESS',
    ]), encoding='utf-8')
    c = mako_mod.load_config(str(conf))
    # 相对 root 以配置文件所在目录为基准
    assert c['root'] == os.path.abspath(os.path.join(str(tmp_path), 'www'))
    assert c['session_lifetime'] == 600
    assert isinstance(c['session_lifetime'], int)
    assert c['session_mode'] == 'absolute'
    assert c['session_cookie'] == 'MYSESS'


def test_load_secret_with_percent (tmp_path, mako_mod):
    # interpolation=None 回归：含 % 的 secret 不抛 InterpolationSyntaxError
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nsecret = 100%sure%d\n', encoding='utf-8')
    c = mako_mod.load_config(str(conf))
    assert c['secret'] == '100%sure%d'


def test_load_missing_section (tmp_path, mako_mod):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[other]\nx = 1\n', encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError) as ei:
        mako_mod.load_config(str(conf))
    assert 'makoserver' in str(ei.value)


def test_load_parse_error (tmp_path, mako_mod):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('this is not ini at all\n', encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError):
        mako_mod.load_config(str(conf))


def test_load_bad_lifetime (tmp_path, mako_mod):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nsession_lifetime = abc\n', encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError):
        mako_mod.load_config(str(conf))


def test_load_lifetime_zero_rejected (tmp_path, mako_mod):
    # 0/负值 = session 恒过期、静默不可用 → 报错退出（决策 #38）
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nsession_lifetime = 0\n', encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError):
        mako_mod.load_config(str(conf))


def test_load_bad_static_types (tmp_path, mako_mod):
    # static_types 格式非法（缺 =）→ ConfigError（决策 #39）
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nstatic_types = woffX\n', encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError):
        mako_mod.load_config(str(conf))


def test_import_side_effect_free (tmp_path):
    # 决策 #37：import makoserver 零副作用（不查配置链、不派生密钥、
    # 不构造 app）；application 属性按需惰性构造
    import subprocess
    import sys as _sys
    code = (
        "import sys\n"
        "sys.path.insert(0, %r)\n"
        "import makoserver\n"
        "assert 'application' not in vars(makoserver), 'eager build!'\n"
        "app = makoserver.application\n"
        "assert app is not None\n"
        "assert 'application' in vars(makoserver)   # cached\n"
        "print('LAZY-OK')\n" % APPDIR)
    env = dict(os.environ)
    # 隔离用户级配置，防 ~/.config 泄漏影响惰性构造
    env['HOME'] = str(tmp_path)
    env['USERPROFILE'] = str(tmp_path)
    env.pop('MAKOSERVER_CONF', None)
    r = subprocess.run([_sys.executable, '-c', code],
                       capture_output=True, env=env)
    assert r.returncode == 0, r.stderr.decode('utf-8', 'ignore')
    assert b'LAZY-OK' in r.stdout


def test_load_bad_max_body (tmp_path, mako_mod):
    # max_body 非整数 → ConfigError（决策 #32）
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nmax_body = huge\n', encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError):
        mako_mod.load_config(str(conf))


def test_load_max_body_default_and_custom (tmp_path, mako_mod):
    # 缺省 64MB；显式配置读出为 int
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\n', encoding='utf-8')
    assert mako_mod.load_config(str(conf))['max_body'] == 67108864
    conf.write_text('[makoserver]\nmax_body = 1024\n', encoding='utf-8')
    c = mako_mod.load_config(str(conf))
    assert c['max_body'] == 1024
    assert isinstance(c['max_body'], int)


def test_load_bad_mode (tmp_path, mako_mod):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nsession_mode = weird\n', encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError):
        mako_mod.load_config(str(conf))


def test_unknown_key_ignored (tmp_path, mako_mod, capsys):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nport = 8080\nunknown_xyz = 1\n',
                    encoding='utf-8')
    c = mako_mod.load_config(str(conf))
    assert 'port' not in c
    assert 'unknown_xyz' not in c


def test_close_miss_key_warns (tmp_path, mako_mod, capsys):
    # session_lifetim 与 session_lifetime 相近 → stderr warning
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nsession_lifetim = 10\n', encoding='utf-8')
    mako_mod.load_config(str(conf))
    err = capsys.readouterr().err
    assert 'session_lifetim' in err


def test_relative_log_paths (tmp_path, mako_mod):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\naccess_log = logs/a.log\n'
                    'error_log = logs/e.log\n', encoding='utf-8')
    c = mako_mod.load_config(str(conf))
    assert c['access_log'] == os.path.abspath(
        os.path.join(str(tmp_path), 'logs', 'a.log'))
    assert c['error_log'] == os.path.abspath(
        os.path.join(str(tmp_path), 'logs', 'e.log'))


#----------------------------------------------------------------------
# 四级查找（find_config_file）
#----------------------------------------------------------------------

@pytest.fixture
def conf_env (tmp_path, mako_mod, monkeypatch):
    """构造四级查找的全部锚点：cli / env / 模块目录 / home。"""
    module_dir = tmp_path / 'moddir'
    module_dir.mkdir()
    home_dir = tmp_path / 'home'
    (home_dir / '.config' / 'makoserver').mkdir(parents=True)
    monkeypatch.setattr(mako_mod, 'MODULE_DIR', str(module_dir))
    monkeypatch.setattr(os.path, 'expanduser', lambda p: str(home_dir))
    monkeypatch.delenv('MAKOSERVER_CONF', raising=False)
    return {
        'cli': tmp_path / 'cli.ini',
        'env': tmp_path / 'env.ini',
        'module': module_dir / 'makoserver.ini',
        'home': home_dir / '.config' / 'makoserver' / 'settings.ini',
    }


def _touch (path):
    path.write_text('[makoserver]\n', encoding='utf-8')
    return str(path)


def test_find_order_cli_first (conf_env, mako_mod, monkeypatch):
    _touch(conf_env['cli'])
    _touch(conf_env['env'])
    _touch(conf_env['module'])
    _touch(conf_env['home'])
    monkeypatch.setenv('MAKOSERVER_CONF', str(conf_env['env']))
    assert mako_mod.find_config_file(str(conf_env['cli'])) == \
        os.path.abspath(str(conf_env['cli']))


def test_find_order_env_second (conf_env, mako_mod, monkeypatch):
    _touch(conf_env['env'])
    _touch(conf_env['module'])
    _touch(conf_env['home'])
    monkeypatch.setenv('MAKOSERVER_CONF', str(conf_env['env']))
    assert mako_mod.find_config_file() == \
        os.path.abspath(str(conf_env['env']))


def test_find_order_module_third (conf_env, mako_mod):
    _touch(conf_env['module'])
    _touch(conf_env['home'])
    assert mako_mod.find_config_file() == \
        os.path.abspath(str(conf_env['module']))


def test_find_order_home_last (conf_env, mako_mod):
    _touch(conf_env['home'])
    assert mako_mod.find_config_file() == \
        os.path.abspath(str(conf_env['home']))


def test_find_none (conf_env, mako_mod):
    assert mako_mod.find_config_file() is None


def test_find_missing_cli_conf_errors (conf_env, mako_mod, monkeypatch):
    # 显式 --conf 指向不存在的文件 → 报错（决策 #40）；
    # MAKOSERVER_CONF 不存在仍宽容继续下寻
    _touch(conf_env['home'])
    with pytest.raises(mako_mod.ConfigError):
        mako_mod.find_config_file(str(conf_env['cli']))
    monkeypatch.setenv('MAKOSERVER_CONF', str(conf_env['env']))
    assert mako_mod.find_config_file() == \
        os.path.abspath(str(conf_env['home']))


#----------------------------------------------------------------------
# root 优先级与启动校验
#----------------------------------------------------------------------

def test_cli_root_overrides_config (site, tmp_path, mako_mod):
    www = tmp_path / 'www'
    www.mkdir()
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\n' % str(www).replace('\\', '/'),
                    encoding='utf-8')
    app = mako_mod.create_app(root=str(site), conf_file=str(conf))
    assert app.mako_server.root == os.path.abspath(str(site))


def test_config_root_used (site, tmp_path, mako_mod):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\n' % str(site).replace('\\', '/'),
                    encoding='utf-8')
    app = mako_mod.create_app(conf_file=str(conf))
    assert app.mako_server.root == os.path.abspath(str(site))


def test_default_root_fallback (site, tmp_path, mako_mod):
    app = mako_mod.create_app(default_root=str(site))
    assert app.mako_server.root == os.path.abspath(str(site))


def test_root_appended_to_sys_path (site, mako_mod):
    """create_app appends root realpath to sys.path tail (decision #26)
    so <%! %> blocks can import site-local .py helpers; appending
    twice must be deduped."""
    import sys
    root_real = os.path.realpath(str(site))
    before = sys.path.count(root_real)
    mako_mod.create_app(root=str(site))
    mako_mod.create_app(root=str(site))
    assert sys.path.count(root_real) == before + 1


def test_template_imports_site_module (site, wf, client_factory):
    """A <%! %> block can import a .py helper living under root
    (py3 namespace package, no __init__.py), end to end."""
    wf('sitepkg/helper.py', 'def shout ():\n    return "HELLO-FROM-ROOT"\n')
    wf('page.mako', '<%!\nfrom sitepkg.helper import shout\n%>${shout()}')
    client = client_factory(site)
    rv = client.get('/page.mako')
    assert rv.status_code == 200
    assert rv.data == b'HELLO-FROM-ROOT'


def test_root_missing_raises (tmp_path, mako_mod):
    bad = str(tmp_path / 'nonexistent')
    with pytest.raises(mako_mod.ConfigError) as ei:
        mako_mod.create_app(root=bad)
    msg = str(ei.value)
    assert bad in msg or 'nonexistent' in msg
    assert 'command line' in msg


def test_root_not_dir_raises (tmp_path, mako_mod):
    f = tmp_path / 'afile.txt'
    f.write_text('x', encoding='utf-8')
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\n'
                    % str(f).replace('\\', '/'), encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError) as ei:
        mako_mod.create_app(conf_file=str(conf))
    assert 'config' in str(ei.value)


def test_log_parent_missing_raises (site, tmp_path, mako_mod):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\nerror_log = nodir/e.log\n'
                    % str(site).replace('\\', '/'), encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError) as ei:
        mako_mod.create_app(conf_file=str(conf))
    assert 'error_log' in str(ei.value)


def test_access_log_parent_missing_raises (site, tmp_path, mako_mod):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = %s\naccess_log = nodir/a.log\n'
                    % str(site).replace('\\', '/'), encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError) as ei:
        mako_mod.create_app(conf_file=str(conf))
    assert 'access_log' in str(ei.value)


def test_config_with_root_missing_raises (tmp_path, mako_mod):
    conf = tmp_path / 'makoserver.ini'
    conf.write_text('[makoserver]\nroot = nowhere_dir\n', encoding='utf-8')
    with pytest.raises(mako_mod.ConfigError) as ei:
        mako_mod.create_app(conf_file=str(conf))
    assert 'config' in str(ei.value)
