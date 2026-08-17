<%!
# index.mako - message list (GET pagination) + posting form
#
# Bridge features exercised:
#   _GET      - page parameter (?page=N, getlist in debug view)
#   _COOKIE   - remembered user name (set by post.mako)
#   _SESSION  - visit counter + one-shot flash messages
#   escape()  - htmlspecialchars equivalent for all user content
#   include   - header.mako / footer.mako shared layout
import os
import json

from common.siteutil import tagline as _tagline

PER_PAGE = 5


def _load_messages (path):
    """Read the message store, tolerant of missing/corrupt file."""
    if not os.path.isfile(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _kv_rows (pairs, esc):
    rows = []
    for k, v in pairs:
        rows.append('<tr><td class="k">%s</td><td class="v">%s</td></tr>'
                    % (esc(k), esc(v)))
    if not rows:
        rows.append('<tr><td class="k" colspan="2">(empty)</td></tr>')
    return '\n'.join(rows)
%>\
<%
root = _SERVER['SCRIPT_DIRNAME']
store = os.path.join(root, 'data', 'messages.json')

messages = _load_messages(store)
messages.sort(key=lambda m: m.get('ts', 0), reverse=True)

# --- GET: pagination -------------------------------------------------
try:
    page = int(_GET.get('page', '1'))
except (TypeError, ValueError):
    page = 1
total = len(messages)
pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
page = min(max(page, 1), pages)
items = messages[(page - 1) * PER_PAGE : page * PER_PAGE]

# --- session: visit counter + one-shot flash --------------------------
_SESSION['visits'] = _SESSION.get('visits', 0) + 1
flash = _SESSION.pop('flash', None)
old = _SESSION.pop('old', None) or {}

# --- cookie: remembered name (fallback for the form) ------------------
saved_name = _COOKIE.get('gb_name', '')

debug = bool(_GET.get('debug'))
%>\
<%include file="header.mako"/>
<p class="dim">${escape(_tagline())} <span class="dim">(imported from common/siteutil.py in a &lt;%! %&gt; block)</span></p>
% if flash:
<div class="flash ${escape(flash.get('type', 'info'))}">${escape(flash.get('text', ''))}</div>
% endif
<p class="stats">
${total} message(s) &middot; page ${page}/${pages}
&middot; your visit #${_SESSION['visits']} <span class="dim">(session)</span>
&middot; ${escape(saved_name) if saved_name else 'anonymous'} <span class="dim">(cookie)</span>
</p>
% for m in items:
<div class="msg">
<div class="meta"><b>${escape(m.get('name', '?'))}</b> &middot; ${escape(m.get('time', ''))} &middot; <span class="dim">${escape(m.get('ip', ''))}</span></div>
<div class="text">${escape(m.get('text', ''))}</div>
</div>
% endfor
% if total == 0:
<p class="empty">No messages yet &mdash; be the first to sign!</p>
% endif
% if pages > 1:
<div class="pager">
% for n in range(1, pages + 1):
% if n == page:
<span class="cur">${n}</span>
% else:
<a href="index.mako?page=${n}">${n}</a>
% endif
% endfor
</div>
% endif
<form method="post" action="post.mako">
<h2>Sign the guestbook</h2>
<p><input type="text" name="name" maxlength="32" placeholder="Name (remembered via cookie)" value="${escape(old.get('name', saved_name))}"></p>
<p><textarea name="message" rows="4" maxlength="500" placeholder="Say something (max 500 chars)...">${escape(old.get('message', ''))}</textarea></p>
<p><button type="submit">Post message</button></p>
</form>
% if debug:
<h2>Debug view <span class="dim">(enabled by GET parameter debug=1)</span></h2>
<table class="dump">
<tr><th colspan="2">_GET</th></tr>
${_kv_rows([(k, ', '.join(_GET.getlist(k))) for k in sorted(_GET.keys())], escape)}
<tr><th colspan="2">_REQUEST (GET + POST)</th></tr>
${_kv_rows([(k, ', '.join(_REQUEST.getlist(k))) for k in sorted(_REQUEST.keys())], escape)}
<tr><th colspan="2">_COOKIE</th></tr>
${_kv_rows(sorted(_COOKIE.items()), escape)}
<tr><th colspan="2">_SESSION</th></tr>
${_kv_rows([(k, json.dumps(v, ensure_ascii=False)) for k, v in sorted(_SESSION.items())], escape)}
<tr><th colspan="2">_SERVER (selected)</th></tr>
${_kv_rows([(k, _SERVER[k]) for k in ('REQUEST_METHOD', 'REQUEST_URI', 'SCRIPT_NAME', 'PATH_INFO', 'QUERY_STRING', 'REMOTE_ADDR') if k in _SERVER], escape)}
</table>
% endif
<%include file="footer.mako"/>
