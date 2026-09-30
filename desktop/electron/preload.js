const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('dshwDesktop', {
  setClickThrough: (through) => ipcRenderer.send('dshw:set-click-through', !!through),
  quit: () => ipcRenderer.send('dshw:quit'),
  reload: () => ipcRenderer.send('dshw:reload'),
  toggleTop: () => ipcRenderer.send('dshw:toggle-top'),
  getState: () => ipcRenderer.invoke('dshw:get-state'),
  onState: (cb) => {
    const handler = (_e, state) => { try { cb(state) } catch (err) {} }
    ipcRenderer.on('dshw:state', handler)
    return () => ipcRenderer.removeListener('dshw:state', handler)
  },
})
