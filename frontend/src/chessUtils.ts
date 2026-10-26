export function sideToMove(fen: string | null | undefined): 'white' | 'black' {
  return (fen || '').split(' ')[1] === 'b' ? 'black' : 'white'
}

export function pieceAt(
  fen: string | null | undefined,
  square: string | null | undefined,
): { type: string; isWhite: boolean } | null {
  const placement = (fen || '').split(' ')[0]
  if (!placement || !square) return null
  const file = square.charCodeAt(0) - 97
  const rank = Number(square[1])
  if (file < 0 || file > 7 || !(rank >= 1 && rank <= 8)) return null
  const row = placement.split('/')[8 - rank]
  if (!row) return null
  let index = 0
  for (const char of row) {
    if (/\d/.test(char)) {
      index += Number(char)
      continue
    }
    if (index === file) {
      return { type: char.toLowerCase(), isWhite: char === char.toUpperCase() }
    }
    index += 1
  }
  return null
}

export function movesFrom(legalMoves: string[] | null | undefined, square: string): string[] {
  return (legalMoves || []).filter((uci) => uci.slice(0, 2) === square)
}

export function destinations(legalMoves: string[] | null | undefined, square: string): string[] {
  return [...new Set(movesFrom(legalMoves, square).map((uci) => uci.slice(2, 4)))]
}
