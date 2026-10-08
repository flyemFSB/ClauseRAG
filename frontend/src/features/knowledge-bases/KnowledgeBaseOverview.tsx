import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { IconDatabase, IconInfo, IconPlus } from "../../components/icons";
import { EmptyState, FailureNotice } from "../../components/failure-notice";
import { SkeletonRows } from "../../components/skeleton";
import { useRetryVersion } from "../ingestion-jobs/api";
import { documentSummariesQueryOptions, uploadDocument, useDeleteDocument } from "../documents/api";
import { usePageVisible } from "../../lib/usePageVisible";
import {
  useCreateKnowledgeBase,
  useDeleteKnowledgeBase,
  useKnowledgeBases,
  useUpdateKnowledgeBase,
} from "./api";
import { CONSOLE_PATHS } from "../shell/paths";
import {
  matchesFilter,
  rowOf,
  refusalOf,
  type QueueItem,
  type QueueState,
  type Row,
  type StatusFilter,
} from "./rows";
import { ConfirmDialog } from "./ConfirmDialog";
import { DocumentFigures } from "./DocumentFigures";
import { KnowledgeBaseBar } from "./KnowledgeBaseBar";
import { MobileActionsDrawer } from "./MobileActionsDrawer";
import { UploadDialog } from "./UploadDialog";
import { DocumentListSection } from "./DocumentListSection";
import { KnowledgeBaseNameDialog } from "./KnowledgeBaseNameDialog";

const POLL_MS = 5_000;

/* — the page ———————————————————————————————————————————————— */

