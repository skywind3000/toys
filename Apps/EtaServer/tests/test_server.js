/* =====================================================================
 *
 * test_server.js - integration tests for eta-server.js
 *
 * Spawns the server on a private port with docroot = demo/ and checks
 * routing, static whitelist, PATH_INFO, POST parsing and sessions.
 * Requires Node 18+ (global fetch).
 *
 * Created by skywind on 2026/02/16
 * Last Modified: 2026/02/16 20:30:00
 *
 * ===================================================================== */
'use strict'

const { spawn } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const assert = require('node:assert')

const PORT = 5177
const BASE = 'http://127.0.0.1:' + PORT
const ROOT = path.join(__dirname, '..', 'demo')
const SERVER = path.join(__dirname, '..', 'eta-server.js')

let passed = 0
let failed = 0
const tmpDemoFiles = []

// write a throwaway file inside the docroot, cleaned up at the end
function writeDemo (name, text) {
  const p = path.join(ROOT, name)
  fs.mkdirSync(path.dirname(p), { recursive: true })
  fs.writeFileSync(p, text)
  tmpDemoFiles.push(p)
  return p
}

async function check (name, fn) {
  try {
    await fn()
    passed++
    console.log('  PASS  ' + name)
  } catch (err) {
    failed++
    console.log('  FAIL  ' + name)
    console.log('        ' + String(err && err.message || err))
  }
}

async function waitForReady (tries) {
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(BASE + '/index.eta')
      await res.text()
      return true
    } catch (e) {
      await new Promise(r => setTimeout(r, 200))
    }
  }
  return false
}

// extract "Set-Cookie: etasess=..." value from a fetch Response
function getSessionCookie (res) {
  const all = res.headers.getSetCookie ? res.headers.getSetCookie() : []
  for (const item of all) {
    if (item.startsWith(SESSION_NAME())) return item.split(';')[0]
  }
  return null
}

function SESSION_NAME () { return 'etasess=' }

