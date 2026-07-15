// capcut-auto 데스크톱 앱(Electron)의 메인 프로세스.
//
// 이 프로세스가 하는 일:
//   1. 처음 실행이면 로컬 Python 환경(venv+패키지)을 준비한다(setup.js, 진행 상황 창 표시).
//   2. 로컬 Python 백엔드(capcut_auto.server:app, uvicorn)를 자식 프로세스로 실행한다.
//   3. 백엔드가 실제로 응답하기 시작할 때까지 기다린 뒤, 그 주소를 여는 창을 띄운다.
//   4. 앱이 종료될 때 백엔드 프로세스를 확실히 함께 종료한다.
//
// webapp/를 `npm run build`로 만든 정적 파일(webapp/dist)을 capcut_auto/server.py
// 자신이 서빙하도록 이미 구성해뒀기 때문에(server.py의 _maybe_mount_frontend 참고),
// 이 창은 그 백엔드 주소 하나만 열면 화면 전체가 뜬다 - 별도로 vite 서버를 띄울 필요가 없다.

const { app, BrowserWindow, dialog } = require('electron')
const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')
const net = require('net')
const http = require('http')
const { ensureEnvironmentReady } = require('./setup')

// REPO_ROOT: 앱 코드(capcut_auto/, category-rules/, webapp/dist)가 있는 위치.
// 패키징된 앱에서는 설치 폴더(예: Program Files) 안이라 보통 쓰기 권한이 없다.
const REPO_ROOT = app.isPackaged
  ? path.join(process.resourcesPath, 'app')
  : path.join(__dirname, '..')

// DATA_DIR: 실제로 쓰기 가능한(사용자별) 위치. .venv와 서버 작업 폴더(업로드/캐시)는
// 항상 여기 둔다 - REPO_ROOT에 쓰려고 하면 설치 폴더 권한 문제로 실패할 수 있다.
const DATA_DIR = app.getPath('userData')

let backendProcess = null
let mainWindow = null

/** 0을 bind하면 OS가 비어 있는 포트를 골라준다 - 이미 다른 서버(예: 개발용 uvicorn)가
 * 8000번을 쓰고 있어도 충돌하지 않는다. */
function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address()
      server.close(() => resolve(port))
    })
  })
}

function waitForBackendReady(port, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const req = http.get({ host: '127.0.0.1', port, path: '/', timeout: 2000 }, (res) => {
        res.resume()
        resolve()
      })
      req.on('error', () => {
        if (Date.now() > deadline) {
          reject(new Error('백엔드가 제한 시간 안에 응답하지 않았습니다.'))
          return
        }
        setTimeout(attempt, 300)
      })
      req.on('timeout', () => req.destroy())
    }
    attempt()
  })
}

async function startBackend(pythonExe, ffmpegDir) {
  const port = await findFreePort()

  // capcut_auto 패키지를 import하려면 cwd가 REPO_ROOT(패키지가 있는 위치)여야 한다.
  // 하지만 그 폴더는 설치 위치라 쓰기 권한이 없을 수 있으므로, 서버가 실제로 파일을
  // 쓰는 작업 폴더(업로드/캐시)는 CAPCUT_AUTO_STATE_DIR로 DATA_DIR 아래를 가리키게 한다.
  const stateDir = path.join(DATA_DIR, 'server_work')
  fs.mkdirSync(stateDir, { recursive: true })

  const env = { ...process.env, CAPCUT_AUTO_STATE_DIR: stateDir }
  if (ffmpegDir) env.CAPCUT_AUTO_FFMPEG_DIR = ffmpegDir

  const child = spawn(pythonExe, ['-m', 'uvicorn', 'capcut_auto.server:app', '--host', '127.0.0.1', '--port', String(port)], {
    cwd: REPO_ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    env,
  })

  child.stdout.on('data', (data) => process.stdout.write(`[backend] ${data}`))
  child.stderr.on('data', (data) => process.stderr.write(`[backend] ${data}`))

  backendProcess = child

  await waitForBackendReady(port)
  return port
}

function stopBackend() {
  if (backendProcess && !backendProcess.killed) {
    backendProcess.kill()
    backendProcess = null
  }
}

function escapeForJs(text) {
  return text.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$/g, '\\$')
}

async function showSetupProgressAndPrepareEnvironment() {
  const progressWindow = new BrowserWindow({
    width: 480,
    height: 320,
    resizable: false,
    title: 'CapCut Auto Editor - 준비 중',
  })
  await progressWindow.loadFile(path.join(__dirname, 'setup-progress.html'))

  const appendLog = (text) => {
    if (progressWindow.isDestroyed()) return
    const script = `document.getElementById('log').textContent += \`${escapeForJs(text)}\`;` +
      `document.getElementById('log').scrollTop = document.getElementById('log').scrollHeight;`
    progressWindow.webContents.executeJavaScript(script).catch(() => {})
  }

  try {
    const result = await ensureEnvironmentReady(DATA_DIR, REPO_ROOT, appendLog)
    return result
  } finally {
    if (!progressWindow.isDestroyed()) progressWindow.close()
  }
}

async function createWindow() {
  try {
    const { pythonExe, ffmpegDir } = await showSetupProgressAndPrepareEnvironment()
    const port = await startBackend(pythonExe, ffmpegDir)
    mainWindow = new BrowserWindow({
      width: 1280,
      height: 900,
      title: 'CapCut Auto Editor',
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
      },
    })
    await mainWindow.loadURL(`http://127.0.0.1:${port}/`)
  } catch (err) {
    dialog.showErrorBox(
      'CapCut Auto Editor를 시작할 수 없습니다',
      `로컬 서버를 준비하지 못했습니다.\n\n` +
        `Python이 설치되어 있고 PATH에 등록되어 있는지 확인해주세요 (winget/python.org에서 설치 시 ` +
        `"Add python.exe to PATH"를 체크해야 합니다).\n\n자세한 오류: ${err.message}`,
    )
    app.quit()
  }
}

app.whenReady().then(createWindow)

app.on('window-all-closed', () => {
  stopBackend()
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', stopBackend)

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})
