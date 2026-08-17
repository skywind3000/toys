#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# makoserver.py - 基于 Mako + Flask 的类 PHP 动态页面服务
#
# Created by skywind on 2026/08/18
# Last Modified: 2026/08/18 04:00:00
#
# 运行形态：
#   1. 独立 dev server:  python makoserver.py [-r root] [-p port] [--host addr]
#   2. WSGI 入口:       import 后使用模块级 application 对象
#   3. CLI 渲染:        python makoserver.py script.mako [args...]
#
# 详见同目录 prd.md 与 spec.md
#
#======================================================================

import sys
import os
import json
import time
import html
import re
import uuid
import hmac
import base64
import socket
import hashlib
import logging
import difflib
import platform
import argparse
import posixpath
import threading
import traceback
import datetime
import configparser

import flask
from werkzeug.utils import redirect as wz_redirect
from mako.template import Template
from mako import runtime as mako_runtime
from mako import exceptions as mako_exceptions

__version__ = '1.0.0'

__all__ = ['MakoServer', 'create_app', 'application', '__version__']


#======================================================================
# 常量
#======================================================================

# 本文件所在目录（WSGI 零配置回退 root / makoserver.ini 查找锚点）
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

# 配置 schema 默认值（[makoserver] 节内扁平键）
DEFAULT_CONFIG = {
    'root': '',
    'secret': '',
    'session_lifetime': 3600,
    'session_mode': 'sliding',
    'session_cookie': 'MAKO_SESSION',
    'access_log': '',
    'error_log': '',
}

KNOWN_KEYS = list(DEFAULT_CONFIG.keys())

# 静态文件扩展名白名单（弃用 mimetypes，注册表映射不可控）
STATIC_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.htm': 'text/html; charset=utf-8',
    '.txt': 'text/plain; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.webp': 'image/webp',
    '.pdf': 'application/pdf',
    '.zip': 'application/zip',
    '.rar': 'application/vnd.rar',
    '.7z': 'application/x-7z-compressed',
    '.tar': 'application/x-tar',
    '.gz': 'application/gzip',
    '.tgz': 'application/gzip',
    '.xz': 'application/x-xz',
}

# 目录请求的 index 兜底顺序
INDEX_FILES = ('index.mako', 'index.html', 'index.htm')

# 全部放开的 HTTP 谓词
ALL_METHODS = ['GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS']

# session cookie 完整串长度上限（超过即 500）
SESSION_COOKIE_LIMIT = 3800


#======================================================================
# 异常
#======================================================================

class ConfigError (Exception):
    """配置或启动参数错误，启动阶段直接报错退出用。"""


class SessionTooLarge (Exception):
    """session 数据超过 cookie 容量上限。"""


#======================================================================
# 配置：查找与加载
#======================================================================

def find_config_file (cli_conf=None):
    """按优先级查找配置文件，命中即用，返回绝对路径或 None。

    顺序：命令行 --conf > 环境变量 MAKOSERVER_CONF >
          makoserver.py 同目录 makoserver.ini >
          ~/.config/makoserver/settings.ini
    指定的文件不存在视为未命中，继续下寻。
    """
    candidates = []
    if cli_conf:
        candidates.append(cli_conf)
    env_conf = os.environ.get('MAKOSERVER_CONF', '')
    if env_conf:
        candidates.append(env_conf)
    candidates.append(os.path.join(MODULE_DIR, 'makoserver.ini'))
    home = os.path.expanduser('~')
    candidates.append(os.path.join(home, '.config', 'makoserver', 'settings.ini'))
    for name in candidates:
        if name and os.path.isfile(name):
            return os.path.abspath(name)
    return None


def load_config (path):
    """加载 INI 配置文件，返回 dict。非法配置抛 ConfigError。"""
    cp = configparser.ConfigParser(interpolation=None)
    try:
        with open(path, 'r', encoding='utf-8-sig') as fp:
            cp.read_file(fp)
    except configparser.Error as e:
        raise ConfigError('config parse error in %s: %s' % (path, e))
    except OSError as e:
        raise ConfigError('cannot read config %s: %s' % (path, e))
    if not cp.has_section('makoserver'):
        raise ConfigError('missing [makoserver] section in %s' % path)
    conf = dict(DEFAULT_CONFIG)
    for key, value in cp.items('makoserver'):
        if key in KNOWN_KEYS:
            conf[key] = value
        else:
            # 未知键忽略；与已知键拼写相近时打 warning 防手误
            close = difflib.get_close_matches(key, KNOWN_KEYS, n=1, cutoff=0.8)
            if close:
                sys.stderr.write('makoserver: warning: unknown config key %r '
                                 '(did you mean %r?) in %s\n' % (key, close[0], path))
    # session_lifetime 显式 int 转换
    try:
        conf['session_lifetime'] = int(str(conf['session_lifetime']).strip())
    except ValueError:
        raise ConfigError('session_lifetime must be an integer in %s' % path)
    # session_mode 校验
    mode = str(conf['session_mode']).strip().lower()
    if mode not in ('sliding', 'absolute'):
        raise ConfigError('session_mode must be sliding or absolute in %s' % path)
    conf['session_mode'] = mode
    # 相对路径以配置文件所在目录为基准
    conf_dir = os.path.dirname(os.path.abspath(path))
    for key in ('root', 'access_log', 'error_log'):
        value = str(conf[key]).strip()
        if value and not os.path.isabs(value):
            value = os.path.abspath(os.path.join(conf_dir, value))
        conf[key] = value
    conf['secret'] = str(conf['secret']).strip()
    conf['session_cookie'] = str(conf['session_cookie']).strip() or 'MAKO_SESSION'
    return conf


