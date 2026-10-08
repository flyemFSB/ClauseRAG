/**
 * 系统设置页面
 *
 * 展示基础设施就绪健康状况探针（`/health/ready`）、数据与删除规则，
 * 以及平台各项运行时限制的生效值。
 */

import { useState, type ReactNode } from "react";
import { Switch } from "@base-ui/react/switch";
import { FailureNotice } from "../../components/failure-notice";
import { StatusMark } from "../../components/state-mark";
import { SkeletonLines } from "../../components/skeleton";
import { IconReplay } from "../../components/icons";
import { formatMillis } from "../../lib/format";
import {
  DEPENDENCY_ROLE,
  dependencyLabel,
  readinessLabel,
  readinessQueryOptions,
  readinessTone,
  useConfig,
} from "./api";
import { ConfigCaveat, ConfigGroup, type ConfigRow } from "./ConfigSheet";
import { useQuery } from "@tanstack/react-query";

const POLL_MS = 5_000;

const LIMITS: readonly ConfigRow[] = [
  {
    name: "单次上传上限",
    env: "MAX_UPLOAD_BYTES",
    detail: "声明超过它的请求在进入路由之前就被 413 拒绝，文件不会被存到任何地方。",
  },
  {
    name: "解析阶段上限",
    env: "PARSE_TIMEOUT_SECONDS",
    detail: "覆盖下载、解析与产物写入。OCR 实测约每页 28 秒，所以默认值大约够三十页扫描件。",
  },
  {
    name: "分块阶段上限",
    env: "CHUNK_TIMEOUT_SECONDS",
    detail:
      "工作全在本进程与对象存储里，所以远低于解析的期限；这个界的意义是让卡住的阶段不会一直占着 running。",
  },
  {
    name: "任务尝试次数",
    env: "JOB_MAX_ATTEMPTS",
    detail: "含第一次投递。耗尽之后任务进入需人工重试，而不是无限重投。",
  },
  {
    name: "重试退避",
    env: "JOB_RETRY_DELAY_SECONDS",
    detail:
      "第 n 次重试等 n × 30 秒，上限 300 秒，并叠加最多一秒抖动，避免 provider 恢复瞬间所有任务同时回来。",
  },
  {
    name: "判定中断的时长",
    env: "JOB_STALE_AFTER_SECONDS",
    detail:
      "running 超过它才被认为是中断的遗留，人工重试会追加新的一次。默认是解析期限的两倍，所以还在自己超时里的尝试不会被误判。",
  },
  {
    name: "worker 并发",
    env: "WORKER_MAX_ASYNC_TASKS",
    detail: "一个 worker 同时跑多少个摄取任务，以及它持有多少条未确认的投递。",
  },
  {
    name: "投递超时",
    env: "JOB_DISPATCH_TIMEOUT_SECONDS",
    detail: "把任务交给 RabbitMQ 的期限。队列不可达时先失败的是这次投递，任务行仍是事实。",
  },
  {
    name: "对象存储超时",
    env: "STORAGE_TIMEOUT_SECONDS",
    detail: "单个存储请求（含一个 multipart 分片）的连接与读取期限。",
  },
  {
    name: "数据库超时",
    env: "DATABASE_TIMEOUT_SECONDS",
    detail: "连接 PostgreSQL 与单条语句的上限。",
  },
  {
    name: "就绪探针超时",
    env: "HEALTH_PROBE_TIMEOUT_SECONDS",
    detail: "探测单个依赖的上限；超时被记成不可用，而不是让整次就绪检查挂住。",
  },
  {
    name: "检索日志探针",
    env: "LANGFUSE_HOST",
    detail: "Langfuse 的地址。两个 key 都缺失时观测性关闭，业务链路照常运行。",
  },
];

