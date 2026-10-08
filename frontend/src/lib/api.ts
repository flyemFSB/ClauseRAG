/**
 * 通用 HTTP/JSON 请求传输层封装
 *
 * 支持调用方传递 AbortSignal 中止信号、显式超时控制与结构化 ApiError 异常分类。
 */

const DEFAULT_TIMEOUT_MS = 10_000;

export type ApiFailureKind = "timeout" | "aborted" | "network" | "http" | "malformed";

export class ApiError extends Error {
  readonly kind: ApiFailureKind;
  readonly status: number | undefined;

  constructor(kind: ApiFailureKind, message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

/** 构造响应结构契约校验失败的 ApiError 实例 */
export function malformed(message: string): ApiError {
  return new ApiError("malformed", message);
}

/** 业务视图常用特定状态码常量 */
export const NOT_FOUND_STATUS = 404;
export const CONFLICT_STATUS = 409;

export interface JsonRequestOptions {
  /** 调用方持有的请求中止信号 */
  readonly signal: AbortSignal;
  readonly method?: "GET" | "POST" | "PATCH" | "DELETE";
  /** 请求体（自动序列化为 JSON 并设置 Content-Type） */
  readonly body?: unknown;
  readonly timeoutMs?: number;
  /** 允许返回的非 2xx 状态码列表（如 503 就绪探测报告） */
  readonly allowStatuses?: readonly number[];
}

export async function requestJson(path: string, options: JsonRequestOptions): Promise<unknown> {
  const response = await send(path, options);
  try {
    return await response.json();
  } catch (cause) {
    throw new ApiError("malformed", `${path} answered a body that is not JSON: ${describe(cause)}`);
  }
}

/** 发送无响应体的请求（如 204 No Content） */
export async function requestEmpty(path: string, options: JsonRequestOptions): Promise<void> {
  await send(path, options);
}

/** 发送 multipart/form-data 文件上传请求 */
export async function requestUpload(
  path: string,
  options: {
    readonly signal: AbortSignal;
    readonly file: File;
    readonly field?: string;
    /** 附加表单字段（如 document_id） */
    readonly extraFields?: Readonly<Record<string, string>>;
  },
): Promise<unknown> {
  const form = new FormData();
  form.append(options.field ?? "file", options.file, options.file.name);
  for (const [name, value] of Object.entries(options.extraFields ?? {})) {
    form.append(name, value);
  }
  const response = await send(path, {
    signal: options.signal,
    method: "POST",
    rawBody: form,
    timeoutMs: 120_000,
  });
  try {
    return await response.json();
  } catch (cause) {
    throw new ApiError("malformed", `${path} answered a body that is not JSON: ${describe(cause)}`);
  }
}

interface RawRequestOptions {
  readonly signal: AbortSignal;
  readonly method?: string;
  readonly rawBody?: BodyInit;
  readonly body?: unknown;
  readonly timeoutMs?: number;
  readonly accept?: string;
  readonly allowStatuses?: readonly number[];
}

async function send(path: string, options: RawRequestOptions): Promise<Response> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const headers: Record<string, string> = { accept: options.accept ?? "application/json" };
  let body: BodyInit | undefined;
  if (options.rawBody !== undefined) {
    body = options.rawBody;
  } else if (options.body !== undefined) {
    headers["content-type"] = "application/json";
    body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method: options.method ?? "GET",
      headers,
      body,
      signal: AbortSignal.any([options.signal, timeoutSignal]),
    });
  } catch (cause) {
    if (options.signal.aborted) {
      throw new ApiError("aborted", `${path} was cancelled`);
    }
    if (timeoutSignal.aborted) {
      throw new ApiError("timeout", `${path} timed out after ${timeoutMs} ms`);
    }
    throw new ApiError("network", `${path} could not be reached: ${describe(cause)}`);
  }

  if (!response.ok && !(options.allowStatuses ?? []).includes(response.status)) {
    throw new ApiError("http", await describeHttpFailure(path, response), response.status);
  }
  return response;
}

/** 解析后端返回的 HTTP 错误详情（兼容 FastAPI 校验错误结构与通用 detail 字段） */
async function describeHttpFailure(path: string, response: Response): Promise<string> {
  const fallback = `${path} answered HTTP ${response.status}`;
  try {
    const payload: unknown = await response.json();
    if (typeof payload === "object" && payload !== null && "detail" in payload) {
      const detail = (payload as { detail: unknown }).detail;
      if (typeof detail === "string") {
        return `${fallback}: ${detail}`;
      }
      if (Array.isArray(detail)) {
        const messages = detail
          .map((entry) =>
            typeof entry === "object" && entry !== null && "msg" in entry
              ? String((entry as { msg: unknown }).msg)
              : "",
          )
          .filter((message) => message.length > 0);
        if (messages.length > 0) {
          return `${fallback}: ${messages.join("; ")}`;
        }
      }
    }
  } catch {
    // 响应体非 JSON 时退化显示状态码
  }
  return fallback;
}

function describe(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}
