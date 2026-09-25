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

export function sourceFromUci(uci) {
  if (!uci || uci.length < 4) return null
  return uci.slice(0, 2)
}

export default function ChessBoard({
  fen,
  orientation = 'white',
  highlight = [],
  selected = null,
  targets = [],
  lastMove = null,
  onSquareClick,
}) {
  const squares = parseFen(fen)
  const ordered = orientation === 'black' ? [...squares].reverse() : squares
  const marked = new Set(highlight.filter(Boolean))
  const reachable = new Set(targets.filter(Boolean))
  const recent = new Set([sourceFromUci(lastMove), squareFromUci(lastMove)].filter(Boolean))
  const interactive = typeof onSquareClick === 'function'
  const Element = interactive ? 'button' : 'div'

  return (
    <div className={interactive ? 'board interactive' : 'board'}>
      {ordered.map((entry) => {
        const isDark = (entry.file + entry.rank) % 2 === 1
        const classes = ['square', isDark ? 'dark' : 'light']
        if (marked.has(entry.square)) classes.push('target')
        if (entry.square === selected) classes.push('selected')
        if (reachable.has(entry.square)) classes.push('reachable')
        if (recent.has(entry.square)) classes.push('recent')
        return (
          <Element
            key={entry.square}
            type={interactive ? 'button' : undefined}
            className={classes.join(' ')}
            title={entry.square}
            aria-label={entry.piece ? `${entry.square} ${entry.piece.type}` : entry.square}
            onClick={interactive ? () => onSquareClick(entry.square) : undefined}
          >
            {entry.piece ? (
              <span className={entry.piece.isWhite ? 'piece-white' : 'piece-black'}>
                {GLYPHS[entry.piece.type]}
              </span>
            ) : null}
          </Element>
        )
      })}
    </div>
  )
}
