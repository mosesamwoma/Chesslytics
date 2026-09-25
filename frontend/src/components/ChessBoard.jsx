const TEXT = '︎'

const GLYPHS = {
  p: `♟${TEXT}`,
  n: `♞${TEXT}`,
  b: `♝${TEXT}`,
  r: `♜${TEXT}`,
  q: `♛${TEXT}`,
  k: `♚${TEXT}`,
}

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']

export function parseFen(fen) {
  const placement = (fen || '').split(' ')[0]
  const rows = placement.split('/')
  const squares = []
  rows.forEach((row, rowIndex) => {
    const rank = 8 - rowIndex
    let file = 0
    for (const char of row) {
      if (/\d/.test(char)) {
        const empty = Number(char)
        for (let step = 0; step < empty; step += 1) {
          squares.push({ square: `${FILES[file]}${rank}`, piece: null, file, rank })
          file += 1
        }
      } else {
        const isWhite = char === char.toUpperCase()
        squares.push({
          square: `${FILES[file]}${rank}`,
          piece: { type: char.toLowerCase(), isWhite },
          file,
          rank,
        })
        file += 1
      }
    }
  })
  return squares
}

export function squareFromUci(uci) {
  if (!uci || uci.length < 4) return null
  return uci.slice(2, 4)
}

export default function ChessBoard({ fen, orientation = 'white', highlight = [] }) {
  const squares = parseFen(fen)
  const ordered = orientation === 'black' ? [...squares].reverse() : squares
  const targets = new Set(highlight.filter(Boolean))

  return (
    <div className="board">
      {ordered.map((entry) => {
        const isDark = (entry.file + entry.rank) % 2 === 0
        const classes = ['square', isDark ? 'dark' : 'light']
        if (targets.has(entry.square)) classes.push('target')
        return (
          <div
            key={entry.square}
            className={classes.join(' ')}
            title={entry.square}
            aria-label={entry.piece ? `${entry.square} ${entry.piece.type}` : entry.square}
          >
            {entry.piece ? (
              <span className={entry.piece.isWhite ? 'piece-white' : 'piece-black'}>
                {GLYPHS[entry.piece.type]}
              </span>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
