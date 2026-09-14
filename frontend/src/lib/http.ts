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

export const apiClient = createClient<paths>({
  baseUrl: API_BASE,
  credentials: "include",
  headers: { "Content-Type": "application/json" },
});

export function unwrap<T extends ApiEnvelope>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): EnvelopeData<T> {
  if (result.error !== undefined) {
    throw new Error(
      `HTTP error ${result.response.status}: ${result.response.statusText}`,
    );
  }

  const envelope = result.data;
  if (!envelope) {
    throw new Error("解析响应失败");
  }
  if (envelope.code !== 200) {
    throw new Error(envelope.message || "请求失败");
  }
  if (envelope.data == null) {
    throw new Error("响应缺少业务数据");
  }

  return envelope.data as EnvelopeData<T>;
}
