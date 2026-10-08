/**
 * 服务端状态的查询键词表。
 *
 * 查询与失效必须命中同一个键，所以键只在 `queryKey` 与 mutation 失效都引用同一处：把键
 * 散落在各页面事件处理器里，重命名或删除后就只剩手动 `refetch()` 能救场。
 */

export const knowledgeBaseKeys = {
  all: () => ["knowledge-bases"] as const,
  list: () => ["knowledge-bases"] as const,
  documents: (knowledgeBaseId: string) =>
    ["knowledge-bases", knowledgeBaseId, "documents"] as const,
};

export const documentKeys = {
  detail: (documentId: string) => ["documents", documentId] as const,
};

export const documentVersionKeys = {
  all: () => ["document-versions"] as const,
  detail: (versionId: string) => ["document-versions", versionId, "detail"] as const,
  jobs: (versionId: string) => ["document-versions", versionId, "jobs"] as const,
};

export const conversationKeys = {
  list: () => ["conversations"] as const,
  detail: (conversationId: string) => ["conversations", conversationId, "detail"] as const,
};

export const readinessKeys = {
  ready: () => ["health", "ready"] as const,
};

export const configKeys = {
  effective: () => ["config", "effective"] as const,
};
