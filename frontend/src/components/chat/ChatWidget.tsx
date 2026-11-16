"use client";

/**
 * 챗봇 창 — 모든 화면 오른쪽 아래 챗봇 버튼 (layout.tsx에 한 번 넣는다).
 * 서버에 AI 키가 없으면(GET /chat/status의 enabled = false) 버튼을 그리지 않는다.
 * 버튼은 맨 위로(ToTop) 자리에 놓고, 맨 위로는 --chat-fab만큼 위로 올린다 (휴대폰은 아래 탭 위, 경기 상세는 안전 영역 위).
 * 대화는 창을 닫아도 남고(레이아웃이 화면을 바꿔도 유지된다) 새로고침하면 사라진다.
 * 흐름: 질문 → POST /chat → 답(문장 · 조건 · 목록 · ▶) 또는 되묻기(버튼) → 고르면 같은 질문을 고른 값과 함께 다시 보낸다.
 */
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ScenePlayer from "@/components/ScenePlayer";
import type { Clip } from "@/lib/api";
import { getChatStatus, postChat, toClip, type ChatAnswer, type ChatReply, type GameRow, type PaRow } from "@/lib/chat";
import { innings, md, rate3 } from "@/lib/format";

type Msg = { id: number; role: "user" | "bot"; text: string; reply?: ChatReply; ask?: { message: string; resolved: Record<string, unknown> } };

const EXAMPLES = ["김도영 2024 홈런 영상 보여줘", "2024년 김도영이 잠실에서 3루타 친 날", "KIA가 올러 선발일 때 LG 상대로 승률은?", "원태인 2025 시즌 기록"];
const FAB_SPACE = "60px"; // 버튼 48px + 간격 12px — 맨 위로가 이만큼 올라간다
let seq = 0;

