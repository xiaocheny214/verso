const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export interface HttpResponseEnvelope<T> {
  code: number;
  message: string;
  data: T;
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  let envelope: HttpResponseEnvelope<T>;
  try {
    envelope = (await response.json()) as HttpResponseEnvelope<T>;
  } catch {
    if (!response.ok) {
      throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
    }
    throw new Error("解析响应失败");
  }

  if (envelope.code !== 200) {
    throw new Error(envelope.message || "请求失败");
  }

  return envelope.data;
}
