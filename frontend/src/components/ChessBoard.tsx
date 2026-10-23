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

export interface BoardArrow {
  from: string
  to: string
  kind: 'best' | 'played'
}

interface ChessBoardProps {
  fen: string
  orientation?: 'white' | 'black'
  highlight?: (string | null | undefined)[]
  selected?: string | null
  targets?: (string | null | undefined)[]
  lastMove?: string | null
  arrows?: BoardArrow[]
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

export function squareCenter(square: string, orientation: 'white' | 'black'): { x: number; y: number } | null {
  const file = FILES.indexOf(square.charAt(0))
  const rank = Number(square.charAt(1))
  if (file < 0 || !(rank >= 1 && rank <= 8)) return null
  if (orientation === 'black') return { x: 7 - file + 0.5, y: rank - 0.5 }
  return { x: file + 0.5, y: 8 - rank + 0.5 }
}

function Arrow({
  arrow,
  orientation,
}: {
  arrow: BoardArrow
  orientation: 'white' | 'black'
}) {
  const start = squareCenter(arrow.from, orientation)
  const end = squareCenter(arrow.to, orientation)
  if (!start || !end) return null
  const dx = end.x - start.x
  const dy = end.y - start.y
  const length = Math.hypot(dx, dy)
  if (length === 0) return null
  const ux = dx / length
  const uy = dy / length
  const head = 0.42
  const tipX = end.x - ux * 0.08
  const tipY = end.y - uy * 0.08
  const baseX = tipX - ux * head
  const baseY = tipY - uy * head
  const wing = 0.26
  const points = [
    `${tipX},${tipY}`,
    `${baseX - uy * wing},${baseY + ux * wing}`,
    `${baseX + uy * wing},${baseY - ux * wing}`,
  ].join(' ')
  return (
    <g className={`arrow arrow-${arrow.kind}`}>
      <line x1={start.x} y1={start.y} x2={baseX} y2={baseY} />
      <polygon points={points} />
    </g>
  )
}

export default function ChessBoard({
  fen,
  orientation = 'white',
  highlight = [],
  selected = null,
  targets = [],
  lastMove = null,
  arrows = [],
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
    <div className="board-frame">
      <div className={interactive ? 'board interactive' : 'board'}>
        {ordered.map((entry, index) => {
          const row = Math.floor(index / 8)
          const column = index % 8
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
              {column === 0 ? <span className="coord-rank">{entry.rank}</span> : null}
              {row === 7 ? <span className="coord-file">{FILES[entry.file]}</span> : null}
              {entry.piece ? (
                <span className={entry.piece.isWhite ? 'piece-white' : 'piece-black'}>
                  {GLYPHS[entry.piece.type]}
                </span>
              ) : null}
            </Element>
          )
        })}
      </div>
      {arrows.length ? (
        <svg className="board-arrows" viewBox="0 0 8 8" aria-hidden="true">
          {arrows.map((arrow) => (
            <Arrow
              key={`${arrow.kind}-${arrow.from}-${arrow.to}`}
              arrow={arrow}
              orientation={orientation}
            />
          ))}
        </svg>
      ) : null}
    </div>
  )
}
