/**
 * 知识资产管理 · 文档管理页面。
 *
 * 采用主从（Master-Detail）视图按文档与版本展示解析产物、流水线任务与阶段详情。
 */

import { useMemo, useState, type ReactNode } from "react";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { useQueries, useQuery } from "@tanstack/react-query";
import { EmptyState, FailureNotice } from "../../components/failure-notice";
import { SkeletonRows } from "../../components/skeleton";
import { IconDocument } from "../../components/icons";
import { formatBytes } from "../../lib/format";
import { usePageVisible } from "../../lib/usePageVisible";
import { StatusBadge } from "../ingestion-jobs/IngestionStatus";
import {
  RETRY_OUTCOME_LABEL,
  useRetryVersion,
  versionJobsQueryOptions,
} from "../ingestion-jobs/api";
import { KnowledgeBaseSelect } from "../knowledge-bases/KnowledgeBaseSelect";
import { useKnowledgeBases } from "../knowledge-bases/api";
import {
  documentKindOf,
  documentStatusOf,
  documentSummariesQueryOptions,
  useDeleteDocument,
  useDocumentDetail,
  versionStatusLabel,
  type DocumentSummary,
} from "../documents/api";
import { CONSOLE_PATHS } from "../shell/paths";
import { VersionCard } from "./VersionCard";

const POLL_MS = 5_000;

