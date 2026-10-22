export const CATEGORY_LABELS: Record<string, string> = {
  allowed_mate: 'Allowed mates',
  missed_mate: 'Missed mates',
  hanging_piece: 'Hanging pieces',
  missed_capture: 'Missed captures',
  time_pressure: 'Time-pressure mistakes',
  opening: 'Opening mistakes',
  middlegame: 'Middlegame mistakes',
  endgame: 'Endgame mistakes',
}

export const MOTIF_LABELS: Record<string, string> = {
  mate: 'Mate allowed',
  fork: 'Fork allowed',
  pin: 'Pin allowed',
  skewer: 'Skewer allowed',
}

export const PHASE_LABELS: Record<string, string> = {
  opening: 'Opening',
  middlegame: 'Middlegame',
  endgame: 'Endgame',
}

export const SEVERITY_ORDER: string[] = ['blunder', 'mistake', 'inaccuracy']

export const PATTERN_KIND_LABELS: Record<string, string> = {
  category: 'Mistake type',
  severity: 'Severity',
  phase: 'Game phase',
  color: 'Colour played',
  opening: 'Opening',
  move_bucket: 'Move number',
  hung_piece: 'Piece left loose',
  motif: 'Tactic handed over',
}

export function categoryLabel(key: string): string {
  return CATEGORY_LABELS[key] || key
}

export function motifLabel(key: string): string {
  return MOTIF_LABELS[key] || key
}

export function phaseLabel(key: string): string {
  return PHASE_LABELS[key] || key
}

export function titleCase(value: string): string {
  if (!value) return value
  return value.charAt(0).toUpperCase() + value.slice(1)
}