def validate_startup (config, root, source):
    """启动校验：root 必须存在且为目录；日志路径父目录存在且可 append。

    失败抛 ConfigError（报错退出优于带病运行）。
    """
    if not os.path.isdir(root):
        raise ConfigError('root=%s (from %s) is not a directory' % (root, source))
    for key in ('error_log', 'access_log'):
        path = config.get(key) or ''
        if not path:
            continue
        parent = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(parent):
            raise ConfigError('%s directory not found: %s (from %s)' % (key, parent, source))
        try:
            fp = open(path, 'a', encoding='utf-8')
            fp.close()
        except OSError as e:
            raise ConfigError('%s cannot open for append: %s (%s)' % (key, path, e))


#======================================================================
# 日志
#======================================================================

class _AppendFileHandler (logging.Handler):
    """每次写日志即时 append 打开文件，不长期持有句柄。

    避免 Windows 下长期锁定日志文件（影响清理/滚动），
    本机场景写入量小，开销可忽略。
    """

    def __init__ (self, path):
        super(_AppendFileHandler, self).__init__()
        self.__path = path

    def emit (self, record):
        try:
            with open(self.__path, 'a', encoding='utf-8') as fp:
                fp.write(self.format(record) + '\n')
        except OSError:
            pass


def make_error_logger (path):
    """构建 error log 的 logger：配置了文件走文件，否则 stderr。

    直接实例化 logging.Logger（不走 getLogger 注册表），避免同进程
    多个 MakoServer 实例（如测试场景）互相覆盖 handler。
    """
    logger = logging.Logger('makoserver.error')
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if path:
        handler = _AppendFileHandler(path)
    else:
        handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    return logger


class PathInfoNormMiddleware:
    """WSGI 前置 middleware：PATH_INFO 归一 + 重复斜杠归并重定向。

    两件事：
    1. Werkzeug 2.2 的 matcher 对空 PATH_INFO（挂载根无斜杠请求，如
       WSGIScriptAlias /app1 下的 http://host/app1）会直接 308 重定向到
       script_root + '/' 并丢失 query，请求到不了视图。这里把空/裸
       PATH_INFO 归一成 '/'（原始值记入 MAKO_RAW_PATH_INFO），使请求
       进入视图后由视图按 3.3 规则发出 301（保留 query）；
    2. 重复斜杠归一：werkzeug 的 merge_slashes 仅在首次匹配失败时
       才触发归一 308，而本站 catch-all <path:> 路由首次即可匹配
       （//a 直接命中），归一永不触发、造成缓存键与 REQUEST_URI
       呈现不一致。故在此显式归并：//a///b → 308 到 /a/b（保留
       query），对齐 spec 3.1 声明的行为。
    """

    def __init__ (self, app):
        self.__app = app

    def __call__ (self, environ, start_response):
        path_info = environ.get('PATH_INFO', '')
        if path_info == '' or not path_info.startswith('/'):
            # 原始值记入 MAKO_RAW_PATH_INFO，视图据此判定挂载根无斜杠
            environ['MAKO_RAW_PATH_INFO'] = path_info
            path_info = '/' + path_info.lstrip('/')
            environ['PATH_INFO'] = path_info
        if '//' in path_info:
            merged = re.sub('/{2,}', '/', path_info)
            location = environ.get('SCRIPT_NAME', '') + merged
            qs = environ.get('QUERY_STRING', '')
            if qs:
                location += '?' + qs
            resp = wz_redirect(location, code=308)
            return resp(environ, start_response)
        return self.__app(environ, start_response)


class AccessLogMiddleware:
    """WSGI middleware：配置了 access_log 时记录请求日志。

    行格式：{iso_time} {remote_addr} {method} {path} {status} {bytes}
    装配于 app.wsgi_app，dev server 与 WSGI 两模式同样生效。
    """

    def __init__ (self, app, path):
        self.__app = app
        self.__path = path
        self.__lock = threading.Lock()

    def __call__ (self, environ, start_response):
        meta = {'status': '-', 'bytes': '-'}

        def capture (status, headers, exc_info=None):
            meta['status'] = str(status).split(' ', 1)[0]
            for name, value in headers:
                if str(name).lower() == 'content-length':
                    meta['bytes'] = str(value)
            return start_response(status, headers, exc_info)
        result = self.__app(environ, capture)
        try:
            uri = environ.get('REQUEST_URI') or environ.get('RAW_URI')
            if not uri:
                uri = environ.get('SCRIPT_NAME', '') + environ.get('PATH_INFO', '')
                qs = environ.get('QUERY_STRING', '')
                if qs:
                    uri += '?' + qs
            line = '%s %s %s %s %s %s\n' % (
                datetime.datetime.now().isoformat(timespec='seconds'),
                environ.get('REMOTE_ADDR', '-'),
                environ.get('REQUEST_METHOD', '-'),
                uri, meta['status'], meta['bytes'])
            with self.__lock:
                with open(self.__path, 'a', encoding='utf-8') as fp:
                    fp.write(line)
        except OSError:
            pass
        return result


