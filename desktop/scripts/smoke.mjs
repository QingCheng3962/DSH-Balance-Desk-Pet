// 无 GUI 冒烟测试：启动独立宿主，逐个请求 /dsh-whale/* 接口，确认插件路由可用。
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { startHost } from '../host/server.mjs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const pluginRoot = path.join(__dirname, '..', '..')

const GETS = [
  '/',
  '/dsh-whale/widget.js',
  '/dsh-whale/image.png',
  '/dsh-whale/rua.gif',
  '/dsh-whale/size.json',
  '/dsh-whale/bubble.json',
  '/dsh-whale/roles.json',
  '/dsh-whale/audio.json',
  '/dsh-whale/bubble-imgs.json',
  '/dsh-whale/usage-settings.json',
  '/dsh-whale/usage-records.json',
  '/dsh-whale/api-models.json',
  '/dsh-whale/last-turn.json',
  '/dsh-whale/wait.json',
]

const host = await startHost({ pluginRoot, port: 0 })
console.log('host listening at', host.url, '路由数:', host.routes.length)

let failed = 0
for (const p of GETS) {
  try {
    const res = await fetch(host.url + p, { headers: { Accept: '*/*' } })
    const buf = Buffer.from(await res.arrayBuffer())
    const ct = res.headers.get('content-type') || ''
    const preview = ct.includes('json') ? buf.toString('utf8').slice(0, 120) : `<${buf.length} bytes>`
    console.log(String(res.status).padEnd(4), p.padEnd(34), ct.padEnd(32), preview)
    if (res.status >= 400) failed++
  } catch (err) {
    failed++
    console.log('ERR ', p, String((err && err.message) || err))
  }
}

// 余额接口单独试（需要联网/凭据，失败不算冒烟失败）
try {
  const res = await fetch(host.url + '/dsh-whale/balance.json')
  const body = await res.json()
  console.log('balance:', res.status, JSON.stringify(body).slice(0, 240))
} catch (err) {
  console.log('balance: 请求异常', String((err && err.message) || err))
}

await host.close()
console.log(failed === 0 ? '\nSMOKE OK' : `\nSMOKE FAILED (${failed})`)
process.exit(failed === 0 ? 0 : 1)