export default function ChatWidget() {
  const path = usePathname();
  const noTab = path.startsWith("/games"); // 경기 상세는 아래 탭이 없다 (TabBar · ToTop과 같은 기준)
  const [status, setStatus] = useState<{ enabled: boolean; as_of: string | null } | null>(null);
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [context, setContext] = useState<Record<string, unknown> | null>(null);
  const [playing, setPlaying] = useState<{ clip: Clip; title: string } | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, busy]);
  useEffect(() => { getChatStatus().then(setStatus); }, []);
  useEffect(() => { // 버튼이 있을 때만 맨 위로를 올린다
    if (!status?.enabled) return;
    document.documentElement.style.setProperty("--chat-fab", FAB_SPACE);
    return () => { document.documentElement.style.removeProperty("--chat-fab"); };
  }, [status?.enabled]);

  if (!status?.enabled) return null;

  async function send(message: string, resolved: Record<string, unknown> = {}, shown?: string) {
    if (!message.trim() || busy) return;
    setMsgs((m) => [...m, { id: ++seq, role: "user", text: shown ?? message }]);
    setBusy(true);
    const reply = await postChat({ message, context, resolved }).catch(() => ({ type: "answer", text: "서버에 연결하지 못했어요." }) as ChatReply);
    setBusy(false);
    if (reply.type === "answer" && reply.context) setContext(reply.context);
    setMsgs((m) => [...m, { id: ++seq, role: "bot", text: reply.text, reply, ask: reply.type === "clarify" ? { message, resolved } : undefined }]);
  }

  return (
    <>
      {open && (
        <section aria-label="BASE:ON 챗봇"
          className="fixed inset-x-0 bottom-0 z-50 flex h-[85dvh] flex-col overflow-hidden rounded-t-3xl border border-line bg-surface pb-[env(safe-area-inset-bottom)] shadow-2xl md:inset-x-auto md:bottom-8 md:right-8 md:h-[min(620px,calc(100dvh-4rem))] md:w-[400px] md:rounded-3xl md:pb-0">
          <header className="flex items-center justify-between border-b border-line px-5 py-3">
            <p className="font-bold">BASE:ON 챗봇 {status.as_of && <span className="ml-1 text-xs font-medium text-muted">{md(status.as_of)} 기준</span>}</p>
            <div className="flex gap-3 text-xs font-bold text-fg-2">
              {msgs.length > 0 && <button onClick={() => { setMsgs([]); setContext(null); setPlaying(null); }} className="hover:underline">새 대화</button>}
              <button onClick={() => setOpen(false)} aria-label="챗봇 닫기" className="text-base">✕</button>
            </div>
          </header>

          {playing && (
            <div className="bg-night p-3 text-white">
              <div className="aspect-video w-full overflow-hidden rounded-xl"><ScenePlayer bare clip={playing.clip} label={playing.title} /></div>
              <div className="mt-2 flex items-center justify-between gap-2 text-xs">
                <span className="truncate font-bold">{playing.title}</span>
                <button onClick={() => setPlaying(null)} className="shrink-0 text-[#d3d4d8] hover:underline">닫기</button>
              </div>
            </div>
          )}

          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {msgs.length === 0 && (
              <div className="text-sm text-fg-2">
                <p className="mb-3">선수 기록이나 장면을 물어보세요.</p>
                <div className="flex flex-col gap-2">
                  {EXAMPLES.map((q) => (
                    <button key={q} onClick={() => send(q)} className="rounded-xl bg-surface-2 px-3 py-2 text-left hover:bg-surface-3">{q}</button>
                  ))}
                </div>
              </div>
            )}
            {msgs.map((m) => m.role === "user" ? (
              <p key={m.id} className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-brand px-3 py-2 text-sm text-white">{m.text}</p>
            ) : (
              <BotBubble key={m.id} m={m} onPlay={setPlaying}
                onPick={(o) => m.ask && send(m.ask.message, { ...m.ask.resolved, [(m.reply as { slot: string }).slot]: o.value }, o.label)} />
            ))}
            {busy && <p className="w-fit rounded-2xl bg-surface-2 px-3 py-2 text-sm text-muted">찾는 중…</p>}
            <div ref={endRef} />
          </div>

          <form onSubmit={(e) => { e.preventDefault(); const q = input; setInput(""); send(q); }} className="flex gap-2 border-t border-line p-3">
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="예: 김도영 2024 잠실 3루타" maxLength={300}
              className="min-w-0 flex-1 rounded-full bg-surface-2 px-4 py-2 text-sm outline-none focus:ring-2 focus:ring-brand" aria-label="질문" />
            <button disabled={busy || !input.trim()} className="rounded-full bg-brand px-4 text-sm font-bold text-white disabled:opacity-40">보내기</button>
          </form>
        </section>
      )}

      {!open && (
        <button onClick={() => setOpen(true)} aria-label="챗봇 열기"
          className={`fixed right-4 z-20 flex h-12 w-12 items-center justify-center rounded-full bg-brand text-white shadow-md hover:brightness-110 md:right-8 md:bottom-8 ${
            noTab ? "bottom-[calc(16px+env(safe-area-inset-bottom))]" : "bottom-[calc(3.5rem+1px+12px+env(safe-area-inset-bottom))]"
          }`}>
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M5 18.5V7a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3H8.5z" />
            <path d="M9 10h6M9 13h3.5" />
          </svg>
        </button>
      )}
    </>
  );
}

function BotBubble({ m, onPlay, onPick }: { m: Msg; onPlay: (p: { clip: Clip; title: string }) => void; onPick: (o: { value: string | number; label: string }) => void }) {
  const r = m.reply;
  return (
    <div className="max-w-[92%] space-y-2 rounded-2xl rounded-bl-md bg-surface-2 px-3 py-2 text-sm">
      <p className="whitespace-pre-line">{m.text}</p>
      {r?.type === "clarify" && (
        <div className="flex flex-wrap gap-2">
          {r.options.map((o) => (
            <button key={String(o.value)} onClick={() => onPick(o)} className="rounded-full border border-line-strong bg-surface px-3 py-1 text-xs font-bold hover:border-brand">{o.label}</button>
          ))}
        </div>
      )}
      {r?.type === "answer" && <Answer r={r} onPlay={onPlay} />}
    </div>
  );
}

