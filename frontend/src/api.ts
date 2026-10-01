export type Capsule = {
  id: string
  topic: string
  content: string
  tags: string[]
  freshness: string | null
  source: string | null
  confidence: string
  created_at: string | null
  updated_at: string | null
  archived: boolean
  file_path: string | null
}

export type CapsuleList = {
  items: Capsule[]
  total: number
  limit: number
  offset: number
}

export type ComposeCapsuleItem = {
  id: string
  topic: string
  content: string
  tags: string[]
  confidence: string
  token_estimate: number
  file_path?: string | null
  source?: string | null
  reason?: string
}

export type ComposeResult = {
  context: string
  token_estimate: number
  capsule_count: number
  truncated: boolean
  included_capsules?: ComposeCapsuleItem[]
  excluded_capsules?: ComposeCapsuleItem[]
  total_candidates?: number
  max_tokens?: number
}

export type TagCount = { name: string; count: number }

const API = '/api/v1'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  })
  if (response.status === 204) {
    return undefined as T
  }
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : response.statusText
    throw new Error(detail || `Request failed (${response.status})`)
  }
  return body as T
}

export type Relationship = {
  id: string
  from_capsule_id: string
  to_capsule_id: string
  relationship_type: string
  created_at: string
}

export type CapsuleRelationships = {
  capsule_id: string
  outgoing: Relationship[]
  incoming: Relationship[]
}

export const api = {
  list: (tag?: string) =>
    request<CapsuleList>(`/capsules${tag ? `?tag=${encodeURIComponent(tag)}` : ''}`),
  search: (query: string, tags?: string[]) =>
    request<Capsule[]>('/search', {
      method: 'POST',
      body: JSON.stringify({ query, tags, archived: false }),
    }),
  create: (payload: Partial<Capsule> & { topic: string; content: string }) =>
    request<Capsule>('/capsules', { method: 'POST', body: JSON.stringify(payload) }),
  update: (id: string, payload: Partial<Capsule>) =>
    request<Capsule>(`/capsules/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  remove: (id: string) => request<void>(`/capsules/${id}`, { method: 'DELETE' }),
  archive: (id: string) => request<Capsule>(`/capsules/${id}/archive`, { method: 'POST' }),
  tags: () => request<TagCount[]>('/tags'),
  listRelationships: () => request<Relationship[]>('/relationships'),
  relationships: (capsuleId: string) =>
    request<CapsuleRelationships>(`/capsules/${capsuleId}/relationships`),
  link: (from_id: string, to_id: string, relationship_type = 'relates_to') =>
    request<Relationship>('/relationships', {
      method: 'POST',
      body: JSON.stringify({
        from_capsule_id: from_id,
        to_capsule_id: to_id,
        relationship_type,
      }),
    }),
  compose: (payload: {
    query?: string
    tags?: string[]
    confidence_min?: string
    max_tokens?: number
    mode?: 'fts' | 'semantic' | 'hybrid'
  }) => request<ComposeResult>('/compose', { method: 'POST', body: JSON.stringify(payload) }),
  stale: (days = 90) => request<{ count: number; capsules: Capsule[] }>(`/stale?days=${days}`),
}

