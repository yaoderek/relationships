export type Bucket = "day" | "week" | "month";
export type PersonSummary = {
  person_id: number; display_name: string; total: number;
  sent: number; received: number; first_ts: string; last_ts: string;
  median_response_seconds_me: number | null;
  median_response_seconds_them: number | null;
  initiation_rate_me: number | null;
  avg_session_messages: number | null; avg_session_seconds: number | null;
  ghosts_by_them: number; ghosts_by_me: number;
  avg_reply_block_me: number | null; avg_reply_block_them: number | null;
  double_texts_me: number; double_texts_them: number;
  streak_days: number;
};
export type PersonTrend = {
  bucket: string; sent: number; received: number;
  median_reply_me: number | null; median_reply_them: number | null;
  texts_per_reply_me: number | null; texts_per_reply_them: number | null;
  double_texts_me: number; double_texts_them: number;
  initiation_me: number | null;
};
export type SentenceCount = { text: string; count: number };
export type YouStats = {
  sent_total: number; avg_chars: number | null; emoji_total: number;
  sent_in_groups: number; sent_in_dms: number;
  top_words: WordCount[]; top_sentences: SentenceCount[];
  top_emojis: EmojiCount[]; reactions_given: TapbackCount[];
  heatmap: HeatCell[]; busiest_day: { date: string; count: number } | null;
  avg_texts_per_reply: number | null; double_texts: number;
};
export type SeriesPoint = { bucket: string; sent: number; received: number };
export type HeatCell = { weekday: number; hour: number; count: number };
export type EmojiCount = { emoji: string; count: number };
export type TapbackCount = { kind: string; count: number };
export type PersonStats = {
  person_id: number; display_name: string; total: number; sent: number; received: number;
  median_response_seconds_me: number | null; p90_response_seconds_me: number | null;
  median_response_seconds_them: number | null; p90_response_seconds_them: number | null;
  avg_chars_me: number | null; avg_chars_them: number | null;
  initiation_rate_me: number | null;
  avg_reply_block_me: number | null; avg_reply_block_them: number | null;
  reply_block_ratio: number | null;
  double_texts_me: number; double_texts_them: number;
  ghosts_by_them: number; ghosts_by_me: number;
  avg_session_messages: number | null; avg_session_seconds: number | null;
  top_words_me: WordCount[]; top_words_them: WordCount[];
  top_emojis_me: EmojiCount[]; top_emojis_them: EmojiCount[];
  tapbacks_from_them: TapbackCount[]; tapbacks_from_me: TapbackCount[];
};
export type HotDay = { date: string; count: number; sent: number; received: number };
export type DaySummary = { date: string; summary: string; sentiment: string | null };
export type CompareSeries = {
  person_id: number; display_name: string;
  series: { bucket: string; total: number }[];
};
export type GroupSummary = {
  chat_id: number; name: string; participants: number; total: number;
  my_share: number; first_ts: string; last_ts: string;
};
export type GroupSeriesPoint = { bucket: string; total: number; mine: number };
export type GroupMember = {
  person_id: number | null; display_name: string; count: number;
  share: number; avg_chars: number | null; tapbacks_received: number;
};
export type GroupStats = {
  chat_id: number; name: string; my_share: number; session_count: number;
  busiest_day: { date: string; count: number } | null; members: GroupMember[];
};
export type WordCount = { word: string; count: number };
export type GroupMemberStats = {
  chat_id: number; person_id: number; display_name: string;
  count: number; share: number; avg_chars: number | null;
  sessions_total: number; sessions_participated: number;
  sessions_ghosted: number; sessions_ended: number;
  top_words: WordCount[]; top_emojis: EmojiCount[];
  top_reactions_given: TapbackCount[]; tapbacks_received: number;
};
export type MemberSeriesPoint = { bucket: string; count: number };

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

export const fetchPersons = (days?: number | null) =>
  get<PersonSummary[]>(`/api/persons${days ? `?days=${days}` : ""}`);
export const fetchOverviewSeries = (bucket: Bucket) =>
  get<SeriesPoint[]>(`/api/overview/timeseries?bucket=${bucket}`);
export const fetchPersonSeries = (id: number, bucket: Bucket, includeGroups = false) =>
  get<SeriesPoint[]>(
    `/api/persons/${id}/timeseries?bucket=${bucket}&include_groups=${includeGroups}`);
export const fetchPersonStats = (id: number) =>
  get<PersonStats>(`/api/persons/${id}/stats`);
export const fetchPersonHeatmap = (id: number) =>
  get<HeatCell[]>(`/api/persons/${id}/heatmap`);
export const fetchPersonTrends = (id: number, bucket: Bucket) =>
  get<PersonTrend[]>(`/api/persons/${id}/trends?bucket=${bucket}`);
export const fetchYou = () => get<YouStats>("/api/you");
export type TimelinePoint = {
  bucket: string; person_id: number; display_name: string; count: number;
};
export const fetchPersonsTimeline = () =>
  get<TimelinePoint[]>("/api/persons/timeline");
