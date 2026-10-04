export type Confidence = "high" | "medium" | "low" | "hearsay";
export type SearchMode = "fts" | "semantic" | "hybrid";

export interface Capsule {
  id: string;
  topic: string;
  content: string;
  tags: string[];
  freshness: string | null;
  source: string | null;
  confidence: Confidence | string;
  created_at: string | null;
  updated_at: string | null;
  archived: boolean;
  file_path: string | null;
  content_hash?: string | null;
  deduped?: boolean;
}

export interface CapsuleList {
  items: Capsule[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateCapsuleInput {
  topic: string;
  content: string;
  tags?: string[];
  freshness?: string;
  source?: string;
  confidence?: Confidence;
}

export interface UpdateCapsuleInput {
  topic?: string;
  content?: string;
  tags?: string[];
  freshness?: string;
  source?: string;
  confidence?: Confidence;
}

export interface ListCapsulesOptions {
  archived?: boolean;
  tag?: string;
  limit?: number;
  offset?: number;
}

export interface SearchInput {
  query?: string;
  tags?: string[];
  confidence?: Confidence;
  archived?: boolean;
  limit?: number;
  offset?: number;
  mode?: SearchMode;
}

export interface ComposeInput {
  tags?: string[];
  query?: string;
  confidence_min?: Confidence;
  max_tokens?: number;
  mode?: SearchMode;
  graph_expansion?: boolean;
  max_hops?: number;
  affinity_weight?: number;
  include_superseded?: boolean;
}

export interface ComposeCapsule {
  id: string;
  topic: string;
  content: string;
  tags: string[];
  confidence: string;
  token_estimate: number;
  file_path?: string | null;
  source?: string | null;
  reason?: string;
}

export interface ComposeResult {
  context: string;
  token_estimate: number;
  capsule_count: number;
  truncated: boolean;
  included_capsules: ComposeCapsule[];
  excluded_capsules: ComposeCapsule[];
  total_candidates: number;
  max_tokens: number;
  graph_expansion: boolean;
  include_superseded: boolean;
}

export interface Relationship {
  id: string;
  from_capsule_id: string;
  to_capsule_id: string;
  relationship_type: string;
  created_at: string | null;
}

export interface CapsuleRelationships {
  outgoing: Relationship[];
  incoming: Relationship[];
}

export interface TagCount {
  name: string;
  count: number;
}

export interface VaultStatus {
  total: number;
  archived: number;
  active: number;
  tags: number;
  relationships: number;
  database: string;
  dialect: string;
  capsules_dir: string;
}

export interface Health {
  status: string;
  service: string;
  version: string;
  database: string;
  dialect: string;
  capsules: number;
  watcher: boolean;
}

export interface KapsuleClientOptions {
  /** Collector base URL. Default `http://127.0.0.1:9100`. */
  baseUrl?: string;
  /** Sent as `Authorization: Bearer` when `CAPSULE_API_TOKEN` is set on the server. */
  apiToken?: string;
  fetch?: typeof fetch;
}
