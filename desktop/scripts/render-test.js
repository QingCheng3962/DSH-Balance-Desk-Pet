// Electron 渲染自检：隐藏窗口加载外壳页，检查挂件是否完成初始化。
const { app, BrowserWindow } = require('electron')
const path = require('node:path')
const { pathToFileURL } = require('node:url')

app.commandLine.appendSwitch('disable-gpu')

app.whenReady().then(async () => {
  const { startHost } = await import(pathToFileURL(path.join(__dirname, '..', 'host', 'server.mjs')).href)
  const host = await startHost({ pluginRoot: path.join(__dirname, '..', '..'), port: 0 })

  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, '..', 'electron', 'preload.js'),
      contextIsolation: true,
      backgroundThrottling: false,
    },
  })

  const logs = []
  win.webContents.on('console-message', (...args) => {
    const e = args[0]
    const msg = typeof e === 'object' && e && e.message ? e.message : args[2]
    logs.push(String(msg))
  })
  win.webContents.on('render-process-gone', (_e, d) => { logs.push('RENDER GONE ' + JSON.stringify(d)) })

  await win.loadURL(host.url + '/')
  await new Promise((r) => setTimeout(r, 5000))

  const result = await win.webContents.executeJavaScript(`(() => {
    const root = document.querySelector('.dshwv-root')
    const img = document.querySelector('.dshwv-img')
    const menuBtn = document.querySelector('.dshwv-menu-btn')
    return {
      whaleInit: !!window.__dshWhaleInit,
      whaleRoot: !!window.__dshWhaleRoot,
      rootInDoc: !!(root && document.body.contains(root)),
      imgSrc: img ? img.getAttribute('src') : null,
      menuBtn: !!menuBtn,
      bodyChildren: document.body.children.length,
      innerW: window.innerWidth,
      innerH: window.innerHeight,
      rootRect: root ? (() => { const r = root.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) } })() : null,
      probe: (() => {
        function at(x, y) {
          const el = document.elementFromPoint(x, y)
          if (!el) return 'null'
          const cs = getComputedStyle(el)
          const cls = (el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className) || ''
          return el.tagName.toLowerCase() + '.' + cls + ' pe=' + cs.pointerEvents + ' op=' + cs.opacity
        }
        const r = document.querySelector('.dshwv-root') ? document.querySelector('.dshwv-root').getBoundingClientRect() : null
        const out = { emptyTopLeft: at(10, 10), screenCenter: at(Math.round(innerWidth / 2), Math.round(innerHeight / 2)) }
        if (r) {
          out.whaleBoxCenter = at(Math.round(r.x + r.width * 0.7), Math.round(r.y + r.height * 0.7))
          out.whaleBoxTopLeft = at(Math.round(r.x + 4), Math.round(r.y + 4))
        }
        return out
      })(),
      blockers: Array.from(document.body.children).map((el) => {
        const cs = getComputedStyle(el)
        const r = el.getBoundingClientRect()
        return {
          tag: el.tagName.toLowerCase(),
          cls: (el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className) || '',
          pe: cs.pointerEvents,
          op: cs.opacity,
          disp: cs.display,
          rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
          area: Math.round(r.width) * Math.round(r.height),
        }
      }).filter((x) => x.pe !== 'none' && x.disp !== 'none' && x.op !== '0' && x.area > 0).map((x) => x.tag + '.' + x.cls + ' pe=' + x.pe + ' op=' + x.op + ' rect=' + x.rect.join(',')),
    }
  })()`)

  console.log('RENDER RESULT:', JSON.stringify(result, null, 2))
  console.log('PAGE LOGS:', JSON.stringify(logs.slice(-20), null, 2))

  await host.close()
  app.quit()
}).catch((err) => {
  console.error('render-test failed:', err)
  app.quit()
})
