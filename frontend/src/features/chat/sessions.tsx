/**
 * 会话上下文与历史会话状态管理。
 *
 * 封装会话列表查询、会话创建、重命名、删除及当前选中会话的状态流转。
 */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useConversations,
  useCreateConversation,
  useDeleteConversation,
  useRenameConversation,
  type Conversation,
} from "./api";
import { useKnowledgeBases, type KnowledgeBase } from "../knowledge-bases/api";

export interface ChatSession {
  readonly id: string;
  /** 会话标题；占位标题时为 null。 */
  readonly title: string | null;
  /** 所属知识库名称（检索范围）。 */
  readonly scope: string;
  /** 侧栏展示的更新时间文本。 */
  readonly at: string;
  /** 时间分组（今天 / 过去 7 天）。 */
  readonly day: "today" | "week";
}

export interface SessionGroup {
  readonly label: string;
  readonly sessions: readonly ChatSession[];
}

/** 按时间分组会话列表（今天、过去 7 天）。 */
export function groupsOf(sessions: readonly ChatSession[]): readonly SessionGroup[] {
  return [
    { label: "今天", sessions: sessions.filter((session) => session.day === "today") },
    { label: "过去 7 天", sessions: sessions.filter((session) => session.day === "week") },
  ].filter((group) => group.sessions.length > 0);
}

const TITLE_LIMIT = 28;

/** 服务端默认占位会话标题。 */
const PLACEHOLDER_TITLE = "新对话";

