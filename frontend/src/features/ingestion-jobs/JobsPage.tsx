/**
 * 摄取任务页面组件。
 *
 * 展示选定知识库下各文档最新版本的流水线阶段状态，支持按状态筛选与按版本重试解析。
 */

import { useMemo, useState, type ReactNode } from "react";
import { Select } from "@base-ui/react/select";
import { Switch } from "@base-ui/react/switch";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { EmptyState, FailureNotice } from "../../components/failure-notice";
import { StatusMark, type MarkTone } from "../../components/state-mark";
import { SkeletonBar, SkeletonRows } from "../../components/skeleton";
import { IconCheck, IconChevronDown, IconReplay } from "../../components/icons";
import { formatTimestamp, shortId } from "../../lib/format";
import { documentVersionKeys, knowledgeBaseKeys } from "../../lib/queryKeys";
import { usePageVisible } from "../../lib/usePageVisible";
import { KnowledgeBaseSelect } from "../knowledge-bases/KnowledgeBaseSelect";
import { useKnowledgeBases } from "../knowledge-bases/api";
import {
  documentSummariesQueryOptions,
  isVersionMoving,
  versionStatusLabel,
  type DocumentSummary,
  type DocumentVersion,
} from "../documents/api";
import {
  jobStageLabel,
  jobStatusLabel,
  jobStatusTone,
  needsManualRetry,
  RETRY_OUTCOME_LABEL,
  toPipelineStages,
  useRetryVersion,
  versionJobsQueryOptions,
  type IngestionJob,
} from "./api";
import { StagePills, type StageName } from "./Stepper";

const POLL_MS = 5_000;

type StatusFilter = "all" | "active" | "failed" | "done";

const FILTER_ITEMS: Record<string, string> = {
  all: "全部状态",
  active: "进行中",
  failed: "需要处理",
  done: "已完成",
};

interface Entry {
  readonly document: DocumentSummary;
  readonly version: DocumentVersion;
  readonly jobs: readonly IngestionJob[] | undefined;
  readonly loading: boolean;
}