export function KnowledgeBaseOverview(): ReactNode {
  const navigate = useNavigate();
  const knowledgeBases = useKnowledgeBases();
  const [chosen, setChosen] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [queue, setQueue] = useState<readonly QueueItem[]>([]);
  const [appendTo, setAppendTo] = useState<string>("");
  const [confirming, setConfirming] = useState<readonly string[] | null>(null);
  const [confirmingKnowledgeBase, setConfirmingKnowledgeBase] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [creating, setCreating] = useState(false);
  const [sheetFor, setSheetFor] = useState<Row | null>(null);
  const [dragging, setDragging] = useState(false);
  const [note, setNote] = useState<{ readonly text: string; readonly tone: "ok" | "error" } | null>(
    null,
  );

  const catalogue = useMemo(() => knowledgeBases.data ?? [], [knowledgeBases.data]);
  const selectedId = chosen ?? catalogue.at(0)?.id ?? null;
  const selectedKnowledgeBase = catalogue.find((entry) => entry.id === selectedId) ?? null;

  const visiblePage = usePageVisible();
  const retry = useRetryVersion(selectedId);
  const removeDocument = useDeleteDocument(selectedId);
  const createKnowledgeBase = useCreateKnowledgeBase();
  const updateKnowledgeBase = useUpdateKnowledgeBase();
  const deleteKnowledgeBase = useDeleteKnowledgeBase();

  const documents = useQuery({
    ...documentSummariesQueryOptions(selectedId),
    // A list with a version still moving keeps itself current; nothing else polls.
    refetchInterval: visiblePage ? POLL_MS : false,
  });

  const rows = useMemo(() => (documents.data ?? []).map(rowOf), [documents.data]);
  const inFlight = rows.some((row) => row.status === "running" || row.status === "queued");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter(
      (row) =>
        matchesFilter(row, filter) &&
        (needle.length === 0 || row.document.title.toLowerCase().includes(needle)),
    );
  }, [rows, query, filter]);

  const allVisibleSelected =
    visible.length > 0 && visible.every((row) => selected.includes(row.document.id));

  function addFiles(files: FileList | null): void {
    if (files === null || files.length === 0) {
      return;
    }
    const added = Array.from(files).map((file, index) => {
      const reason = refusalOf(file);
      return {
        id: `q${String(Date.now())}-${String(index)}`,
        file,
        state: (reason === null ? "waiting" : "rejected") as QueueState,
        ...(reason === null ? {} : { reason }),
      };
    });
    setQueue((current) => [...current, ...added]);
  }

  /** 按顺序依次上传等待中的文件。 */
  async function runUpload(): Promise<void> {
    if (selectedId === null) {
      return;
    }
    setNote(null);
    for (const item of queue.filter((entry) => entry.state === "waiting")) {
      setQueue((current) =>
        current.map((entry) => (entry.id === item.id ? { ...entry, state: "uploading" } : entry)),
      );
      const uploaded = await uploadDocument(
        selectedId,
        item.file,
        AbortSignal.timeout(120_000),
        appendTo.length === 0 ? undefined : appendTo,
      ).then(
        () => ({ ok: true as const }),
        (error: unknown) => ({
          ok: false as const,
          message: error instanceof Error ? error.message : "上传失败",
        }),
      );
      setQueue((current) =>
        current.map((entry) =>
          entry.id === item.id
            ? uploaded.ok
              ? { ...entry, state: "done" }
              : { ...entry, state: "failed", reason: uploaded.message }
            : entry,
        ),
      );
    }
  }

  async function reparse(versionIds: readonly string[]): Promise<void> {
    setNote(null);
    let created = 0;
    let covered = 0;
    let refused = 0;
    for (const versionId of versionIds) {
      try {
        const result = await retry.mutateAsync(versionId);
        if (result.created) {
          created += 1;
        } else {
          covered += 1;
        }
      } catch {
        refused += 1;
      }
    }
    const parts = [
      created > 0 ? `${String(created)} 个版本已追加解析重试` : "",
      covered > 0 ? `${String(covered)} 个版本已由队列或运行中的 worker 覆盖` : "",
      refused > 0 ? `${String(refused)} 个版本被拒绝（状态不允许重试）` : "",
    ].filter((part) => part.length > 0);
    setNote({
      text: parts.length === 0 ? "没有可重试的版本。" : parts.join("；"),
      tone: refused > 0 && created === 0 ? "error" : "ok",
    });
    setSelected([]);
    setSheetFor(null);
  }

  async function remove(ids: readonly string[]): Promise<void> {
    setNote(null);
    const failed: string[] = [];
    for (const id of ids) {
      try {
        await removeDocument.mutateAsync(id);
      } catch (error) {
        failed.push(error instanceof Error ? error.message : id);
      }
    }
    setConfirming(null);
    setSelected([]);
    if (failed.length > 0) {
      setNote({
        text: `${String(failed.length)} 份文档没有删除：${failed.join("；")}`,
        tone: "error",
      });
    }
  }

  const versionIdsOf = (ids: readonly string[]): readonly string[] =>
    ids
      .map((id) => rows.find((row) => row.document.id === id)?.version?.id)
      .filter((id): id is string => id !== undefined);

  return (
    <div className="h-full overflow-y-auto">
      <div
        className={`w-full max-w-[1240px] px-4 py-4 sm:px-5 sm:py-5 ${selected.length > 0 ? "pb-20 md:pb-5" : ""}`}
      >
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-title font-semibold text-ink">知识库</h1>
            <p className="mt-1 text-body text-ink-secondary">
              管理你的商业合同与法务知识库，支持文档上传、条款解析与双通道检索配置。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                setNameDraft("");
                setCreating(true);
              }}
              className="flex h-8 items-center gap-2 rounded-md border border-control-border bg-canvas px-3 text-label font-medium text-ink tint hover:bg-surface"
            >
              <IconDatabase size={15} />
              新建知识库
            </button>
            <button
              type="button"
              disabled={selectedId === null}
              onClick={() => {
                setQueue([]);
                setAppendTo("");
                setNote(null);
                setUploadOpen(true);
              }}
              className="flex h-8 items-center gap-2 rounded-md bg-accent-strong px-4 text-label font-medium text-canvas tint hover:bg-accent disabled:opacity-40"
            >
              <IconPlus size={16} />
              上传文档
            </button>
          </div>
        </header>

        <KnowledgeBaseBar
          knowledgeBases={catalogue}
          value={selectedId}
          knowledgeBase={selectedKnowledgeBase}
          onSelect={(next) => {
            setChosen(next);
            setSelected([]);
            setQuery("");
            setNote(null);
          }}
          onRename={() => {
            setNameDraft(selectedKnowledgeBase?.name ?? "");
            setRenaming(true);
          }}
          onDelete={() => {
            setConfirmingKnowledgeBase(true);
          }}
        />

        {note === null ? null : (
          <div className="mt-3">
            <FailureNotice
              title={note.tone === "ok" ? "操作结果" : "操作未完成"}
              detail={note.text}
              action={
                <button
                  type="button"
                  onClick={() => {
                    setNote(null);
                  }}
                  className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
                >
                  知道了
                </button>
              }
            />
          </div>
        )}

        {selectedId === null ? (
          <div className="mt-5">
            {knowledgeBases.isPending ? (
              <SkeletonRows rows={3} />
            ) : knowledgeBases.isError ? (
              <FailureNotice
                title="知识库列表没有读出来"
                detail={
                  knowledgeBases.error instanceof Error ? knowledgeBases.error.message : "请求失败"
                }
                action={
                  <button
                    type="button"
                    onClick={() => {
                      void knowledgeBases.refetch();
                    }}
                    className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
                  >
                    重试
                  </button>
                }
              />
            ) : (
              <EmptyState title="还没有知识库">
                知识库是一次检索的范围：会话、文档与检索调试都必须在某一个知识库里。先新建一个，再上传文档。
              </EmptyState>
            )}
          </div>
        ) : (
          <>
            <DocumentFigures
              rows={rows}
              knowledgeBaseName={selectedKnowledgeBase?.name ?? ""}
              isPending={documents.isPending}
              inFlight={inFlight}
            />

            <DocumentListSection
              rows={rows}
              visible={visible}
              selected={selected}
              allVisibleSelected={allVisibleSelected}
              query={query}
              filter={filter}
              onQueryChange={setQuery}
              onFilterChange={setFilter}
              isPending={documents.isPending}
              errorMessage={documents.error instanceof Error ? documents.error.message : "请求失败"}
              onRetry={() => {
                void documents.refetch();
              }}
              onSelectionChange={setSelected}
              onReparse={(versionId) => {
                if (versionId !== null) {
                  void reparse([versionId]);
                }
              }}
              onReparseSelection={() => {
                void reparse(versionIdsOf(selected));
              }}
              onOpenSheet={setSheetFor}
              onRequestDelete={(documentId) => {
                setConfirming([documentId]);
              }}
              onRequestDeleteSelection={() => {
                setConfirming(selected);
              }}
              onOpenDocument={(documentId) => {
                void navigate({ to: CONSOLE_PATHS.documents, search: { doc: documentId } });
              }}
            />
          </>
        )}
      </div>

      {/* 移动端操作抽屉 */}
      <MobileActionsDrawer
        row={sheetFor}
        onClose={() => {
          setSheetFor(null);
        }}
        onOpenDocument={(documentId) => {
          void navigate({ to: CONSOLE_PATHS.documents, search: { doc: documentId } });
        }}
        onReparse={(versionId) => {
          void reparse([versionId]);
        }}
        onRequestDelete={(documentId) => {
          setConfirming([documentId]);
        }}
      />

      <UploadDialog
        open={uploadOpen}
        onOpenChange={(open) => {
          setUploadOpen(open);
          if (!open) {
            setQueue([]);
          }
        }}
        knowledgeBaseName={selectedKnowledgeBase?.name ?? ""}
        rows={rows}
        appendTo={appendTo}
        onAppendToChange={setAppendTo}
        queue={queue}
        onAddFiles={addFiles}
        onRemove={(id) => {
          setQueue((current) => current.filter((entry) => entry.id !== id));
        }}
        dragging={dragging}
        onDraggingChange={setDragging}
        onUpload={() => {
          void runUpload();
        }}
        uploading={queue.some((entry) => entry.state === "uploading")}
      />

      {creating || renaming ? (
        <KnowledgeBaseNameDialog
          key={renaming ? "rename" : "create"}
          title={renaming ? "重命名知识库" : "新建知识库"}
          confirmLabel={renaming ? "保存" : "创建"}
          initial={renaming ? nameDraft : ""}
          pending={createKnowledgeBase.isPending || updateKnowledgeBase.isPending}
          onOpenChange={(open) => {
            if (!open) {
              setCreating(false);
              setRenaming(false);
            }
          }}
          onSubmit={(name) => {
            if (renaming && selectedKnowledgeBase !== null) {
              updateKnowledgeBase.mutate(
                { id: selectedKnowledgeBase.id, name },
                {
                  onSuccess: () => {
                    setRenaming(false);
                    setNote({ text: `已重命名为「${name}」。`, tone: "ok" });
                  },
                  onError: (error) => {
                    setNote({
                      text: error instanceof Error ? error.message : "重命名失败",
                      tone: "error",
                    });
                    setRenaming(false);
                  },
                },
              );
              return;
            }
            createKnowledgeBase.mutate(
              { name, description: null },
              {
                onSuccess: (created) => {
                  setChosen(created.id);
                  setCreating(false);
                  setNote({ text: `已创建「${created.name}」，现在可以上传文档。`, tone: "ok" });
                },
                onError: (error) => {
                  setNote({
                    text: error instanceof Error ? error.message : "创建失败",
                    tone: "error",
                  });
                  setCreating(false);
                },
              },
            );
          }}
        />
      ) : null}

      <ConfirmDialog
        open={confirming !== null}
        title={`删除 ${String(confirming?.length ?? 0)} 个文档？`}
        description="文档版本、父子块与向量条目会一并删除；已引用它们的回答不会改变，但引用将无法再打开。"
        confirmLabel="删除"
        notice={
          <span className="flex items-center gap-2 text-label text-ink-secondary">
            <IconInfo size={14} />
            此操作不可撤销
          </span>
        }
        onOpenChange={(open) => {
          if (!open) {
            setConfirming(null);
          }
        }}
        onConfirm={() => {
          void remove(confirming ?? []);
        }}
      />

      <ConfirmDialog
        open={confirmingKnowledgeBase}
        title={`删除知识库「${selectedKnowledgeBase?.name ?? ""}」？`}
        description={`这个知识库里的 ${String(rows.length)} 份文档、它们的版本、任务与向量会一并删除，绑定它的会话也将没有可检索的范围。此操作不可撤销。`}
        confirmLabel="删除知识库"
        onOpenChange={setConfirmingKnowledgeBase}
        onConfirm={() => {
          if (selectedKnowledgeBase === null) {
            return;
          }
          deleteKnowledgeBase.mutate(selectedKnowledgeBase.id, {
            onSuccess: () => {
              setConfirmingKnowledgeBase(false);
              setChosen(null);
              setNote({ text: "知识库及其文档已删除。", tone: "ok" });
            },
            onError: (error) => {
              setConfirmingKnowledgeBase(false);
              setNote({
                text: error instanceof Error ? error.message : "删除失败",
                tone: "error",
              });
            },
          });
        }}
      />
    </div>
  );
}
