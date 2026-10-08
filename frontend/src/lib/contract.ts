/**
 * 前后端契约响应解析与数据类型校验工具
 *
 * 提供基础类型（对象、字符串、数值、布尔、枚举、数组）的安全校验与断言函数，
 * 校验失败时统一抛出包含字段详情的 ApiError("malformed")。
 */

import { malformed } from "./api";

export type JsonObject = Record<string, unknown>;

export function asRecord(value: unknown, label: string): JsonObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw malformed(`${label} is not an object`);
  }
  return value as JsonObject;
}

export function asString(record: JsonObject, key: string): string {
  const value = record[key];
  if (typeof value !== "string") {
    throw malformed(`${key} is ${JSON.stringify(value)}`);
  }
  return value;
}

export function asNullableString(record: JsonObject, key: string): string | null {
  const value = record[key];
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== "string") {
    throw malformed(`${key} is ${JSON.stringify(value)}`);
  }
  return value;
}

export function asNumber(record: JsonObject, key: string): number {
  const value = record[key];
  if (typeof value !== "number") {
    throw malformed(`${key} is ${JSON.stringify(value)}`);
  }
  return value;
}

export function asNullableNumber(record: JsonObject, key: string): number | null {
  const value = record[key];
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value !== "number") {
    throw malformed(`${key} is ${JSON.stringify(value)}`);
  }
  return value;
}

export function asBoolean(record: JsonObject, key: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") {
    throw malformed(`${key} is ${JSON.stringify(value)}`);
  }
  return value;
}

export function asStringArray(record: JsonObject, key: string): readonly string[] {
  const value = record[key];
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string")) {
    throw malformed(`${key} is not an array of strings`);
  }
  return value as readonly string[];
}

export function asArray(record: JsonObject, key: string): readonly unknown[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw malformed(`${key} is not an array`);
  }
  return value;
}

/** 读取受限字符串枚举值 */
export function asEnum<T extends string>(
  record: JsonObject,
  key: string,
  allowed: readonly T[],
): T {
  const value = record[key];
  if (typeof value !== "string" || !allowed.includes(value as T)) {
    throw malformed(`${key} is ${JSON.stringify(value)}, and not one of ${allowed.join(", ")}`);
  }
  return value as T;
}

/** 解析数组列表，确保载荷为合法数组后逐项映射 */
export function parseList<T>(
  payload: unknown,
  label: string,
  parse: (entry: unknown) => T,
): readonly T[] {
  if (!Array.isArray(payload)) {
    throw malformed(`${label} is not an array`);
  }
  return payload.map(parse);
}
