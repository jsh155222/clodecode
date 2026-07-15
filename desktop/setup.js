// 최초 실행 시 필요한 로컬 환경(Python venv + 패키지, ffmpeg)을 자동으로 준비한다.
// install.bat의 핵심 로직(venv 생성 → pip install → ffmpeg 확보)을 Node에서 그대로 재현한 것.
//
// 검증 상태: venv 생성 + pip install 단계는 OS에 상관없는 표준 Python 동작이라 이 저장소의
// 리눅스 개발 환경에서 실제로 끝까지 실행해 확인했다. ffmpeg 자동 다운로드(Windows 전용,
// install.bat과 동일하게 gyan.dev 빌드 + PowerShell Expand-Archive 사용)는 실제 Windows에서
// 아직 검증하지 못했다 - install.bat도 같은 방식이라 동작할 것으로 신뢰하지만, 최종 확인은
// 실사용자의 Windows PC에서 필요하다.

const { spawn } = require('child_process')
const path = require('path')
const fs = require('fs')
const https = require('https')

function venvPythonPath(venvDir) {
  return process.platform === 'win32'
    ? path.join(venvDir, 'Scripts', 'python.exe')
    : path.join(venvDir, 'bin', 'python')
}

function findSeedPython() {
  // venv를 만들 때 쓸 "씨앗" 파이썬 - 시스템 PATH에 있는 것을 그대로 쓴다.
  return process.platform === 'win32' ? 'python' : 'python3'
}

function runCommand(command, args, options, onOutput) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { ...options, stdio: ['ignore', 'pipe', 'pipe'] })
    child.stdout.on('data', (d) => onOutput && onOutput(d.toString()))
    child.stderr.on('data', (d) => onOutput && onOutput(d.toString()))
    child.on('error', reject)
    child.on('close', (code) => {
      if (code === 0) resolve()
      else reject(new Error(`${command} ${args.join(' ')} 명령이 종료 코드 ${code}로 실패했습니다.`))
    })
  })
}

/** 이 파이썬으로 capcut_auto 백엔드에 필요한 패키지를 전부 import할 수 있는지 실제로 확인한다. */
function checkPythonEnvironmentReady(pythonExe, repoRoot) {
  return new Promise((resolve) => {
    const child = spawn(pythonExe, ['-c', 'import capcut_auto.server, fastapi, uvicorn'], {
      cwd: repoRoot,
      stdio: 'ignore',
    })
    child.on('error', () => resolve(false))
    child.on('close', (code) => resolve(code === 0))
  })
}

async function ensurePythonEnvironment(dataDir, repoRoot, onOutput) {
  // install.bat으로 이미 저장소 안에 venv를 만들어둔 개발 체크아웃(패키징 안 된 실행)이라면
  // 그걸 그대로 쓴다 - 새로 또 만들 필요 없다.
  const repoVenvPython = venvPythonPath(path.join(repoRoot, '.venv'))
  if (fs.existsSync(repoVenvPython) && (await checkPythonEnvironmentReady(repoVenvPython, repoRoot))) {
    return repoVenvPython
  }

  const venvDir = path.join(dataDir, '.venv')
  const venvPython = venvPythonPath(venvDir)

  if (fs.existsSync(venvPython) && (await checkPythonEnvironmentReady(venvPython, repoRoot))) {
    return venvPython
  }

  onOutput('처음 실행이라 필요한 패키지를 설치합니다. 몇 분 정도 걸릴 수 있어요...\n')
  if (!fs.existsSync(venvDir)) {
    onOutput('가상환경을 만드는 중...\n')
    await runCommand(findSeedPython(), ['-m', 'venv', venvDir], {}, onOutput)
  }

  onOutput('필요한 패키지를 설치하는 중...\n')
  const requirementsPath = path.join(repoRoot, 'requirements.txt')
  await runCommand(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip'], {}, onOutput)
  await runCommand(venvPython, ['-m', 'pip', 'install', '-r', requirementsPath], {}, onOutput)

  return venvPython
}

function hasFfmpegOnPath() {
  return new Promise((resolve) => {
    const child = spawn(process.platform === 'win32' ? 'where' : 'which', ['ffmpeg'], { stdio: 'ignore' })
    child.on('error', () => resolve(false))
    child.on('close', (code) => resolve(code === 0))
  })
}

function downloadFile(url, destPath) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(destPath)
    https
      .get(url, (res) => {
        if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
          file.close()
          downloadFile(res.headers.location, destPath).then(resolve, reject)
          return
        }
        res.pipe(file)
        file.on('finish', () => file.close(resolve))
      })
      .on('error', reject)
  })
}

/** install.bat과 동일한 방식(gyan.dev 빌드 zip + PowerShell 압축 해제)으로 ffmpeg를 받는다.
 * Windows 전용 - Mac/Linux는 brew/apt로 이미 시스템에 있는 경우가 많아 자동 다운로드하지 않는다. */
async function ensureFfmpegWindows(dataDir, onOutput) {
  const ffmpegDir = path.join(dataDir, 'ffmpeg', 'bin')
  if (fs.existsSync(path.join(ffmpegDir, 'ffmpeg.exe'))) return ffmpegDir

  onOutput('ffmpeg를 내려받는 중...\n')
  fs.mkdirSync(ffmpegDir, { recursive: true })
  const zipPath = path.join(dataDir, 'ffmpeg_temp.zip')
  const extractDir = path.join(dataDir, 'ffmpeg_extract')

  await downloadFile('https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip', zipPath)
  await runCommand(
    'powershell',
    ['-NoProfile', '-Command', `Expand-Archive -Path '${zipPath}' -DestinationPath '${extractDir}' -Force`],
    {},
    onOutput,
  )

  const extracted = fs.readdirSync(extractDir).find((name) => name.startsWith('ffmpeg-'))
  if (!extracted) throw new Error('ffmpeg 압축 해제 결과를 찾을 수 없습니다.')
  fs.copyFileSync(path.join(extractDir, extracted, 'bin', 'ffmpeg.exe'), path.join(ffmpegDir, 'ffmpeg.exe'))
  fs.copyFileSync(path.join(extractDir, extracted, 'bin', 'ffprobe.exe'), path.join(ffmpegDir, 'ffprobe.exe'))

  fs.rmSync(zipPath, { force: true })
  fs.rmSync(extractDir, { recursive: true, force: true })
  return ffmpegDir
}

/** 필요한 모든 준비를 마치고, 백엔드를 실행할 때 쓸 { pythonExe, ffmpegDir } 를 반환한다. */
async function ensureEnvironmentReady(dataDir, repoRoot, onOutput) {
  const pythonExe = await ensurePythonEnvironment(dataDir, repoRoot, onOutput)

  let ffmpegDir = null
  if (!(await hasFfmpegOnPath())) {
    if (process.platform === 'win32') {
      ffmpegDir = await ensureFfmpegWindows(dataDir, onOutput)
    } else {
      onOutput(
        'ffmpeg가 설치되어 있지 않습니다. macOS는 "brew install ffmpeg", Linux는 배포판 패키지 관리자로 설치한 뒤 다시 실행해주세요.\n',
      )
    }
  }

  return { pythonExe, ffmpegDir }
}

module.exports = { ensureEnvironmentReady, checkPythonEnvironmentReady, venvPythonPath }
