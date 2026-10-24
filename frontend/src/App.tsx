import { Link, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext.tsx'
import Account from './pages/Account.tsx'
import Admin from './pages/Admin.tsx'
import NavBar from './components/NavBar.tsx'
import RecoveryCode from './components/RecoveryCode.tsx'
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
  const { status, user, error, retry, recoveryCode, dismissRecovery } = useAuth()

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
      <div className="auth-shell">
        <aside className="auth-brand">
          <div className="auth-logo">
            <span className="nav-logo" aria-hidden="true">
              &#9822;
            </span>
            <span>Chesslytics</span>
          </div>
          <div>
            <h2>Learn from the mistakes you keep repeating.</h2>
            <p>
              Stockfish reviews your games, finds the patterns behind your losses, and turns them
              into puzzles you can practise.
            </p>
            <ul className="auth-points">
              <li>See which mistake types cost you the most</li>
              <li>Replay your own blunders as training puzzles</li>
              <li>Track your accuracy and progress week by week</li>
            </ul>
          </div>
          <div className="auth-foot">Import from Chess.com or Lichess, or upload a PGN.</div>
        </aside>
        <main className="auth-panel">
          <Routes>
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/verify-email" element={<VerifyEmail />} />
            <Route path="*" element={<Login />} />
          </Routes>
        </main>
      </div>
    )
  }

  if (recoveryCode) {
    return (
      <div className="auth-panel" style={{ minHeight: '100vh' }}>
        <RecoveryCode
          code={recoveryCode}
          heading="Save your recovery code"
          intro="This is the only time it is shown. If you ever forget your password, this code lets you set a new one yourself, without asking anyone."
          continueLabel="Continue to Chesslytics"
          onDone={dismissRecovery}
        />
      </div>
    )
  }

  return (
    <div className="app">
      <NavBar />
      <main className="main">
        {user && !user.has_recovery_code ? (
          <div className="notice" style={{ marginBottom: 16 }}>
            You do not have a recovery code yet. Without one, a forgotten password can only be
            fixed by email or an administrator.{' '}
            <Link to="/account">Create a recovery code</Link>
          </div>
        ) : null}
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
