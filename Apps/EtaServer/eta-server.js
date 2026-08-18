#! /usr/bin/env node
/* =====================================================================
 *
 * eta-server.js - PHP-style dev server for .eta templates
 *
 * File path is route: drop a .eta file in the document root and it
 * becomes a page, no server code changes needed.  Bridge API mirrors
 * PHP superglobals (_GET / _POST / _SERVER / _SESSION / ...).
 *
 * Usage:
 *   eta-server -r <root> -p <port> [-H <host>]
 *   eta-server [options] script.eta [args...]   # CLI render, result to stdout
 *   eta-server [options] - [args...]            # read the script from stdin
 *
 * Created by skywind on 2026/02/16
 * Last Modified: 2026/08/18 00:00:00
 *
 * ===================================================================== */
'use strict'

const http = require('node:http')
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const os = require('node:os')
const { createRequire } = require('node:module')
const { Eta } = require('eta')

const VERSION = '0.1.0'
const MAX_BODY = 64 * 1024 * 1024
const SESSION_COOKIE = 'etasess'
const SESSION_TTL = 30 * 60 * 1000          // sliding timeout: 30 min
// cookie capacity guard (MakoServer parity): an oversized session
// cookie is silently dropped by browsers anyway; fail loudly instead
const SESSION_COOKIE_LIMIT = 4096
const SELF_PATH = path.resolve(__filename)

// extension whitelist for static files (fail-closed outside this table)
const STATIC_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.htm': 'text/html; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.map': 'application/json',
  '.xml': 'application/xml',
  '.csv': 'text/csv; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.bmp': 'image/bmp',
  '.avif': 'image/avif',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.otf': 'font/otf',
  '.eot': 'application/vnd.ms-fontobject',
  '.mp3': 'audio/mpeg',
  '.ogg': 'audio/ogg',
  '.wav': 'audio/wav',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.wasm': 'application/wasm',
  '.pdf': 'application/pdf',
  '.zip': 'application/zip',
  '.rar': 'application/vnd.rar',
  '.7z': 'application/x-7z-compressed',
  '.tar': 'application/x-tar',
  '.gz': 'application/gzip',
  '.tgz': 'application/gzip',
  '.xz': 'application/x-xz',
}

const HTML_SPECIAL = {
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}

/* ---------------------------------------------------------------------
 * utilities
 * ------------------------------------------------------------------- */

