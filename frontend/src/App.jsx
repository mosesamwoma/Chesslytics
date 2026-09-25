import { Link, Route, Routes } from 'react-router-dom'
import NavBar from './components/NavBar.jsx'
import ChessDNA from './pages/ChessDNA.jsx'
import Dashboard from './pages/Dashboard.jsx'
import GameAnalysis from './pages/GameAnalysis.jsx'
import Games from './pages/Games.jsx'
import Patterns from './pages/Patterns.jsx'

function NotFound() {
  return (
    <div className="notice">
      Nothing at this address. <Link to="/">Back to the dashboard</Link>
    </div>
  )
}

export default function App() {
  return (
    <div className="app">
      <NavBar />
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/games" element={<Games />} />
          <Route path="/games/:gameId" element={<GameAnalysis />} />
          <Route path="/patterns" element={<Patterns />} />
          <Route path="/dna" element={<ChessDNA />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}
