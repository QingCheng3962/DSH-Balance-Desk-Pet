// 为 DSH 插件宿主侧（lib/index.js）提供一个最小可用的 cordis 风格上下文桩。
// 插件的 apply(root) 只用到 root.on / root.effect / root.inject，
// 以及在 ctx 上的 webServer / credentials / on / effect / get。
import { createCredentials } from './credentials.mjs'

export function createShim() {
  const routes = []
  const tapIndexHandlers = []
  const effects = []
  const listeners = new Map()

  const addListener = (name, cb) => {
    if (!listeners.has(name)) listeners.set(name, new Set())
    listeners.get(name).add(cb)
    return () => {
      const set = listeners.get(name)
      if (set) set.delete(cb)
    }
  }

  const emit = (name, ...args) => {
    const set = listeners.get(name)
    if (!set) return
    for (const cb of Array.from(set)) {
      try { cb(...args) } catch (err) {}
    }
  }

  const webServer = {
    register(route) {
      routes.push(route)
      return () => {
        const i = routes.indexOf(route)
        if (i >= 0) routes.splice(i, 1)
      }
    },
    tapIndex(fn) {
      tapIndexHandlers.push(fn)
      return () => {
        const i = tapIndexHandlers.indexOf(fn)
        if (i >= 0) tapIndexHandlers.splice(i, 1)
      }
    },
  }

  const credentials = createCredentials()

  const ctx = {
    // DSH 可选服务：独立版一律不可用，插件内部已做判空回落
    get() { return null },
    on: addListener,
    effect(fn) { const d = fn(); effects.push(d); return d },
    webServer,
    credentials,
  }

  const root = {
    on: addListener,
    effect(fn) { const d = fn(); effects.push(d); return d },
    // 独立版没有服务注入流程：直接同步注入
    inject(_services, cb) { cb(ctx) },
  }

  const match = (pathname) => {
    for (const r of routes) {
      if (!r || !r.path) continue
      if (r.kind === 'prefix') {
        if (pathname.startsWith(r.path)) return r
      } else if (pathname === r.path) {
        return r
      }
    }
    return null
  }

  return { routes, tapIndexHandlers, effects, ctx, root, match, emit }
}
