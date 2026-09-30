// 用 Chromium 把原版那条 SVG 原样渲染成 PNG（作为对照基准）。
// 用法: electron render_svg_ref.js <out.png> <width> <height>
const { app, BrowserWindow } = require('electron')
const fs = require('node:fs')
const path = require('node:path')

const OUT = process.argv[2]
const W = Number(process.argv[3] || 560)
const H = Number(process.argv[4] || 382)

// 原封不动抄自 assets/whale-widget.js:11552
const SVG = '<svg viewBox="0 0 1026 700" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">' +
  '<path class="dshwv-bshape" fill="#FFFFFF" stroke="#203170" stroke-width="18" stroke-linejoin="round" stroke-linecap="round" d="M 827 248 A 373 232 0 1 0 81 246 A 373 232 0 0 0 301 465 A 57 32 10 0 0 413 484 A 373 232 0 0 0 827 248 Z"/>' +
  '<ellipse class="dshwv-b1" cx="352" cy="561" rx="37.5" ry="26" fill="#FFFFFF" stroke="#203170" stroke-width="18"/>' +
  '<ellipse class="dshwv-b2" cx="442" cy="646" rx="24.5" ry="18" fill="#FFFFFF" stroke="#203170" stroke-width="18"/>' +
  '</svg>'

app.disableHardwareAcceleration()

app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: W, height: H, show: false, webPreferences: { offscreen: true } })
  const html = '<!doctype html><html><body style="margin:0;background:transparent">' +
    '<script>window.__go=async()=>{' +
    'const svg=' + JSON.stringify(SVG) + ';' +
    'const img=new Image();' +
    'img.src="data:image/svg+xml;charset=utf-8,"+encodeURIComponent(svg);' +
    'await img.decode();' +
    'const c=document.createElement("canvas");c.width=' + W + ';c.height=' + H + ';' +
    'const g=c.getContext("2d");g.drawImage(img,0,0,' + W + ',' + H + ');' +
    'return c.toDataURL("image/png");};</script></body></html>'
  await win.loadURL('data:text/html;base64,' + Buffer.from(html).toString('base64'))
  const dataUrl = await win.webContents.executeJavaScript('window.__go()')
  fs.writeFileSync(OUT, Buffer.from(dataUrl.split(',')[1], 'base64'))
  console.log('saved ' + OUT + ' ' + W + 'x' + H)
  app.quit()
}).catch((err) => { console.error('failed:', err); app.quit() })
