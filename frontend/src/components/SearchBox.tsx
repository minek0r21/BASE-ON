"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { normalizeQuery, qk, searchPlayers, type PlayerHit } from "@/lib/api";
import { teamColor } from "@/lib/constants";

const DEBOUNCE_MS = 300; // BO-CM-01 검색 결과 레이어 (설계 9장)

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
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
        className={`w-full rounded-lg border border-line bg-surface px-3 outline-none focus:border-bar ${
          large ? "py-3 text-lg" : "py-1.5 text-sm"
        }`}
      />

      {showLayer && (
        <ul
          id={listId}
          role="listbox"
          className="absolute inset-x-0 top-full z-30 mt-1 max-h-96 overflow-y-auto rounded-lg border border-line bg-surface py-1 shadow-lg"
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
              <span className="font-semibold">{p.name}</span>
              <span className="text-muted">
                {[p.team, p.position, p.bats_throws].filter(Boolean).join(" · ")}
              </span>
            </li>
          ))}
          {hits.length === 0 && (
            <li className="px-3 py-2 text-sm text-muted">
              {isError ? "검색하지 못했습니다. 잠시 후 다시 시도해 주세요." : pending ? "찾는 중…" : "일치하는 선수가 없습니다."}
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
