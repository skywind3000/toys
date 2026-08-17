#! /usr/bin/env python
# -*- coding: utf-8 -*-
#======================================================================
#
# siteutil.py - site-local helper module under the document root
#
# Since MakoServer appends the document root to sys.path (spec
# decision #26), any template can import this in a module block:
#
#     <%!
#     from common.siteutil import tagline
#     %>
#
# Note: py3 namespace package, no __init__.py required. Module
# objects are cached in sys.modules - editing this file needs a
# server restart (unlike .mako templates which check mtime).
#
#======================================================================

def tagline ():
    """Return the site tagline shown in the guestbook header."""
    return 'root on sys.path works'
