import { Link, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext.tsx'
import Account from './pages/Account.tsx'
import Admin from './pages/Admin.tsx'
import NavBar from './components/NavBar.tsx'
import ChessDNA from './pages/ChessDNA.tsx'
import Coach from './pages/Coach.tsx'
import Dashboard from './pages/Dashboard.tsx'
import ForgotPassword from './pages/ForgotPassword.tsx'
import GameAnalysis from './pages/GameAnalysis.tsx'
import Games from './pages/Games.tsx'
import Jobs from './pages/Jobs.tsx'
import Login from './pages/Login.tsx'
import Patterns from './pages/Patterns.tsx'
import ResetPassword from './pages/ResetPassword.tsx'
import Training from './pages/Training.tsx'
import VerifyEmail from './pages/VerifyEmail.tsx'

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
          Could not reach the server: {typeof error === 'string' ? error : error?.message}{' '}
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