#======================================================================
# 模板加载：TemplateStore
#======================================================================

class TemplateStore:
    """自定义模板集合（不用 TemplateLookup，其文件读取无 rstrip 钩子）。

    实现 Mako Collection 协议 get_template(uri) / adjust_uri(uri, relativeto)，
    带 mtime + size 缓存（请求时检查，不引入 watchdog）。
    """

    def __init__ (self, base_dir):
        self.base_dir = base_dir
        self.__cache = {}
        self.__lock = threading.Lock()

    def get_template (self, uri):
        path = os.path.join(self.base_dir, *uri.split('/'))
        with self.__lock:
            try:
                st = os.stat(path)
            except OSError:
                raise mako_exceptions.TopLevelLookupException(
                    'template not found: %s' % uri)
            entry = self.__cache.get(uri)
            if entry is not None and entry[1] == st.st_mtime_ns \
                    and entry[2] == st.st_size:
                return entry[3]
            try:
                with open(path, 'r', encoding='utf-8-sig') as fp:
                    text = fp.read()
            except OSError:
                raise mako_exceptions.TopLevelLookupException(
                    'template not found: %s' % uri)
            # 尾部空白截断：文件末尾空白永远不属于输出内容
            text = text.rstrip()
            tpl = Template(text=text, lookup=self, uri=uri,
                           input_encoding='utf-8')
            self.__cache[uri] = (path, st.st_mtime_ns, st.st_size, tpl)
            return tpl

    def adjust_uri (self, uri, relativeto):
        if uri.startswith('/'):
            return uri
        if relativeto is None:
            return uri
        return posixpath.normpath(
            posixpath.join(posixpath.dirname(relativeto), uri))


#======================================================================
# 字节缓冲：BytesBuffer
#======================================================================

class BytesBuffer:
    """实现 Mako buffer 协议（write/getvalue）的字节缓冲。

    write(str) 即时 UTF-8 编码追加；write(bytes/bytearray/memoryview) 直通。
    内部为 chunk 列表，避免 bytes 不可变的反复拷贝。
    """

    def __init__ (self):
        self.__chunks = []

    def write (self, x):
        if isinstance(x, str):
            self.__chunks.append(x.encode('utf-8'))
        elif isinstance(x, (bytes, bytearray, memoryview)):
            self.__chunks.append(bytes(x))
        else:
            raise TypeError('BytesBuffer.write expects str or bytes-like')

    def getvalue (self):
        return b''.join(self.__chunks)


def make_echo (buf):
    """构造 echo(*args)：模仿 PHP echo，None 输出空串，其它 str() 后编码。"""
    def echo (*args):
        for item in args:
            if item is None:
                continue
            if isinstance(item, str):
                buf.write(item)
            elif isinstance(item, (bytes, bytearray, memoryview)):
                buf.write(bytes(item))
            else:
                buf.write(str(item))
    return echo


#======================================================================
# Bridge：PHPDict / RespObject
#======================================================================

class PHPDict (dict):
    """仿 PHP 超全局数组：单值 = 同名参数最后一次出现，getlist 取全部。"""

    def __init__ (self, *args, **kwargs):
        super(PHPDict, self).__init__(*args, **kwargs)
        self.__lists = {}

    def setlist (self, name, values):
        self.__lists[name] = list(values)

    def getlist (self, name):
        return list(self.__lists.get(name, []))

    @staticmethod
    def from_multidict (md):
        d = PHPDict()
        for key in md.keys():
            values = md.getlist(key)
            d[key] = values[-1]
            d.setlist(key, values)
        return d


def merge_php_dict (get_d, post_d):
    """合并 _REQUEST：POST 覆盖同名 GET；getlist 返回 GET+POST 全部值。"""
    d = PHPDict()
    for key, value in get_d.items():
        d[key] = value
    for key, value in post_d.items():
        d[key] = value
    for key in get_d.keys():
        d.setlist(key, get_d.getlist(key) + post_d.getlist(key))
    for key in post_d.keys():
        if key not in get_d:
            d.setlist(key, post_d.getlist(key))
    return d


