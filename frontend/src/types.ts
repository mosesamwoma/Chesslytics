export type Side = 'white' | 'black'
export type Severity = 'inaccuracy' | 'mistake' | 'blunder'

export interface AuthInfo {
  registration_enabled: boolean
  min_password_length: number
  email_enabled: boolean
}

export interface User {
  id: number
  username: string
  role: string
  is_admin: boolean
  is_active: boolean
  created_at: string | null
  last_login_at: string | null
  email_verified: boolean
  digest_enabled: boolean
  has_recovery_code: boolean
  email?: string | null
}

export interface UserEnvelope {
  user: User
}

export interface RegisterResult extends UserEnvelope {
  recovery_code: string
}

export interface RecoveryResult {
  recovery_code: string
  user?: User
}

export interface Game {
  id: number
  fingerprint: string
  white: string
  black: string
  result: string
  date: string | null
  event: string | null
  eco: string | null
  opening: string | null
  variation: string | null
  time_control: string | null
  white_elo: number | null
  black_elo: number | null
  source: string | null
  analyzed: boolean
  analyzed_at: string | null
  analyzed_depth: number | null
  move_count: number
  mistake_count: number
  accuracy: Accuracy
  notes: string | null
  tags: string[]
}

export interface Accuracy {
  white: number | null
  black: number | null
}

export interface GamesPage {
  total: number
  limit: number
  offset: number
  player: string | null
  games: Game[]
}

export interface GameFilters {
  q?: string
  result?: string
  analyzed?: string
  opening?: string
  color?: string
  tag?: string
  sort?: string
}

export interface TagCount {
  tag: string
  count: number
}

export interface ImportOptions {
  source: 'chesscom' | 'lichess'
  username: string
  max_games: number
  months: number
}

export interface Move {
  ply: number
  move_number: number
  color: Side
  san: string | null
  uci: string | null
  fen_before: string | null
  fen_after: string | null
  eval_before_cp: number | null
  eval_after_cp: number | null
  eval_before_mate: number | null
  eval_after_mate: number | null
  loss_cp: number | null
  winpct_before: number | null
  winpct_after: number | null
  best_move_uci: string | null
  best_move_san: string | null
  depth_reached: number | null
  phase: string | null
  clock_before: number | null
  clock_after: number | null
}

export interface Motif {
  kind: string
  detail?: string | null
}

export interface HungPiece {
  square?: string
  name?: string
  piece?: string
  see_pawns?: number | null
  exchange?: string[]
}

export interface TacticEntry {
  kind: string
  detail: string
  move: string | null
  squares: string[]
}

export interface LineInfo {
  outcome: string
  mate_in: number | null
  gain_cp: number
  san: string[]
  themes: string[]
  squares: string[]
}

export interface ForcedMate {
  for: 'mover' | 'opponent'
  in: number
  san: string[]
}

export interface Tactics {
  heuristic: boolean
  themes: string[]
  missed: TacticEntry[]
  allowed: TacticEntry[]
  line: LineInfo | null
  forced_mate: ForcedMate | null
  exchange: string | null
  squares: string[]
  failed?: boolean
}

export interface MistakeFacts {
  motifs_allowed?: Motif[]
  hung_piece?: HungPiece | null
  best_line?: string[]
  tactics?: Tactics
  player_elo?: number | null
  rating_scale?: number
}

export interface Mistake {
  id: number
  game_id: number
  ply: number
  move_number: number
  color: Side
  player: string | null
  opponent: string | null
  played_move: string | null
  played_uci: string | null
  best_move: string | null
  best_move_uci: string | null
  fen: string | null
  fen_after: string | null
  eval_before: number | null
  eval_after: number | null
  loss: number
  loss_cp: number
  winpct_before: number
  winpct_after: number
  severity: Severity
  category: string
  category_basis: string | null
  phase: string
  opening: string | null
  in_time_pressure: boolean
  time_remaining: number | null
  game_decided: boolean
  in_book: boolean | null
  book_move: string | null
  verified_by: string | null
  verified_loss: number | null
  agreed: boolean | null
  facts: MistakeFacts | null
}

export interface GameDetail extends Game {
  moves: Move[]
  mistakes: Mistake[]
}

