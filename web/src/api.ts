export type Bucket = "day" | "week" | "month";
export type PersonSummary = {
  person_id: number; display_name: string; total: number;
  sent: number; received: number; first_ts: string; last_ts: string;
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
  top_emojis_me: EmojiCount[]; top_emojis_them: EmojiCount[];
  tapbacks_from_them: TapbackCount[]; tapbacks_from_me: TapbackCount[];
};
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

export const fetchPersons = () => get<PersonSummary[]>("/api/persons");
export const fetchOverviewSeries = (bucket: Bucket) =>
  get<SeriesPoint[]>(`/api/overview/timeseries?bucket=${bucket}`);
export const fetchPersonSeries = (id: number, bucket: Bucket, includeGroups = false) =>
  get<SeriesPoint[]>(
    `/api/persons/${id}/timeseries?bucket=${bucket}&include_groups=${includeGroups}`);
export const fetchPersonStats = (id: number) =>
  get<PersonStats>(`/api/persons/${id}/stats`);
export const fetchPersonHeatmap = (id: number) =>
  get<HeatCell[]>(`/api/persons/${id}/heatmap`);
export const fetchCompare = (ids: number[], bucket: Bucket) =>
  get<CompareSeries[]>(`/api/compare?ids=${ids.join(",")}&bucket=${bucket}`);
export const fetchGroups = () => get<GroupSummary[]>("/api/groups");
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
