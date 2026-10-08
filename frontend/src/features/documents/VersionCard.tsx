/**
 * 文档版本卡片组件（版本元数据、流水线阶段进度与产物详情抽屉）。
 */

import { useMemo, useState, type ReactNode } from "react";
import { Drawer } from "@base-ui/react/drawer";
import { FailureNotice } from "../../components/failure-notice";
import { SkeletonLines } from "../../components/skeleton";
import { IconClose, IconReplay } from "../../components/icons";
import { formatBytes, formatTimestamp } from "../../lib/format";
import { useMediaQuery } from "../../lib/useMediaQuery";
import { StatusBadge } from "../ingestion-jobs/IngestionStatus";
import { newestJobsByStage, toPipelineStages, type IngestionJob } from "../ingestion-jobs/api";
import {
  STAGE_LABEL,
  STATE_LABEL,
  StageDetailPanel,
  StagePills,
  type Stage,
  type StageName,
} from "../ingestion-jobs/Stepper";
import {
  documentKindOf,
  documentStatusOf,
  useVersionDetail,
  versionStatusLabel,
  type DocumentVersion,
} from "./api";

export interface VersionCardProps {
  readonly version: DocumentVersion;
  readonly jobs: readonly IngestionJob[] | undefined;
  readonly jobsPending: boolean;
  readonly jobsError: string | null;
  readonly current: boolean;
  readonly onRetry: (versionId: string) => void;
  readonly retryNote: { readonly text: string; readonly tone: "ok" | "error" } | null;
  readonly retrying: boolean;
}

export function VersionCard({
  version,
  jobs,
  jobsPending,
  jobsError,
  current,
  onRetry,
  retryNote,
  retrying,
}: VersionCardProps): ReactNode {
  // 当前选中的流水线阶段节点；为 null 时仅展示阶段概览条
  const [selectedStage, setSelectedStage] = useState<StageName | null>(null);
  const isWide = useMediaQuery("(min-width: 1024px)");
  // 仅在用户主动展开阶段时按需加载版本产物详情
  const detail = useVersionDetail(selectedStage === null ? null : version.id);

  const stages: readonly Stage[] = useMemo(() => toPipelineStages(jobs ?? []), [jobs]);
  const stage =
    selectedStage === null ? undefined : stages.find((entry) => entry.name === selectedStage);
  const job =
    selectedStage === null ? null : (newestJobsByStage(jobs ?? []).get(selectedStage) ?? null);

  const status = documentStatusOf(version);

  return (
    <li className="rounded-lg border border-border p-4 shadow-tactile bg-canvas">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-dense font-semibold text-ink">
          v{String(version.versionOrdinal)}
        </span>
        {current ? (
          <span className="inline-flex h-5 items-center rounded-sm bg-accent-soft px-1.5 text-label font-medium text-accent-strong">
            当前生效版本
          </span>
        ) : null}
        <span className="text-label tabular-nums text-ink-secondary">
          {formatTimestamp(version.createdAt)}
        </span>
        <span className="text-label text-ink-secondary">
          {documentKindOf(version.mimeType)} · {formatBytes(version.sizeBytes)}
        </span>
        <span className="ml-auto flex items-center gap-1">
          <StatusBadge status={status} />
          {status === "running" ? null : (
            <button
              type="button"
              disabled={retrying}
              onClick={() => {
                onRetry(version.id);
              }}
              className="flex h-7 items-center gap-1.5 rounded-md px-2 text-label font-medium text-ink-secondary tint hover:bg-surface-hover hover:text-ink disabled:opacity-50 active:scale-95"
            >
              <IconReplay size={13} />
              重新解析
            </button>
          )}
        </span>
      </div>

      <p className="mt-1 text-label tabular-nums text-ink-secondary">
        版本状态 {versionStatusLabel(version.status)} · 校验和 {version.checksum.slice(0, 12)}
      </p>

      <div className="mt-3">
        {jobsPending ? (
          <SkeletonLines lines={1} />
        ) : jobsError === null ? (
          <StagePills
            stages={stages}
            selected={selectedStage}
            onSelect={(name) => {
              // 再次点击同一阶段可收起详情面板
              setSelectedStage((currentStage) => (currentStage === name ? null : name));
            }}
          />
        ) : (
          <FailureNotice title="这一版本的任务没有读出来" detail={jobsError} />
        )}
      </div>

      {retryNote === null ? null : (
        <p
          className={`mt-2 text-label ${retryNote.tone === "ok" ? "text-ink-secondary" : "text-error-ink"}`}
        >
          {retryNote.text}
        </p>
      )}

      {stage === undefined ? null : isWide ? (
        <div className="mt-3">
          {detail.isPending && stage.name === "parse" ? (
            <SkeletonLines lines={3} />
          ) : (
            <StageDetailPanel
              stage={stage}
              job={job}
              artifact={detail.data?.parseArtifact ?? null}
            />
          )}
        </div>
      ) : (
        <Drawer.Root
          open
          onOpenChange={(open) => {
            if (!open) {
              setSelectedStage(null);
            }
          }}
        >
          <Drawer.Portal>
            <Drawer.Backdrop className="fixed inset-0 z-40 bg-[var(--scrim)]" />
            <Drawer.Viewport className="fixed inset-0 z-50 flex items-end justify-center p-2 sm:items-stretch sm:justify-end">
              {/* 移动端抽屉展示阶段详情面板 */}
              <Drawer.Popup className="flex max-h-full w-[420px] max-w-full flex-col overflow-hidden rounded-[var(--radius-island)] bg-float shadow-dialog outline-none focus-visible:shadow-none">
                <header className="flex shrink-0 items-center gap-2 border-b border-divider px-4 py-3">
                  <h3 className="text-dense font-medium text-ink">{STAGE_LABEL[stage.name]}</h3>
                  <span className="text-label text-ink-secondary">{STATE_LABEL[stage.state]}</span>
                  <Drawer.Close
                    aria-label="关闭阶段详情"
                    className="ml-auto flex h-7 w-7 items-center justify-center rounded-md text-ink-secondary tint hover:bg-surface-hover hover:text-ink"
                  >
                    <IconClose size={16} />
                  </Drawer.Close>
                </header>
                <div className="min-h-0 flex-1 overflow-y-auto p-4">
                  <StageDetailPanel
                    stage={stage}
                    job={job}
                    artifact={detail.data?.parseArtifact ?? null}
                  />
                </div>
              </Drawer.Popup>
            </Drawer.Viewport>
          </Drawer.Portal>
        </Drawer.Root>
      )}
    </li>
  );
}