class RespObject:
    """响应控制对象（RESP）：header/status/redirect/json/setcookie/write。

    CLI 模式下除 write/json 外全部 no-op。
    """

    def __init__ (self, echo_func, cli=False):
        self.__echo = echo_func
        self.__cli = cli
        self.__headers = []     # (name, value) 列表，Set-Cookie 追加其余覆盖
        self.__status = None
        self.__cookies = {}     # name -> 完整 cookie 串，同名后设覆盖

    def write (self, *args):
        self.__echo(*args)

    def header (self, name, value):
        if self.__cli:
            return
        name = str(name)
        lower = name.lower()
        if lower == 'set-cookie':
            self.__headers.append((name, str(value)))
            return
        for i, item in enumerate(self.__headers):
            if item[0].lower() == lower:
                self.__headers[i] = (name, str(value))
                return
        self.__headers.append((name, str(value)))

    def status (self, code):
        if self.__cli:
            return
        self.__status = int(code)

    def redirect (self, url, code=302):
        self.header('Location', url)
        self.status(code)

    def json (self, data):
        text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        if not self.__cli:
            self.header('Content-Type', 'application/json')
        self.__echo(text)

    def setcookie (self, name, value='', *, max_age=None, expires=None,
                   path='/', domain=None, secure=False, httponly=False,
                   samesite=None):
        if self.__cli:
            return
        parts = ['%s=%s' % (name, value)]
        if expires is not None:
            if isinstance(expires, (int, float)):
                stamp = datetime.datetime.utcfromtimestamp(expires)
                parts.append('Expires=' + stamp.strftime('%a, %d %b %Y %H:%M:%S GMT'))
            else:
                parts.append('Expires=%s' % expires)
        if max_age is not None:
            parts.append('Max-Age=%d' % int(max_age))
        if path:
            parts.append('Path=%s' % path)
        if domain:
            parts.append('Domain=%s' % domain)
        if secure:
            parts.append('Secure')
        if httponly:
            parts.append('HttpOnly')
        if samesite:
            parts.append('SameSite=%s' % samesite)
        self.__cookies[str(name)] = '; '.join(parts)

    def collect (self):
        """组装阶段取内部状态：(status, headers, cookies)。"""
        return (self.__status, list(self.__headers), dict(self.__cookies))


#======================================================================
# Session：签名 cookie 编解码与密钥派生
#======================================================================

_HOST_SECRET = None


def derive_host_secret ():
    """由本机指纹派生 session 签名密钥（模块级缓存，进程内不重算）。

    多分量收集（hostname / 主板 UUID 或 machine-id / CPU / MAC），
    逐项容错，sha256(':'.join(components)) 直接作 HMAC-SHA256 密钥。
    """
    global _HOST_SECRET
    if _HOST_SECRET is not None:
        return _HOST_SECRET
    components = ['MAKOSERVER-HOST-KEY']
    try:
        components.append(socket.gethostname())
    except Exception:
        pass
    if os.name == 'nt':
        got = False
        try:
            import subprocess
            proc = subprocess.run(['wmic', 'csproduct', 'get', 'uuid'],
                                  capture_output=True, timeout=10)
            out = proc.stdout.decode('utf-8', 'ignore')
            for line in out.splitlines():
                line = line.strip()
                if line and not line.upper().startswith('UUID'):
                    components.append(line)
                    got = True
                    break
        except Exception:
            pass
        if not got:
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                     r'SOFTWARE\Microsoft\Cryptography')
                try:
                    value = winreg.QueryValueEx(key, 'MachineGuid')[0]
                    components.append(str(value))
                finally:
                    winreg.CloseKey(key)
            except Exception:
                pass
    else:
        for name in ('/etc/machine-id', '/var/lib/dbus/machine-id',
                     '/sys/class/dmi/id/product_uuid'):
            try:
                with open(name, 'r', encoding='ascii', errors='ignore') as fp:
                    value = fp.read().strip()
                if value:
                    components.append(value)
                    break
            except Exception:
                pass
    try:
        value = platform.processor()
        if value:
            components.append(value)
    except Exception:
        pass
    try:
        skip = False
        try:
            with open('/proc/version', 'r', encoding='ascii', errors='ignore') as fp:
                pv = fp.read().lower()
            if ('microsoft' in pv) or ('wsl' in pv):
                skip = True
        except Exception:
            pass
        if not skip:
            mac = uuid.getnode()
            # bit40 本地管理位为 1 表示随机/本地 MAC，不稳定，跳过
            if ((mac >> 40) & 0x01) == 0:
                components.append('%012x' % mac)
    except Exception:
        pass
    text = ':'.join(components)
    _HOST_SECRET = hashlib.sha256(text.encode('utf-8', 'ignore')).digest()
    return _HOST_SECRET


class SessionCodec:
    """签名 session cookie 编解码。

    格式：{data_b64}.{ts}.{sig}
    sig = hmac_sha256(secret, data_b64 + '.' + ts).hexdigest()
    """

    def __init__ (self, secret, lifetime, mode, cookie_name):
        self.secret = secret
        self.lifetime = lifetime
        self.mode = mode
        self.cookie_name = cookie_name

    def encode (self, data, ts):
        payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        data_b64 = base64.urlsafe_b64encode(payload.encode('utf-8')).rstrip(b'=')
        ts_s = str(int(ts)).encode('ascii')
        sig = hmac.new(self.secret, data_b64 + b'.' + ts_s,
                       hashlib.sha256).hexdigest()
        return (data_b64 + b'.' + ts_s + b'.' + sig.encode('ascii')).decode('ascii')

    def decode (self, value, now=None):
        """校验 cookie，成功返回 (data_dict, ts)，失败返回 None。"""
        if not value or not isinstance(value, str):
            return None
        if now is None:
            now = int(time.time())
        parts = value.split('.')
        if len(parts) != 3:
            return None
        try:
            data_b64 = parts[0].encode('ascii')
            ts_s = parts[1].encode('ascii')
            sig = parts[2]
            ts = int(parts[1])
        except (UnicodeEncodeError, ValueError):
            return None
        expect = hmac.new(self.secret, data_b64 + b'.' + ts_s,
                          hashlib.sha256).hexdigest()
        try:
            if not hmac.compare_digest(sig, expect):
                return None
        except TypeError:
            return None
        if now - ts >= self.lifetime:
            return None
        pad = data_b64 + b'=' * (-len(data_b64) % 4)
        try:
            data = json.loads(base64.urlsafe_b64decode(pad).decode('utf-8'))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        return (data, ts)