function Answer({ r, onPlay }: { r: ChatAnswer; onPlay: (p: { clip: Clip; title: string }) => void }) {
  return (
    <>
      {!!r.conditions?.length && <p className="text-xs text-muted">🔍 {r.conditions.join(" · ")}</p>}
      {r.note && <p className="text-xs text-[#a05a00]">※ {r.note}</p>}
      {r.record && !r.text.includes("승률") && ( /* 답 문장에 이미 있으면 다시 쓰지 않는다 (승 · 패만 거른 질문일 때 전체 성적) */
        <p className="text-xs font-bold">{r.record.win}승 {r.record.loss}패{r.record.draw ? ` ${r.record.draw}무` : ""}
          {r.record.win_pct != null && ` · 승률 ${rate3(r.record.win_pct)}`}</p>
      )}
      {r.menu === "pa" && !!r.rows?.length && (
        <ul className="divide-y divide-line rounded-xl bg-surface">
          {(r.rows as PaRow[]).map((p) => (
            <li key={p.pa_id} className="flex items-center justify-between gap-2 px-3 py-2 text-xs">
              <span><b>{md(p.date)}</b> {p.batter} {p.inning}회{p.inning_half} <b>{p.result}</b> <span className="text-muted">vs {p.pitcher}</span></span>
              {p.video && (
                <button onClick={() => onPlay({ clip: toClip(p.video!), title: `${md(p.date)} ${p.batter} ${p.result}` })}
                  aria-label={`${md(p.date)} ${p.batter} ${p.result} 영상 재생`} className="shrink-0 rounded-md bg-accent px-2 py-0.5 text-white">▶</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {r.menu === "games" && !!r.rows?.length && (
        <ul className="divide-y divide-line rounded-xl bg-surface">
          {(r.rows as GameRow[]).map((g) => (
            <li key={g.game_pk} className="flex justify-between px-3 py-2 text-xs">
              <span><b>{md(g.date)}</b> {g.is_home ? "홈" : "원정"} vs {g.opponent}</span>
              <span>{g.team_score}:{g.opp_score} <b>{g.result}</b></span>
            </li>
          ))}
        </ul>
      )}
      {r.menu === "stats" && <Stats r={r} />}
      {r.menu === "other" && !!r.table?.length && (
        <div className="overflow-x-auto rounded-xl bg-surface">
          <table className="w-full text-xs">
            <thead><tr>{r.columns?.map((c) => <th key={c} className="px-2 py-1 text-left text-muted">{c}</th>)}</tr></thead>
            <tbody>{r.table.map((row, i) => <tr key={i} className="border-t border-line">{row.map((v, j) => <td key={j} className="px-2 py-1">{String(v ?? "")}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
      {r.menu === "games" && r.total != null && r.shown != null && r.total > r.shown && <p className="text-xs text-muted">총 {r.total}개 중 최근 {r.shown}개</p>}
    </>
  );
}

const BAT: [string, string, (v: number) => string][] = [
  ["avg", "타율", rate3], ["hr", "홈런", String], ["h", "안타", String], ["ops", "OPS", rate3],
  ["obp", "출루율", rate3], ["slg", "장타율", rate3], ["pa", "타석", String], ["so", "삼진", String],
];
const PIT: [string, string, (v: number) => string][] = [
  ["g", "경기", String], ["gs", "선발", String], ["outs", "이닝", innings], ["whip", "WHIP", (v) => v.toFixed(2)],
  ["so", "삼진", String], ["bb", "볼넷", String], ["hr", "피홈런", String], ["avg", "피안타율", rate3],
];

function Stats({ r }: { r: ChatAnswer }) {
  const blocks = [["타격", r.batting, BAT], ["투구", r.pitching, PIT]] as const;
  return (
    <>
      {blocks.map(([title, s, keys]) => s && (
        <div key={title} className="rounded-xl bg-surface p-2">
          <p className="mb-1 text-xs font-bold">{r.name} {r.season} {title}</p>
          <div className="grid grid-cols-4 gap-1 text-center text-xs">
            {keys.filter(([k]) => typeof s[k] === "number").map(([k, label, f]) => (
              <div key={k}><p className="text-muted">{label}</p><p className="font-bold">{f(s[k] as number)}</p></div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
}
