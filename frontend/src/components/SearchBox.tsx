"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { normalizeQuery, qk, searchPlayers, type PlayerHit } from "@/lib/api";
import { PlayerAvatar } from "@/components/ui/Media";
import { teamColor } from "@/lib/constants";
import { useRecentPlayers } from "@/lib/local";

const DEBOUNCE_MS = 300; // BO-CM-01 검색 결과 레이어 (설계 9장)

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

const CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ";
const choOf = (ch: string) => {
  const c = ch.charCodeAt(0) - 0xac00;
  return c >= 0 && c <= 11171 ? CHO[Math.floor(c / 588)] : ch;
};

/** 이름에서 검색어와 맞는 글자를 굵게 — 초성(ㄱㄷㅇ)이면 초성이 이어서 맞는 자리, 아니면 그대로 들어 있는 자리. 옛 이름으로 찾은 것은 그대로 */
function Marked({ name, q }: { name: string; q: string }) {
  const chars = [...name];
  const pos = chars.flatMap((c, i) => (c === " " ? [] : [i])); // 띄어쓰기를 뺀 글자의 원래 자리 (「코엔 윈」 ↔ 「ㅋㅇㅇ」)
  const bare = pos.map((i) => chars[i]);
  const cho = /^[ㄱ-ㅎ]+$/.test(q);
  const at = cho ? bare.map(choOf).join("").indexOf(q) : bare.join("").indexOf(q);
  if (!q || at < 0) return <>{name}</>;
  const from = pos[at], to = pos[at + q.length - 1] + 1;
  return <>{chars.slice(0, from).join("")}<b className="font-extrabold">{chars.slice(from, to).join("")}</b>{chars.slice(to).join("")}</>;
}

export const playerHref = (id: string, extra: Record<string, string> = {}) =>
  `/players/?${new URLSearchParams({ id, ...extra })}`;

export default function SearchBox({
  autoFocus = false,
  large = false,
  onSelect,
  placeholder = "선수 이름이나 초성 (예: ㄱㄷㅇ)",
  disabled = false,
}: {
  autoFocus?: boolean;
  large?: boolean;
  /** 주면 고른 선수를 넘겨받고(비교 탭에 추가), 없으면 그 선수 화면으로 이동 */
  onSelect?: (p: PlayerHit) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const router = useRouter();
  const recent = useRecentPlayers();
  const listId = useId();
  const boxRef = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);

  const q = useDebounced(normalizeQuery(text), DEBOUNCE_MS);
  const { data, isFetching, isError } = useQuery({
    queryKey: qk.search(q),
    queryFn: ({ signal }) => searchPlayers(q, signal),
    enabled: q.length > 0,
    placeholderData: keepPreviousData,
  });
  const hits = q.length > 0 ? (data ?? []) : [];
  const pending = normalizeQuery(text) !== q || isFetching;

  // 레이어 바깥을 누르면 닫는다
  useEffect(() => {
    const onDown = (e: PointerEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onDown);
    return () => document.removeEventListener("pointerdown", onDown);
  }, []);

  const go = (p: PlayerHit) => {
    setOpen(false);
    setText("");
    if (onSelect) onSelect(p);
    else router.push(playerHref(p.player_id));
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.nativeEvent.isComposing) return; // 한글 조합 중 Enter·화살표는 IME 몫 (조합 전 결과로 이동하지 않게)
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      const p = hits[active >= 0 ? active : 0];
      if (p) go(p);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const showLayer = open && normalizeQuery(text).length > 0;

  return (
    <div ref={boxRef} className="relative">
      <input
        type="search"
        role="combobox"
        aria-expanded={showLayer}
        aria-controls={listId}
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        autoFocus={autoFocus}
        value={text}
        maxLength={30}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          setActive(-1);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        className={`w-full border outline-none focus:border-bar ${
          large
            ? "h-[60px] rounded-[18px] border-[#b4b5ba] bg-white pl-14 pr-4 text-[17px] shadow-[0_4px_16px_rgba(0,0,0,0.06)]"
            : "rounded-lg border-line bg-surface px-3 py-1.5 text-sm"
        }`}
      />
      {large && (
        <svg viewBox="0 0 24 24" className="pointer-events-none absolute top-[18px] left-5 h-6 w-6 text-fg-2" aria-hidden>
          <circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="m15.5 15.5 4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      )}

      {showLayer && (
        <ul
          id={listId}
          role="listbox"
          className="absolute inset-x-0 top-full z-30 mt-1 max-h-96 animate-rise overflow-y-auto rounded-lg border border-line bg-surface py-1 shadow-lg"
        >
          {hits.map((p, i) => (
            <li
              key={p.player_id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onPointerEnter={() => setActive(i)}
              onClick={() => go(p)}
              className={`flex cursor-pointer items-center gap-3 px-3 py-2 text-sm ${i === active ? "bg-bg" : ""}`}
            >
              <span className="h-6 w-1 shrink-0 rounded-full" style={{ background: teamColor(p.team) }} />
              <span className="font-medium"><Marked name={p.name} q={q} /></span>
              {p.former_names.length > 0 && (
                <span className="text-xs text-fg-2">옛 이름 <Marked name={p.former_names.join(" · ")} q={q} /></span>
              )}
              <span className="text-muted">
                {[p.team, p.position, p.bats_throws].filter(Boolean).join(" · ")}
              </span>
              {/* 동명이인: 팀 · 포지션 · 투타까지 같은 경우가 있어 출생 연도 · 등번호도 (FR-01-04) */}
              {p.same_name && (
                <span className="ml-auto flex shrink-0 items-center gap-1.5 text-xs text-fg-2">
                  <span className="rounded-md bg-surface-2 px-1.5 py-0.5 font-semibold">동명이인</span>
                  {[p.birth_year && `${p.birth_year}년생`, p.back_number && `${p.back_number}번`].filter(Boolean).join(" · ")}
                </span>
              )}
            </li>
          ))}
          {hits.length === 0 && (isError || pending ? (
            <li className="px-3 py-2 text-sm text-muted">{isError ? "검색하지 못했어요. 잠시 뒤 다시 시도해 주세요." : "찾는 중…"}</li>
          ) : (
            // 결과 없음 — 찾을 수 있는 범위와 다른 길(초성 · 옛 이름 · 최근 본 선수) (09 「검색 결과가 없을 때」)
            <li className="px-4 py-3.5 text-sm">
              <p className="font-bold">‘{text.trim()}’ 검색 결과가 없어요</p>
              <p className="mt-1 text-fg-2">2024~2026 시즌에 1군 기록이 있는 선수만 찾을 수 있어요.</p>
              <p className="mt-2.5 flex flex-wrap gap-1.5 text-xs text-fg-2">
                <span className="rounded-md bg-surface-2 px-2 py-1">초성으로 · ㄱㄷㅇ</span>
                <span className="rounded-md bg-surface-2 px-2 py-1">옛 이름으로도 찾아요</span>
              </p>
              {!onSelect && recent.length > 0 && (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span className="text-xs text-muted">최근 본 선수</span>
                  {recent.slice(0, 3).map((r) => (
                    <Link key={r.id} href={playerHref(r.id)} onClick={() => setOpen(false)}
                          className="flex h-8 items-center gap-1.5 rounded-full border border-line bg-surface pr-3 pl-1 text-[13px] font-bold hover:bg-surface-2">
                      <PlayerAvatar id={r.id} name={r.name} team={r.team} size={24} /> {r.name}
                    </Link>
                  ))}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
