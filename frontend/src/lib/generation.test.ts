/**
 * 代际栅栏（Generation Fence）单测
 *
 * 验证代次递增失效、作废当前代与多实例隔离机制。
 */

import { expect, test } from "vite-plus/test";
import { createGeneration } from "./generation";

test("开始新一代会让此前各代失效", () => {
  const generation = createGeneration();
  const first = generation.begin();
  expect(generation.isCurrent(first)).toBe(true);

  const second = generation.begin();
  expect(generation.isCurrent(first)).toBe(false);
  expect(generation.isCurrent(second)).toBe(true);
});

test("abandon 作废当前代但不再取号", () => {
  const generation = createGeneration();
  const attempt = generation.begin();
  generation.abandon();
  expect(generation.isCurrent(attempt)).toBe(false);

  // 作废后仍支持开启新代次
  const next = generation.begin();
  expect(generation.isCurrent(next)).toBe(true);
  expect(generation.isCurrent(attempt)).toBe(false);
});

test("两个栅栏互不影响", () => {
  const left = createGeneration();
  const right = createGeneration();
  const attempt = left.begin();
  right.begin();
  expect(left.isCurrent(attempt)).toBe(true);
});