#======================================================================
# MakoServer：请求处理流水线
#======================================================================

class MakoServer:
    """核心服务对象：持有 root / 配置 / TemplateStore / 屏蔽集合等状态。"""

    def __init__ (self, root, config, conf_path=None):
        self.root = os.path.abspath(root)
        self.root_real = os.path.realpath(self.root)
        self.config = dict(config)
        self.conf_path = conf_path
        self.store = TemplateStore(self.root)
        if config.get('secret'):
            secret = config['secret'].encode('utf-8')
        else:
            secret = derive_host_secret()
        self.codec = SessionCodec(secret, config['session_lifetime'],
                                  config['session_mode'], config['session_cookie'])
        # 运行时敏感路径屏蔽集合（存 normcase(realpath)）
        self.blocked = set()
        if conf_path:
            self.blocked.add(os.path.normcase(os.path.realpath(conf_path)))
        for key in ('error_log', 'access_log'):
            if config.get(key):
                self.blocked.add(os.path.normcase(os.path.realpath(config[key])))
        self.error_logger = make_error_logger(config.get('error_log') or None)

    #----------------------------------------------------------------------
    # 小工具
    #----------------------------------------------------------------------

    def __not_found (self):
        return flask.Response('404 Not Found\n', status=404,
                              content_type='text/plain; charset=utf-8')

    def __method_not_allowed (self):
        resp = flask.Response('405 Method Not Allowed\n', status=405,
                              content_type='text/plain; charset=utf-8')
        resp.headers['Allow'] = 'GET, HEAD'
        return resp

    def __internal_error (self):
        tb = traceback.format_exc()
        try:
            path = flask.request.path
        except RuntimeError:
            path = ''
        self.error_logger.error('internal error for %s\n%s', path, tb)
        body = '<h1>500 Internal Server Error</h1>\n<p>%s</p>\n<pre>%s</pre>\n' % (
            html.escape(path), html.escape(tb))
        return flask.Response(body, status=500,
                              content_type='text/html; charset=utf-8')

    def __is_blocked (self, real):
        return os.path.normcase(real) in self.blocked

    def __within_root (self, real):
        """realpath 收口：real 必须在 root_real 之内（或即 root_real）。"""
        try:
            common = os.path.commonpath([os.path.normcase(real),
                                         os.path.normcase(self.root_real)])
        except ValueError:
            return False
        return common == os.path.normcase(self.root_real)

    #----------------------------------------------------------------------
    # 入口：分支判定
    #----------------------------------------------------------------------

    def handle (self, url_path):
        """处理一个请求，url_path 为路由剥出的 URL 尾部（已解码）。"""
        # 3.2 step 1：POSIX 规范化
        rel = posixpath.normpath('/' + url_path).lstrip('/')
        trailing = url_path.endswith('/')
        # 3.2 step 2：空字节拒绝
        if '\x00' in rel:
            return self.__not_found()
        # 3.2 step 3：NT 特判（有意跨平台分裂）
        if os.name == 'nt':
            if ':' in rel:
                return self.__not_found()
            rel = rel.rstrip(' .')
        # 3.2 step 4：拼合与真实路径收口
        if rel:
            full = os.path.join(self.root_real, rel.replace('/', os.sep))
        else:
            full = self.root_real
        try:
            real = os.path.realpath(full)
        except (OSError, ValueError):
            return self.__not_found()
        if not self.__within_root(real):
            return self.__not_found()
        # 3.2 step 5：敏感路径屏蔽（初始 real 快速路径）
        if self.__is_blocked(real):
            return self.__not_found()
        # 3.3 分支判定（basename 显式 lower 归一，全平台大小写不敏感）
        name = os.path.basename(real).lower()
        if name.endswith('.mako'):
            if os.path.isfile(real):
                # 尾斜杠本身算尾挂：/demo.mako/ → PATH_INFO='/'
                path_info = '/' if trailing else ''
                return self.__render(real, rel, '/' + rel, path_info)
            return self.__not_found()
        if os.path.isfile(real):
            if trailing:
                # 文件路径带尾斜杠 → 404（对齐 Apache）
                return self.__not_found()
            return self.__serve_static(real)
        if os.path.isdir(real):
            return self.__serve_dir(real, rel)
        return self.__walk_back(real, trailing)

    #----------------------------------------------------------------------
    # 静态分支
    #----------------------------------------------------------------------

    def __serve_static (self, real):
        base = os.path.basename(real).lower()
        ext = os.path.splitext(base)[1]
        ctype = STATIC_TYPES.get(ext)
        if ctype is None:
            # 白名单外一律 404（fail-closed，与不存在同响应）
            return self.__not_found()
        if flask.request.method not in ('GET', 'HEAD'):
            return self.__method_not_allowed()
        try:
            with open(real, 'rb') as fp:
                data = fp.read()
        except OSError:
            return self.__internal_error()
        return flask.Response(data, status=200, content_type=ctype)

    #----------------------------------------------------------------------
    # 目录分支：301 补斜杠 + index 兜底
    #----------------------------------------------------------------------

    def __serve_dir (self, real, rel):
        req = flask.request
        environ = req.environ
        # 挂载根无斜杠（原始 PATH_INFO 为空）→ 301 补斜杠
        raw_pi = environ.get('MAKO_RAW_PATH_INFO', environ.get('PATH_INFO', ''))
        if raw_pi == '' and environ.get('SCRIPT_NAME', ''):
            location = environ['SCRIPT_NAME'] + '/'
            qs = environ.get('QUERY_STRING', '')
            if qs:
                location += '?' + qs
            return wz_redirect(location, code=301)
        # 目录请求无尾斜杠 → 301（对齐 Apache DirectorySlash）
        if not req.path.endswith('/'):
            location = req.script_root + req.path + '/'
            qs = environ.get('QUERY_STRING', '')
            if qs:
                location += '?' + qs
            return wz_redirect(location, code=301)
        # index 兜底：index.mako / index.html / index.htm
        for fn in INDEX_FILES:
            cand = os.path.join(real, fn)
            cand_real = os.path.realpath(cand)
            if not os.path.isfile(cand_real):
                continue
            if not self.__within_root(cand_real):
                continue
            if self.__is_blocked(cand_real):
                return self.__not_found()
            if fn == 'index.mako':
                script_rel = (rel + '/index.mako') if rel else 'index.mako'
                suffix = ('/' + rel + '/') if rel else '/'
                return self.__render(cand_real, script_rel, suffix, '')
            # index.html / index.htm 走静态（豁免 trailing，同受谓词限制）
            return self.__serve_static(cand_real)
        return self.__not_found()

    #----------------------------------------------------------------------
    # 尾挂回溯（PATH_INFO 机制，对齐 PHP AcceptPathInfo）
    #----------------------------------------------------------------------

    def __walk_back (self, real, trailing):
        current = real
        suffix_parts = []
        root_norm = os.path.normcase(self.root_real)
        while True:
            if os.path.normcase(current) == root_norm:
                return self.__not_found()
            parent = os.path.dirname(current)
            if parent == current or not parent:
                return self.__not_found()
            suffix_parts.insert(0, os.path.basename(current))
            current = parent
            if os.path.isfile(current):
                base = os.path.basename(current).lower()
                if not base.endswith('.mako'):
                    # 静态文件不带尾挂
                    return self.__not_found()
                if self.__is_blocked(current):
                    return self.__not_found()
                path_info = '/' + '/'.join(suffix_parts)
                if trailing:
                    path_info += '/'
                rel_target = os.path.relpath(current, self.root_real)
                rel_target = rel_target.replace(os.sep, '/')
                return self.__render(current, rel_target, '/' + rel_target,
                                     path_info)
            if os.path.isdir(current):
                # 回溯碰到存在的目录 → 404（不兜底，对齐 Apache mod_dir）
                return self.__not_found()

    #----------------------------------------------------------------------
    # 模板分支：渲染 + 响应组装
    #----------------------------------------------------------------------

    def __render (self, script_path, script_rel, script_suffix, path_info):
        try:
            tpl = self.store.get_template(script_rel)
        except Exception:
            return self.__internal_error()
        buf = BytesBuffer()
        echo = make_echo(buf)
        resp = RespObject(echo)
        bridge, session_state, session_dict = self.__build_bridge(
            echo, resp, script_path, script_suffix, path_info)
        try:
            ctx = mako_runtime.Context(buf, **bridge)
            ctx._outputting_as_unicode = False
            ctx._set_with_template(tpl)
            mako_runtime._render_context(tpl, tpl.callable_, ctx)
        except Exception:
            # 丢弃 partial output，返回干净的 500
            return self.__internal_error()
        # 渲染成功：session 收口 + 响应组装
        try:
            session_cookie = self.__finalize_session(session_state, session_dict)
        except (SessionTooLarge, TypeError, ValueError):
            return self.__internal_error()
        return self.__assemble(buf, resp, session_cookie)

    def __build_bridge (self, echo, resp, script_path, script_suffix, path_info):
        """构造 bridge 注入名。_BODY 必须最先构造（get_data 先于 form）。"""
        req = flask.request
        environ = req.environ
        body = req.get_data(cache=True)
        get_d = PHPDict.from_multidict(req.args)
        post_d = PHPDict.from_multidict(req.form)
        request_d = merge_php_dict(get_d, post_d)

        server = {}
        for key in ('REQUEST_METHOD', 'QUERY_STRING', 'CONTENT_TYPE',
                    'CONTENT_LENGTH', 'REMOTE_ADDR', 'SERVER_NAME',
                    'SERVER_PORT'):
            if key in environ:
                server[key] = environ[key]
        server['REQUEST_SCHEME'] = environ.get('wsgi.url_scheme', 'http')
        for key, value in environ.items():
            if key.startswith('HTTP_') and isinstance(value, str):
                server[key] = value
        # REQUEST_URI：编码态原文，三级取值
        request_uri = environ.get('REQUEST_URI') or environ.get('RAW_URI')
        if not request_uri:
            request_uri = environ.get('SCRIPT_NAME', '') + environ.get('PATH_INFO', '')
            qs = environ.get('QUERY_STRING', '')
            if qs:
                request_uri += '?' + qs
        server['REQUEST_URI'] = request_uri
        # SCRIPT_NAME / PATH_INFO 按分支判定结果覆写构造
        prefix = environ.get('SCRIPT_NAME', '')
        server['SCRIPT_NAME'] = prefix + script_suffix
        server['PATH_INFO'] = path_info
        script_abs = os.path.abspath(script_path)
        server['SCRIPT_FILENAME'] = script_abs
        server['DOCUMENT_ROOT'] = self.root_real
        server['SCRIPT_DIRNAME'] = os.path.dirname(script_abs)

        # _JSON：Content-Type 含 json 子串才解析，失败为 None
        json_data = None
        ctype = (req.content_type or '').lower()
        if body and ('json' in ctype):
            try:
                json_data = json.loads(body.decode('utf-8'))
            except Exception:
                json_data = None

        # session 载入
        cookie_value = req.cookies.get(self.codec.cookie_name)
        session_state = {'valid': False, 'ts': 0, 'snapshot': None}
        session_dict = {}
        if cookie_value:
            decoded = self.codec.decode(cookie_value)
            if decoded is not None:
                session_dict, ts = decoded
                session_state['valid'] = True
                session_state['ts'] = ts
                session_state['snapshot'] = json.dumps(
                    session_dict, sort_keys=True, separators=(',', ':'))

        bridge = {
            'echo': echo,
            '_REQUEST': request_d,
            '_BODY': body,
            '_GET': get_d,
            '_POST': post_d,
            '_SERVER': server,
            '_JSON': json_data,
            '_COOKIE': dict(req.cookies),
            '_SESSION': session_dict,
            'RESP': resp,
        }
        return bridge, session_state, session_dict

    def __finalize_session (self, state, session_dict):
        """渲染结束后按 sliding/absolute 规则决定是否下发 Set-Cookie。

        返回完整 cookie 串或 None；可能抛 SessionTooLarge / TypeError。
        """
        # 规范化 JSON 串深比较（检出嵌套层级的原地修改）
        dump = json.dumps(session_dict, sort_keys=True, separators=(',', ':'))
        if state['valid']:
            if self.codec.mode == 'sliding':
                ts = int(time.time())
            else:
                if dump == state['snapshot']:
                    return None
                ts = state['ts']
        else:
            if not session_dict:
                return None
            ts = int(time.time())
        value = self.codec.encode(session_dict, ts)
        cookie = '%s=%s; Path=/; HttpOnly; SameSite=Lax' % (
            self.codec.cookie_name, value)
        if len(cookie.encode('utf-8')) > SESSION_COOKIE_LIMIT:
            raise SessionTooLarge(
                'session data exceeds the cookie capacity limit (about 4KB)')
        return cookie

    def __assemble (self, buf, resp, session_cookie):
        status, headers, cookies = resp.collect()
        if status is None:
            status = 200
        content_type = None
        header_list = []
        raw_setcookies = []
        for name, value in headers:
            lower = name.lower()
            if lower == 'content-type':
                content_type = value
            elif lower == 'set-cookie':
                raw_setcookies.append(value)
            else:
                header_list.append((name, value))
        if content_type is None:
            content_type = 'text/html; charset=utf-8'
        # session cookie 名独占：脚本 setcookie 同名条目丢弃不下发
        session_name = self.codec.cookie_name
        for name in cookies:
            if name == session_name:
                self.error_logger.warning(
                    'setcookie(%r) conflicts with the reserved session '
                    'cookie name, dropped', name)
                continue
            raw_setcookies.append(cookies[name])
        if session_cookie:
            raw_setcookies.append(session_cookie)
        response = flask.Response(buf.getvalue(), status=status,
                                  content_type=content_type)
        for name, value in header_list:
            response.headers[name] = value
        for value in raw_setcookies:
            response.headers.add('Set-Cookie', value)
        return response


