/**
 * 导出后端 OpenAPI schema 到项目根目录的 openapi.json。
 *
 * 为什么不用 "python ../backend/scripts/dump_openapi.py"：
 *   1) venv 的解释器路径随平台不同（Windows 是 venv/Scripts/python.exe，
 *      macOS/Linux 是 venv/bin/python），写死一个另一个就跑不了；
 *   2) 直接写 python 会用到系统解释器，缺依赖时 `import app` 会直接失败，
 *      报出来的错还跟真实原因（装了没装依赖）对不上。
 *
 * 这里在 Node 里探测一次，优先用项目 venv，找不到才回退系统 python。
 */
import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendDir = dirname(dirname(fileURLToPath(import.meta.url)))
const backendDir = join(frontendDir, '..', 'backend')
const scriptPath = join(backendDir, 'scripts', 'dump_openapi.py')

const venvPython =
  process.platform === 'win32'
    ? join(backendDir, 'venv', 'Scripts', 'python.exe')
    : join(backendDir, 'venv', 'bin', 'python')

const python = existsSync(venvPython) ? venvPython : 'python'

if (!existsSync(scriptPath)) {
  console.error(`[gen:openapi] 找不到导出脚本: ${scriptPath}`)
  process.exit(1)
}

console.log(`[gen:openapi] 解释器: ${python}`)
try {
  execFileSync(python, [scriptPath], { cwd: backendDir, stdio: 'inherit' })
} catch (err) {
  console.error('[gen:openapi] 导出失败，先确认后端依赖已安装（backend/venv）')
  process.exit(err.status ?? 1)
}