export function SystemSettingsPage(): ReactNode {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const readiness = useQuery({
    ...readinessQueryOptions(),
    refetchInterval: autoRefresh ? POLL_MS : false,
  });
  const config = useConfig();

  const overall =
    readiness.data?.status === "ready"
      ? { tone: "success" as const, label: "全部依赖可用" }
      : { tone: "error" as const, label: "有依赖不可用" };

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-5 px-4 py-4 sm:px-5 sm:py-5">
        <header>
          <h1 className="text-title font-semibold text-ink">系统设置</h1>
          <p className="mt-1 max-w-[92ch] text-body text-ink-secondary">
            平台当前的运行状况，以及这个部署运行时所受的上限与数据规则。
          </p>
        </header>

        <section className="rounded-lg border border-border bg-canvas" aria-label="服务就绪">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-3">
            <h2 className="text-section font-semibold text-ink">服务就绪</h2>
            <div className="flex flex-wrap items-center gap-3">
              {readiness.isSuccess ? (
                <StatusMark
                  tone={overall.tone}
                  label={overall.label}
                  title={readiness.data.status}
                  variant="pill"
                />
              ) : null}
              {readiness.isSuccess ? (
                <span className="text-label tabular-nums text-ink-secondary">
                  探针总耗时 {formatMillis(readiness.data.durationMs)}
                </span>
              ) : null}
              <label className="flex items-center gap-2 text-dense text-ink">
                <Switch.Root
                  checked={autoRefresh}
                  onCheckedChange={(checked) => {
                    setAutoRefresh(checked);
                  }}
                  className={`flex h-5 w-9 shrink-0 items-center rounded-[var(--radius-pill)] border p-0.5 tint ${
                    autoRefresh
                      ? "border-accent bg-accent"
                      : "border-control-border bg-surface-strong"
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
              <button
                type="button"
                onClick={() => {
                  void readiness.refetch();
                }}
                className="flex h-8 items-center gap-1.5 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
              >
                <IconReplay size={14} />
                立即探测
              </button>
            </div>
          </header>

          {readiness.isPending ? (
            <div className="p-4">
              <SkeletonLines lines={4} />
            </div>
          ) : null}

          {readiness.isError ? (
            <div className="p-4">
              <FailureNotice
                title="探针本身没有答上来"
                detail={readiness.error.message}
                action={
                  <button
                    type="button"
                    onClick={() => {
                      void readiness.refetch();
                    }}
                    className="h-8 rounded-md bg-surface px-3 text-label font-medium text-ink tint hover:bg-surface-hover"
                  >
                    重试
                  </button>
                }
              />
            </div>
          ) : null}

          {readiness.isSuccess ? (
            <table className="w-full border-collapse">
              <thead>
                <tr className="bg-surface">
                  <th className="px-4 py-2 text-left text-label font-medium text-ink-secondary">
                    依赖
                  </th>
                  <th className="px-4 py-2 text-left text-label font-medium text-ink-secondary">
                    作用
                  </th>
                  <th className="px-4 py-2 text-left text-label font-medium text-ink-secondary">
                    状态
                  </th>
                  <th className="px-4 py-2 text-right text-label font-medium text-ink-secondary">
                    延迟
                  </th>
                </tr>
              </thead>
              <tbody>
                {readiness.data.dependencies.map((dependency) => (
                  <tr key={dependency.name} className="border-t border-divider">
                    <td className="px-4 py-2 align-top text-dense font-medium text-ink">
                      {dependencyLabel(dependency.name)}
                    </td>
                    <td className="px-4 py-2 align-top text-dense text-ink-secondary">
                      {DEPENDENCY_ROLE[dependency.name] ?? "—"}
                      {dependency.detail === null ? null : (
                        <span className="mt-1 block font-mono text-quote text-error-ink">
                          {dependency.detail}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 align-top">
                      <StatusMark
                        tone={readinessTone(dependency.state)}
                        label={readinessLabel(dependency.state)}
                        title={dependency.state}
                      />
                    </td>
                    <td className="px-4 py-2 text-right align-top text-dense tabular-nums text-ink-secondary">
                      {formatMillis(dependency.latencyMs)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </section>

        <section
          className="rounded-lg border border-border bg-canvas px-4 py-4"
          aria-label="数据与保留"
        >
          <h2 className="text-section font-semibold text-ink">数据、删除与日志</h2>
          <dl className="mt-3 flex flex-col gap-3">
            <Policy
              term="单主体部署，没有登录"
              detail="平台以展示为目的上线：没有登录页、没有会话 Cookie，也没有账号。知识库、文档与对话都属于同一个平台主体，所以平台内部没有跨用户的权限边界，任何能打开这个地址的人都能检索全部文档。"
              source="docs/adr（ADR-0033）"
            />
            <Policy
              term="删除是异步清理，不是立刻抹除"
              detail="删除文档或知识库会先移除行记录，同时留下一条持久化的清理意图：派生出来的对象与密集向量由 worker 的清理通道删除。清理失败会重试，删除本身不会因此被回滚。"
              source="docs/adr（清理意图）"
            />
            <Policy
              term="日志里没有什么"
              detail="结构化事件带请求、任务、追踪与文档标识，但从不记录密钥、签名地址或完整文档原文。"
              source="docs/architecture/frontend-contract.md"
            />
            <Policy
              term="上传上限在执行之前生效"
              detail="声明长度超过上限的请求都在进入路由之前被 413 拒绝。"
              source="docs/architecture/frontend-contract.md"
            />
          </dl>
        </section>

        <ConfigCaveat>
          这里的值是业务 API 进程<span className="font-medium text-ink">实际读到</span>
          的配置：环境变量（含 <span className="font-mono">.env</span>
          ）覆盖过哪一项，这里就是覆盖后的结果， 密钥项只报是否已配置。
        </ConfigCaveat>

        {config.isError ? (
          <FailureNotice
            title="读不到生效配置"
            detail={config.error instanceof Error ? config.error.message : "未知错误"}
          />
        ) : null}

        <ConfigGroup title="运行时上限与保留" rows={LIMITS} config={config.data} />
      </div>
    </div>
  );
}

function Policy({
  term,
  detail,
  source,
}: {
  readonly term: string;
  readonly detail: string;
  readonly source: string;
}): ReactNode {
  return (
    <div>
      <dt className="text-dense font-medium text-ink">{term}</dt>
      <dd className="mt-1 max-w-[92ch] text-dense text-ink-secondary">
        {detail}
        <span className="mt-1 block font-mono text-quote text-ink-muted">{source}</span>
      </dd>
    </div>
  );
}