export interface JobSummary {
  games_analyzed: number
  mistakes: number
  moves_scored: number
  player_not_found?: boolean
}

export interface JobOptions {
  player?: string | null
  color?: string
  limit_kind?: string
  limit_value?: number
  min_loss?: number
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'

export interface Job {
  id: number
  status: JobStatus
  duration_seconds: number | null
  options: JobOptions | null
  total_games: number
  done_games: number
  message: string | null
  summary: JobSummary | null
  error: string | null
  cancel_requested: boolean
  created_at: string | null
  started_at: string | null
  finished_at: string | null
}

export interface JobEnvelope {
  job: Job
}

export interface JobsPage {
  total: number
  limit: number
  offset: number
  jobs: Job[]
}

export interface AnalysisOptions {
  game_ids?: number[]
  player?: string
  color?: Side | 'both'
  depth?: number
  time_limit?: number
  min_loss?: number
  update_profile?: boolean
  rating_aware?: boolean
}

export interface UploadOptions {
  player?: string
  color?: string
  depth?: number
  min_loss?: number
  ignore_decided?: boolean
  rating_aware?: boolean
}

export interface UploadSummary {
  uploaded: string
  parsed: number
  stored: number
  skipped: number
  errors: string[]
  job: Job | null
  job_error: string | null
}

export interface CountRow {
  key: string
  count: number
  games?: number
}

export interface Overview {
  games: number
  games_analyzed: number
  mistakes: number
  average_loss: number
  time_pressure_mistakes: number
  by_category: CountRow[]
  by_phase: CountRow[]
  by_severity: CountRow[]
  top_openings: CountRow[]
}

export interface LabelledCount {
  label: string
  count: number
  games?: number
}

export interface ProfileBody {
  average_loss?: number
  games_analyzed?: number
  games_with_clock?: number
  most_problematic_phase?: { phase: string } | null
  time_pressure?: {
    count?: number
    share?: number
    threshold_seconds?: number
  }
  tactical_weaknesses?: LabelledCount[]
  most_common_categories?: LabelledCount[]
  phase_breakdown?: { phase: string; count: number; games?: number }[]
  severity_breakdown?: { severity: string; count: number }[]
  average_loss_by_phase?: { phase: string; count: number; average_loss: number }[]
  opening_patterns?: { opening: string; count: number; games: number }[]
  observations?: string[]
}

export interface ProfileResponse {
  player: string | null
  color: string
  games_analyzed: number
  moves_scored: number
  moves_failed: number
  mistake_count: number
  engine: string | null
  profile: ProfileBody | null
}

export interface ProgressWeek {
  week_start: string
  games: number
  moves: number
  mistakes: number
  mistakes_per_100: number | null
  average_loss: number | null
}

export interface TrendSide {
  average_loss: number
  mistakes_per_100: number
}

export interface Progress {
  player: string | null
  weeks: ProgressWeek[]
  trend: { weeks: number; recent: TrendSide; earlier: TrendSide } | null
}

export interface OpeningRow {
  opening: string
  eco: string | null
  games: number
  win_rate: number | null
  wins: number
  draws: number
  losses: number
  average_loss: number | null
  mistakes_per_game: number
  as_white: number
  as_black: number
  worst_move: number | null
  worst_move_mistakes: number
  mistakes: number
  top_category: string | null
  [key: string]: string | number | null
}

export interface OpeningsReport {
  player: string | null
  openings: OpeningRow[]
}

export interface Pattern {
  kind: string
  key: string
  count: number
  games: number
  recurring: boolean
  description: string | null
}

export interface PatternsResponse {
  patterns: Pattern[]
}

export interface Review {
  status: string
  box: number
  due: boolean
  due_at: string | null
}

export interface Puzzle {
  id: number
  game_id: number
  move_number: number
  color: Side
  orientation?: Side
  player: string | null
  fen: string
  legal_moves: string[]
  severity: Severity
  category: string
  loss: number
  phase: string
  opening: string | null
  in_book: boolean | null
  attempts: number
  solved: boolean
  themes: string[]
  review: Review | null
}

export interface PuzzlePage {
  total: number
  tolerance_winpct?: number
  puzzles: Puzzle[]
}

export interface ActivityDay {
  date: string
  count: number
  met: boolean
}

export interface Activity {
  daily_goal: number
  today: number
  goal_met: boolean
  current_streak: number
  longest_streak: number
  week: ActivityDay[]
}

export interface TrainingStats {
  activity: Activity
  due_now: number
  new_puzzles: number
  mastered: number
  puzzles_available: number
  attempts: number
  correct: number
  accuracy: number
  weakest_category: { category: string } | null
  by_category?: { category: string; correct: number; attempts: number; accuracy: number }[]
}

export interface AttemptResult {
  correct: boolean
  verdict: string
  played_uci: string
  played_san?: string | null
  best_move?: string | null
  best_move_uci?: string | null
  loss_vs_best?: number | null
  graded_by?: string | null
  category_basis?: string | null
  notes?: string[] | null
  fen_after: string
  attempts?: { attempts: number }
  review?: Review | null
  line?: LineStep | null
}

export interface LineStep {
  done: boolean
  step: number
  total: number
  opponent_uci: string
  opponent_san: string
  fen: string
  legal_moves: string[]
}

export interface LineResult {
  correct: boolean
  done: boolean
  step: number
  total: number
  played_san: string
  fen: string
  legal_moves?: string[]
  opponent_uci?: string
  opponent_san?: string
  expected_uci?: string
  expected_san?: string
}

export interface Solution {
  fen: string
  best_move?: string | null
  best_move_uci?: string | null
  played_move?: string | null
  book_move?: string | null
  category_basis?: string | null
  best_line_san?: string[]
  facts?: MistakeFacts | null
}

export interface CoachSection {
  title: string
  body: string
}

export interface CoachInsight {
  player: string | null
  model: string
  summary: string
  focus_drill: string
  sections: CoachSection[] | null
}

export interface TimeControlRow {
  key: string
  games: number
  moves: number
  mistakes: number
  mistakes_per_100: number | null
  average_loss: number | null
  win_rate: number | null
  top_category: string | null
}

export interface TimeControlReport {
  player: string | null
  time_controls: TimeControlRow[]
}

export interface EmailStatus {
  enabled: boolean
  provider: string
  from: string | null
  public_url: string | null
  missing: string[]
}

export interface AdminUser {
  id: number
  username: string
  is_admin: boolean
  is_active: boolean
  locked: boolean
  games: number
  mistakes: number
  last_login_at: string | null
}

export interface AdminUsersPage {
  total: number
  limit: number
  offset: number
  users: AdminUser[]
}

export interface AdminStats {
  users: number
  active_users: number
  admins: number
  active_users_24h: number
  new_users_7d: number
  games: number
  games_analyzed: number
  jobs_running: number
  jobs_queued: number
}

export interface AuditEvent {
  id: number
  created_at: string | null
  actor: string | null
  action: string
  detail: string | null
  target: string | null
  ip: string | null
}

export interface ResetLink {
  path: string
  expires_in: number
}

export interface RestoreResult {
  games_restored: number
  mistakes_restored: number
  attempts_restored: number
  games_already_present?: number
  games_unreadable?: number
}

export interface ThemeCount {
  theme: string
  count: number
}

export interface LibraryTheme {
  theme: string
  lichess: string
  available: number
  mistakes?: number
}

export interface LibraryStatus {
  count: number
  themes: LibraryTheme[]
  recommended: LibraryTheme[]
}

export interface LibraryPuzzle {
  id: number
  source_id: string
  rating: number
  themes: string[]
  fen: string
  orientation: Side
  legal_moves: string[]
  opponent_uci: string
  opponent_san: string
  step: number
  total: number
}

export interface LibraryMoveResult {
  correct: boolean
  done: boolean
  step: number
  total: number
  played_san: string
  opponent_uci?: string
  opponent_san?: string
  fen?: string
  legal_moves?: string[]
}

export interface LibrarySolution {
  id: number
  san: string[]
  opponent_first: string
}

export interface BlindSpotInsight {
  kind: 'theme_piece' | 'theme_region' | 'piece'
  theme?: string
  piece?: string
  region?: string
  count: number
}

export interface BlindSpots {
  player: string | null
  total: number
  themes: ThemeCount[]
  pieces: { piece: string; count: number }[]
  regions: { region: string; count: number }[]
  loose_squares: number[]
  landing_squares: number[]
  insights: BlindSpotInsight[]
}