function clampTitle(question: string): string {
  const oneLine = question.replace(/\s+/g, " ").trim();
  return oneLine.length <= TITLE_LIMIT ? oneLine : `${oneLine.slice(0, TITLE_LIMIT - 1)}…`;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/** 计算会话更新时间在侧栏中的展示文本与所属时间区间。 */
function whenOf(
  updatedAt: string,
  now: number,
): { readonly at: string; readonly day: "today" | "week" } {
  const parsed = Date.parse(updatedAt);
  if (Number.isNaN(parsed)) {
    return { at: "—", day: "week" };
  }
  const sameDay = new Date(parsed).toDateString() === new Date(now).toDateString();
  if (sameDay) {
    return {
      at: new Intl.DateTimeFormat("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(parsed),
      day: "today",
    };
  }
  if (now - parsed < 7 * DAY_MS) {
    return {
      at: new Intl.DateTimeFormat("zh-CN", { weekday: "short" }).format(parsed),
      day: "week",
    };
  }
  return {
    at: new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit" }).format(parsed),
    day: "week",
  };
}

function toSession(
  conversation: Conversation,
  knowledgeBaseNames: ReadonlyMap<string, string>,
  now: number,
): ChatSession {
  const when = whenOf(conversation.updatedAt, now);
  return {
    id: conversation.id,
    title: conversation.title === PLACEHOLDER_TITLE ? null : conversation.title,
    scope: knowledgeBaseNames.get(conversation.knowledgeBaseId) ?? "知识库已删除",
    at: when.at,
    day: when.day,
  };
}

export interface SessionStore {
  readonly sessions: readonly ChatSession[];
  readonly activeId: string | null;
  readonly active: ChatSession | null;
  /** 会话重置代际计数，切换会话时递增以清空提问区状态。 */
  readonly epoch: number;
  /** 可选知识库列表及默认选中的知识库 ID。 */
  readonly knowledgeBases: readonly KnowledgeBase[];
  readonly knowledgeBaseId: string | null;
  readonly setKnowledgeBaseId: (id: string) => void;
  readonly knowledgeBasesPending: boolean;
  readonly knowledgeBasesError: string | null;
  /** 新建会话。 */
  readonly start: () => void;
  readonly startPending: boolean;
  readonly startError: string | null;
  readonly select: (id: string) => void;
  readonly rename: (id: string, title: string) => void;
  readonly remove: (id: string) => void;
  readonly conversationsPending: boolean;
  readonly conversationsError: string | null;
  /** 确保当前存在可用会话（若无则自动在当前选定知识库中创建）。 */
  readonly ensureConversation: () => Promise<string | null>;
  /** 将用户首个提问自动更新为会话标题。 */
  readonly nameActive: (conversationId: string, question: string) => void;
}

const SessionContext = createContext<SessionStore | null>(null);

export function SessionProvider({ children }: { readonly children: ReactNode }): ReactNode {
  const conversations = useConversations();
  const knowledgeBases = useKnowledgeBases();
  const create = useCreateConversation();
  const renameOne = useRenameConversation();
  const removeOne = useDeleteConversation();
  const client = useQueryClient();

  const [activeId, setActiveId] = useState<string | null>(null);
  const [epoch, setEpoch] = useState(0);
  const [chosenKnowledgeBase, setChosenKnowledgeBase] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);

  const knowledgeBaseList = useMemo(() => knowledgeBases.data ?? [], [knowledgeBases.data]);
  // 默认选中首个可用知识库
  const knowledgeBaseId = chosenKnowledgeBase ?? knowledgeBaseList.at(0)?.id ?? null;

  const knowledgeBaseNames = useMemo(() => {
    const names = new Map<string, string>();
    for (const knowledgeBase of knowledgeBaseList) {
      names.set(knowledgeBase.id, knowledgeBase.name);
    }
    return names;
  }, [knowledgeBaseList]);

  // 组件初始化时固定时间基准，避免多次渲染读取时钟导致分组不一致
  const [now] = useState(() => Date.now());
  const sessions = useMemo(
    () =>
      (conversations.data ?? []).map((conversation) =>
        toSession(conversation, knowledgeBaseNames, now),
      ),
    [conversations.data, knowledgeBaseNames, now],
  );

  const start = useCallback(() => {
    if (knowledgeBaseId === null) {
      setStartError("还没有知识库，先在「知识资产管理 → 知识库」里建一个。");
      return;
    }
    setStartError(null);
    void (async () => {
      try {
        const created = await create.mutateAsync({ knowledgeBaseId });
        setActiveId(created.id);
        setEpoch((current) => current + 1);
      } catch (error) {
        setStartError(error instanceof Error ? error.message : "新建对话失败");
      }
    })();
  }, [create, knowledgeBaseId]);

  const ensureConversation = useCallback(async (): Promise<string | null> => {
    if (activeId !== null) {
      return activeId;
    }
    if (knowledgeBaseId === null) {
      return null;
    }
    try {
      const created = await create.mutateAsync({ knowledgeBaseId });
      // 不递增 epoch，以保留正在提交的问题流
      setActiveId(created.id);
      return created.id;
    } catch {
      return null;
    }
  }, [activeId, create, knowledgeBaseId]);

  const nameActive = useCallback(
    (conversationId: string, question: string) => {
      // 直接读取缓存数据，防止状态闭包陈旧覆盖已有标题
      const list = client.getQueryData<readonly Conversation[]>(["conversations"]) ?? [];
      const current = list.find((entry) => entry.id === conversationId);
      if (current !== undefined && current.title !== PLACEHOLDER_TITLE) {
        return;
      }
      renameOne.mutate({ id: conversationId, title: clampTitle(question) });
    },
    [client, renameOne],
  );

  const select = useCallback((id: string) => {
    setActiveId(id);
    setEpoch((current) => current + 1);
  }, []);

  const rename = useCallback(
    (id: string, title: string) => {
      const next = title.trim();
      if (next.length === 0) {
        return;
      }
      renameOne.mutate({ id, title: next });
    },
    [renameOne],
  );

  const remove = useCallback(
    (id: string) => {
      void (async () => {
        try {
          await removeOne.mutateAsync(id);
          setActiveId((current) => (current === id ? null : current));
        } catch {
          // 删除失败时保持列表现状，等待服务端状态对齐
        }
      })();
    },
    [removeOne],
  );

  const value = useMemo<SessionStore>(
    () => ({
      sessions,
      activeId,
      active: sessions.find((session) => session.id === activeId) ?? null,
      epoch,
      knowledgeBases: knowledgeBaseList,
      knowledgeBaseId,
      setKnowledgeBaseId: setChosenKnowledgeBase,
      knowledgeBasesPending: knowledgeBases.isPending,
      knowledgeBasesError: knowledgeBases.isError ? (knowledgeBases.error as Error).message : null,
      start,
      startPending: create.isPending,
      startError,
      select,
      rename,
      remove,
      conversationsPending: conversations.isPending,
      conversationsError: conversations.isError ? (conversations.error as Error).message : null,
      ensureConversation,
      nameActive,
    }),
    [
      activeId,
      conversations.error,
      conversations.isError,
      conversations.isPending,
      create.isPending,
      ensureConversation,
      epoch,
      knowledgeBaseId,
      knowledgeBaseList,
      knowledgeBases.error,
      knowledgeBases.isError,
      knowledgeBases.isPending,
      nameActive,
      remove,
      rename,
      select,
      sessions,
      start,
      startError,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSessions(): SessionStore {
  const store = useContext(SessionContext);
  if (store === null) {
    throw new Error("useSessions must be used inside SessionProvider");
  }
  return store;
}
