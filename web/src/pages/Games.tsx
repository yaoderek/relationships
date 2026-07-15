import { useEffect, useState } from "react";
import {
  fetchFinishConvo, fetchWhichGroupChat, fetchWhoSaidIt, fetchWhoSaysItMore,
} from "../api";
import type {
  FinishConvoRound, GameMessage, WhichGroupChatRound, WhoSaidItRound,
  WhoSaysItMoreRound,
} from "../api";
import Dropdown from "../components/Dropdown";

type GameId = "who-said-it" | "finish-the-convo" | "which-group-chat"
  | "who-says-it-more";

const GAMES: { id: GameId; label: string }[] = [
  { id: "who-said-it", label: "Who Said It" },
  { id: "finish-the-convo", label: "Finish the Convo" },
  { id: "which-group-chat", label: "Which Group Chat" },
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

function Bubble({ m, gap, name }: {
  m: GameMessage; gap: number; name?: string;
}) {
  return (
    <div style={{ marginBottom: gap }}>
      {name && (
        <div style={{ fontSize: 11, opacity: 0.55, margin: "0 0 2px 12px" }}>
          {name}
        </div>
      )}
      <div style={{ display: "flex",
                    justifyContent: m.is_from_me ? "flex-end" : "flex-start" }}>
        <div className={`bubble ${m.is_from_me ? "bubble-me" : "bubble-them"}`}>
          {m.text}
        </div>
      </div>
    </div>
  );
}

// iMessage-style rhythm: same sender stays tight, sender change gets air.
// When senderName is given, it is shown above the first bubble of each of
// the other person's runs, iOS style.
function Bubbles({ messages, senderName }: {
  messages: GameMessage[]; senderName?: string;
}) {
  return (
    <>
      {messages.map((m, i) => {
        const prev = messages[i - 1];
        const next = messages[i + 1];
        const gap = next && next.is_from_me === m.is_from_me ? 3 : 10;
        const name = !m.is_from_me && senderName
          && (!prev || prev.is_from_me) ? senderName : undefined;
        return <Bubble key={i} m={m} gap={gap} name={name} />;
      })}
    </>
  );
}

const NO_DATA = <p>Not enough message history for this game.</p>;
const LOADING = <p>Loading round…</p>;

function NextButton({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="next-round" style={{
      display: "inline-flex", alignItems: "center", gap: 8, marginTop: 4,
      padding: "6px 14px", fontSize: 13, font: "inherit", fontWeight: 500,
      border: "1px solid rgba(128,128,128,0.35)", borderRadius: 8,
      background: "transparent", color: "inherit",
    }}>
      Next round
      <span aria-hidden style={{ fontSize: 12, opacity: 0.6 }}>→</span>
    </button>
  );
}

type ChoiceState = "idle" | "correct" | "wrong" | "dim";

function choiceStyle(state: ChoiceState) {
  return {
    display: "block", width: "100%", textAlign: "left" as const,
    padding: "8px 12px", marginBottom: 8, borderRadius: 8, font: "inherit",
    border: "1px solid rgba(128,128,128,0.35)", color: "inherit",
    cursor: state === "idle" ? "pointer" : "default",
    background: state === "correct" ? "rgba(46,204,64,0.25)"
      : state === "wrong" ? "rgba(255,65,54,0.25)" : "transparent",
    opacity: state === "dim" ? 0.55 : 1,
    transition: "background 0.25s ease, opacity 0.25s ease",
  };
}

function choiceClass(state: ChoiceState) {
  if (state === "correct") return "choice-correct";
  if (state === "wrong") return "choice-wrong";
  return "";
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
    <div className="game-round">
      <p>Who are you texting with here?</p>
      <div style={{ margin: "16px 0" }}>
        <Bubbles messages={round.messages} />
      </div>
      {round.choices.map((c) => {
        const state: ChoiceState = picked === null ? "idle"
          : c.person_id === round.answer_person_id ? "correct"
          : c.person_id === picked ? "wrong" : "dim";
        return (
          <button key={c.person_id} style={choiceStyle(state)}
                  className={choiceClass(state)}
                  onClick={() => pick(c.person_id)}>
            {c.display_name}
          </button>
        );
      })}
      {picked !== null && (
        <div className="game-reveal" style={{ marginTop: 12 }}>
          <p>It was <b>{answer?.display_name}</b> — {round.date}.</p>
          <NextButton onClick={next} />
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
    <div className="game-round">
      <p>What did you actually say next?</p>
      <div style={{ margin: "16px 0" }}>
        <Bubbles messages={round.context} senderName={round.person_name} />
      </div>
      {round.options.map((o, i) => {
        const state: ChoiceState = picked === null ? "idle"
          : i === round.answer_index ? "correct"
          : i === picked ? "wrong" : "dim";
        return (
          <button key={i} style={choiceStyle(state)}
                  className={choiceClass(state)} onClick={() => pick(i)}>
            {o}
          </button>
        );
      })}
      {picked !== null && (
        <div className="game-reveal" style={{ marginTop: 12 }}>
          <p>That was <b>{round.person_name}</b> — {round.date}.
             {round.aftermath.length > 0 && " And then:"}</p>
          <Bubbles messages={round.aftermath}
                   senderName={round.person_name} />
          <NextButton onClick={next} />
        </div>
      )}
    </div>
  );
}

function WhichGroupChat({ onResult }: { onResult: (ok: boolean) => void }) {
  const { round, next } = useRound<WhichGroupChatRound>(fetchWhichGroupChat);
  const [picked, setPicked] = useState<number | null>(null);
  useEffect(() => setPicked(null), [round]);
  if (round === undefined) return LOADING;
  if (round === null) return NO_DATA;
  const pick = (id: number) => {
    if (picked !== null) return;
    setPicked(id);
    onResult(id === round.answer_chat_id);
  };
  const answer = round.choices.find(
    (c) => c.chat_id === round.answer_chat_id);
  return (
    <div className="game-round">
      <p>Which group chat is this from?</p>
      <div style={{ margin: "16px 0" }}>
        <Bubbles messages={round.messages} />
      </div>
      {round.choices.map((c) => {
        const state: ChoiceState = picked === null ? "idle"
          : c.chat_id === round.answer_chat_id ? "correct"
          : c.chat_id === picked ? "wrong" : "dim";
        return (
          <button key={c.chat_id} style={choiceStyle(state)}
                  className={choiceClass(state)}
                  onClick={() => pick(c.chat_id)}>
            {c.name}
          </button>
        );
      })}
      {picked !== null && (
        <div className="game-reveal" style={{ marginTop: 12 }}>
          <p>It was <b>{answer?.name}</b> — {round.date}.</p>
          <NextButton onClick={next} />
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
    <div className="game-round">
      <p>Who says this more (per 1,000 texts)?</p>
      <p style={{ fontSize: 32, fontWeight: 700, margin: "16px 0" }}>
        “{round.word}”
      </p>
      {round.choices.map((c) => {
        const state: ChoiceState = picked === null ? "idle"
          : c.person_id === round.answer_person_id ? "correct"
          : c.person_id === picked ? "wrong" : "dim";
        return (
          <button key={c.person_id} style={choiceStyle(state)}
                  className={choiceClass(state)}
                  onClick={() => pick(c.person_id)}>
            {c.display_name}
            {picked !== null &&
              ` — ${c.count} times (${c.per_1k}/1k texts)`}
          </button>
        );
      })}
      {picked !== null && (
        <div className="game-reveal" style={{ marginTop: 12 }}>
          <NextButton onClick={next} />
        </div>
      )}
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
        <Dropdown
          value={game}
          options={GAMES.map((g) => ({ value: g.id, label: g.label }))}
          onChange={(v) => switchGame(v as GameId)}
        />
        <span>
          Score: {score.correct}/{score.played} · Streak: {score.streak}
        </span>
      </div>
      <div style={{ maxWidth: 560 }}>
        {game === "who-said-it" && <WhoSaidIt onResult={onResult} />}
        {game === "finish-the-convo" && <FinishConvo onResult={onResult} />}
        {game === "which-group-chat" && <WhichGroupChat onResult={onResult} />}
        {game === "who-says-it-more" && <WhoSaysItMore onResult={onResult} />}
      </div>
    </>
  );
}