#======================================================================
# 应用构建
#======================================================================

def create_app (root=None, conf_file=None, default_root=None,
                default_source='default'):
    """构建 Flask 应用。

    root: 命令行 -r 指定的根目录（最高优先）
    conf_file: 命令行 --conf / 查找命中的配置文件路径（None = 无配置）
    default_root: root 的最终回退（dev=cwd, WSGI=makoserver.py 所在目录）
    出错抛 ConfigError。
    """
    if conf_file:
        config = load_config(conf_file)
        conf_path = os.path.abspath(conf_file)
    else:
        config = dict(DEFAULT_CONFIG)
        conf_path = None
    if root:
        final_root = os.path.abspath(root)
        source = 'command line'
    elif config.get('root'):
        final_root = config['root']
        source = 'config'
    else:
        final_root = os.path.abspath(default_root or MODULE_DIR)
        source = default_source
    validate_startup(config, final_root, source)
    server = MakoServer(final_root, config, conf_path)

    app = flask.Flask('makoserver', static_folder=None)
    app.mako_server = server
    app.wsgi_app = PathInfoNormMiddleware(app.wsgi_app)

    def view_index ():
        return server.handle('')

    def view_path (url_path):
        return server.handle(url_path)

    app.add_url_rule('/', 'mako_index', view_index, methods=ALL_METHODS,
                     provide_automatic_options=False)
    app.add_url_rule('/<path:url_path>', 'mako_catchall', view_path,
                     methods=ALL_METHODS, provide_automatic_options=False)

    if config.get('access_log'):
        app.wsgi_app = AccessLogMiddleware(app.wsgi_app, config['access_log'])
    return app


