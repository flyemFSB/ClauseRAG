/**
 * 知识库文档及其版本数据模型与 API 服务。
 *
 * 封装文档查询、版本详情与解析产物、支持的 MIME 映射与状态枚举转换。
 */

import { useMutation, useQuery, useQueries, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { requestEmpty, requestJson, requestUpload } from "../../lib/api";
import {
  asNullableNumber,
  asNumber,
  asRecord,
  asString,
  asStringArray,
  parseList,
} from "../../lib/contract";
import { documentKeys, documentVersionKeys, knowledgeBaseKeys } from "../../lib/queryKeys";
import type { DocumentStatus } from "../ingestion-jobs/IngestionStatus";
import { useKnowledgeBases } from "../knowledge-bases/api";

export interface DocumentVersion {
  readonly id: string;
  readonly documentId: string;
  readonly versionOrdinal: number;
  readonly status: string;
  readonly mimeType: string;
  readonly checksum: string;
  readonly sizeBytes: number;
  readonly createdAt: string;
  readonly updatedAt: string;
}

export interface DocumentSummary {
  readonly id: string;
  readonly knowledgeBaseId: string;
  readonly title: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly latestVersion: DocumentVersion | null;
}

export function parseDocumentVersion(payload: unknown): DocumentVersion {
  const record = asRecord(payload, "document version");
  return {
    id: asString(record, "id"),
    documentId: asString(record, "document_id"),
    versionOrdinal: asNumber(record, "version_ordinal"),
    status: asString(record, "status"),
    mimeType: asString(record, "mime_type"),
    checksum: asString(record, "checksum"),
    sizeBytes: asNumber(record, "size_bytes"),
    createdAt: asString(record, "created_at"),
    updatedAt: asString(record, "updated_at"),
  };
}

function parseDocumentSummary(payload: unknown): DocumentSummary {
  const record = asRecord(payload, "document");
  const latest = record["latest_version"];
  return {
    id: asString(record, "id"),
    knowledgeBaseId: asString(record, "knowledge_base_id"),
    title: asString(record, "title"),
    createdAt: asString(record, "created_at"),
    updatedAt: asString(record, "updated_at"),
    latestVersion: latest === null || latest === undefined ? null : parseDocumentVersion(latest),
  };
}

export async function fetchDocumentSummaries(
  knowledgeBaseId: string,
  signal: AbortSignal,
): Promise<readonly DocumentSummary[]> {
  const payload = await requestJson(`/api/v1/knowledge-bases/${knowledgeBaseId}/documents`, {
    signal,
  });
  return parseList(payload, "documents", parseDocumentSummary);
}

export function documentSummariesQueryOptions(knowledgeBaseId: string | null) {
  return {
    queryKey: knowledgeBaseKeys.documents(knowledgeBaseId ?? ""),
    queryFn: ({ signal }: { readonly signal: AbortSignal }) =>
      fetchDocumentSummaries(knowledgeBaseId ?? "", signal),
    enabled: knowledgeBaseId !== null,
    staleTime: 10_000,
  };
}

export function useDocumentSummaries(knowledgeBaseId: string | null) {
  return useQuery(documentSummariesQueryOptions(knowledgeBaseId));
}

/** 版本生命周期状态中文标签映射。 */
export const VERSION_STATUS_LABEL: Readonly<Record<string, string>> = {
  uploaded: "已上传",
  parsing: "解析中",
  parsed: "已解析",
  chunking: "分块中",
  embedding: "向量化中",
  indexing: "建索引中",
  ready: "已就绪",
  parse_failed: "解析失败",
  chunk_failed: "分块失败",
  embedding_failed: "向量化失败",
  index_failed: "索引失败",
  manual_retry_required: "需人工重试",
};

export function versionStatusLabel(status: string): string {
  return VERSION_STATUS_LABEL[status] ?? status;
}

/** 判断流水线是否仍在推进该版本处理。 */
export function isVersionMoving(status: string): boolean {
  return !(status === "ready" || status.endsWith("_failed") || status === "manual_retry_required");
}

/** 将版本状态映射为通用的四态状态徽标枚举（queued, running, parsed, failed）。 */
export function documentStatusOf(version: DocumentVersion | null): DocumentStatus {
  if (version === null) {
    return "queued";
  }
  switch (version.status) {
    case "parsed":
    case "ready":
      return "parsed";
    case "parsing":
    case "chunking":
    case "embedding":
    case "indexing":
      return "running";
    case "parse_failed":
    case "chunk_failed":
    case "embedding_failed":
    case "index_failed":
    case "manual_retry_required":
      return "failed";
    default:
      return "queued";
  }
}

/** MIME 类型对应的人类可读名称映射。 */
const MIME_KIND: Readonly<Record<string, string>> = {
  "application/pdf": "PDF",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel",
  "text/plain": "TXT",
  "text/markdown": "Markdown",
  "text/html": "HTML",
  "image/png": "图像",
  "image/jpeg": "图像",
  "image/webp": "图像",
  "image/bmp": "图像",
  "image/tiff": "图像",
};

export function documentKindOf(mimeType: string): string {
  return MIME_KIND[mimeType] ?? mimeType;
}

/** 平台支持上传的文件扩展名列表。 */
export const SUPPORTED_UPLOAD_EXTENSIONS: readonly string[] = [
  ".pdf",
  ".docx",
  ".pptx",
  ".xlsx",
  ".txt",
  ".md",
  ".markdown",
  ".html",
  ".htm",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".bmp",
  ".tif",
  ".tiff",
];

/* — one document, its versions, and the artifact of one version ————————————— */

export interface DocumentDetail {
  readonly id: string;
  readonly knowledgeBaseId: string;
  readonly title: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly versions: readonly DocumentVersion[];
}

/** 解析阶段产物元数据（存储 Markdown 统计）。 */
export interface ParseArtifact {
  readonly parserName: string;
  readonly parserVersion: string;
  readonly pageCount: number | null;
  readonly warnings: readonly string[];
  readonly checksum: string;
  readonly sizeBytes: number;
}

export interface DocumentVersionDetail extends DocumentVersion {
  readonly parseArtifact: ParseArtifact | null;
}

function parseDocumentDetail(payload: unknown): DocumentDetail {
  const record = asRecord(payload, "document detail");
  return {
    id: asString(record, "id"),
    knowledgeBaseId: asString(record, "knowledge_base_id"),
    title: asString(record, "title"),
    createdAt: asString(record, "created_at"),
    updatedAt: asString(record, "updated_at"),
    versions: parseList(record["versions"], "document versions", parseDocumentVersion),
  };
}

function parseParseArtifact(payload: unknown): ParseArtifact | null {
  if (payload === null || payload === undefined) {
    return null;
  }
  const record = asRecord(payload, "parse artifact");
  return {
    parserName: asString(record, "parser_name"),
    parserVersion: asString(record, "parser_version"),
    pageCount: asNullableNumber(record, "page_count"),
    warnings: asStringArray(record, "warnings"),
    checksum: asString(record, "checksum"),
    sizeBytes: asNumber(record, "size_bytes"),
  };
}

export async function fetchDocumentDetail(
  documentId: string,
  signal: AbortSignal,
): Promise<DocumentDetail> {
  return parseDocumentDetail(await requestJson(`/api/v1/documents/${documentId}`, { signal }));
}

export function documentDetailQueryOptions(documentId: string | null) {
  return {
    queryKey: documentKeys.detail(documentId ?? ""),
    queryFn: ({ signal }: { readonly signal: AbortSignal }) =>
      fetchDocumentDetail(documentId ?? "", signal),
    enabled: documentId !== null,
    staleTime: 4_000,
  };
}

export function useDocumentDetail(documentId: string | null) {
  return useQuery(documentDetailQueryOptions(documentId));
}

export async function fetchVersionDetail(
  versionId: string,
  signal: AbortSignal,
): Promise<DocumentVersionDetail> {
  const payload = await requestJson(`/api/v1/document-versions/${versionId}`, { signal });
  const record = asRecord(payload, "document version");
  return {
    ...parseDocumentVersion(payload),
    parseArtifact: parseParseArtifact(record["parse_artifact"]),
  };
}

export function versionDetailQueryOptions(versionId: string | null) {
  return {
    queryKey: documentVersionKeys.detail(versionId ?? ""),
    queryFn: ({ signal }: { readonly signal: AbortSignal }) =>
      fetchVersionDetail(versionId ?? "", signal),
    enabled: versionId !== null,
    staleTime: 4_000,
  };
}

export function useVersionDetail(versionId: string | null) {
  return useQuery(versionDetailQueryOptions(versionId));
}

/** 全局文档目录聚合条目（关联知识库）。 */
export interface CatalogueEntry {
  readonly document: DocumentSummary;
  readonly knowledgeBaseId: string;
  readonly knowledgeBaseName: string;
}

/** 跨所有知识库聚合查询完整文档目录的 Hook。 */
export function useDocumentCatalogue(enabled = true): {
  readonly entries: readonly CatalogueEntry[];
  readonly pending: boolean;
  readonly error: string | null;
} {
  const knowledgeBases = useKnowledgeBases();
  const catalogue = useMemo(() => knowledgeBases.data ?? [], [knowledgeBases.data]);

  const queries = useQueries({
    queries: catalogue.map((knowledgeBase) => ({
      ...documentSummariesQueryOptions(knowledgeBase.id),
      enabled: enabled && knowledgeBases.isSuccess,
    })),
  });

  return useMemo(() => {
    const entries = queries.flatMap((query, index) => {
      const knowledgeBase = catalogue[index];
      if (knowledgeBase === undefined) {
        return [];
      }
      return (query.data ?? []).map((document) => ({
        document,
        knowledgeBaseId: knowledgeBase.id,
        knowledgeBaseName: knowledgeBase.name,
      }));
    });
    const failed = queries.find((query) => query.isError);
    return {
      entries,
      pending: knowledgeBases.isPending || queries.some((query) => query.isPending),
      error:
        knowledgeBases.isError || failed !== undefined
          ? "文档目录没有完整读出来：某个知识库的文档列表请求失败。"
          : null,
    };
  }, [catalogue, knowledgeBases.isError, knowledgeBases.isPending, queries]);
}

const UPLOAD_TIMEOUT_MS = 120_000;
const DELETE_TIMEOUT_MS = 30_000;

/** 上传文档（新建文档或为已有文档创建新版本）。 */
export async function uploadDocument(
  knowledgeBaseId: string,
  file: File,
  signal: AbortSignal,
  documentId?: string,
): Promise<void> {
  await requestUpload(`/api/v1/knowledge-bases/${knowledgeBaseId}/documents`, {
    signal,
    file,
    ...(documentId === undefined ? {} : { extraFields: { document_id: documentId } }),
  });
}

export function useUploadDocument(knowledgeBaseId: string | null) {
  const client = useQueryClient();
  return useMutation<void, unknown, { readonly file: File; readonly documentId?: string }>({
    mutationFn: ({ file, documentId }) =>
      uploadDocument(
        knowledgeBaseId ?? "",
        file,
        AbortSignal.timeout(UPLOAD_TIMEOUT_MS),
        documentId,
      ),
    onSuccess: async () => {
      if (knowledgeBaseId !== null) {
        await client.invalidateQueries({ queryKey: knowledgeBaseKeys.documents(knowledgeBaseId) });
      }
    },
  });
}

/** 删除指定文档及其所有版本。 */
export async function deleteDocument(documentId: string, signal: AbortSignal): Promise<void> {
  await requestEmpty(`/api/v1/documents/${documentId}`, { signal, method: "DELETE" });
}

export function useDeleteDocument(knowledgeBaseId: string | null) {
  const client = useQueryClient();
  return useMutation<void, unknown, string>({
    mutationFn: (documentId: string) =>
      deleteDocument(documentId, AbortSignal.timeout(DELETE_TIMEOUT_MS)),
    onSuccess: async (_result, documentId) => {
      client.removeQueries({ queryKey: documentKeys.detail(documentId) });
      if (knowledgeBaseId !== null) {
        await client.invalidateQueries({ queryKey: knowledgeBaseKeys.documents(knowledgeBaseId) });
      }
    },
  });
}