function escapeHtml (value) {
  return String(value).replace(/[&<>"']/g, c => HTML_SPECIAL[c])
}

// utf-8-sig semantics: tolerate a leading BOM (file and stdin alike)
function stripBom (text) {
  if (text.charCodeAt(0) === 0xFEFF) return text.slice(1)
  return text
}

function errorPage (code, title, detail) {
  let body = '<!DOCTYPE html>\n<html><head><meta charset="utf-8">'
  body += '<title>' + code + ' ' + escapeHtml(title) + '</title>'
  body += '<style>body{font-family:monospace;margin:2em}'
  body += 'pre{background:#f5f5f5;padding:1em;overflow:auto}</style></head>'
  body += '<body><h1>' + code + ' ' + escapeHtml(title) + '</h1>'
  if (detail) body += '<pre>' + escapeHtml(detail) + '</pre>'
  body += '<hr><p>EtaServer ' + VERSION + '</p></body></html>\n'
  return body
}

function sendError (res, code, title, detail) {
  if (res.headersSent) {
    try { res.destroy() } catch (e) { /* ignore */ }
    return
  }
  const body = errorPage(code, title, detail)
  res.writeHead(code, {
    'Content-Type': 'text/html; charset=utf-8',
    'Content-Length': Buffer.byteLength(body)
  })
  res.end(req_HEAD(res) ? undefined : body)
}

function req_HEAD (res) {
  return res.req && res.req.method === 'HEAD'
}

// stable per-machine secret: hostname + user + home + first real MAC
// + document root (per-site key: same machine, different roots get
// different secrets, so a session cookie from site A never verifies
// on site B even when both run on this host)
function deriveSecret (rootDir) {
  let rootReal = ''
  try {
    rootReal = fs.realpathSync(rootDir)
  } catch (e) {
    rootReal = path.resolve(rootDir)
  }
  let mac = ''
  try {
    const ifs = os.networkInterfaces()
    for (const key of Object.keys(ifs)) {
      for (const item of ifs[key] || []) {
        if (item.mac && item.mac !== '00:00:00:00:00:00') {
          mac = item.mac
          break
        }
      }
      if (mac) break
    }
  } catch (e) { /* ignore */ }
  let username = ''
  let home = ''
  try {
    const info = os.userInfo()
    username = info.username || ''
    home = info.homedir || ''
  } catch (e) {
    home = os.homedir()
  }
  const seed = ['eta-server', os.hostname(), username, home, mac,
    rootReal].join('|')
  return crypto.createHash('sha256').update(seed).digest('hex')
}

function signPayload (secret, data) {
  return crypto.createHmac('sha256', secret).update(data).digest('base64url')
}

function encodeSession (data, secret) {
  const payload = JSON.stringify({ d: data, e: Date.now() + SESSION_TTL })
  const b64 = Buffer.from(payload, 'utf8').toString('base64url')
  return b64 + '.' + signPayload(secret, b64)
}

// returns the session dict, or null if missing / tampered / expired
function decodeSession (cookie, secret) {
  if (!cookie || typeof cookie !== 'string') return null
  const i = cookie.lastIndexOf('.')
  if (i <= 0) return null
  const b64 = cookie.slice(0, i)
  const sig = cookie.slice(i + 1)
  const expect = signPayload(secret, b64)
  if (sig.length !== expect.length) return null
  try {
    const a = Buffer.from(sig)
    const b = Buffer.from(expect)
    if (!crypto.timingSafeEqual(a, b)) return null
  } catch (e) {
    return null
  }
  let payload = null
  try {
    payload = JSON.parse(Buffer.from(b64, 'base64url').toString('utf8'))
  } catch (e) {
    return null
  }
  if (!payload || typeof payload.e !== 'number') return null
  if (payload.e < Date.now()) return null
  if (!payload.d || typeof payload.d !== 'object') return null
  return payload.d
}

function parseCookies (header) {
  const out = {}
  if (!header) return out
  for (const part of String(header).split(';')) {
    const i = part.indexOf('=')
    if (i < 0) continue
    const key = part.slice(0, i).trim()
    const val = part.slice(i + 1).trim()
    if (!key || (key in out)) continue
    try {
      out[key] = decodeURIComponent(val)
    } catch (e) {
      out[key] = val
    }
  }
  return out
}

function readBody (req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    let size = 0
    req.on('data', (chunk) => {
      size += chunk.length
      if (size > MAX_BODY) {
        const err = new Error('request body too large')
        err.status = 413
        reject(err)
        req.destroy()
        return
      }
      chunks.push(chunk)
    })
    req.on('end', () => resolve(Buffer.concat(chunks)))
    req.on('error', reject)
  })
}

function parseForm (buf) {
  const out = {}
  const sp = new URLSearchParams(buf.toString('utf8'))
  for (const pair of sp.entries()) {
    out[pair[0]] = pair[1]
  }
  return out
}

/* ---------------------------------------------------------------------
 * path hardening helpers
 * ------------------------------------------------------------------- */

// Windows reserved device names, with or without an extension
const DEVICE_NAME = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$/i

// a path segment that Win32 cannot open as a regular file: ADS colon
// (foo.txt::$DATA, foo:bar) or a reserved device name
function win32BadSegment (name) {
  if (name.indexOf(':') >= 0) return true
  return DEVICE_NAME.test(name)
}

// containment check: p equals root or lives strictly inside it
function containsPath (root, p) {
  if (p === root) return true
  const rel = path.relative(root, p)
  return rel !== '' && !rel.startsWith('..') && !path.isAbsolute(rel)
}

// realpath containment: resolve symlinks / junctions, reject anything
// whose real location lives outside the real document root. Returns
// the real path, or null when missing / escaping.
function realInside (rootReal, abs) {
  let real = null
  try {
    real = fs.realpathSync(abs)
  } catch (e) {
    return null
  }
  return containsPath(rootReal, real) ? real : null
}

/* ---------------------------------------------------------------------
 * response control object injected into templates as RESP
 * ------------------------------------------------------------------- */

