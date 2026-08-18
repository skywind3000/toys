# -*- coding: utf-8 -*-
#======================================================================
#
# conftest.py - MakoServer 测试公共 fixture 与工具
#
# 说明：
#   makoserver 的模块级 application 为惰性构造（PEP 562 __getattr__，
#   决策 #37），import 本身零副作用；这里显式把 import 路径指向
#   Apps/MakoServer。
#
#======================================================================

import os
import sys
import shutil
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
APPDIR = os.path.dirname(HERE)
if APPDIR not in sys.path:
    sys.path.insert(0, APPDIR)

import makoserver          # noqa: E402


@pytest.fixture
def mako_mod ():
    """返回 makoserver 模块对象。"""
    return makoserver


@pytest.fixture
def site (tmp_path):
    """提供一个干净的文档根目录（作为 pathlib.Path 返回）。"""
    root = tmp_path / 'site'
    root.mkdir()
    return root


def _write (root, rel, data, binary=False):
    """在 root 下按相对路径 rel 写文件，自动建中间目录。"""
    path = os.path.join(str(root), *rel.split('/'))
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    if binary:
        with open(path, 'wb') as fp:
            fp.write(data)
    else:
        with open(path, 'w', encoding='utf-8', newline='') as fp:
            fp.write(data)
    return path


@pytest.fixture
def wf (site):
    """写文本文件到 site，返回绝对路径。用法 wf('a/b.mako', '...')"""
    def _wf (rel, data):
        return _write(site, rel, data, binary=False)
    return _wf


@pytest.fixture
def wfb (site):
    """写二进制文件到 site，返回绝对路径。"""
    def _wfb (rel, data):
        return _write(site, rel, data, binary=True)
    return _wfb


@pytest.fixture
def app_factory (mako_mod):
    """构建 Flask app。create_app(root=..., conf_file=..., default_root=...)"""
    def _factory (**kw):
        return mako_mod.create_app(**kw)
    return _factory


@pytest.fixture
def client_factory (app_factory):
    """给定 root / 配置，直接返回 test client。"""
    def _client (root, **kw):
        kw.setdefault('root', str(root))
        app = app_factory(**kw)
        return app.test_client()
    return _client


def rmtree (path):
    shutil.rmtree(str(path), ignore_errors=True)
