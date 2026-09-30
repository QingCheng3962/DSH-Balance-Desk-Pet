// 独立宿主：把 DSH 插件 lib/index.js 挂到一个本地 HTTP 服务上。
// 所有 /dsh-whale/* 接口都由插件原样提供，Electron 只负责渲染与窗口行为。
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createShim } from './shim.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const JSON_HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
}

function loadShellHtml() {
  const candidates = [
    path.join(__dirname, '..', 'shell', 'index.html'),
    process.resourcesPath ? path.join(process.resourcesPath, 'shell', 'index.html') : '',
  ].filter(Boolean)
  for (const p of candidates) {
    try { return fs.readFileSync(p, 'utf8') } catch (err) {}
  }
  return null
}

export async function startHost(opts = {}) {
  const pluginRoot = opts.pluginRoot || path.join(__dirname, '..', '..')
  const entry = path.join(pluginRoot, 'lib', 'index.js')
  if (!fs.existsSync(entry)) throw new Error('找不到插件入口: ' + entry)

  const mod = await import(pathToFileURL(entry).href)
  const plugin = mod.default
  if (!plugin || typeof plugin.apply !== 'function') throw new Error('插件入口不是合法的 DSH 插件')

  const shim = createShim()
  plugin.apply(shim.root)

  const shellHtml = loadShellHtml()

  const server = http.createServer((req, res) => {
    Promise.resolve().then(() => {
      const url = new URL(req.url || '/', 'http://127.0.0.1')
      const pathname = decodeURIComponent(url.pathname)

      if (pathname === '/' || pathname === '/index.html') {
        if (!shellHtml) throw new Error('shell/index.html 缺失')
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' })
        return res.end(shellHtml)
      }

      const route = shim.match(pathname)
      if (!route) {
        res.writeHead(404, JSON_HEADERS)
        return res.end(JSON.stringify({ ok: false, error: 'not found: ' + pathname }))
      }
      return route.handler(req, res)
    }).catch((err) => {
      try {
        res.writeHead(500, JSON_HEADERS)
        res.end(JSON.stringify({ ok: false, error: String((err && err.message) || err) }))
      } catch (e) {}
    })
  })

  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(opts.port || 0, '127.0.0.1', () => resolve())
  })

  const port = server.address().port
  return {
    port,
    url: 'http://127.0.0.1:' + port,
    emit: shim.emit,
    routes: shim.routes,
    close: () => new Promise((resolve) => server.close(() => resolve())),
  }
}
