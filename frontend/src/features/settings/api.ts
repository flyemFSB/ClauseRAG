/** 系统依赖就绪探针 API，请求 `/health/ready` 获取基础设施运行状态。 */

import { useQuery } from "@tanstack/react-query";
import { requestJson } from "../../lib/api";
import {
  asBoolean,
  asNullableString,
  asNumber,
  asRecord,
  asString,
  parseList,
} from "../../lib/contract";
import { configKeys, readinessKeys } from "../../lib/queryKeys";
import type { MarkTone } from "../../components/state-mark";

const READY_PATH = "/health/ready";
const UNAVAILABLE_STATUS = 503;

export interface DependencyHealth {
  readonly name: string;
  readonly state: string;
  readonly latencyMs: number;
  readonly detail: string | null;
}

export interface ReadinessReport {
  readonly status: string;
  readonly durationMs: number;
  readonly dependencies: readonly DependencyHealth[];
}

function parseDependency(payload: unknown): DependencyHealth {
  const record = asRecord(payload, "dependency");
  return {
    name: asString(record, "name"),
    state: asString(record, "state"),
    latencyMs: asNumber(record, "latency_ms"),
    detail: asNullableString(record, "detail"),
  };
}

export async function fetchReadiness(signal: AbortSignal): Promise<ReadinessReport> {
  const payload = await requestJson(READY_PATH, {
    signal,
    allowStatuses: [UNAVAILABLE_STATUS],
  });
  const record = asRecord(payload, "readiness");
  return {
    status: asString(record, "status"),
    durationMs: asNumber(record, "duration_ms"),
    dependencies: parseList(record["dependencies"], "dependencies", parseDependency),
  };
}

export function readinessQueryOptions() {
  return {
    queryKey: readinessKeys.ready(),
    queryFn: ({ signal }: { readonly signal: AbortSignal }) => fetchReadiness(signal),
    staleTime: 5_000,
  };
}

export function useReadiness() {
  return useQuery(readinessQueryOptions());
}

const CONFIG_PATH = "/api/v1/config";

/** 一项生效配置：密钥项只有 `configured`，没有 `value`。 */
export interface ConfigEntry {
  readonly env: string;
  readonly value: string | null;
  readonly secret: boolean;
  readonly configured: boolean;
}

export interface EffectiveConfig {
  readonly entries: Readonly<Record<string, ConfigEntry>>;
}

function parseConfigEntry(payload: unknown): ConfigEntry {
  const record = asRecord(payload, "config entry");
  return {
    env: asString(record, "env"),
    value: asNullableString(record, "value"),
    secret: asBoolean(record, "secret"),
    configured: asBoolean(record, "configured"),
  };
}

/** 获取本进程实际生效的配置（密钥只报是否已配置）。 */
export async function fetchEffectiveConfig(signal: AbortSignal): Promise<EffectiveConfig> {
  const record = asRecord(await requestJson(CONFIG_PATH, { signal }), "config");
  const entries = parseList(record["entries"], "config entries", parseConfigEntry);
  return { entries: Object.fromEntries(entries.map((entry) => [entry.env, entry])) };
}

export function configQueryOptions() {
  return {
    queryKey: configKeys.effective(),
    queryFn: ({ signal }: { readonly signal: AbortSignal }) => fetchEffectiveConfig(signal),
    staleTime: 60_000,
  };
}

/** 读取本进程生效配置 Hook。 */
export function useConfig() {
  return useQuery(configQueryOptions());
}

/**
 * 一个配置项的展示文本。
 *
 * - 载荷未到时是省略号：那是"还不知道"，不能冒充"没有这一项"；
 * - 密钥项只报已配置 / 未配置，值永远不上屏；
 * - 可选端点为空是"未设置"；
 * - 服务端没报这一项时是破折号——意味着前端认识的项目比后端多，是值漂移的信号，不该被静默忽略。
 */
export function configValue(config: EffectiveConfig | undefined, env: string): string {
  if (config === undefined) {
    return "…";
  }
  const entry = config.entries[env];
  if (entry === undefined) {
    return "—";
  }
  if (entry.secret) {
    return entry.configured ? "已配置" : "未配置";
  }
  if (entry.value === null || entry.value === "") {
    return "未设置";
  }
  return entry.value;
}

export const DEPENDENCY_LABEL: Readonly<Record<string, string>> = {
  postgres: "ParadeDB",
  rabbitmq: "RabbitMQ",
  rustfs: "对象存储",
};

export function dependencyLabel(name: string): string {
  return DEPENDENCY_LABEL[name] ?? name;
}

/** 各基础设施依赖在架构中承担的业务职责说明 */
export const DEPENDENCY_ROLE: Readonly<Record<string, string>> = {
  postgres: "业务事实与会话；pgvector 向量索引与 pg_search BM25 索引；LangGraph 检查点",
  rabbitmq: "唯一的业务队列：摄取任务的传递",
  rustfs: "原始文档与解析产物",
};

export function readinessTone(state: string): MarkTone {
  return state === "healthy" ? "success" : "error";
}

export function readinessLabel(state: string): string {
  switch (state) {
    case "healthy":
      return "可用";
    case "unhealthy":
      return "不可用";
    default:
      return state;
  }
}
