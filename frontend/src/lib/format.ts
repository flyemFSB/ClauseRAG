/**
 * 业务数据与指标格式化工具
 *
 * 包含短 UUID 截取、毫秒/秒级耗时、时长区间、字节大小及本地化日期时间格式化。
 */

const SHORT_ID_CHARS = 8;

/** 截取 UUID 后 8 位作为紧凑标识展示 */
export function shortId(id: string): string {
  return id.length <= SHORT_ID_CHARS ? id : id.slice(-SHORT_ID_CHARS);
}

/** 格式化毫秒耗时为 ms 或保留 1 位小数的秒数 */
export function formatMillis(milliseconds: number): string {
  if (milliseconds < 1000) {
    return `${String(milliseconds)} ms`;
  }
  return `${(milliseconds / 1000).toFixed(1)} s`;
}

/** 格式化两时间戳之间的时间跨度（运行中则计算至当前时刻） */
export function formatSpan(from: string, to: string | null, now: number): string {
  const start = Date.parse(from);
  const end = to === null ? now : Date.parse(to);
  if (Number.isNaN(start) || Number.isNaN(end)) {
    return "—";
  }
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) {
    return `${String(seconds)} s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    const remainder = seconds % 60;
    return remainder === 0
      ? `${String(minutes)} min`
      : `${String(minutes)} min ${String(remainder)} s`;
  }
  const hours = Math.floor(minutes / 60);
  return `${String(hours)} h ${String(minutes % 60)} min`;
}

/** 格式化字节大小为 B、KB 或 MB 字符串 */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${String(bytes)} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** 将 ISO-8601 时间戳格式化为本地可读日期时间（精确到分钟） */
export function formatTimestamp(value: string | null): string {
  if (value === null) {
    return "—";
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) {
    return "—";
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed);
}
