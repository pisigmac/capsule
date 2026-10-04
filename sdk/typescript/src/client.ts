import type {
  Capsule,
  CapsuleList,
  CapsuleRelationships,
  ComposeInput,
  ComposeResult,
  CreateCapsuleInput,
  Health,
  KapsuleClientOptions,
  ListCapsulesOptions,
  Relationship,
  SearchInput,
  TagCount,
  UpdateCapsuleInput,
  VaultStatus,
} from "./types";

export class KapsuleError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    const message =
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "detail" in detail
          ? String((detail as { detail: unknown }).detail)
          : `Kapsule API error ${status}`;
    super(message);
    this.name = "KapsuleError";
    this.status = status;
    this.detail = detail;
  }
}

export class KapsuleClient {
  private readonly baseUrl: string;
  private readonly apiToken?: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: KapsuleClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "http://127.0.0.1:9100").replace(/\/$/, "");
    this.apiToken = options.apiToken;
    this.fetchImpl = options.fetch ?? fetch;
  }

  health(): Promise<Health> {
    return this.request<Health>("GET", "/health");
  }

  status(): Promise<VaultStatus> {
    return this.request<VaultStatus>("GET", "/api/v1/status");
  }

  createCapsule(input: CreateCapsuleInput): Promise<Capsule> {
    return this.request<Capsule>("POST", "/api/v1/capsules", input);
  }

  listCapsules(options: ListCapsulesOptions = {}): Promise<CapsuleList> {
    return this.request<CapsuleList>("GET", "/api/v1/capsules", undefined, options);
  }

  getCapsule(id: string): Promise<Capsule> {
    return this.request<Capsule>("GET", `/api/v1/capsules/${id}`);
  }

  updateCapsule(id: string, input: UpdateCapsuleInput): Promise<Capsule> {
    return this.request<Capsule>("PATCH", `/api/v1/capsules/${id}`, input);
  }

  async deleteCapsule(id: string): Promise<void> {
    await this.request<void>("DELETE", `/api/v1/capsules/${id}`);
  }

  archiveCapsule(id: string): Promise<Capsule> {
    return this.request<Capsule>("POST", `/api/v1/capsules/${id}/archive`);
  }

  search(input: SearchInput = {}): Promise<Capsule[]> {
    return this.request<Capsule[]>("POST", "/api/v1/search", input);
  }

  compose(input: ComposeInput = {}): Promise<ComposeResult> {
    return this.request<ComposeResult>("POST", "/api/v1/compose", input);
  }

  listRelationships(): Promise<Relationship[]> {
    return this.request<Relationship[]>("GET", "/api/v1/relationships");
  }

  createRelationship(
    fromId: string,
    toId: string,
    relationshipType = "relates_to",
  ): Promise<Relationship> {
    return this.request<Relationship>("POST", "/api/v1/relationships", {
      from_capsule_id: fromId,
      to_capsule_id: toId,
      relationship_type: relationshipType,
    });
  }

  capsuleRelationships(id: string): Promise<CapsuleRelationships> {
    return this.request<CapsuleRelationships>("GET", `/api/v1/capsules/${id}/relationships`);
  }

  listTags(): Promise<TagCount[]> {
    return this.request<TagCount[]>("GET", "/api/v1/tags");
  }

  stale(days = 90): Promise<{ count: number; capsules: Capsule[] }> {
    return this.request("GET", "/api/v1/stale", undefined, { days });
  }

  sync(): Promise<{ synced: number; directory: string }> {
    return this.request("POST", "/api/v1/sync");
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    query?: object,
  ): Promise<T> {
    const url = new URL(this.baseUrl + path);
    if (query) {
      for (const [key, value] of Object.entries(query as Record<string, unknown>)) {
        if (value !== undefined && value !== null) {
          url.searchParams.set(key, String(value));
        }
      }
    }

    const headers: Record<string, string> = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (this.apiToken) headers.Authorization = `Bearer ${this.apiToken}`;

    const response = await this.fetchImpl(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    if (response.status === 204) return undefined as T;

    const text = await response.text();
    const parsed = text ? (JSON.parse(text) as unknown) : undefined;
    if (!response.ok) throw new KapsuleError(response.status, parsed);
    return parsed as T;
  }
}
