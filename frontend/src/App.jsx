import { Link, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext.jsx'
import NavBar from './components/NavBar.jsx'
import ChessDNA from './pages/ChessDNA.jsx'
import Coach from './pages/Coach.jsx'
import Dashboard from './pages/Dashboard.jsx'
import GameAnalysis from './pages/GameAnalysis.jsx'
import Games from './pages/Games.jsx'
import Login from './pages/Login.jsx'
import Patterns from './pages/Patterns.jsx'
import Training from './pages/Training.jsx'

function NotFound() {
  return (
    <div className="notice">
      Nothing at this address. <Link to="/">Back to the dashboard</Link>
    </div>
  )
}

export default function App() {
  const { status, error, retry } = useAuth()

  if (status === 'loading') {
    return (
      <main className="main">
        <div className="notice">Loading…</div>
      </main>
    )
  }

  if (status === 'error') {
    return (
      <main className="main">
        <div className="notice error">
          Could not reach the server: {error?.message}{' '}
          <button type="button" className="button" onClick={retry}>
            Retry
          </button>
        </div>
      </main>
    )
  }

  if (status === 'anonymous') {
    return <Login />
  }

  return (
    <div className="app">
      <NavBar />
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/games" element={<Games />} />
          <Route path="/games/:gameId" element={<GameAnalysis />} />
          <Route path="/patterns" element={<Patterns />} />
          <Route path="/training" element={<Training />} />
          <Route path="/dna" element={<ChessDNA />} />
          <Route path="/coach" element={<Coach />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}