function makeResp () {
  const resp = {
    code: 200,
    headers: [],                 // list of [name, value] pairs
    binary: null,                // writeraw buffer, null until touched
    text: null,                  // RESP.json() body, null until set
    header: function (name, value) {
      resp.headers.push([String(name), String(value)])
    },
    status: function (code) {
      resp.code = Number(code) || 200
    },
    redirect: function (url, code) {
      resp.code = code || 302
      resp.headers.push(['Location', String(url)])
    },
    setcookie: function (name, value, opts) {
      // session cookie name monopoly (MakoServer parity): a script
      // setcookie() with the session name would fight the framework
      // over the same cookie; drop the script's line and warn
      if (String(name) === SESSION_COOKIE) {
        console.error('eta-server: warning: RESP.setcookie() with the ' +
          'session cookie name "' + SESSION_COOKIE + '" is ignored')
        return
      }
      opts = opts || {}
      let s = encodeURIComponent(name) + '=' + encodeURIComponent(String(value))
      if (opts.maxage != null) s += '; Max-Age=' + Math.floor(Number(opts.maxage))
      if (opts.expires) {
        const exp = opts.expires.toUTCString
          ? opts.expires.toUTCString() : String(opts.expires)
        s += '; Expires=' + exp
      }
      s += '; Path=' + (opts.path || '/')
      if (opts.domain) s += '; Domain=' + opts.domain
      s += '; SameSite=' + (opts.samesite || 'Lax')
      if (opts.httponly !== false) s += '; HttpOnly'
      if (opts.secure) s += '; Secure'
      resp.headers.push(['Set-Cookie', s])
    },
    json: function (data) {
      resp.header('Content-Type', 'application/json; charset=utf-8')
      resp.text = JSON.stringify(data)
    },
    writeraw: function (chunk) {
      if (!Buffer.isBuffer(chunk) && !(chunk instanceof Uint8Array)) {
        throw new TypeError('RESP.writeraw() only accepts bytes')
      }
      const buf = Buffer.from(chunk)
      resp.binary = resp.binary ? Buffer.concat([resp.binary, buf]) : buf
    },
    write: function () {
      // no-op alias: in eta, output goes through template text / <%= %>
      throw new Error('use template text or <%= %> for output')
    },
    escape: escapeHtml,
  }
  return resp
}

/* ---------------------------------------------------------------------
 * template rendering pipeline
 * ------------------------------------------------------------------- */

function buildServerEnv (req, parsed, scriptAbs, scriptName, pathInfo, ctx) {
  const headers = req.headers
  const now = Date.now()
  const env = {
    REQUEST_METHOD: req.method,
    QUERY_STRING: parsed.queryString,
    REQUEST_URI: req.url,
    SCRIPT_NAME: scriptName,
    PATH_INFO: pathInfo,
    SCRIPT_FILENAME: scriptAbs,
    SCRIPT_DIRNAME: path.dirname(scriptAbs),
    DOCUMENT_ROOT: ctx.root,
    REMOTE_ADDR: req.socket.remoteAddress || '',
    CONTENT_TYPE: headers['content-type'] || '',
    CONTENT_LENGTH: headers['content-length'] || '',
    SERVER_NAME: ctx.host,
    SERVER_PORT: String(ctx.port),
    REQUEST_SCHEME: 'http',
    SERVER_PROTOCOL: 'HTTP/' + (req.httpVersion || '1.1'),
    REQUEST_TIME: Math.floor(now / 1000),
    REQUEST_TIME_FLOAT: now / 1000,
  }
  for (const key of Object.keys(headers)) {
    const name = 'HTTP_' + key.toUpperCase().replace(/-/g, '_')
    if (!(name in env)) env[name] = String(headers[key])
  }
  return env
}