async function main () {
  const child = spawn(process.execPath,
    [SERVER, '-r', ROOT, '-p', String(PORT)],
    { stdio: ['ignore', 'pipe', 'pipe'] })
  let stderr = ''
  child.stderr.on('data', (c) => { stderr += c.toString() })

  try {
    const ready = await waitForReady(50)
    if (!ready) {
      console.error('server did not start:\n' + stderr)
      process.exit(1)
    }

    await check('GET /index.eta renders', async () => {
      const res = await fetch(BASE + '/index.eta', { redirect: 'manual' })
      assert.strictEqual(res.status, 200)
      const body = await res.text()
      assert.ok(body.indexOf('EtaServer Demo') >= 0)
      assert.ok(body.indexOf('Hello, <b>world</b>') >= 0)
    })

    await check('GET / falls back to index.eta', async () => {
      const res = await fetch(BASE + '/')
      assert.strictEqual(res.status, 200)
      const body = await res.text()
      assert.ok(body.indexOf('EtaServer Demo') >= 0)
    })

    await check('GET query param reaches _GET', async () => {
      const res = await fetch(BASE + '/index.eta?name=skywind')
      const body = await res.text()
      assert.ok(body.indexOf('Hello, <b>skywind</b>') >= 0)
    })

    await check('directory without slash gets 301', async () => {
      const res = await fetch(BASE + '/sub', { redirect: 'manual' })
      assert.strictEqual(res.status, 301)
      assert.strictEqual(res.headers.get('location'), '/sub/')
      await res.text()
    })

    await check('directory index.html fallback', async () => {
      const res = await fetch(BASE + '/sub/')
      assert.strictEqual(res.status, 200)
      const body = await res.text()
      assert.ok(body.indexOf('static index.html fallback') >= 0)
    })

    await check('static file served with Content-Type', async () => {
      const res = await fetch(BASE + '/style.css')
      assert.strictEqual(res.status, 200)
      assert.ok(String(res.headers.get('content-type')).indexOf('text/css') >= 0)
      const body = await res.text()
      assert.ok(body.indexOf('font-family') >= 0)
    })

    await check('POST static file rejected with 405', async () => {
      const res = await fetch(BASE + '/style.css', { method: 'POST' })
      assert.strictEqual(res.status, 405)
      assert.strictEqual(res.headers.get('allow'), 'GET, HEAD')
      await res.text()
    })

    await check('missing file returns 404', async () => {
      const res = await fetch(BASE + '/no-such.eta')
      assert.strictEqual(res.status, 404)
      await res.text()
    })

    await check('non-whitelist extension returns 404', async () => {
      const res = await fetch(BASE + '/../eta-server.js')
      assert.ok(res.status === 404)
      await res.text()
    })

    await check('path traversal blocked', async () => {
      const res = await fetch(BASE + '/tests/../eta-server.js',
        { redirect: 'manual' })
      assert.strictEqual(res.status, 404)
      await res.text()
    })

    await check('PATH_INFO tail is passed to script', async () => {
      const res = await fetch(BASE + '/hello.eta/linwei/42')
      assert.strictEqual(res.status, 200)
      assert.ok(String(res.headers.get('content-type')).indexOf('text/plain') >= 0)
      const body = await res.text()
      assert.ok(body.indexOf('PATH_INFO   : /linwei/42') >= 0)
      // segments line uses <%~ %> raw output, so JSON is unescaped
      assert.ok(body.indexOf('["linwei","42"]') >= 0)
    })

    await check('JSON API echoes GET', async () => {
      const res = await fetch(BASE + '/api.eta?a=1&b=two')
      assert.strictEqual(res.status, 200)
      assert.ok(String(res.headers.get('content-type')).indexOf('json') >= 0)
      const data = await res.json()
      assert.deepStrictEqual(data.query, { a: '1', b: 'two' })
    })

    await check('form POST reaches _POST', async () => {
      const res = await fetch(BASE + '/api.eta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'name=skywind&age=18',
      })
      const data = await res.json()
      assert.strictEqual(data.method, 'POST')
      assert.deepStrictEqual(data.post, { name: 'skywind', age: '18' })
    })

    await check('JSON body reaches _JSON', async () => {
      const res = await fetch(BASE + '/api.eta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hello: 'eta' }),
      })
      const data = await res.json()
      assert.deepStrictEqual(data.json, { hello: 'eta' })
    })

    await check('session cookie persists across requests', async () => {
      const r1 = await fetch(BASE + '/index.eta')
      await r1.text()
      const cookie = getSessionCookie(r1)
      assert.ok(cookie, 'first response must set etasess cookie')
      const r2 = await fetch(BASE + '/index.eta', {
        headers: { Cookie: cookie }
      })
      const body2 = await r2.text()
      assert.ok(body2.indexOf('Visits in this session: <b>2</b>') >= 0)
      // sliding session: must chain the re-signed cookie from r2
      const cookie2 = getSessionCookie(r2)
      assert.ok(cookie2, 'second response must re-sign etasess cookie')
      const r3 = await fetch(BASE + '/index.eta', {
        headers: { Cookie: cookie2 }
      })
      const body3 = await r3.text()
      assert.ok(body3.indexOf('Visits in this session: <b>3</b>') >= 0)
    })

    await check('tampered session cookie is rejected', async () => {
      const r1 = await fetch(BASE + '/index.eta')
      await r1.text()
      const cookie = getSessionCookie(r1)
      assert.ok(cookie)
      // corrupt the payload part (keep signature)
      const tampered = cookie.replace('etasess=', 'etasess=xx')
      const r2 = await fetch(BASE + '/index.eta', {
        headers: { Cookie: tampered }
      })
      const body2 = await r2.text()
      assert.ok(body2.indexOf('Visits in this session: <b>1</b>') >= 0)
    })

    await check('require() demo works (node:path)', async () => {
      const res = await fetch(BASE + '/require.eta')
      assert.strictEqual(res.status, 200)
      const body = await res.text()
      assert.ok(body.indexOf('require() demo') >= 0)
      assert.ok(body.indexOf('SCRIPT_DIRNAME') >= 0)
    })

    await check('TypeScript library loads via require(.ts)', async () => {
      const res = await fetch(BASE + '/tsdemo.eta')
      assert.strictEqual(res.status, 200)
      const body = await res.text()
      assert.ok(body.indexOf('alice (age 30)') >= 0)
      assert.ok(body.indexOf('sum([1,2,3]) = 6') >= 0)
    })

    await check('template runtime error gives 500 page', async () => {
      const res = await fetch(BASE + '/broken.eta')
      assert.strictEqual(res.status, 500)
      const body = await res.text()
      assert.ok(body.indexOf('Internal Server Error') >= 0)
    })

    await check('top-level await fetch works in template', async () => {
      const res = await fetch(BASE + '/fetchdemo.eta')
      assert.strictEqual(res.status, 200)
      const body = await res.text()
      assert.ok(body.indexOf('top-level await') >= 0)
      // self-fetch embedded hello.eta response proves event loop kept
      // serving while the template awaited
      assert.ok(body.indexOf('PATH_INFO   : /from-fetchdemo') >= 0)
    })

    await check('etainfo() page renders all sections', async () => {
      const res = await fetch(BASE + '/etainfo.eta?probe=1')
      assert.strictEqual(res.status, 200)
      const body = await res.text()
      assert.ok(body.indexOf('etainfo()') >= 0)
      assert.ok(body.indexOf('EtaServer Version') >= 0)
      assert.ok(body.indexOf('This Request (_SERVER)') >= 0)
      assert.ok(body.indexOf('Request Parameters') >= 0)
      assert.ok(body.indexOf('Environment Variables') >= 0)
      assert.ok(body.indexOf('Bridge API') >= 0)
      assert.ok(body.indexOf('probe') >= 0)        // _GET echoed in table
      assert.ok(body.indexOf('QUERY_STRING') >= 0)
    })

    // ==================== path hardening ====================

    await check('symlink/junction escaping the root gives 404', async () => {
      const outDir = fs.mkdtempSync(path.join(os.tmpdir(), 'eta-out-'))
      fs.writeFileSync(path.join(outDir, 'evil.eta'), 'EVIL')
      fs.writeFileSync(path.join(outDir, 'data.json'), '{"evil":1}')
      const junc = path.join(ROOT, '_t_junc')
      tmpDemoFiles.push(junc)
      const type = process.platform === 'win32' ? 'junction' : 'dir'
      fs.symlinkSync(outDir, junc, type)
      try {
        const r1 = await fetch(BASE + '/_t_junc/evil.eta')
        await r1.text()
        assert.strictEqual(r1.status, 404, 'escaping .eta template')
        const r2 = await fetch(BASE + '/_t_junc/data.json')
        await r2.text()
        assert.strictEqual(r2.status, 404, 'escaping static file')
      } finally {
        fs.rmSync(outDir, { recursive: true, force: true })
      }
    })

    await check('symlink staying inside the root still serves', async () => {
      const link = path.join(ROOT, '_t_in.txt')
      tmpDemoFiles.push(link)
      fs.symlinkSync(path.join(ROOT, 'style.css'), link)
      const res = await fetch(BASE + '/_t_in.txt')
      assert.strictEqual(res.status, 200)
      await res.text()
    })

    await check('DOS device names give 404', async () => {
      for (const name of ['/NUL', '/con.txt', '/COM1']) {
        const res = await fetch(BASE + name)
        await res.text()
        assert.strictEqual(res.status, 404, name)
      }
    })

    await check('NTFS ADS colon paths give 404', async () => {
      const res = await fetch(BASE + '/hello.eta%3A%3A%24DATA')
      await res.text()
      assert.strictEqual(res.status, 404)
    })

    await check('trailing dot behaves like the filesystem', async () => {
      // Win32 opens 'hello.eta.' as 'hello.eta'; POSIX has no such file
      const res = await fetch(BASE + '/hello.eta.')
      await res.text()
      const expect = process.platform === 'win32' ? 200 : 404
      assert.strictEqual(res.status, expect)
    })

    await check('duplicate slashes merge with 308', async () => {
      const r1 = await fetch(BASE + '//style.css', { redirect: 'manual' })
      assert.strictEqual(r1.status, 308)
      assert.strictEqual(r1.headers.get('location'), '/style.css')
      const r2 = await fetch(BASE + '//sub///index.html?x=1',
        { redirect: 'manual' })
      assert.strictEqual(r2.status, 308)
      assert.strictEqual(r2.headers.get('location'), '/sub/index.html?x=1')
    })

    await check('%2f-encoded duplicate slashes merge with 308', async () => {
      const res = await fetch(BASE + '/sub%2f%2findex.html',
        { redirect: 'manual' })
      assert.strictEqual(res.status, 308)
      assert.strictEqual(res.headers.get('location'), '/sub/index.html')
    })

    // ==================== bridge / _SERVER parity ====================

    await check('HTTP _SERVER has SERVER_PROTOCOL and REQUEST_TIME', async () => {
      writeDemo('_t_srvinfo.eta',
        '<%~ _SERVER.SERVER_PROTOCOL %>;<%~ _SERVER.REQUEST_TIME %>;' +
        '<%~ _SERVER.REQUEST_TIME_FLOAT %>')
      const res = await fetch(BASE + '/_t_srvinfo.eta')
      assert.strictEqual(res.status, 200)
      const parts = (await res.text()).split(';')
      assert.strictEqual(parts[0], 'HTTP/1.1')
      assert.ok(/^\d+$/.test(parts[1]))
      assert.ok(/^\d+(\.\d+)?$/.test(parts[2]))
    })

    await check('+json content types reach _JSON', async () => {
      const res = await fetch(BASE + '/api.eta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/vnd.api+json' },
        body: JSON.stringify({ marked: 'json' }),
      })
      assert.strictEqual(res.status, 200)
      const data = await res.json()
      assert.deepStrictEqual(data.json, { marked: 'json' })
    })

    // ==================== static whitelist expansion ====================

    await check('expanded static types served with right Content-Type', async () => {
      writeDemo('_t.csv', 'a,b\n1,2')
      writeDemo('_t.md', '# hello')
      writeDemo('_t.js', 'var x = 1')
      writeDemo('_t.webm', 'bytes')
      const expect = [
        ['_t.csv', 'text/csv; charset=utf-8'],
        ['_t.md', 'text/markdown; charset=utf-8'],
        ['_t.js', 'text/javascript; charset=utf-8'],
        ['_t.webm', 'video/webm'],
      ]
      for (const item of expect) {
        const res = await fetch(BASE + '/' + item[0])
        assert.strictEqual(res.status, 200, item[0])
        assert.strictEqual(res.headers.get('content-type'), item[1])
        await res.text()
      }
    })

    // ==================== session hardening ====================

    await check('session over 4KB gives 500', async () => {
      writeDemo('_t_bigsess.eta',
        '<% _SESSION.blob = "x".repeat(5000) %>ok')
      const res = await fetch(BASE + '/_t_bigsess.eta')
      assert.strictEqual(res.status, 500)
      const body = await res.text()
      assert.ok(body.indexOf('4KB') >= 0)
    })

    await check('deriveSecret mixes in the document root', async () => {
      const mod = require(SERVER)
      const a = mod.deriveSecret(ROOT)
      const b = mod.deriveSecret(path.join(ROOT, 'sub'))
      assert.strictEqual(typeof a, 'string')
      assert.strictEqual(a.length, 64)
      assert.notStrictEqual(a, b)
      assert.strictEqual(a, mod.deriveSecret(ROOT))
    })

    await check('session cookie name monopoly (setcookie dropped)', async () => {
      writeDemo('_t_sessmono.eta',
        '<% _SESSION.k = 1 %><% RESP.setcookie("etasess", "evil") %>ok')
      const res = await fetch(BASE + '/_t_sessmono.eta')
      assert.strictEqual(res.status, 200)
      await res.text()
      const all = res.headers.getSetCookie
        ? res.headers.getSetCookie() : []
      const sess = all.filter((c) => c.startsWith('etasess='))
      assert.strictEqual(sess.length, 1)
      assert.ok(sess[0].indexOf('evil') < 0)
    })

    // ==================== RESP small parity items ====================

    await check('RESP.status(9999) gives 500', async () => {
      writeDemo('_t_status.eta', '<% RESP.status(9999) %>x')
      const res = await fetch(BASE + '/_t_status.eta')
      assert.strictEqual(res.status, 500)
      const body = await res.text()
      assert.ok(body.indexOf('invalid status') >= 0)
    })

    await check('RESP.escape works like escape()', async () => {
      writeDemo('_t_respescape.eta', '<%~ RESP.escape("<a>&") %>')
      const res = await fetch(BASE + '/_t_respescape.eta')
      assert.strictEqual(res.status, 200)
      assert.strictEqual(await res.text(), '&lt;a&gt;&amp;')
    })
  } finally {
    for (const f of tmpDemoFiles) {
      try { fs.rmSync(f, { recursive: true, force: true }) } catch (e) { }
    }
    child.kill()
  }

  console.log('')
  console.log('passed: ' + passed + ', failed: ' + failed)
  process.exit(failed > 0 ? 1 : 0)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
