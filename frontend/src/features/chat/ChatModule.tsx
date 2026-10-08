import { memo, useCallback, useMemo, useState, type ReactNode } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { Drawer } from "@base-ui/react/drawer";
import { IconDatabase } from "../../components/icons";
import { FailureNotice } from "../../components/failure-notice";
import { SkeletonLines } from "../../components/skeleton";
import type { CitationPayload } from "../../lib/sse";
import type { KnowledgeBase } from "../knowledge-bases/api";
import { useConversationDetail, type ChatMessage } from "./api";
import { AnswerBody, locationLabel } from "./AnswerBody";
import { ChatWelcome } from "./ChatWelcome";
import { Composer } from "./Composer";
import { EvidenceInspector } from "./EvidenceInspector";
import { QuestionBubble, StatusLine, Thread } from "./Thread";
import { INITIAL_RUN_STATE, runText, useAgentRun, type RunState } from "./run";
import { useSessions } from "./sessions";
import { useMediaQuery } from "../../lib/useMediaQuery";

/** 合同审查核心交互模块容器。 */
export function ChatModule(): ReactNode {
  const { epoch, active } = useSessions();
  return (
    <ChatSession
      key={epoch}
      title={active?.title ?? null}
      scopeName={active?.scope ?? null}
      conversationId={active?.id ?? null}
    />
  );
}

/** 将已持久化的历史助理消息转换为运行状态视图。 */
function stateOfStored(message: ChatMessage): RunState {
  const status: RunState["status"] =
    message.status === "completed"
      ? "completed"
      : message.status === "failed"
        ? "failed"
        : message.status === "cancelled"
          ? "cancelled"
          : "streaming";
  return {
    ...INITIAL_RUN_STATE,
    status,
    authoritativeAnswer: message.content,
    citations: message.citations,
    evidenceStatus: message.evidenceStatus,
    retrievalRounds: message.retrievalRounds,
    intent: message.intent,
    finishReason: message.finishReason,
    errorClass: message.errorClass,
    errorMessage: null,
    assistantMessageId: message.id,
  };
}

interface StoredTurn {
  readonly question: ChatMessage;
  readonly answer: ChatMessage | null;
}

/** 将平面消息列表配对重组成问答轮次列表。 */
function turnsOf(messages: readonly ChatMessage[]): readonly StoredTurn[] {
  const turns: StoredTurn[] = [];
  for (const message of messages) {
    if (message.role === "user") {
      turns.push({ question: message, answer: null });
      continue;
    }
    const current = turns.at(-1);
    if (current === undefined || current.answer !== null) {
      turns.push({
        question: { ...message, role: "user", content: "" },
        answer: message,
      });
      continue;
    }
    turns[turns.length - 1] = { question: current.question, answer: message };
  }
  return turns;
}

/** 单轮历史问答记录展示组件（使用 memo 避免流式高频触发历史重解析）。 */
const StoredTurnView = memo(function StoredTurnView({
  turn,
  onCopy,
  onOpenSource,
}: {
  readonly turn: StoredTurn;
  readonly onCopy: (citation: CitationPayload) => void;
  readonly onOpenSource: (citation: CitationPayload) => void;
}): ReactNode {
  const citations = turn.answer?.citations ?? [];
  const citationById = new Map(citations.map((citation) => [citation.citationId, citation]));
  const order = citations.map((citation) => citation.citationId);
  return (
    <article className="flex flex-col gap-5">
      {/* 用户消息在右 */}
      {turn.question.content.length === 0 ? null : (
        <QuestionBubble question={turn.question.content} />
      )}
      {/* AI消息在左 */}
      {turn.answer === null ? null : (
        <div className="flex justify-start">
          <div className="w-full max-w-[95%] sm:max-w-[90%] lg:max-w-[88%] flex flex-col gap-3 rounded-lg border border-border bg-canvas p-5 shadow-tactile">
            <header className="flex items-center justify-between border-b border-divider pb-3">
              <div className="flex items-center gap-2">
                <span className="flex h-5 w-5 items-center justify-center rounded bg-ink text-canvas font-mono text-[10px] font-bold">
                  §
                </span>
                <h3 className="text-dense font-semibold text-ink">条款审查报告与风险洞察</h3>
              </div>
              <span className="font-mono text-[11px] text-ink-muted">已落定审查记录</span>
            </header>
            <AnswerBody
              text={turn.answer.content}
              citationById={citationById}
              order={order}
              onCopy={onCopy}
              onOpenSource={onOpenSource}
            />
            <footer className="mt-2 border-t border-divider pt-3">
              <StatusLine state={stateOfStored(turn.answer)} />
            </footer>
          </div>
        </div>
      )}
    </article>
  );
});