#======================================================================
# CLI 渲染模式
#======================================================================

def render_cli (script, args):
    """像 php xxx.php 一样渲染单个脚本，结果写 stdout。失败 exit(1)。"""
    script_abs = os.path.abspath(script)
    if not os.path.isfile(script_abs):
        sys.stderr.write('makoserver: no such file: %s\n' % script)
        sys.exit(1)
    base_dir = os.path.dirname(script_abs)
    store = TemplateStore(base_dir)
    uri = os.path.basename(script_abs)
    buf = BytesBuffer()
    echo = make_echo(buf)
    resp = RespObject(echo, cli=True)
    server = {
        'REQUEST_METHOD': 'GET',
        'QUERY_STRING': '',
        'SCRIPT_NAME': script_abs,
        'SCRIPT_FILENAME': script_abs,
        'SCRIPT_DIRNAME': base_dir,
        'PATH_INFO': '',
        'REMOTE_ADDR': '',
        'SERVER_NAME': '',
        'SERVER_PORT': '',
        'CONTENT_TYPE': '',
        'CONTENT_LENGTH': '',
        'argv': [script] + list(args),
    }
    bridge = {
        'echo': echo,
        '_REQUEST': PHPDict(),
        '_BODY': b'',
        '_GET': PHPDict(),
        '_POST': PHPDict(),
        '_SERVER': server,
        '_JSON': None,
        '_COOKIE': {},
        '_SESSION': {},
        'RESP': resp,
    }
    try:
        tpl = store.get_template(uri)
        ctx = mako_runtime.Context(buf, **bridge)
        ctx._outputting_as_unicode = False
        ctx._set_with_template(tpl)
        mako_runtime._render_context(tpl, tpl.callable_, ctx)
    except SystemExit:
        raise
    except BaseException:
        # stdout 不输出 partial 内容，traceback 走 stderr
        traceback.print_exc()
        sys.exit(1)
    sys.stdout.buffer.write(buf.getvalue())
    sys.stdout.buffer.flush()


