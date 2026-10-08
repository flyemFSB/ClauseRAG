/**
 * 知识库数据模型与 API 服务。
 *
 * 提供知识库列表查询、创建、更新（重命名/清除描述）与级联删除。
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { requestEmpty, requestJson } from "../../lib/api";
import { asNullableString, asRecord, asString, parseList } from "../../lib/contract";
import { knowledgeBaseKeys } from "../../lib/queryKeys";

export interface KnowledgeBase {
  readonly id: string;
  readonly name: string;
  readonly description: string | null;
  readonly createdAt: string;
  readonly updatedAt: string;
}

export function parseKnowledgeBase(payload: unknown): KnowledgeBase {
  const record = asRecord(payload, "knowledge base");
  return {
    id: asString(record, "id"),
    name: asString(record, "name"),
    description: asNullableString(record, "description"),
    createdAt: asString(record, "created_at"),
    updatedAt: asString(record, "updated_at"),
  };
}

export async function fetchKnowledgeBases(signal: AbortSignal): Promise<readonly KnowledgeBase[]> {
  const payload = await requestJson("/api/v1/knowledge-bases", { signal });
  return parseList(payload, "knowledge bases", parseKnowledgeBase);
}

export function knowledgeBasesQueryOptions() {
  return {
    queryKey: knowledgeBaseKeys.list(),
    queryFn: ({ signal }: { readonly signal: AbortSignal }) => fetchKnowledgeBases(signal),
    staleTime: 30_000,
  };
}

export function useKnowledgeBases() {
  return useQuery(knowledgeBasesQueryOptions());
}

const WRITE_TIMEOUT_MS = 15_000;

/** 创建新知识库。 */
export async function createKnowledgeBase(
  name: string,
  description: string | null,
  signal: AbortSignal,
): Promise<KnowledgeBase> {
  return parseKnowledgeBase(
    await requestJson("/api/v1/knowledge-bases", {
      signal,
      method: "POST",
      body: { name, description },
    }),
  );
}

export function useCreateKnowledgeBase() {
  const client = useQueryClient();
  return useMutation<
    KnowledgeBase,
    unknown,
    { readonly name: string; readonly description: string | null }
  >({
    mutationFn: ({ name, description }) =>
      createKnowledgeBase(name, description, AbortSignal.timeout(WRITE_TIMEOUT_MS)),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: knowledgeBaseKeys.list() });
    },
  });
}

/** 更新知识库名称或描述（支持清空描述）。 */
export async function updateKnowledgeBase(
  knowledgeBaseId: string,
  changes: { readonly name?: string; readonly description?: string | null },
  signal: AbortSignal,
): Promise<KnowledgeBase> {
  return parseKnowledgeBase(
    await requestJson(`/api/v1/knowledge-bases/${knowledgeBaseId}`, {
      signal,
      method: "PATCH",
      body: changes,
    }),
  );
}

export function useUpdateKnowledgeBase() {
  const client = useQueryClient();
  return useMutation<
    KnowledgeBase,
    unknown,
    { readonly id: string; readonly name?: string; readonly description?: string | null }
  >({
    mutationFn: ({ id, ...changes }) =>
      updateKnowledgeBase(id, changes, AbortSignal.timeout(WRITE_TIMEOUT_MS)),
    onSuccess: (updated) => {
      client.setQueryData<readonly KnowledgeBase[]>(knowledgeBaseKeys.list(), (current) =>
        current?.map((entry) => (entry.id === updated.id ? updated : entry)),
      );
    },
  });
}

/** 级联删除知识库（一并删除所属文档、版本与相关索引）。 */
export async function deleteKnowledgeBase(
  knowledgeBaseId: string,
  signal: AbortSignal,
): Promise<void> {
  await requestEmpty(`/api/v1/knowledge-bases/${knowledgeBaseId}`, {
    signal,
    method: "DELETE",
  });
}

export function useDeleteKnowledgeBase() {
  const client = useQueryClient();
  return useMutation<void, unknown, string>({
    mutationFn: (knowledgeBaseId: string) =>
      deleteKnowledgeBase(knowledgeBaseId, AbortSignal.timeout(WRITE_TIMEOUT_MS)),
    onSuccess: async (_result, knowledgeBaseId) => {
      client.removeQueries({ queryKey: knowledgeBaseKeys.documents(knowledgeBaseId) });
      await client.invalidateQueries({ queryKey: knowledgeBaseKeys.list() });
    },
  });
}