export function JobsPage(): ReactNode {
  const knowledgeBases = useKnowledgeBases();
  const [chosen, setChosen] = useState<string | null>(null);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [openStage, setOpenStage] = useState<{ versionId: string; stage: StageName } | null>(null);
  const [note, setNote] = useState<{ versionId: string; text: string; tone: MarkTone } | null>(
    null,
  );
  const client = useQueryClient();
  const visible = usePageVisible();
  const polling = autoRefresh && visible;

  // 默认选中首个可用知识库
  const selected = chosen ?? knowledgeBases.data?.at(0)?.id ?? null;
  const retry = useRetryVersion(selected);

  const documents = useQuery({
    ...documentSummariesQueryOptions(selected),
    // 仅在存在推进中的文档版本时轮询文档列表
    refetchInterval: (query) => (polling && anyMoving(query.state.data) ? POLL_MS : false),
  });

  const pairs = useMemo(() => {
    const list: { document: DocumentSummary; version: DocumentVersion }[] = [];
    for (const document of documents.data ?? []) {
      if (document.latestVersion !== null) {
        list.push({ document, version: document.latestVersion });
      }
    }
    return list;
  }, [documents.data]);

  const jobQueries = useQueries({
    queries: pairs.map((pair) => ({
      ...versionJobsQueryOptions(pair.version.id),
      // 仅对未落定的版本执行周期轮询
      refetchInterval: polling && isVersionMoving(pair.version.status) ? POLL_MS : false,
    })),
  });

  const entries: readonly Entry[] = pairs.map((pair, index) => ({
    document: pair.document,
    version: pair.version,
    jobs: jobQueries[index]?.data,
    loading: jobQueries[index]?.isPending ?? true,
  }));

  const sorted = [...entries].sort(
    (left, right) => Date.parse(right.version.updatedAt) - Date.parse(left.version.updatedAt),
  );
  const shown =
    filter === "all" ? sorted : sorted.filter((entry) => bucketOf(entry.jobs) === filter);
  const runningCount = entries.filter((entry) => bucketOf(entry.jobs) === "active").length;

  async function runRetry(versionId: string): Promise<void> {
    setNote(null);
    try {
      const result = await retry.mutateAsync(versionId);
      setNote({
        versionId,
        text: `${RETRY_OUTCOME_LABEL[result.outcome] ?? `后端返回 ${result.outcome}`}（版本状态 ${versionStatusLabel(result.versionStatus)}）`,
        tone: result.created ? "success" : "muted",
      });
      await client.invalidateQueries({ queryKey: knowledgeBaseKeys.documents(selected ?? "") });
    } catch (error) {
      setNote({
        versionId,
        text: error instanceof Error ? error.message : "重试请求失败",
        tone: "error",
      });
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-5 px-4 py-4 sm:px-5 sm:py-5">
        <header>
          <h1 className="text-title font-semibold text-ink">摄取任务</h1>
          <p className="mt-1 max-w-[92ch] text-body text-ink-secondary">
            每份文档的最新版本走到哪一步：五个阶段各自的真实状态、修订与尝试次数，需要人工处理的阶段可以在这里重试。
          </p>
        </header>

        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-canvas p-4">
          <KnowledgeBaseSelect
            knowledgeBases={knowledgeBases.data ?? []}
            value={selected}
            onChange={(next) => {
              setChosen(next);
              setOpenStage(null);
              setNote(null);
            }}
          />

          <Select.Root
            items={FILTER_ITEMS}
            value={filter}
            onValueChange={(next) => {
              if (typeof next === "string") {
                setFilter(next as StatusFilter);
              }
            }}
          >
            <Select.Trigger
              aria-label="状态筛选"
              className="flex h-8 items-center justify-between gap-2 rounded-md border border-control-border bg-canvas px-2.5 text-body text-ink tint hover:bg-surface"
            >
              <Select.Value />
              <Select.Icon className="text-ink-muted">
                <IconChevronDown size={14} />
              </Select.Icon>
            </Select.Trigger>
            <Select.Portal>
              <Select.Positioner sideOffset={4} alignItemWithTrigger={false} className="z-50">
                <Select.Popup className="min-w-[var(--anchor-width)] rounded-lg bg-float p-1 shadow-popover">
                  <Select.List>
                    {Object.entries(FILTER_ITEMS).map(([value, label]) => (
                      <Select.Item
                        key={value}
                        value={value}
                        className="flex h-8 cursor-default items-center gap-2 rounded-md px-2 text-dense text-ink-secondary tint select-none data-[highlighted]:bg-surface-hover data-[highlighted]:text-ink"
                      >
                        <span className="flex w-4 shrink-0 items-center text-accent">
                          <Select.ItemIndicator>
                            <IconCheck size={14} />
                          </Select.ItemIndicator>
                        </span>
                        <Select.ItemText>{label}</Select.ItemText>
                      </Select.Item>
                    ))}
                  </Select.List>
                </Select.Popup>
              </Select.Positioner>
            </Select.Portal>
          </Select.Root>

          <label className="flex h-8 items-center gap-2 text-dense text-ink">
            <Switch.Root
              checked={autoRefresh}
              onCheckedChange={(checked) => {
                setAutoRefresh(checked);
              }}
              // 开关视觉状态受 autoRefresh 单一数据源驱动，确保滑块与轨道严格同步。
              className={`flex h-5 w-9 shrink-0 items-center rounded-[var(--radius-pill)] border p-0.5 tint ${
                autoRefresh ? "border-accent bg-accent" : "border-control-border bg-surface-strong"
              }`}
            >
              <Switch.Thumb
                className={`block h-4 w-4 rounded-[var(--radius-pill)] bg-canvas tint ${
                  autoRefresh ? "translate-x-4" : "translate-x-0"
                }`}
              />
            </Switch.Root>
            自动刷新
          </label>

          <span className="text-label text-ink-secondary">
            {polling ? "每 5 秒刷新一次" : autoRefresh ? "页面不在前台，已暂停刷新" : "刷新已关闭"}
          </span>

          <button
            type="button"
            onClick={() => {
              void client.invalidateQueries({ queryKey: documentVersionKeys.all() });
              if (selected !== null) {
                void client.invalidateQueries({ queryKey: knowledgeBaseKeys.documents(selected) });
              }
            }}
            className="ml-auto flex h-8 items-center gap-1.5 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
          >
            <IconReplay size={14} />
            立即刷新
          </button>
        </div>

        <p className="max-w-[92ch] text-dense text-ink-secondary">
          {runningCount > 0
            ? `本库有 ${String(runningCount)} 份文档在流水线中。`
            : "本库当前没有在流水线中的文档。"}
          本页按每份文档的<span className="font-medium text-ink">最新版本</span>读取任务
          （契约按文档版本发布任务，没有库级任务索引）；更早版本的任务在文档详情里。
        </p>

        {knowledgeBases.isError ? (
          <FailureNotice
            title="读不到知识库列表"
            detail={knowledgeBases.error.message}
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
        ) : null}

        {documents.isError ? (
          <FailureNotice
            title="读不到这个知识库的文档"
            detail={documents.error.message}
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
        ) : null}

        {knowledgeBases.isSuccess && knowledgeBases.data.length === 0 ? (
          <EmptyState title="还没有知识库">
            任务属于某个知识库的某份文档，所以先创建一个知识库并上传文档，这一页才会有内容。
          </EmptyState>
        ) : null}

        {documents.isPending && selected !== null ? (
          <div className="rounded-lg border border-border bg-canvas">
            <SkeletonRows rows={4} rowHeight="h-8" />
          </div>
        ) : null}

        {documents.isSuccess && sorted.length === 0 ? (
          <EmptyState title="这个知识库还没有文档">
            上传一份文档后，它的解析、分块、向量化与建索引四个阶段会在这里逐条出现。
          </EmptyState>
        ) : null}

        {sorted.length > 0 && shown.length === 0 ? (
          <EmptyState title="这个筛选下没有任务">
            换个状态筛选，或者选「全部状态」查看这个知识库的全部文档。筛选只改变显示，不会删除任何任务行。
          </EmptyState>
        ) : null}

        {shown.length === 0 ? null : (
          <ul className="divide-y divide-border overflow-hidden rounded-lg border border-border bg-canvas">
            {shown.map((entry) => (
              <DocumentTasks
                key={entry.version.id}
                entry={entry}
                openStage={openStage}
                onOpenStage={setOpenStage}
                note={note?.versionId === entry.version.id ? note : null}
                retrying={retry.isPending}
                onRetry={runRetry}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function DocumentTasks({
  entry,
  openStage,
  onOpenStage,
  note,
  retrying,
  onRetry,
}: {
  readonly entry: Entry;
  readonly openStage: { versionId: string; stage: StageName } | null;
  readonly onOpenStage: (next: { versionId: string; stage: StageName } | null) => void;
  readonly note: { versionId: string; text: string; tone: MarkTone } | null;
  readonly retrying: boolean;
  readonly onRetry: (versionId: string) => Promise<void>;
}): ReactNode {
  const { document, version, jobs } = entry;
  const selectedStage = openStage?.versionId === version.id ? openStage.stage : null;
  const selectedJob = (jobs ?? []).find((job) => stageNameOf(job.stage) === selectedStage);

  return (
    <li className="px-3 py-3">
      <div className="flex min-h-8 flex-wrap items-center gap-x-3 gap-y-2">
        <span className="min-w-0 flex-1 truncate text-body font-medium text-ink">
          {document.title}
        </span>
        <span className="text-label tabular-nums text-ink-secondary">
          v{String(version.versionOrdinal)}
        </span>
        <StatusMark
          tone={versionTone(version.status)}
          label={versionStatusLabel(version.status)}
          title={version.status}
          variant="pill"
        />
        <span className="text-label tabular-nums text-ink-secondary">
          {formatTimestamp(version.updatedAt)}
        </span>
        {needsManualRetry(jobs ?? []) ? (
          <button
            type="button"
            disabled={retrying}
            onClick={() => {
              void onRetry(version.id);
            }}
            className="flex h-7 items-center gap-1.5 rounded-md bg-surface px-2.5 text-label font-medium text-ink tint hover:bg-surface-hover disabled:opacity-50"
          >
            <IconReplay size={14} />
            重试解析
          </button>
        ) : null}
      </div>

      <div className="mt-2">
        {entry.loading ? (
          <div className="flex items-center gap-2">
            <SkeletonBar className="h-6 w-24 rounded-[var(--radius-pill)]" />
            <SkeletonBar className="h-6 w-24 rounded-[var(--radius-pill)]" />
            <SkeletonBar className="h-6 w-24 rounded-[var(--radius-pill)]" />
            <SkeletonBar className="h-6 w-24 rounded-[var(--radius-pill)]" />
            <SkeletonBar className="h-6 w-24 rounded-[var(--radius-pill)]" />
          </div>
        ) : (
          <StagePills
            stages={toPipelineStages(jobs ?? [])}
            selected={selectedStage}
            onSelect={(stage) => {
              onOpenStage(selectedStage === stage ? null : { versionId: version.id, stage });
            }}
          />
        )}
      </div>

      {note === null ? null : (
        <div className="mt-2">
          <StatusMark tone={note.tone} label={note.text} />
        </div>
      )}

      {selectedStage === null ? null : (
        <div className="mt-3 rounded-md bg-surface p-3">
          {entry.loading ? (
            <SkeletonRows rows={2} rowHeight="h-7" />
          ) : selectedJob === undefined ? (
            <p className="text-dense text-ink-secondary">
              这个阶段还没有任务行：队列还没走到它，所以现在没有可读的记录。
            </p>
          ) : (
            <JobDetail job={selectedJob} />
          )}
        </div>
      )}
    </li>
  );
}

function JobDetail({ job }: { readonly job: IngestionJob }): ReactNode {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <span className="text-label font-medium text-ink">{jobStageLabel(job.stage)}</span>
        <StatusMark
          tone={jobStatusTone(job.status)}
          label={jobStatusLabel(job.status)}
          title={job.status}
          variant="pill"
        />
        <span className="font-mono text-quote text-ink-secondary">{job.stage}</span>
        <span className="text-label tabular-nums text-ink-secondary">
          修订 {String(job.revision)} · 尝试 {String(job.attempt)}
        </span>
        <span className="text-label tabular-nums text-ink-secondary">
          开始 {formatTimestamp(job.startedAt)} · 结束 {formatTimestamp(job.finishedAt)}
        </span>
        <span className="text-label tabular-nums text-ink-secondary">任务 {shortId(job.id)}</span>
      </div>

      {job.errorClass === null && job.errorMessage === null ? null : (
        <div className="rounded-sm border border-border bg-canvas p-2">
          <p className="font-mono text-quote text-error-ink">{job.errorClass ?? "—"}</p>
          <p className="mt-1 text-dense break-words text-ink-secondary">{job.errorMessage ?? ""}</p>
        </div>
      )}

      {job.status === "manual_retry_required" ? (
        <p className="max-w-[92ch] text-dense text-ink">
          这个阶段已经没有自动重试的余量：需要先确认原因，再发起一次解析重试。
        </p>
      ) : null}
    </div>
  );
}

/** 是否还有任何一份文档的最新版本在动：列表是否值得继续读的判据。 */
function anyMoving(documents: readonly DocumentSummary[] | undefined): boolean {
  return (documents ?? []).some(
    (document) => document.latestVersion !== null && isVersionMoving(document.latestVersion.status),
  );
}

/* — aggregates the filters and the row marks are computed from ————————————————— */

function bucketOf(jobs: readonly IngestionJob[] | undefined): StatusFilter {
  if (jobs === undefined || jobs.length === 0) {
    return "active";
  }
  if (jobs.some((job) => job.status === "failed" || job.status === "manual_retry_required")) {
    return "failed";
  }
  if (jobs.some((job) => job.status === "running" || job.status === "pending")) {
    return "active";
  }
  return "done";
}

/** 根据文档版本的生命周期状态映射对应的状态徽标语义色调。 */
function versionTone(status: string): MarkTone {
  if (status === "ready") {
    return "success";
  }
  if (status.endsWith("_failed")) {
    return "error";
  }
  if (status === "manual_retry_required") {
    return "warning";
  }
  return "running";
}

function stageNameOf(stage: string): StageName {
  return stage as StageName;
}