export const fetchWordContext = (word: string) =>
  get<SentenceCount[]>(`/api/you/word-context?word=${encodeURIComponent(word)}`);
export type VernacularYear = { bucket: string; words: WordCount[] };
export const fetchVernacularTimeline = () =>
  get<VernacularYear[]>("/api/you/vernacular-timeline");
export type CatchphraseYear = { bucket: string; sentences: SentenceCount[] };
export const fetchCatchphrasesTimeline = () =>
  get<CatchphraseYear[]>("/api/you/catchphrases-timeline");
export type CalendarDay = { date: string; count: number };
export const fetchYouCalendar = () => get<CalendarDay[]>("/api/you/calendar");
export type Topic = {
  cluster_id: number; label: string; msg_count: number; share: number;
  people: { name: string; share: number }[];
};
export const fetchTopics = () => get<Topic[]>("/api/language/topics");
export type VoicePoint = {
  person_id: number; name: string; msgs: number;
  divergence: number; mirroring: number;
};
export const fetchVoice = () => get<VoicePoint[]>("/api/language/voice");
export type DriftPoint = { month: string; drift: number | null; novelty: number | null };
export const fetchDrift = () => get<DriftPoint[]>("/api/language/drift");
export type SignatureScope = { scope: string; label: string };
export const fetchSignatureScopes = () =>
  get<SignatureScope[]>("/api/language/scopes");
export type SignaturePhrase = { phrase: string; count: number; score: number };
export const fetchSignature = (scope: string) =>
  get<{ scope: string; phrases: SignaturePhrase[] }>(
    `/api/language/signature?scope=${encodeURIComponent(scope)}`);
export type PersonCluster = {
  cluster_id: number; label: string;
  members: { person_id: number; name: string }[];
};
export const fetchPeopleClusters = () =>
  get<PersonCluster[]>("/api/language/people-clusters");
export type MapPoint = {
  person_id: number; name: string; period: string;
  x: number; y: number; z: number; cluster_id: number; msgs: number;
};
export type PeopleMap = { periods: string[]; points: MapPoint[] };
export const fetchPeopleMap = () => get<PeopleMap>("/api/language/people-map");
export type SearchHit = {
  text: string; total: number; mine: number; similarity: number;
};
export const fetchLanguageSearch = (q: string) =>
  get<SearchHit[]>(`/api/language/search?q=${encodeURIComponent(q)}`);
export type YouHotDay = {
  date: string; count: number; sent: number; top_contact: string | null;
};
export const fetchYouHotDays = () => get<YouHotDay[]>("/api/you/hot-days");
export const fetchHotDays = (id: number) =>
  get<HotDay[]>(`/api/persons/${id}/hot-days`);
export const fetchDaySummary = (id: number, date: string) =>
  get<DaySummary>(`/api/persons/${id}/day-summary?date=${date}`);
export const fetchCompare = (ids: number[], bucket: Bucket) =>
  get<CompareSeries[]>(`/api/compare?ids=${ids.join(",")}&bucket=${bucket}`);
export const fetchGroups = (days?: number | null) =>
  get<GroupSummary[]>(`/api/groups${days ? `?days=${days}` : ""}`);
export const fetchGroupSeries = (id: number, bucket: Bucket) =>
  get<GroupSeriesPoint[]>(`/api/groups/${id}/timeseries?bucket=${bucket}`);
export const fetchGroupHeatmap = (id: number) =>
  get<HeatCell[]>(`/api/groups/${id}/heatmap`);
export const fetchGroupStats = (id: number) => get<GroupStats>(`/api/groups/${id}/stats`);
export const fetchGroupMemberStats = (id: number, personId: number) =>
  get<GroupMemberStats>(`/api/groups/${id}/members/${personId}/stats`);
export const fetchGroupMemberSeries = (id: number, personId: number, bucket: Bucket) =>
  get<MemberSeriesPoint[]>(
    `/api/groups/${id}/members/${personId}/timeseries?bucket=${bucket}`);

export type GameMessage = { text: string; is_from_me: boolean };
export type GameChoice = { person_id: number; display_name: string };
export type WhoSaidItRound = {
  messages: GameMessage[]; choices: GameChoice[];
  answer_person_id: number; date: string;
};
export type FinishConvoRound = {
  context: GameMessage[]; options: string[]; answer_index: number;
  person_name: string; date: string; aftermath: GameMessage[];
};
export type WhoSaysItMoreChoice = {
  person_id: number; display_name: string; count: number; per_1k: number;
};
export type WhoSaysItMoreRound = {
  word: string; choices: WhoSaysItMoreChoice[]; answer_person_id: number;
};

async function getOrNull<T>(url: string): Promise<T | null> {
  const res = await fetch(url);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

export const fetchWhoSaidIt = () =>
  getOrNull<WhoSaidItRound>("/api/games/who-said-it");
export const fetchFinishConvo = () =>
  getOrNull<FinishConvoRound>("/api/games/finish-the-convo");
export const fetchWhoSaysItMore = () =>
  getOrNull<WhoSaysItMoreRound>("/api/games/who-says-it-more");
