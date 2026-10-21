import { Link, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext.jsx'
import Account from './pages/Account.jsx'
import Admin from './pages/Admin.jsx'
import NavBar from './components/NavBar.jsx'
import ChessDNA from './pages/ChessDNA.jsx'
import Coach from './pages/Coach.jsx'
import Dashboard from './pages/Dashboard.jsx'
import ForgotPassword from './pages/ForgotPassword.jsx'
import GameAnalysis from './pages/GameAnalysis.jsx'
import Games from './pages/Games.jsx'
import Jobs from './pages/Jobs.jsx'
import Login from './pages/Login.jsx'
import Patterns from './pages/Patterns.jsx'
import ResetPassword from './pages/ResetPassword.jsx'
import Training from './pages/Training.jsx'
import VerifyEmail from './pages/VerifyEmail.jsx'

function NotFound() {
  return (
    <div className="notice">
      Nothing at this address. <Link to="/">Back to the dashboard</Link>
    </div>
  )
}

export default function App() {
  const { status, user, error, retry } = useAuth()

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
    return (
      <main className="main">
        <Routes>
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="*" element={<Login />} />
        </Routes>
      </main>
    )
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
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/account" element={<Account />} />
          <Route path="/verify-email" element={<VerifyEmail />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          {user?.is_admin ? <Route path="/admin" element={<Admin />} /> : null}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}
