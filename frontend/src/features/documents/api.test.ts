/**
 * 文档版本推进状态判定逻辑单元测试。
 *
 * 验证各落定状态（不再轮询）与进行中状态（继续轮询）的正确映射。
 */

import { expect, test } from "vite-plus/test";
import { documentSummariesQueryOptions, isVersionMoving, versionDetailQueryOptions } from "./api";
import { knowledgeBaseKeys } from "../../lib/queryKeys";

test.each([
  "ready",
  "parse_failed",
  "chunk_failed",
  "embedding_failed",
  "index_failed",
  "manual_retry_required",
])("落定，不再轮询：%s", (status) => {
  expect(isVersionMoving(status)).toBe(false);
});

test.each(["uploaded", "parsing", "parsed", "chunking", "embedding", "indexing"])(
  "仍在推进，继续轮询：%s",
  (status) => {
    expect(isVersionMoving(status)).toBe(true);
  },
);

test("没见过的状态按仍在推进处理", () => {
  // 保守方向是对的：多问一次只是多一次请求，少问一次会让页面停在过期的进度上。
  expect(isVersionMoving("parsing_paused")).toBe(true);
});

test("文档列表查询与失效命中同一个键", () => {
  // 这是 mutation 能替页面刷新缓存的前提：两边各写一份键，重命名或删除后就会悄悄失配。
  expect(documentSummariesQueryOptions("kb-1").queryKey).toEqual(
    knowledgeBaseKeys.documents("kb-1"),
  );
});

test("版本详情查询与失效命中同一个键", () => {
  expect(versionDetailQueryOptions("v-1").queryKey).toEqual(["document-versions", "v-1", "detail"]);
});
