import { useState } from 'react'
import { useCopy } from '../hooks/useCopy.ts'

interface RecoveryCodeProps {
  code: string
  heading: string
  intro: string
  continueLabel: string
  onDone: () => void
}

export default function RecoveryCode({
  code,
  heading,
  intro,
  continueLabel,
  onDone,
}: RecoveryCodeProps) {
  const [saved, setSaved] = useState(false)
  const copier = useCopy()

  return (
    <div className="card login recovery">
      <h1>{heading}</h1>
      <p className="subtitle">{intro}</p>
      <div className="recovery-code mono" aria-label="Recovery code">
        {code}
      </div>
      <div className="row">
        <button type="button" className="button" onClick={() => copier.copy(code)}>
          {copier.copied ? 'Copied' : copier.failed ? 'Copy failed, select it by hand' : 'Copy code'}
        </button>
      </div>
      <p className="muted">
        Anyone with this code and your username can set a new password, so keep it private, in a
        password manager or on paper. It works once; after you use it you get a new one.
      </p>
      <label className="row">
        <input
          type="checkbox"
          checked={saved}
          onChange={(event) => setSaved(event.target.checked)}
        />
        <span>I have saved my recovery code</span>
      </label>
      <button type="button" className="button primary" disabled={!saved} onClick={onDone}>
        {continueLabel}
      </button>
    </div>
  )
}