async function renderTemplate (req, res, ctx, scriptAbs, scriptName, pathInfo) {
  let bodyBuf = Buffer.alloc(0)
  try {
    bodyBuf = await readBody(req)
  } catch (err) {
    if (err.status === 413) {
      return sendError(res, 413, 'Payload Too Large', err.message)
    }
    return sendError(res, 400, 'Bad Request', err.message)
  }

  const parsed = ctx.parsed
  const query = {}
  for (const pair of parsed.searchParams.entries()) {
    query[pair[0]] = pair[1]
  }

  let post = {}
  let jsonVal = null
  const ctype = String(req.headers['content-type'] || '')
  if (ctype.indexOf('application/x-www-form-urlencoded') >= 0) {
    post = parseForm(bodyBuf)
  } else if (ctype.indexOf('json') >= 0) {
    // any json-ish content type (application/json, application/*+json,
    // text/json) is parsed, same as MakoServer
    try {
      jsonVal = JSON.parse(bodyBuf.toString('utf8'))
    } catch (e) {
      jsonVal = null
    }
  }

  const cookies = parseCookies(req.headers['cookie'])
  const session = decodeSession(cookies[SESSION_COOKIE], ctx.secret) || {}
  const hadSessionCookie = (SESSION_COOKIE in cookies)

  const resp = makeResp()
  const data = {
    _GET: query,
    _POST: post,
    _REQUEST: Object.assign({}, query, post),
    _SERVER: buildServerEnv(req, parsed, scriptAbs, scriptName, pathInfo, ctx),
    _COOKIE: cookies,
    _SESSION: session,
    _BODY: bodyBuf,
    _JSON: jsonVal,
    RESP: resp,
    escape: escapeHtml,
    require: createRequire(scriptAbs),
  }

  let html = ''
  try {
    // read the file ourselves and render the string: bypasses eta's
    // file resolution quirks and gives mtime-based reload for free
    const src = stripBom(fs.readFileSync(scriptAbs, 'utf8'))
    html = await ctx.eta.renderStringAsync(src, data)
  } catch (err) {
    const detail = (err && err.stack) ? err.stack : String(err)
    return sendError(res, 500, 'Internal Server Error', detail)
  }

  // ---- assemble response headers ----
  const headers = { 'Content-Type': 'text/html; charset=utf-8' }
  const setCookies = []
  for (const pair of resp.headers) {
    const name = pair[0]
    if (name.toLowerCase() === 'set-cookie') {
      setCookies.push(pair[1])
      continue
    }
    headers[name] = pair[1]
  }

  // ---- session cookie: re-sign (sliding) when session has data ----
  if (Object.keys(session).length > 0) {
    const sessCookie = SESSION_COOKIE + '=' + encodeSession(session, ctx.secret) +
      '; Path=/; HttpOnly; SameSite=Lax'
    if (Buffer.byteLength(sessCookie, 'utf8') > SESSION_COOKIE_LIMIT) {
      // browsers silently drop oversized cookies; fail loudly instead
      // (MakoServer SessionTooLarge parity)
      return sendError(res, 500, 'Internal Server Error',
        'session data exceeds the cookie capacity limit (about 4KB)')
    }
    setCookies.push(sessCookie)
  } else if (hadSessionCookie) {
    setCookies.push(SESSION_COOKIE + '=; Path=/; HttpOnly; SameSite=Lax' +
      '; Max-Age=0')
  }
  if (setCookies.length > 0) headers['Set-Cookie'] = setCookies

  // ---- status validation (MakoServer decision #38 parity): an
  // out-of-range code must become a 500, not a broken writeHead ----
  if (!Number.isInteger(resp.code) || resp.code < 100 || resp.code > 999) {
    return sendError(res, 500, 'Internal Server Error',
      'invalid status code: ' + resp.code)
  }

  // ---- pick body: binary short-circuit > RESP.json() > rendered html ----
  let body = html
  if (resp.binary !== null) {
    body = resp.binary
  } else if (resp.text !== null) {
    body = resp.text
  }

  const buf = Buffer.isBuffer(body) ? body : Buffer.from(String(body), 'utf8')
  headers['Content-Length'] = buf.length
  res.writeHead(resp.code, headers)
  res.end(req.method === 'HEAD' ? undefined : buf)
}

/* ---------------------------------------------------------------------
 * static files
 * ------------------------------------------------------------------- */

function sendStatic (req, res, abs, type) {
  let stat = null
  try {
    stat = fs.statSync(abs)
  } catch (e) {
    return sendError(res, 404, 'Not Found')
  }
  res.writeHead(200, {
    'Content-Type': type,
    'Content-Length': stat.size
  })
  if (req.method === 'HEAD') {
    res.end()
    return
  }
  const stream = fs.createReadStream(abs)
  stream.on('error', () => {
    try { res.destroy() } catch (e) { /* ignore */ }
  })
  stream.pipe(res)
}

/* ---------------------------------------------------------------------
 * request dispatcher
 * ------------------------------------------------------------------- */

