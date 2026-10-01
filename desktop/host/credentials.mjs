// DSH 凭据文件（~/.dsh/.credentials.yaml）的极简读写实现。
// 只处理 DSH 实际使用的结构：
//   version: 1
//   refs:
//     DEEPSEEK_API_KEY: sk-xxxx
// 值用 JSON 双引号样式写出，js-yaml 可正常读取；读取时兼容裸值与引号值。
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

export function dshHome() {
  return process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
}

export function credentialsFile() {
  return path.join(dshHome(), '.credentials.yaml')
}

function unquote(v) {
  const s = String(v == null ? '' : v).trim()
  if (s.length >= 2 && s[0] === '"' && s[s.length - 1] === '"') {
    try { return JSON.parse(s) } catch (err) { return s.slice(1, -1) }
  }
  if (s.length >= 2 && s[0] === "'" && s[s.length - 1] === "'") return s.slice(1, -1)
  return s
}

function readDoc() {
  const doc = { version: 1, refs: {}, raw: [] }
  let text = ''
  try { text = fs.readFileSync(credentialsFile(), 'utf8') } catch (err) { return doc }
  const lines = text.split(/\r?\n/)
  let inRefs = false
  for (const line of lines) {
    if (/^refs\s*:\s*$/.test(line)) { inRefs = true; continue }
    const vm = /^version\s*:\s*(.+)$/.exec(line)
    if (vm) { doc.version = Number(unquote(vm[1])) || 1; inRefs = false; continue }
    if (inRefs) {
      const m = /^\s+([A-Za-z0-9_.\-]+)\s*:\s*(.*)$/.exec(line)
      if (m) doc.refs[m[1]] = unquote(m[2])
      continue
    }
    if (line.trim()) doc.raw.push(line)
  }
  return doc
}

function writeDoc(doc) {
  const file = credentialsFile()
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const out = []
  out.push('version: ' + (Number(doc.version) || 1))
  out.push('refs:')
  for (const [k, v] of Object.entries(doc.refs || {})) {
    out.push('  ' + k + ': ' + JSON.stringify(String(v == null ? '' : v)))
  }
  for (const line of doc.raw || []) out.push(line)
  fs.writeFileSync(file, out.join('\n') + '\n', 'utf8')
}

export function createCredentials() {
  return {
    async resolve(ref) {
      const key = String(ref || '').trim()
      if (!key) return null
      const doc = readDoc()
      if (!(key in doc.refs)) return null
      const value = doc.refs[key]
      if (!value) return null
      return { value }
    },
    async set(ref, value) {
      const key = String(ref || '').trim()
      if (!key) throw new Error('empty credential ref')
      const doc = readDoc()
      doc.refs[key] = String(value == null ? '' : value)
      writeDoc(doc)
      return true
    },
    async unset(ref) {
      const key = String(ref || '').trim()
      if (!key) return false
      const doc = readDoc()
      if (key in doc.refs) {
        delete doc.refs[key]
        writeDoc(doc)
      }
      return true
    },
  }
}