#======================================================================
# 命令行入口
#======================================================================

def main (argv=None):
    parser = argparse.ArgumentParser(
        prog='makoserver.py',
        description='Mako + Flask dynamic page server (PHP-like .mako serving)')
    parser.add_argument('-r', '--root', default=None,
                        help='document root directory')
    parser.add_argument('-p', '--port', type=int, default=5000,
                        help='port to listen on (default 5000)')
    parser.add_argument('--host', default='127.0.0.1',
                        help='address to bind (default 127.0.0.1)')
    parser.add_argument('--conf', default=None,
                        help='configuration file')
    parser.add_argument('--version', action='version',
                        version='makoserver.py ' + __version__)
    parser.add_argument('script', nargs='?', default=None,
                        help='render a single script and exit (CLI mode)')
    parser.add_argument('args', nargs=argparse.REMAINDER,
                        help='arguments passed to the script verbatim')
    opts = parser.parse_args(argv)
    if opts.script:
        render_cli(opts.script, opts.args)
        return 0
    conf_path = find_config_file(opts.conf)
    try:
        app = create_app(root=opts.root, conf_file=conf_path,
                         default_root=os.getcwd(), default_source='cwd')
    except ConfigError as e:
        sys.stderr.write('makoserver: %s\n' % e)
        return 1
    app.run(host=opts.host, port=opts.port, threaded=True)
    return 0


#======================================================================
# 模块级 WSGI 入口
#======================================================================

application = None


def _wsgi_bootstrap ():
    """WSGI 模式（被 import 时）构建 application。"""
    conf_path = find_config_file()
    try:
        return create_app(conf_file=conf_path, default_root=MODULE_DIR,
                          default_source='script dir')
    except ConfigError as e:
        sys.stderr.write('makoserver: %s\n' % e)
        sys.exit(1)


if __name__ != '__main__':
    application = _wsgi_bootstrap()
else:
    sys.exit(main())