async function handleRequest (req, res, ctx) {
  // ---- slash merging: //a///b -> 308 /a/b (checked on the raw URL
  // first, because new URL() would treat a leading '//' as
  // protocol-relative and misparse the host part) ----
  const rawUrl = req.url || ''
  const rawPath = rawUrl.split(/[?#]/)[0]
  if (rawPath.indexOf('//') >= 0) {
    const loc = rawPath.replace(/\/{2,}/g, '/') +
      (rawUrl.length > rawPath.length ? rawUrl.slice(rawPath.length) : '')
    res.writeHead(308, { 'Location': loc })
    res.end()
    return
  }

  let parsed = null
  let pathname = ''
  try {
    parsed = new URL(req.url, 'http://localhost')
    pathname = decodeURIComponent(parsed.pathname)
  } catch (e) {
    return sendError(res, 404, 'Not Found')
  }
  if (pathname.indexOf('\0') >= 0) {
    return sendError(res, 404, 'Not Found')
  }
  if (pathname.indexOf('//') >= 0) {
    // %2f-encoded slashes survive the raw check above; normalize them
    // the same way once decoded
    const loc = pathname.replace(/\/{2,}/g, '/') + (parsed.search || '')
    res.writeHead(308, { 'Location': loc })
    res.end()
    return
  }
  if (process.platform === 'win32') {
    // Win32 silently drops trailing dots / spaces when opening files
    // ('demo.eta.' resolves to 'demo.eta'); strip them up front so
    // extension decisions and containment checks agree with what the
    // file system actually opens (MakoServer spec 3.2 rstrip)
    pathname = pathname.replace(/[. ]+$/, '') || '/'
    // ADS colons (foo.txt::$DATA) and reserved device names (NUL,
    // CON.txt, ...) cannot be served as regular files: fail-closed
    for (const seg of pathname.split('/')) {
      if (seg && win32BadSegment(seg)) {
        return sendError(res, 404, 'Not Found')
      }
    }
  }
  ctx.parsed = parsed
  parsed.queryString = (req.url.indexOf('?') >= 0)
    ? req.url.slice(req.url.indexOf('?') + 1) : ''

  const root = ctx.root
  let target = path.resolve(root, '.' + pathname)
  if (!containsPath(root, target)) {
    return sendError(res, 404, 'Not Found')
  }
  if (target === SELF_PATH) {
    return sendError(res, 404, 'Not Found')
  }

  // ---- template branch: xxx.eta or xxx.eta/PATH_INFO ----
  const lower = pathname.toLowerCase()
  let scriptRel = null
  let pathInfo = ''
  if (lower.endsWith('.eta')) {
    scriptRel = pathname
  } else {
    const i = lower.indexOf('.eta/')
    if (i >= 0) {
      scriptRel = pathname.slice(0, i + 4)
      pathInfo = pathname.slice(i + 4)
    }
  }
  if (scriptRel !== null) {
    const scriptAbs = path.resolve(root, '.' + scriptRel)
    if (!containsPath(root, scriptAbs)) {
      return sendError(res, 404, 'Not Found')
    }
    let stat = null
    try {
      stat = fs.statSync(scriptAbs)
    } catch (e) {
      return sendError(res, 404, 'Not Found')
    }
    if (!stat.isFile()) {
      return sendError(res, 404, 'Not Found')
    }
    // realpath containment: a symlink / junction inside root pointing
    // outside must not be rendered
    if (!realInside(ctx.rootReal, scriptAbs)) {
      return sendError(res, 404, 'Not Found')
    }
    return renderTemplate(req, res, ctx, scriptAbs, scriptRel, pathInfo)
  }

  // ---- directory branch: 301 slash, then index fallbacks ----
  let stat = null
  try {
    stat = fs.statSync(target)
  } catch (e) {
    return sendError(res, 404, 'Not Found')
  }
  // realpath containment applies to both directories and static files:
  // a symlink / junction escaping the root is a plain 404
  const real = realInside(ctx.rootReal, target)
  if (!real) {
    return sendError(res, 404, 'Not Found')
  }
  if (stat.isDirectory()) {
    if (!pathname.endsWith('/')) {
      const loc = pathname + '/' + (parsed.search || '')
      res.writeHead(301, { 'Location': loc })
      res.end()
      return
    }
    const idxEta = path.join(real, 'index.eta')
    try {
      if (fs.statSync(idxEta).isFile()) {
        const name = pathname + 'index.eta'
        return renderTemplate(req, res, ctx, idxEta, name, '')
      }
    } catch (e) { /* no index.eta */ }
    for (const name of ['index.html', 'index.htm']) {
      const f = path.join(real, name)
      try {
        if (fs.statSync(f).isFile()) {
          return sendStatic(req, res, f, STATIC_TYPES[path.extname(f)])
        }
      } catch (e) { /* keep looking */ }
    }
    return sendError(res, 404, 'Not Found')
  }

  // ---- static file branch: whitelist + method check ----
  const ext = path.extname(real).toLowerCase()
  const type = STATIC_TYPES[ext]
  if (!type) {
    return sendError(res, 404, 'Not Found')
  }
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { 'Allow': 'GET, HEAD' })
    res.end()
    return
  }
  return sendStatic(req, res, real, type)
}

