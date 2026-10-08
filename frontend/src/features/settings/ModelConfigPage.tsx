/**
 * 模型与检索生成配置只读看板
 *
 * 集中展示当前部署在模型选型、召回与上下文预算、融合与门控、生成与引用
 * 等维度的生效参数及对应环境变量映射。
 */

import type { ReactNode } from "react";
import { FailureNotice } from "../../components/failure-notice";
import { ConfigCaveat, ConfigGroup, type ConfigRow } from "./ConfigSheet";
import { useConfig } from "./api";

const MODELS: readonly ConfigRow[] = [
  {
    name: "嵌入模型",
    env: "EMBEDDING_MODEL",
    detail:
      "SiliconFlow 的 OpenAI 兼容接口。契约实测它只回答密集向量，没有稀疏字段，所以这里没有 sparse 的说法。",
  },
  {
    name: "向量维度",
    env: "EMBEDDING_DIMENSION",
    detail:
      "集合就是按它创建的：换模型必须换维度，因此也换一个集合重建，而不是往旧集合里混入别的宽度。",
  },
  {
    name: "生成模型",
    env: "CHAT_MODEL",
    detail:
      "同时承担回答、意图分类与反问。默认是 instruct 而非 reasoning：分类要在一个很小的预算里先给出 JSON。",
  },
  {
    name: "重排模型",
    env: "RERANK_MODEL",
    detail:
      "relevance_score 落在 [0,1]。服务不可用时保留融合顺序，并在结果里标注降级，而不是把缺的分值写成 0。",
  },
];

const BUDGET: readonly ConfigRow[] = [
  { name: "dense 召回数", env: "DENSE_TOP_K", detail: "一次向量检索读多少个点。" },
  {
    name: "keyword 召回数",
    env: "KEYWORD_TOP_K",
    detail: "一次关键词检索读多少行。",
  },
  {
    name: "融合保留数",
    env: "FUSION_LIMIT",
    detail: "RRF 之后进入重排之前的候选上限。",
  },
  {
    name: "重排保留数",
    env: "RERANK_LIMIT",
    detail: "一次重排调用最多带多少条候选；provider 没有文档化上限，这个数是本部署自己定的。",
  },
  {
    name: "父块上限",
    env: "FINAL_PARENT_LIMIT",
    detail: "进入上下文的父块数量：子块负责命中，父块负责提供答案要读的整段。",
  },
  {
    name: "上下文预算",
    env: "MAX_CONTEXT_TOKENS",
    detail: "一次回答可携带的上下文 token 上限；超出就按重排顺序截断。",
  },
  {
    name: "检索轮次上限",
    env: "MAX_RETRIEVAL_ROUNDS",
    detail: "证据门控最多让一次运行再检索一轮，这就是「有界 agent 循环」的那个界。",
  },
];

const FUSION: readonly ConfigRow[] = [
  {
    name: "RRF 常数 k",
    env: "RRF_RANK_CONSTANT",
    detail: "融合公式 RRF(d) = Σ weight_c / (k + rank_c) 的 k。",
  },
  {
    name: "dense 权重",
    env: "DENSE_CHANNEL_WEIGHT",
    detail: "融合时 dense 通道的权重。",
  },
  {
    name: "keyword 权重",
    env: "KEYWORD_CHANNEL_WEIGHT",
    detail: "融合时 keyword 通道的权重。",
  },
  {
    name: "重排阈值",
    env: "MIN_RERANK_SCORE",
    detail:
      "候选要成为证据必须达到的重排分。默认值是刻意保守的占位值，需要在最终语料上标定后再改。",
  },
  {
    name: "单通道超时",
    env: "RETRIEVAL_CHANNEL_TIMEOUT_SECONDS",
    detail: "一个通道超过它就被记为 failed，但不影响其他通道已经答出的内容。",
  },
  {
    name: "整轮超时",
    env: "RETRIEVAL_TIMEOUT_SECONDS",
    detail: "一轮检索的总上限，压在两个通道之上。",
  },
];

const GENERATION: readonly ConfigRow[] = [
  {
    name: "回答 token 上限",
    env: "CHAT_MAX_TOKENS",
    detail:
      "达到上限的运行会带上 provider 自己的 finish_reason（length），这是「被截断」的原始陈述。",
  },
  {
    name: "采样温度",
    env: "CHAT_TEMPERATURE",
    detail: "合同审查问答要的是确定性与可复现，不是天马行空的多样性。",
  },
  {
    name: "携带历史条数",
    env: "CHAT_HISTORY_MESSAGES",
    detail: "提示与分类能看到几条更早的消息；整段历史会让每一轮的成本无上限增长。",
  },
  {
    name: "分类 token 上限",
    env: "QUERY_UNDERSTANDING_MAX_TOKENS",
    detail: "意图分类只答一个很小的 JSON；超了就是分类失败，退回按原问题检索。",
  },
  {
    name: "引用原文长度",
    env: "CITATION_QUOTE_CHARS",
    detail: "引用片段按行边界裁剪的长度上限。",
  },
  {
    name: "无效引用策略",
    env: "CITATION_INVALID_ID_POLICY",
    detail:
      "模型给出了不在本次证据里的引用 id 时：strip 删掉标记并在终态里报告，reject 直接让这次运行失败。两者都不静默接受。",
  },
];

const VECTORS: readonly ConfigRow[] = [
  {
    name: "向量集合",
    env: "QDRANT_COLLECTION",
    detail: "业务子块的集合名。",
  },
];

export function ModelConfigPage(): ReactNode {
  const config = useConfig();

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-5 px-4 py-4 sm:px-5 sm:py-5">
        <header>
          <h1 className="text-title font-semibold text-ink">模型配置</h1>
          <p className="mt-1 max-w-[92ch] text-body text-ink-secondary">
            本部署检索与生成所用的模型、召回预算、融合常量与证据门控。这些值是运行进程启动时读到的配置，改动它们意味着改环境变量并重启进程。
          </p>
        </header>

        <ConfigCaveat>
          这里的值是业务 API 进程<span className="font-medium text-ink">实际读到</span>
          的配置：环境变量（含 <span className="font-mono">.env</span>
          ）覆盖过哪一项，这里就是覆盖后的结果，而不是代码里的默认值。
          密钥项只报是否已配置。改动它们意味着改环境变量并重启进程。
        </ConfigCaveat>

        {config.isError ? (
          <FailureNotice
            title="读不到生效配置"
            detail={config.error instanceof Error ? config.error.message : "未知错误"}
          />
        ) : null}

        <ConfigGroup title="模型" rows={MODELS} config={config.data} />
        <ConfigGroup title="召回与上下文预算" rows={BUDGET} config={config.data} />
        <ConfigGroup title="融合与证据门控" rows={FUSION} config={config.data} />
        <ConfigGroup title="生成与引用" rows={GENERATION} config={config.data} />
        <ConfigGroup title="向量集合" rows={VECTORS} config={config.data} />
      </div>
    </div>
  );
}
