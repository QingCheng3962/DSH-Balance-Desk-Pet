const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, screen, shell } = require('electron')
const path = require('node:path')
const fs = require('node:fs')
const os = require('node:os')
const { pathToFileURL } = require('node:url')

const DEV = process.argv.includes('--dev')
const SELFTEST = process.env.DSHW_DESKTOP_SELFTEST === '1'
const FIXED_PORT = Number(process.env.DSHW_DESKTOP_PORT || 38733)

function bootLog(msg) {
  if (!SELFTEST) return
  try { fs.appendFileSync(path.join(os.tmpdir(), 'dshw-boot.log'), new Date().toISOString() + ' ' + msg + '\n') } catch (err) {}
}
bootLog('main loaded argv=' + JSON.stringify(process.argv))

let win = null
let tray = null
let host = null
let forceThrough = false
let alwaysOnTop = true
let hidden = false

function resolvePluginRoot() {
  const candidates = [
    path.join(__dirname, '..', '..'),
    process.resourcesPath || '',
  ].filter(Boolean)
  for (const root of candidates) {
    try {
      if (fs.existsSync(path.join(root, 'lib', 'index.js'))) return root
    } catch (err) {}
  }
  return candidates[0]
}

const PLUGIN_ROOT = resolvePluginRoot()

function trayIcon() {
  const candidates = [
    path.join(PLUGIN_ROOT, 'assets', 'DSniang1.png'),
    path.join(PLUGIN_ROOT, 'assets', 'DSH2.png'),
  ]
  for (const p of candidates) {
    try {
      const img = nativeImage.createFromPath(p)
      if (!img.isEmpty()) return img.resize({ width: 16, height: 16 })
    } catch (err) {}
  }
  return nativeImage.createEmpty()
}

function currentState() {
  return { forceThrough, alwaysOnTop, hidden }
}

function broadcastState() {
  if (win && !win.isDestroyed()) win.webContents.send('dshw:state', currentState())
  if (tray) tray.setContextMenu(buildTrayMenu())
}

function applyIgnoreMouseEvents() {
  if (!win || win.isDestroyed()) return
  if (forceThrough) {
    win.setIgnoreMouseEvents(true, { forward: true })
    return
  }
  win.setIgnoreMouseEvents(lastIgnored, { forward: true })
}

let lastIgnored = true

function createWindow(url) {
  const area = screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea
  win = new BrowserWindow({
    x: area.x,
    y: area.y,
    width: area.width,
    height: area.height,
    show: false,
    paintWhenInitiallyHidden: true,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    skipTaskbar: true,
    alwaysOnTop: alwaysOnTop,
    hasShadow: false,
    acceptFirstMouse: true,
    title: 'DSH 小鲸鱼桌面挂件',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
      spellcheck: false,
    },
  })

  win.setAlwaysOnTop(alwaysOnTop, 'floating')
  try { win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true }) } catch (err) {}
  win.setIgnoreMouseEvents(true, { forward: true })

  win.once('ready-to-show', () => {
    if (!hidden && !SELFTEST) win.showInactive()
  })

  win.webContents.on('did-finish-load', () => {
    if (DEV) win.webContents.openDevTools({ mode: 'detach' })
  })

  win.loadURL(url + '/')
  return win
}

function buildTrayMenu() {
  return Menu.buildFromTemplate([
    {
      label: hidden ? '显示挂件' : '隐藏挂件',
      click: () => {
        hidden = !hidden
        if (win && !win.isDestroyed()) {
          if (hidden) win.hide()
          else { win.showInactive(); win.setIgnoreMouseEvents(true, { forward: true }); lastIgnored = true }
        }
        broadcastState()
      },
    },
    { type: 'separator' },
    {
      label: '始终置顶',
      type: 'checkbox',
      checked: alwaysOnTop,
      click: (item) => {
        alwaysOnTop = item.checked
        if (win && !win.isDestroyed()) win.setAlwaysOnTop(alwaysOnTop, 'floating')
        broadcastState()
      },
    },
    {
      label: '全局穿透（暂停交互）',
      type: 'checkbox',
      checked: forceThrough,
      click: (item) => {
        forceThrough = item.checked
        applyIgnoreMouseEvents()
        broadcastState()
      },
    },
    { type: 'separator' },
    {
      label: '重新加载挂件',
      click: () => { if (win && !win.isDestroyed()) win.webContents.reloadIgnoringCache() },
    },
    {
      label: '打开数据目录',
      click: () => {
        const dir = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
        try { shell.openPath(dir) } catch (err) {}
      },
    },
    { type: 'separator' },
    { label: '退出', click: () => { app.quit() } },
  ])
}

