import { ProjectProvider, useProject } from './state/ProjectContext'
import { StartScreen } from './screens/StartScreen'
import { AutoEditScreen } from './screens/AutoEditScreen'
import { ShootingGuideScreen } from './screens/ShootingGuideScreen'

function AppShell() {
  const { mode, setMode, returnToStart } = useProject()

  return (
    <main className="app-shell">
      {mode === null ? <StartScreen onSelectMode={setMode} /> : null}
      {mode === 'AUTO_EDIT' ? <AutoEditScreen onExitToStart={returnToStart} /> : null}
      {mode === 'SHOOTING_GUIDE' ? <ShootingGuideScreen onBack={returnToStart} /> : null}
    </main>
  )
}

function App() {
  return (
    <ProjectProvider>
      <AppShell />
    </ProjectProvider>
  )
}

export default App