/* ---------------------------------------------------------------------
 * CLI rendering mode
 * ------------------------------------------------------------------- */

async function renderCli (script, args) {
  // render a single script like "php xxx.php", writing the result to
  // stdout. A script name of '-' reads the template source from stdin
  // (POSIX convention; PHP CLI likewise uses argv[0] = '-' for stdin
  // scripts). Exits with 1 on failure (no partial content on stdout:
  // eta rendering is a pure function returning the full string).
  let src = null
  let scriptAbs = null
  let baseDir = null
  if (script === '-') {
    // stdin mode: includes resolve against cwd, the only natural
    // anchor when there is no script file
    baseDir = process.cwd()
    scriptAbs = '-'
    try {
      src = fs.readFileSync(0, 'utf8')
    } catch (err) {
      console.error('eta-server: cannot read stdin: ' + err.message)
      process.exit(1)
    }
  } else {
    scriptAbs = path.resolve(script)
    let stat = null
    try {
      stat = fs.statSync(scriptAbs)
    } catch (e) { /* fall through to the error below */ }
    if (!stat || !stat.isFile()) {
      console.error('eta-server: no such file: ' + script)
      process.exit(1)
    }
    baseDir = path.dirname(scriptAbs)
    try {
      src = fs.readFileSync(scriptAbs, 'utf8')
    } catch (err) {
      console.error('eta-server: cannot read file: ' + script)
      process.exit(1)
    }
  }
  src = stripBom(src)

  // bridge degraded to CLI values (mirrors MakoServer 6.4): no
  // request, no session, empty body; argv[0] = the script itself
  const resp = makeResp()
  const now = Date.now()
  const data = {
    _GET: {},
    _POST: {},
    _REQUEST: {},
    _SERVER: {
      REQUEST_METHOD: 'GET',
      QUERY_STRING: '',
      SCRIPT_NAME: scriptAbs,
      SCRIPT_FILENAME: scriptAbs,
      SCRIPT_DIRNAME: baseDir,
      PATH_INFO: '',
      REMOTE_ADDR: '',
      SERVER_NAME: '',
      SERVER_PORT: '',
      CONTENT_TYPE: '',
      CONTENT_LENGTH: '',
      REQUEST_TIME: Math.floor(now / 1000),
      REQUEST_TIME_FLOAT: now / 1000,
      argv: [script].concat(args),
    },
    _COOKIE: {},
    _SESSION: {},
    _BODY: Buffer.alloc(0),
    _JSON: null,
    RESP: resp,
    escape: escapeHtml,
    require: createRequire(script === '-'
      ? path.join(baseDir, 'stdin.js') : scriptAbs),
  }
  const eta = new Eta({ views: baseDir, cache: false, useWith: true, autoTrim: false })
  let html = ''
  try {
    html = await eta.renderStringAsync(src, data)
  } catch (err) {
    // traceback goes to stderr, stdout stays clean
    console.error((err && err.stack) ? err.stack : String(err))
    process.exit(1)
  }

  // body priority identical to HTTP mode (decision #6): writeraw
  // short-circuit > RESP.json() > rendered text
  let body = html
  if (resp.binary !== null) {
    body = resp.binary
  } else if (resp.text !== null) {
    body = resp.text
  }
  process.stdout.write(body)
}

/* ---------------------------------------------------------------------
 * server bootstrap
 * ------------------------------------------------------------------- */

