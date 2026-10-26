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
  discovered_attack: 'Discovered attack allowed',
  trapped_piece: 'Trapped piece',
  back_rank_weakness: 'Back-rank weakness',
  promotion: 'Promotion allowed',
  passed_pawn: 'Passed pawn',
  overloaded_defender: 'Overloaded defender',
  remove_defender: 'Remove the defender',
}

export const THEME_LABELS: Record<string, string> = {
  mate: 'Checkmate',
  back_rank: 'Back rank',
  fork: 'Fork',
  pin: 'Pin',
  skewer: 'Skewer',
  discovered_attack: 'Discovered attack',
  hanging_piece: 'Hanging piece',
  trapped_piece: 'Trapped piece',
  sacrifice: 'Sacrifice',
  zwischenzug: 'In-between move',
  deflection: 'Deflection',
  remove_defender: 'Remove the defender',
  interference: 'Interference',
  overloaded_defender: 'Overloaded defender',
  promotion: 'Promotion',
  passed_pawn: 'Passed pawn',
  capture_chain: 'Capture sequence',
}

export const THEME_ORDER: string[] = Object.keys(THEME_LABELS)

export const REGION_LABELS: Record<string, string> = {
  queenside: 'queenside',
  center: 'the centre',
  kingside: 'kingside',
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

export function themeLabel(key: string): string {
  return THEME_LABELS[key] || key.replace(/_/g, ' ')
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
