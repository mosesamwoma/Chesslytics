const TEXT = '︎'

export interface BoardPiece {
  type: string
  isWhite: boolean
}

export interface BoardSquare {
  square: string
  piece: BoardPiece | null
  file: number
  rank: number
}

interface ChessBoardProps {
  fen: string
  orientation?: 'white' | 'black'
  highlight?: (string | null | undefined)[]
  selected?: string | null
  targets?: (string | null | undefined)[]
  lastMove?: string | null
  onSquareClick?: (square: string) => void
}

const GLYPHS: Record<string, string> = {
  p: `♟${TEXT}`,
  n: `♞${TEXT}`,
  b: `♝${TEXT}`,
  r: `♜${TEXT}`,
  q: `♛${TEXT}`,
  k: `♚${TEXT}`,
}

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']

export function parseFen(fen: string | null | undefined): BoardSquare[] {
  const placement = (fen || '').split(' ')[0]
  const rows = placement.split('/')
  const squares: BoardSquare[] = []
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

export function squareFromUci(uci: string | null | undefined): string | null {
  if (!uci || uci.length < 4) return null
  return uci.slice(2, 4)
}

export function sourceFromUci(uci: string | null | undefined): string | null {
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
}: ChessBoardProps) {
  const squares = parseFen(fen)
  const ordered = orientation === 'black' ? [...squares].reverse() : squares
  const marked = new Set(highlight.filter((value): value is string => Boolean(value)))
  const reachable = new Set(targets.filter((value): value is string => Boolean(value)))
  const recent = new Set(
    [sourceFromUci(lastMove), squareFromUci(lastMove)].filter((value): value is string =>
      Boolean(value),
    ),
  )
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
            onClick={interactive && onSquareClick ? () => onSquareClick(entry.square) : undefined}
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