function startServer (rootDir, port, host) {
  const root = path.resolve(rootDir)
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
    return Promise.reject(new Error('document root not found: ' + root))
  }
  port = Number(port) || 5000
  host = host || '127.0.0.1'

  const ctx = {
    root: root,
    rootReal: fs.realpathSync(root),
    host: host,
    port: port,
    secret: deriveSecret(root),
    eta: new Eta({ views: root, cache: false, useWith: true, autoTrim: false }),
    parsed: null,
  }

  const server = http.createServer((req, res) => {
    handleRequest(req, res, ctx).catch((err) => {
      sendError(res, 500, 'Internal Server Error', String(err && err.stack || err))
    })
  })

  return new Promise((resolve, reject) => {
    server.once('error', (err) => {
      if (err.code === 'EADDRINUSE') {
        reject(new Error('port ' + port + ' is already in use on ' + host))
      } else {
        reject(err)
      }
    })
    server.listen(port, host, () => {
      resolve(server)
    })
  })
}

function printBanner (root, port, host) {
  console.log('EtaServer ' + VERSION + ' (PHP-style .eta server)')
  console.log('  root : ' + root)
  console.log('  url  : http://' + (host === '0.0.0.0' ? '127.0.0.1' : host) +
    ':' + port + '/')
  console.log('  press Ctrl+C to stop')
}

function printHelp () {
  console.log('usage: eta-server [options] [script] [args...]')
  console.log('')
  console.log('with no positional argument, start the HTTP dev server;')
  console.log('with a script argument, render it once to stdout (CLI mode)')
  console.log('like "php script.php"; use "-" to read the script from stdin')
  console.log('')
  console.log('options:')
  console.log('  -r, --root <dir>    document root (default: cwd, HTTP mode only)')
  console.log('  -p, --port <port>   listen port (default: 5000, HTTP mode only)')
  console.log('  -H, --host <host>   bind address (default: 127.0.0.1, HTTP mode only)')
  console.log('  -h, --help          show this help')
  console.log('')
  console.log('CLI mode:')
  console.log('  script              script path (any extension); "-" reads stdin')
  console.log('  args...             everything after the script name is passed')
  console.log('                      through verbatim, readable via _SERVER.argv')
}

function parseArgs (argv) {
  const opts = { root: process.cwd(), port: 5000, host: '127.0.0.1',
    script: null, args: [] }
  const args = argv.slice(2)
  for (let i = 0; i < args.length; i++) {
    const a = args[i]
    if (a === '-r' || a === '--root') {
      if (i + 1 >= args.length) throw new Error('missing value for ' + a)
      opts.root = path.resolve(args[++i])
    } else if (a === '-p' || a === '--port') {
      if (i + 1 >= args.length) throw new Error('missing value for ' + a)
      opts.port = Number(args[++i])
      if (!opts.port) throw new Error('invalid port')
    } else if (a === '-H' || a === '--host') {
      if (i + 1 >= args.length) throw new Error('missing value for ' + a)
      opts.host = args[++i]
    } else if (a === '-h' || a === '--help') {
      printHelp()
      process.exit(0)
    } else {
      // first positional argument is the script: CLI render mode.
      // everything after the script name is never parsed and passed
      // through verbatim (same as argparse REMAINDER in MakoServer),
      // including arguments that look like options
      opts.script = a
      opts.args = args.slice(i + 1)
      break
    }
  }
  return opts
}

if (require.main === module) {
  let opts = null
  try {
    opts = parseArgs(process.argv)
  } catch (err) {
    console.error('eta-server: ' + err.message)
    process.exit(1)
  }
  if (opts.script) {
    renderCli(opts.script, opts.args).catch((err) => {
      console.error((err && err.stack) ? err.stack : String(err))
      process.exit(1)
    })
  } else {
    startServer(opts.root, opts.port, opts.host).then((server) => {
      printBanner(path.resolve(opts.root), opts.port, opts.host)
      process.on('SIGINT', () => {
        server.close(() => process.exit(0))
        setTimeout(() => process.exit(0), 1000).unref()
      })
    }).catch((err) => {
      console.error('eta-server: ' + err.message)
      process.exit(1)
    })
  }
}

module.exports = { startServer, renderCli, deriveSecret, VERSION }
