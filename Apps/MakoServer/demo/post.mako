<%!
# post.mako - POST handler: validate, persist, cookie + flash, redirect
#
# Bridge features exercised:
#   _POST           - form fields (name / message)
#   _SERVER         - REQUEST_METHOD gate, SCRIPT_DIRNAME for storage
#   _SESSION        - flash message + preserved input on validation error
#   RESP.setcookie  - remember user name for 30 days
#   RESP.redirect   - PRG pattern (POST -> 302 -> GET), like PHP
import os
import json
import time
import datetime
%>\
<%
if _SERVER['REQUEST_METHOD'] != 'POST':
    # only reachable via crafted GET/PUT/etc - bounce back home
    RESP.redirect('index.mako')
    return

name = (_POST.get('name') or '').strip()
text = (_POST.get('message') or '').strip()
if not name:
    name = 'Anonymous'
if len(name) > 32:
    name = name[:32]

def _fail (msg):
    _SESSION['flash'] = {'type': 'err', 'text': msg}
    _SESSION['old'] = {'name': name, 'message': text}
    RESP.redirect('index.mako')
    return False

if not text:
    _fail('Message cannot be empty.')
    return

if len(text) > 500:
    _fail('Message too long (max 500 chars).')
    return

# --- persist to data/messages.json (next to this script) --------------
root = _SERVER['SCRIPT_DIRNAME']
data_dir = os.path.join(root, 'data')
store = os.path.join(data_dir, 'messages.json')

messages = []
if os.path.isfile(store):
    try:
        with open(store, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        if isinstance(loaded, list):
            messages = loaded
    except Exception:
        pass

messages.append({
    'name': name,
    'text': text,
    'ts': int(time.time()),
    'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'ip': _SERVER.get('REMOTE_ADDR', ''),
})

os.makedirs(data_dir, exist_ok=True)
tmp = store + '.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(messages, f, ensure_ascii=False, indent=1)
os.replace(tmp, store)

# --- cookie: remember the name; session: one-shot success flash -------
RESP.setcookie('gb_name', name, max_age=3600 * 24 * 30)
_SESSION['flash'] = {'type': 'ok', 'text': 'Message posted. Thanks for signing!'}
RESP.redirect('index.mako')
return
%>
