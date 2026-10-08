/**
 * 看板分析指标配置与演示数据。
 *
 * 聚合平台暂无直接统计接口的业务分析指标（置信度、采纳率、合同类型分布示意数据）。
 */

export const SYNTHETIC_NOTICE =
  "看板数值中，知识总量、容量、就绪数、最近更新、流水线吞吐与异常列表来自真实的文档与任务行；检索置信度、引用采纳率与合同类型分布标注为示意——平台没有分析端点，需要新增统计能力。";

export interface ContractTypeShare {
  readonly label: string;
  readonly count: number;
  readonly share: number;
}

/** 检索平均置信度（示意数据）。 */
export const RETRIEVAL_QUALITY = {
  confidence: 0.884,
  label: "88.4%",
  window: "最近 7 天 · 1,284 次问询",
} as const;

/** 引用采纳率（示意数据）。 */
export const CITATION_ADOPTION = {
  adoption: 0.942,
  label: "94.2%",
  window: "法务/审查人员核验或复制引用的比例",
} as const;

/** 审查合同类型分布（示意数据）。 */
export const CONTRACT_TYPES: readonly ContractTypeShare[] = [
  { label: "主服务协议 (MSA)", count: 153, share: 0.38 },
  { label: "保密协议 (NDA)", count: 96, share: 0.24 },
  { label: "SaaS与软件许可", count: 72, share: 0.18 },
  { label: "工作说明书 (SOW)", count: 52, share: 0.13 },
  { label: "其他商业协议", count: 29, share: 0.07 },
];

/** 格式化坐标轴整数计数值。 */
export function formatCount(value: number): string {
  return String(Math.round(value));
}