function setupIpc() {
  ipcMain.on('dshw:set-click-through', (_e, through) => {
    lastIgnored = !!through
    if (!forceThrough && win && !win.isDestroyed()) {
      win.setIgnoreMouseEvents(lastIgnored, { forward: true })
      // 离开挂件交互区后把焦点还给下面的窗口
      if (lastIgnored && win.isFocused()) { try { win.blur() } catch (err) {} }
    }
  })
  ipcMain.on('dshw:quit', () => app.quit())
  ipcMain.on('dshw:reload', () => { if (win && !win.isDestroyed()) win.webContents.reloadIgnoringCache() })
  ipcMain.on('dshw:toggle-top', () => {
    alwaysOnTop = !alwaysOnTop
    if (win && !win.isDestroyed()) win.setAlwaysOnTop(alwaysOnTop, 'floating')
    broadcastState()
  })
  ipcMain.handle('dshw:get-state', () => currentState())
}

async function createTray() {
  tray = new Tray(trayIcon())
  tray.setToolTip('DSH 小鲸鱼桌面挂件')
  tray.setContextMenu(buildTrayMenu())
  tray.on('click', () => {
    if (!win || win.isDestroyed()) return
    hidden = false
    win.showInactive()
    win.setIgnoreMouseEvents(true, { forward: true })
    lastIgnored = true
    broadcastState()
  })
}

async function bootstrap() {
  bootLog('bootstrap start pluginRoot=' + PLUGIN_ROOT)
  const hostEntry = path.join(__dirname, '..', 'host', 'server.mjs')
  bootLog('host entry=' + hostEntry + ' exists=' + fs.existsSync(hostEntry))
  let startHost
  try {
    ({ startHost } = await import(pathToFileURL(hostEntry).href))
  } catch (err) {
    bootLog('import host failed: ' + String((err && err.stack) || err))
    throw err
  }
  bootLog('host module imported')

  let port = FIXED_PORT
  try {
    host = await startHost({ pluginRoot: PLUGIN_ROOT, port })
  } catch (err) {
    console.warn('[dsh-whale-desktop] 固定端口启动失败，改用随机端口：' + (err && err.message))
    host = await startHost({ pluginRoot: PLUGIN_ROOT, port: 0 })
    port = host.port
  }
  console.log('[dsh-whale-desktop] host:', host.url, 'routes:', host.routes.length)
  bootLog('host started ' + host.url + ' routes=' + host.routes.length)

  createWindow(host.url)
  setupIpc()
  if (!SELFTEST) await createTray()
  bootLog('window created')

  screen.on('display-metrics-changed', reposition)
  screen.on('display-added', reposition)
  screen.on('display-removed', reposition)

  if (SELFTEST) {
    await new Promise((r) => setTimeout(r, 6000))
    try {
      const info = await win.webContents.executeJavaScript(
        '({ init: !!window.__dshWhaleInit, root: !!window.__dshWhaleRoot, bridge: !!window.dshwDesktop, top: ' + alwaysOnTop + ' })'
      )
      info.pluginRoot = PLUGIN_ROOT
      info.hostUrl = host.url
      console.log('SELFTEST:', JSON.stringify(info))
      try { fs.writeFileSync(path.join(os.tmpdir(), 'dshw-selftest.json'), JSON.stringify(info, null, 2), 'utf8') } catch (err) {}
    } catch (err) {
      console.log('SELFTEST ERROR:', String((err && err.message) || err))
      try { fs.writeFileSync(path.join(os.tmpdir(), 'dshw-selftest.json'), JSON.stringify({ error: String((err && err.message) || err) }, null, 2), 'utf8') } catch (e) {}
    }
    app.quit()
  }
}

function reposition() {
  if (!win || win.isDestroyed()) return
  const area = screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).workArea
  win.setBounds(area)
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (win && !win.isDestroyed()) { hidden = false; win.showInactive(); broadcastState() }
  })

  app.whenReady().then(bootstrap).catch((err) => {
    console.error('[dsh-whale-desktop] 启动失败:', err)
    bootLog('bootstrap failed: ' + String((err && err.stack) || err))
    try { fs.writeFileSync(path.join(os.tmpdir(), 'dshw-selftest.json'), JSON.stringify({ error: String((err && err.stack) || err) }, null, 2), 'utf8') } catch (e) {}
    app.quit()
  })

  app.on('window-all-closed', () => {
    if (host) { try { host.close() } catch (err) {} }
    app.quit()
  })

  app.on('before-quit', () => {
    if (host) { try { host.close() } catch (err) {} host = null }
  })
}
