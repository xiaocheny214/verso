import createClient from "openapi-fetch";

import type { paths } from "@/lib/api/schema";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

interface ApiEnvelope {
  code?: number;
  message?: string;
  data?: unknown;
}

type EnvelopeData<T> = T extends { data?: infer Data }
  ? NonNullable<Data>
  : never;

export class ApiError extends Error {
  readonly code: number;

  constructor(code: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.code = code;
  }
}

export function isUnauthenticated(error: unknown): boolean {
  return error instanceof ApiError && error.code === 401;
}

export const apiClient = createClient<paths>({
  baseUrl: API_BASE,
  credentials: "include",
  headers: { "Content-Type": "application/json" },
});

function readEnvelope<T extends ApiEnvelope>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (result.error !== undefined) {
    throw new ApiError(
      result.response.status,
      `HTTP error ${result.response.status}: ${result.response.statusText}`,
    );
  }

  const envelope = result.data;
  if (!envelope) {
    throw new ApiError(0, "解析响应失败");
  }
  if (envelope.code !== 200) {
    throw new ApiError(envelope.code ?? 0, envelope.message || "请求失败");
  }
  return envelope;
}

export function unwrap<T extends ApiEnvelope>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): EnvelopeData<T> {
  const envelope = readEnvelope(result);
  if (envelope.data == null) {
    throw new ApiError(envelope.code ?? 0, "响应缺少业务数据");
  }

  return envelope.data as EnvelopeData<T>;
}

export function unwrapVoid<T extends ApiEnvelope>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): void {
  readEnvelope(result);
}