/** 提问输入操作栏封装组件。 */
function ComposerBar({
  onAsk,
  busy,
  autoFocus,
  knowledgeBases,
  knowledgeBaseId,
  onKnowledgeBaseChange,
}: {
  readonly onAsk: (question: string) => void;
  readonly busy: boolean;
  readonly autoFocus: boolean;
  readonly knowledgeBases: readonly KnowledgeBase[];
  readonly knowledgeBaseId: string | null;
  readonly onKnowledgeBaseChange: (knowledgeBaseId: string) => void;
}): ReactNode {
  const [draft, setDraft] = useState("");
  return (
    <Composer
      value={draft}
      onChange={setDraft}
      onSubmit={() => {
        const asked = draft.trim();
        if (asked.length > 0) {
          setDraft("");
          onAsk(asked);
        }
      }}
      busy={busy}
      autoFocus={autoFocus}
      knowledgeBases={knowledgeBases}
      knowledgeBaseId={knowledgeBaseId}
      onKnowledgeBaseChange={onKnowledgeBaseChange}
    />
  );
}

function ChatSession({
  title,
  scopeName,
  conversationId: initialConversationId,
}: {
  readonly title: string | null;
  readonly scopeName: string | null;
  readonly conversationId: string | null;
}): ReactNode {
  const {
    knowledgeBases,
    knowledgeBaseId,
    setKnowledgeBaseId,
    ensureConversation,
    nameActive,
    startError,
  } = useSessions();

  const [conversationId, setConversationId] = useState<string | null>(initialConversationId);
  const [question, setQuestion] = useState<string | null>(null);
  const [runKey, setRunKey] = useState(0);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [viewerNotice, setViewerNotice] = useState<CitationPayload | null>(null);
  const [askError, setAskError] = useState<string | null>(null);

  const history = useConversationDetail(conversationId);
  const { state, cancel } = useAgentRun(conversationId, question, runKey);
  const text = runText(state);
  const isWide = useMediaQuery("(min-width: 1280px)");

  const citationById = useMemo(
    () => new Map(state.citations.map((citation) => [citation.citationId, citation])),
    [state.citations],
  );
  const order = useMemo(
    () => state.citations.map((citation) => citation.citationId),
    [state.citations],
  );
  const openCitation = sourceId === null ? null : (citationById.get(sourceId) ?? null);

  const storedTurns = useMemo(() => {
    const live = new Set(
      [state.userMessageId, state.assistantMessageId].filter((id): id is string => id !== null),
    );
    return turnsOf((history.data?.messages ?? []).filter((message) => !live.has(message.id)));
  }, [history.data, state.assistantMessageId, state.userMessageId]);

  const ask = useCallback(
    (asked: string) => {
      setAskError(null);
      void (async () => {
        const target = conversationId ?? (await ensureConversation());
        if (target === null) {
          setAskError(
            knowledgeBases.length === 0
              ? "还没有知识库。先在「知识资产管理 → 知识库」里建一个并上传文档，再回到这里提问。"
              : "无法新建会话，请稍后重试。",
          );
          return;
        }
        setConversationId(target);
        setQuestion(asked);
        setSourceId(null);
        setRunKey((key) => key + 1);
        nameActive(target, asked);
      })();
    },
    [conversationId, ensureConversation, knowledgeBases.length, nameActive],
  );

  const onCopy = useCallback((citation: CitationPayload) => {
    void navigator.clipboard.writeText(citation.quote).catch(() => undefined);
  }, []);
  const onOpenSource = useCallback((citation: CitationPayload) => {
    setSourceId(citation.citationId);
  }, []);

  const composer = (
    <ComposerBar
      onAsk={ask}
      busy={state.status === "streaming" && question !== null}
      autoFocus={question === null}
      knowledgeBases={knowledgeBases}
      knowledgeBaseId={knowledgeBaseId}
      onKnowledgeBaseChange={setKnowledgeBaseId}
    />
  );

  const liveTurn =
    question === null ? null : (
      <Thread
        state={state}
        question={question}
        onReplay={() => {
          setSourceId(null);
          setRunKey((key) => key + 1);
        }}
        onCancel={cancel}
        answer={
          <AnswerBody
            text={text}
            citationById={citationById}
            order={order}
            onCopy={onCopy}
            onOpenSource={onOpenSource}
            isStreaming={state.status === "streaming"}
          />
        }
      />
    );

  const inspector =
    openCitation === null ? null : (
      <EvidenceInspector
        citation={openCitation}
        rank={order.indexOf(openCitation.citationId) + 1}
        total={order.length}
        onClose={() => {
          setSourceId(null);
        }}
        onCopy={onCopy}
        onOpenDocument={setViewerNotice}
      />
    );

  const notice =
    askError === null ? null : (
      <FailureNotice
        title="这次提问没有发出去"
        detail={askError}
        action={
          <button
            type="button"
            onClick={() => {
              setAskError(null);
            }}
            className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
          >
            知道了
          </button>
        }
      />
    );

  const loading = history.isPending && conversationId !== null;

  return (
    <div className="flex min-h-0 flex-1">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <header className="flex h-[52px] shrink-0 items-center gap-3 border-b border-divider px-5">
          <h1 className="min-w-0 flex-1 truncate text-dense font-semibold text-ink">
            {title ?? "新审查记录"}
          </h1>
          {scopeName === null ? null : (
            <span className="hidden shrink-0 items-center gap-2 text-label text-ink-secondary sm:flex">
              <IconDatabase size={13} />
              {scopeName}
            </span>
          )}
        </header>

        {question === null && storedTurns.length === 0 && !loading ? (
          <ChatWelcome onAsk={ask} composer={composer} notice={notice ?? undefined} />
        ) : (
          <>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <div className="mx-auto flex w-full max-w-[920px] flex-col gap-6 px-4 py-6 sm:px-6">
                {notice}
                {loading ? <SkeletonLines lines={4} /> : null}
                {history.isError ? (
                  <FailureNotice
                    title="这段会话没有读出来"
                    detail={
                      history.error instanceof Error ? history.error.message : "会话详情请求失败"
                    }
                    action={
                      <button
                        type="button"
                        onClick={() => {
                          void history.refetch();
                        }}
                        className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
                      >
                        重试
                      </button>
                    }
                  />
                ) : null}
                {storedTurns.map((turn) => (
                  <StoredTurnView
                    key={turn.question.id}
                    turn={turn}
                    onCopy={onCopy}
                    onOpenSource={onOpenSource}
                  />
                ))}
                {liveTurn}
                {startError === null ? null : (
                  <FailureNotice
                    title="无法新建会话"
                    detail={startError}
                    action={
                      <button
                        type="button"
                        onClick={() => {
                          void history.refetch();
                        }}
                        className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
                      >
                        重试
                      </button>
                    }
                  />
                )}
              </div>
            </div>

            <div className="shrink-0 px-4 pb-4 sm:px-6">
              <div className="mx-auto w-full max-w-[920px]">{composer}</div>
            </div>
          </>
        )}
      </div>

      {/* 宽屏右侧常驻对照面板 */}
      {openCitation !== null && isWide ? (
        <aside className="w-[480px] shrink-0 border-l border-divider bg-canvas">{inspector}</aside>
      ) : null}

      {/* 窄屏抽屉弹层 */}
      {openCitation !== null && !isWide ? (
        <Drawer.Root
          open
          onOpenChange={(open) => {
            if (!open) {
              setSourceId(null);
            }
          }}
        >
          <Drawer.Portal>
            <Drawer.Backdrop className="fixed inset-0 z-40 bg-[var(--scrim)]" />
            <Drawer.Viewport className="fixed inset-0 z-50 flex justify-end">
              <Drawer.Popup className="w-[480px] max-w-full bg-float shadow-dialog outline-none focus-visible:shadow-none">
                {inspector}
              </Drawer.Popup>
            </Drawer.Viewport>
          </Drawer.Portal>
        </Drawer.Root>
      ) : null}

      <Dialog.Root
        open={viewerNotice !== null}
        onOpenChange={(open) => {
          if (!open) {
            setViewerNotice(null);
          }
        }}
      >
        <Dialog.Portal>
          <Dialog.Backdrop className="fixed inset-0 z-40 bg-[var(--scrim)]" />
          <Dialog.Viewport className="fixed inset-0 z-50 flex items-center justify-center p-6">
            <Dialog.Popup className="w-[420px] max-w-full rounded-lg bg-float p-5 shadow-dialog">
              <Dialog.Title className="text-section font-semibold text-ink">
                文档查看器尚未实现
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-dense text-ink-secondary">
                正式实现会在这里打开「{viewerNotice?.documentName}」的解析产物并定位到{" "}
                {viewerNotice === null ? "" : locationLabel(viewerNotice)}。契约目前只发布解析产物的
                摘要（解析器、页数、行区间与校验和），没有返回规范化 Markdown 正文的接口，因此当前
                版本只提供右侧的原文对照。
              </Dialog.Description>
              <div className="mt-5 flex justify-end">
                <Dialog.Close className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-strong">
                  知道了
                </Dialog.Close>
              </div>
            </Dialog.Popup>
          </Dialog.Viewport>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
