import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { requestEmpty, requestJson } from "../../lib/api";
import type { CitationPayload } from "../../lib/sse";
import { conversationKeys } from "../../lib/queryKeys";
import {
  asArray,
  asNullableNumber,
  asNullableString,
  asNumber,
  asRecord,
  asString,
  asStringArray,
  parseList,
} from "../../lib/contract";

const CONVERSATIONS_PATH = "/api/v1/conversations";

const WRITE_TIMEOUT_MS = 15_000;

export interface Conversation {
  readonly id: string;
  readonly knowledgeBaseId: string;
  readonly title: string;
  readonly createdAt: string;
  readonly updatedAt: string;
}

/** 单轮问答消息实体及执行上下文。 */
export interface ChatMessage {
  readonly id: string;
  readonly role: string;
  readonly content: string;
  readonly status: string;
  readonly createdAt: string;
  readonly evidenceStatus: string | null;
  readonly retrievalRounds: number | null;
  readonly intent: string | null;
  readonly finishReason: string | null;
  readonly errorClass: string | null;
  readonly citations: readonly CitationPayload[];
}

export interface ConversationDetail {
  readonly conversation: Conversation;
  readonly messages: readonly ChatMessage[];
}

export function parseConversation(payload: unknown): Conversation {
  const record = asRecord(payload, "conversation");
  return {
    id: asString(record, "id"),
    knowledgeBaseId: asString(record, "knowledge_base_id"),
    title: asString(record, "title"),
    createdAt: asString(record, "created_at"),
    updatedAt: asString(record, "updated_at"),
  };
}

function parseCitationPayload(payload: unknown): CitationPayload {
  const record = asRecord(payload, "citation");
  return {
    citationId: asString(record, "citation_id"),
    documentId: asString(record, "document_id"),
    documentVersionId: asString(record, "document_version_id"),
    documentName: asString(record, "document_name"),
    parentId: asString(record, "parent_id"),
    childIds: asStringArray(record, "child_ids"),
    headingPath: asStringArray(record, "heading_path"),
    lineStart: asNumber(record, "line_start"),
    lineEnd: asNumber(record, "line_end"),
    quote: asString(record, "quote"),
  };
}

function parseMessage(payload: unknown): ChatMessage {
  const record = asRecord(payload, "message");
  return {
    id: asString(record, "id"),
    role: asString(record, "role"),
    content: asString(record, "content"),
    status: asString(record, "status"),
    createdAt: asString(record, "created_at"),
    evidenceStatus: asNullableString(record, "evidence_status"),
    retrievalRounds: asNullableNumber(record, "retrieval_rounds"),
    intent: asNullableString(record, "intent"),
    finishReason: asNullableString(record, "finish_reason"),
    errorClass: asNullableString(record, "error_class"),
    citations: asArray(record, "citations").map(parseCitationPayload),
  };
}

function parseConversationDetail(payload: unknown): ConversationDetail {
  const record = asRecord(payload, "conversation detail");
  return {
    conversation: parseConversation(record["conversation"]),
    messages: parseList(record["messages"], "messages", parseMessage),
  };
}

/** 获取当前用户的所有会话列表。 */
export async function fetchConversations(signal: AbortSignal): Promise<readonly Conversation[]> {
  const payload = await requestJson(CONVERSATIONS_PATH, { signal });
  return parseList(payload, "conversations", parseConversation);
}

export function conversationsQueryOptions() {
  return {
    queryKey: conversationKeys.list(),
    queryFn: ({ signal }: { readonly signal: AbortSignal }) => fetchConversations(signal),
    staleTime: 10_000,
  };
}

/** 查询当前用户会话列表。 */
export function useConversations() {
  return useQuery(conversationsQueryOptions());
}

/** 获取单个会话的详情及历史消息记录。 */
export async function fetchConversationDetail(
  conversationId: string,
  signal: AbortSignal,
): Promise<ConversationDetail> {
  return parseConversationDetail(
    await requestJson(`${CONVERSATIONS_PATH}/${conversationId}`, { signal }),
  );
}

export function conversationDetailQueryOptions(conversationId: string | null) {
  return {
    queryKey: conversationKeys.detail(conversationId ?? ""),
    queryFn: ({ signal }: { readonly signal: AbortSignal }) =>
      fetchConversationDetail(conversationId ?? "", signal),
    enabled: conversationId !== null,
    staleTime: 0,
  };
}

/** 查询单个会话详情 Hook。 */
export function useConversationDetail(conversationId: string | null) {
  return useQuery(conversationDetailQueryOptions(conversationId));
}

/** 在指定知识库下创建新会话。 */
export async function createConversation(
  knowledgeBaseId: string,
  signal: AbortSignal,
  title?: string,
): Promise<Conversation> {
  return parseConversation(
    await requestJson(`/api/v1/knowledge-bases/${knowledgeBaseId}/conversations`, {
      signal,
      method: "POST",
      body: title === undefined ? {} : { title },
    }),
  );
}

/** 修改会话标题。 */
export async function renameConversation(
  conversationId: string,
  title: string,
  signal: AbortSignal,
): Promise<Conversation> {
  return parseConversation(
    await requestJson(`${CONVERSATIONS_PATH}/${conversationId}`, {
      signal,
      method: "PATCH",
      body: { title },
    }),
  );
}

/** 删除指定会话。 */
export async function deleteConversation(
  conversationId: string,
  signal: AbortSignal,
): Promise<void> {
  await requestEmpty(`${CONVERSATIONS_PATH}/${conversationId}`, { signal, method: "DELETE" });
}

/** 创建会话变更 Hook。 */
export function useCreateConversation() {
  const client = useQueryClient();
  return useMutation<
    Conversation,
    unknown,
    { readonly knowledgeBaseId: string; readonly title?: string }
  >({
    mutationFn: ({ knowledgeBaseId, title }) =>
      createConversation(knowledgeBaseId, AbortSignal.timeout(WRITE_TIMEOUT_MS), title),
    onSuccess: async (created) => {
      client.setQueryData<readonly Conversation[]>(conversationKeys.list(), (current) => [
        created,
        ...(current ?? []).filter((entry) => entry.id !== created.id),
      ]);
      await client.invalidateQueries({ queryKey: conversationKeys.list() });
    },
  });
}

/** 重命名会话变更 Hook。 */
export function useRenameConversation() {
  const client = useQueryClient();
  return useMutation<Conversation, unknown, { readonly id: string; readonly title: string }>({
    mutationFn: ({ id, title }) =>
      renameConversation(id, title, AbortSignal.timeout(WRITE_TIMEOUT_MS)),
    onSuccess: async (renamed) => {
      client.setQueryData<readonly Conversation[]>(conversationKeys.list(), (current) =>
        (current ?? []).map((entry) => (entry.id === renamed.id ? renamed : entry)),
      );
      await client.invalidateQueries({ queryKey: conversationKeys.detail(renamed.id) });
    },
  });
}

/** 删除会话变更 Hook。 */
export function useDeleteConversation() {
  const client = useQueryClient();
  return useMutation<void, unknown, string>({
    mutationFn: (conversationId: string) =>
      deleteConversation(conversationId, AbortSignal.timeout(WRITE_TIMEOUT_MS)),
    onSuccess: async (_result, conversationId) => {
      client.setQueryData<readonly Conversation[]>(conversationKeys.list(), (current) =>
        (current ?? []).filter((entry) => entry.id !== conversationId),
      );
      client.removeQueries({ queryKey: conversationKeys.detail(conversationId) });
    },
  });
}