export function DocumentManagement(): ReactNode {
  const rawSearch = useRouterState({ select: (state) => state.location.search });
  const navigate = useNavigate();
  const knowledgeBases = useKnowledgeBases();
  const [chosenKnowledgeBase, setChosenKnowledgeBase] = useState<string | null>(null);
  const [retryNote, setRetryNote] = useState<{
    readonly versionId: string;
    readonly text: string;
    readonly tone: "ok" | "error";
  } | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const visible = usePageVisible();
  const catalogue = useMemo(() => knowledgeBases.data ?? [], [knowledgeBases.data]);
  const knowledgeBaseId = chosenKnowledgeBase ?? catalogue.at(0)?.id ?? null;
  const retry = useRetryVersion(knowledgeBaseId);
  const removeDocument = useDeleteDocument(knowledgeBaseId);

  const documents = useQuery({
    ...documentSummariesQueryOptions(knowledgeBaseId),
    refetchInterval: visible ? POLL_MS : false,
  });
  const summaries = documents.data ?? [];

  const requested = (rawSearch as unknown as Record<string, unknown>)["doc"];
  const selectedId =
    typeof requested === "string" && summaries.some((entry) => entry.id === requested)
      ? requested
      : (summaries.at(0)?.id ?? null);

  const detail = useDocumentDetail(selectedId);
  const versions = detail.data?.versions ?? [];
  const selected = summaries.find((entry) => entry.id === selectedId) ?? null;

  const jobQueries = useQueries({
    queries: versions.map((version) => ({
      ...versionJobsQueryOptions(version.id),
      refetchInterval: visible ? POLL_MS : false,
    })),
  });

  function select(documentId: string): void {
    void navigate({ to: CONSOLE_PATHS.documents, search: { doc: documentId }, replace: true });
  }

  async function runRetry(versionId: string): Promise<void> {
    setRetryNote(null);
    try {
      const result = await retry.mutateAsync(versionId);
      setRetryNote({
        versionId,
        text: `${RETRY_OUTCOME_LABEL[result.outcome] ?? `后端返回 ${result.outcome}`}（版本状态 ${versionStatusLabel(result.versionStatus)}）`,
        tone: result.created ? "ok" : "error",
      });
      await detail.refetch();
      await documents.refetch();
    } catch (error) {
      setRetryNote({
        versionId,
        text: error instanceof Error ? error.message : "重试请求失败",
        tone: "error",
      });
    }
  }

  const rail = (
    <ul className="flex flex-col gap-1 px-2">
      {summaries.map((document) => (
        <li key={document.id}>
          <button
            type="button"
            onClick={() => {
              select(document.id);
            }}
            aria-current={document.id === selectedId ? "true" : undefined}
            className={`flex w-full flex-col gap-1 rounded-md px-2 py-2 text-left tint ${
              document.id === selectedId ? "bg-surface-hover" : "hover:bg-surface"
            }`}
          >
            <span className="flex items-center gap-2 text-dense text-ink">
              <span className="shrink-0 text-ink-secondary">
                <IconDocument size={16} />
              </span>
              <span className="truncate">{document.title}</span>
            </span>
            <span className="flex items-center gap-2 pl-6">
              <StatusBadge status={documentStatusOf(document.latestVersion)} />
              <span className="text-label tabular-nums text-ink-secondary">
                {document.latestVersion === null
                  ? "无版本"
                  : `v${String(document.latestVersion.versionOrdinal)}`}
              </span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="flex h-full min-h-0">
      <div className="hidden w-64 shrink-0 flex-col overflow-y-auto border-r border-border lg:flex">
        <div className="flex flex-col gap-2 px-4 pt-4 pb-2">
          <h2 className="text-label font-medium text-ink-secondary">文档</h2>
          <KnowledgeBaseSelect
            knowledgeBases={catalogue}
            value={knowledgeBaseId}
            onChange={(next) => {
              setChosenKnowledgeBase(next);
              setRetryNote(null);
              setDeleteError(null);
            }}
          />
        </div>
        {documents.isPending ? (
          <SkeletonRows rows={4} />
        ) : documents.isError ? (
          <div className="px-3 py-2">
            <FailureNotice
              title="文档列表没有读出来"
              detail={documents.error instanceof Error ? documents.error.message : "请求失败"}
              action={
                <button
                  type="button"
                  onClick={() => {
                    void documents.refetch();
                  }}
                  className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
                >
                  重试
                </button>
              }
            />
          </div>
        ) : summaries.length === 0 ? (
          <p className="px-4 py-4 text-label text-ink-secondary">
            {knowledgeBaseId === null
              ? "还没有知识库。先建一个再上传文档。"
              : "这个知识库还没有文档。上传后这里会列出每一份文档的版本。"}
          </p>
        ) : (
          rail
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="w-full max-w-[900px] px-4 py-4 sm:px-5 sm:py-5">
          <header>
            <h1 className="text-title font-semibold text-ink">文档管理</h1>
            <p className="mt-1 text-body text-ink-secondary">
              按文档与版本查看解析产物与流水线任务，点击阶段节点查看该阶段实际发生了什么。
            </p>
          </header>

          {deleteError === null ? null : (
            <div className="mt-4">
              <FailureNotice
                title="删除没有完成"
                detail={deleteError}
                action={
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteError(null);
                    }}
                    className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
                  >
                    知道了
                  </button>
                }
              />
            </div>
          )}

          {/* 窄屏或移动端下展示文档选择下拉框 */}
          <label className="mt-4 flex flex-col gap-1 lg:hidden">
            <span className="text-label text-ink-secondary">选择文档</span>
            <select
              value={selectedId ?? ""}
              onChange={(event) => {
                select(event.target.value);
              }}
              className="h-8 rounded-md border border-control-border bg-canvas px-2 text-dense text-ink"
            >
              {summaries.map((document) => (
                <option key={document.id} value={document.id}>
                  {document.title}
                </option>
              ))}
            </select>
          </label>

          {selected === null ? (
            <div className="mt-6">
              {knowledgeBaseId === null ? (
                <EmptyState title="还没有知识库">
                  知识库是一次检索的范围。先在「知识资产管理 →
                  知识库」新建一个并上传文档，这一页就会列出每份文档的版本与流水线。
                </EmptyState>
              ) : documents.isPending ? (
                <SkeletonRows rows={3} />
              ) : (
                <EmptyState title="这个知识库还没有文档">
                  先在「知识资产管理 →
                  知识库」上传一份文档；上传后解析、分块、嵌入与索引会在这里逐个阶段出现。
                </EmptyState>
              )}
            </div>
          ) : (
            <>
              <div className="mt-5 flex flex-wrap items-baseline gap-2 border-b border-border pb-3">
                <h2 className="text-section font-semibold text-ink">{selected.title}</h2>
                <span className="text-label text-ink-secondary">
                  {selected.latestVersion === null
                    ? "无版本"
                    : `${documentKindOf(selected.latestVersion.mimeType)} · ${formatBytes(selected.latestVersion.sizeBytes)}`}
                </span>
                <button
                  type="button"
                  disabled={removeDocument.isPending}
                  onClick={() => {
                    void (async () => {
                      try {
                        await removeDocument.mutateAsync(selected.id);
                        await documents.refetch();
                      } catch (error) {
                        setDeleteError(error instanceof Error ? error.message : "删除失败");
                      }
                    })();
                  }}
                  className="ml-auto flex h-7 items-center rounded-md px-2 text-label font-medium text-error-ink tint hover:bg-error/10 disabled:opacity-50"
                >
                  删除文档
                </button>
              </div>

              {detail.isPending ? (
                <div className="mt-4">
                  <SkeletonRows rows={2} />
                </div>
              ) : detail.isError ? (
                <div className="mt-4">
                  <FailureNotice
                    title="版本列表没有读出来"
                    detail={detail.error instanceof Error ? detail.error.message : "请求失败"}
                    action={
                      <button
                        type="button"
                        onClick={() => {
                          void detail.refetch();
                        }}
                        className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
                      >
                        重试
                      </button>
                    }
                  />
                </div>
              ) : (
                <ul className="mt-4 flex flex-col gap-3">
                  {versions.length === 0 ? (
                    <li className="text-dense text-ink-secondary">
                      这一文档没有版本了。重新上传即可生成新的版本。
                    </li>
                  ) : (
                    versions.map((version, index) => {
                      const jobs = jobQueries[index];
                      const jobsError = jobs?.error;
                      return (
                        <VersionCard
                          key={version.id}
                          version={version}
                          jobs={jobs?.data}
                          jobsPending={jobs?.isPending ?? true}
                          jobsError={
                            jobs?.isError === true
                              ? ((jobsError as Error | undefined)?.message ?? "请求失败")
                              : null
                          }
                          current={index === 0}
                          onRetry={(versionId) => {
                            void runRetry(versionId);
                          }}
                          retryNote={retryNote?.versionId === version.id ? retryNote : null}
                          retrying={retry.isPending}
                        />
                      );
                    })
                  )}
                </ul>
              )}

              <footer className="mt-4 text-label text-ink-secondary">
                一个文档可以有多份上传：每一次上传是一个版本，流水线的每个阶段都是该版本的一行任务。删除只能整份
                文档删除——契约没有单版本删除。
              </footer>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export type { DocumentSummary };
