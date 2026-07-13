import { useEffect, useState } from "react";
import {
  fetchFinishConvo, fetchWhoSaidIt, fetchWhoSaysItMore,
} from "../api";
import type {
  FinishConvoRound, GameMessage, WhoSaidItRound, WhoSaysItMoreRound,
} from "../api";

type GameId = "who-said-it" | "finish-the-convo" | "who-says-it-more";

const GAMES: { id: GameId; label: string }[] = [
  { id: "who-said-it", label: "Who Said It" },
  { id: "finish-the-convo", label: "Finish the Convo" },
  { id: "who-says-it-more", label: "Who Says It More" },
];

// round semantics: undefined = loading, null = not enough data (404)
function useRound<T>(fetcher: () => Promise<T | null>) {
  const [round, setRound] = useState<T | null | undefined>(undefined);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let alive = true;
    setRound(undefined);
    fetcher().then((r) => { if (alive) setRound(r); }).catch(console.error);
    return () => { alive = false; };
  }, [nonce]);
  return { round, next: () => setNonce((n) => n + 1) };
}

function Bubble({ m }: { m: GameMessage }) {
  return (
    <div style={{ display: "flex",
                  justifyContent: m.is_from_me ? "flex-end" : "flex-start" }}>
      <div style={{
        maxWidth: "70%", padding: "8px 12px", borderRadius: 16, marginBottom: 6,
        background: m.is_from_me ? "#0b93f6" : "#e5e5ea",
        color: m.is_from_me ? "#fff" : "#000",
      }}>{m.text}</div>
    </div>
  );
}

const NO_DATA = <p>Not enough message history for this game.</p>;
const LOADING = <p>Loading round…</p>;

function choiceStyle(state: "idle" | "correct" | "wrong" | "dim") {
  return {
    display: "block", width: "100%", textAlign: "left" as const,
    padding: "8px 12px", marginBottom: 8, borderRadius: 8,
    border: "1px solid #ccc", cursor: state === "idle" ? "pointer" : "default",
    background: state === "correct" ? "#c8f7c5"
      : state === "wrong" ? "#f7c5c5" : "#fff",
    opacity: state === "dim" ? 0.6 : 1,
  };
}

function WhoSaidIt({ onResult }: { onResult: (ok: boolean) => void }) {
  const { round, next } = useRound<WhoSaidItRound>(fetchWhoSaidIt);
  const [picked, setPicked] = useState<number | null>(null);
  useEffect(() => setPicked(null), [round]);
  if (round === undefined) return LOADING;
  if (round === null) return NO_DATA;
  const pick = (id: number) => {
    if (picked !== null) return;
    setPicked(id);
    onResult(id === round.answer_person_id);
  };
  const answer = round.choices.find(
    (c) => c.person_id === round.answer_person_id);
  return (
    <div>
      <p>Who are you texting with here?</p>
      <div style={{ margin: "16px 0" }}>
        {round.messages.map((m, i) => <Bubble key={i} m={m} />)}
      </div>
      {round.choices.map((c) => {
        const state = picked === null ? "idle"
          : c.person_id === round.answer_person_id ? "correct"
          : c.person_id === picked ? "wrong" : "dim";
        return (
          <button key={c.person_id} style={choiceStyle(state)}
                  onClick={() => pick(c.person_id)}>
            {c.display_name}
          </button>
        );
      })}
      {picked !== null && (
        <div style={{ marginTop: 12 }}>
          <p>It was <b>{answer?.display_name}</b> — {round.date}.</p>
          <button onClick={next}>Next round</button>
        </div>
      )}
    </div>
  );
}

function FinishConvo({ onResult }: { onResult: (ok: boolean) => void }) {
  const { round, next } = useRound<FinishConvoRound>(fetchFinishConvo);
  const [picked, setPicked] = useState<number | null>(null);
  useEffect(() => setPicked(null), [round]);
  if (round === undefined) return LOADING;
  if (round === null) return NO_DATA;
  const pick = (i: number) => {
    if (picked !== null) return;
    setPicked(i);
    onResult(i === round.answer_index);
  };
  return (
    <div>
      <p>What did you actually say next?</p>
      <div style={{ margin: "16px 0" }}>
        {round.context.map((m, i) => <Bubble key={i} m={m} />)}
      </div>
      {round.options.map((o, i) => {
        const state = picked === null ? "idle"
          : i === round.answer_index ? "correct"
          : i === picked ? "wrong" : "dim";
        return (
          <button key={i} style={choiceStyle(state)} onClick={() => pick(i)}>
            {o}
          </button>
        );
      })}
      {picked !== null && (
        <div style={{ marginTop: 12 }}>
          <p>That was <b>{round.person_name}</b> — {round.date}.
             {round.aftermath.length > 0 && " And then:"}</p>
          {round.aftermath.map((m, i) => <Bubble key={i} m={m} />)}
          <button onClick={next}>Next round</button>
        </div>
      )}
    </div>
  );
}

function WhoSaysItMore({ onResult }: { onResult: (ok: boolean) => void }) {
  const { round, next } = useRound<WhoSaysItMoreRound>(fetchWhoSaysItMore);
  const [picked, setPicked] = useState<number | null>(null);
  useEffect(() => setPicked(null), [round]);
  if (round === undefined) return LOADING;
  if (round === null) return NO_DATA;
  const pick = (id: number) => {
    if (picked !== null) return;
    setPicked(id);
    onResult(id === round.answer_person_id);
  };
  return (
    <div>
      <p>Who says this more (per 1,000 texts)?</p>
      <p style={{ fontSize: 32, fontWeight: 700, margin: "16px 0" }}>
        “{round.word}”
      </p>
      {round.choices.map((c) => {
        const state = picked === null ? "idle"
          : c.person_id === round.answer_person_id ? "correct"
          : c.person_id === picked ? "wrong" : "dim";
        return (
          <button key={c.person_id} style={choiceStyle(state)}
                  onClick={() => pick(c.person_id)}>
            {c.display_name}
            {picked !== null &&
              ` — ${c.count} times (${c.per_1k}/1k texts)`}
          </button>
        );
      })}
      {picked !== null && <button onClick={next}>Next round</button>}
    </div>
  );
}

export default function Games() {
  const [game, setGame] = useState<GameId>("who-said-it");
  const [score, setScore] = useState({ played: 0, correct: 0, streak: 0 });
  const onResult = (ok: boolean) =>
    setScore((s) => ({
      played: s.played + 1,
      correct: s.correct + (ok ? 1 : 0),
      streak: ok ? s.streak + 1 : 0,
    }));
  const switchGame = (id: GameId) => {
    setGame(id);
    setScore({ played: 0, correct: 0, streak: 0 });
  };
  return (
    <>
      <h1>Games</h1>
      <div style={{ display: "flex", alignItems: "center", gap: 16,
                    marginBottom: 24 }}>
        <select value={game}
                onChange={(e) => switchGame(e.target.value as GameId)}>
          {GAMES.map((g) => (
            <option key={g.id} value={g.id}>{g.label}</option>
          ))}
        </select>
        <span>
          Score: {score.correct}/{score.played} · Streak: {score.streak}
        </span>
      </div>
      <div style={{ maxWidth: 560 }}>
        {game === "who-said-it" && <WhoSaidIt onResult={onResult} />}
        {game === "finish-the-convo" && <FinishConvo onResult={onResult} />}
        {game === "who-says-it-more" && <WhoSaysItMore onResult={onResult} />}
      </div>
    </>
  );
}
