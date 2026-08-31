import { useCallback, useEffect, useState, type FormEvent, type MouseEvent } from 'react'
import {
  Archive,
  Clock,
  Copy,
  Layers,
  Plus,
  Search,
  Sparkles,
  Target,
  Trash2,
  X,
} from 'lucide-react'
import { api, type Capsule, type ComposeResult, type TagCount } from './api'

type View = 'library' | 'compose' | 'stale'
type Draft = {
  id?: string
  topic: string
  content: string
  tags: string
  confidence: string
}

const EMPTY_DRAFT: Draft = { topic: '', content: '', tags: '', confidence: 'medium' }

function App() {
  const [view, setView] = useState<View>('library')
  const [capsules, setCapsules] = useState<Capsule[]>([])
  const [tags, setTags] = useState<TagCount[]>([])
  const [activeTag, setActiveTag] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT)
  const [composeQuery, setComposeQuery] = useState('')
  const [composeTags, setComposeTags] = useState('')
  const [composeMin, setComposeMin] = useState('medium')
  const [composeTokens, setComposeTokens] = useState(2000)
  const [composed, setComposed] = useState<ComposeResult | null>(null)
  const [stale, setStale] = useState<Capsule[]>([])

  const fail = (err: unknown) => {
    setError(err instanceof Error ? err.message : 'Something went wrong')
  }

  const refreshTags = useCallback(async () => {
    try {
      setTags(await api.tags())
    } catch (err) {
      fail(err)
    }
  }, [])

  const loadLibrary = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      if (searchQuery.trim()) {
        const results = await api.search(
          searchQuery.trim(),
          activeTag ? [activeTag] : undefined,
        )
        setCapsules(results)
      } else {
        const data = await api.list(activeTag || undefined)
        setCapsules(data.items)
      }
      await refreshTags()
    } catch (err) {
      fail(err)
    } finally {
      setLoading(false)
    }
  }, [searchQuery, activeTag, refreshTags])

  useEffect(() => {
    void loadLibrary()
  }, [loadLibrary])

  const loadStale = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.stale(90)
      setStale(data.capsules)
    } catch (err) {
      fail(err)
    } finally {
      setLoading(false)
    }
  }

  const runCompose = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const tagList = composeTags.split(',').map((item) => item.trim()).filter(Boolean)
      setComposed(
        await api.compose({
          query: composeQuery || undefined,
          tags: tagList.length ? tagList : undefined,
          confidence_min: composeMin,
          max_tokens: composeTokens,
        }),
      )
    } catch (err) {
      fail(err)
    } finally {
      setLoading(false)
    }
  }

  const saveDraft = async (event: FormEvent) => {
    event.preventDefault()
    const tagsArray = draft.tags.split(',').map((item) => item.trim()).filter(Boolean)
    try {
      if (draft.id) {
        await api.update(draft.id, {
          topic: draft.topic,
          content: draft.content,
          tags: tagsArray,
          confidence: draft.confidence,
        })
      } else {
        await api.create({
          topic: draft.topic,
          content: draft.content,
          tags: tagsArray,
          confidence: draft.confidence,
        })
      }
      setModalOpen(false)
      setDraft(EMPTY_DRAFT)
      await loadLibrary()
    } catch (err) {
      fail(err)
    }
  }

  const removeCapsule = async (id: string, event: MouseEvent) => {
    event.stopPropagation()
    if (!confirm('Delete this capsule file and its index row?')) return
    try {
      await api.remove(id)
      await loadLibrary()
    } catch (err) {
      fail(err)
    }
  }

  const archiveCapsule = async (id: string, event: MouseEvent) => {
    event.stopPropagation()
    try {
      await api.archive(id)
      await loadLibrary()
    } catch (err) {
      fail(err)
    }
  }

  const openEdit = (capsule: Capsule) => {
    setDraft({
      id: capsule.id,
      topic: capsule.topic,
      content: capsule.content,
      tags: capsule.tags.join(', '),
      confidence: capsule.confidence,
    })
    setModalOpen(true)
  }

  const copyContext = async () => {
    if (!composed?.context) return
    await navigator.clipboard.writeText(composed.context)
  }

  return (
    <div className="app-container">
      <header className="header">
        <div className="header-title">
          <Sparkles size={28} />
          <div>
            <h1 style={{ margin: 0, fontSize: '1.8rem' }}>Capsule</h1>
            <p className="header-sub">Atomic knowledge. Files are the source of truth.</p>
          </div>
        </div>

        <nav className="view-tabs" aria-label="Primary">
          <button className={view === 'library' ? 'tab active' : 'tab'} onClick={() => setView('library')}>
            Library
          </button>
          <button
            className={view === 'compose' ? 'tab active' : 'tab'}
            onClick={() => setView('compose')}
          >
            Compose
          </button>
          <button
            className={view === 'stale' ? 'tab active' : 'tab'}
            onClick={() => {
              setView('stale')
              void loadStale()
            }}
          >
            Stale
          </button>
        </nav>

        <button
          className="btn btn-primary"
          onClick={() => {
            setDraft(EMPTY_DRAFT)
            setModalOpen(true)
          }}
        >
          <Plus size={18} />
          New Capsule
        </button>
      </header>

      {error ? (
        <div className="error-banner" role="alert">
          <span>{error}</span>
          <button className="btn-ghost" onClick={() => setError('')}>
            <X size={16} />
          </button>
        </div>
      ) : null}

      {view === 'library' ? (
        <>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void loadLibrary()
            }}
            className="search-bar"
          >
            <Search size={18} color="var(--text-secondary)" />
            <input
              type="search"
              placeholder="Search capsules"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </form>

          {tags.length > 0 ? (
            <div className="tag-list filter-row">
              <button
                className={activeTag === '' ? 'tag active' : 'tag'}
                onClick={() => setActiveTag('')}
              >
                all
              </button>
              {tags.map((tag) => (
                <button
                  key={tag.name}
                  className={activeTag === tag.name ? 'tag active' : 'tag'}
                  onClick={() => setActiveTag(tag.name === activeTag ? '' : tag.name)}
                >
                  #{tag.name} {tag.count}
                </button>
              ))}
            </div>
          ) : null}

          {loading ? (
            <div className="loading-state">
              <div className="spinner">
                <Sparkles size={32} />
              </div>
              <p>Loading capsules…</p>
            </div>
          ) : capsules.length === 0 ? (
            <div className="empty-state glass">
              <Layers size={48} color="var(--text-secondary)" />
              <h2>No capsules found</h2>
              <p>Create a fact, or drop a .capsule.md file into the capsules directory.</p>
            </div>
          ) : (
            <div className="capsule-grid">
              {capsules.map((capsule) => (
                <div key={capsule.id} className="capsule-card glass" onClick={() => openEdit(capsule)}>
                  <div className="capsule-header">
                    <h3 className="capsule-title">{capsule.topic}</h3>
                    <div className="card-actions">
                      <button className="btn-ghost icon" onClick={(event) => void archiveCapsule(capsule.id, event)} title="Archive">
                        <Archive size={16} />
                      </button>
                      <button className="btn-ghost icon" onClick={(event) => void removeCapsule(capsule.id, event)} title="Delete">
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                  <div className="capsule-content">{capsule.content}</div>
                  {capsule.tags.length > 0 ? (
                    <div className="tag-list">
                      {capsule.tags.map((tag) => (
                        <span key={tag} className="tag">#{tag}</span>
                      ))}
                    </div>
                  ) : null}
                  <div className="capsule-footer">
                    <div className="confidence-badge">
                      <Target size={14} className={`confidence-${capsule.confidence}`} />
                      <span style={{ textTransform: 'capitalize' }}>{capsule.confidence}</span>
                    </div>
                    <div className="confidence-badge">
                      <Clock size={14} />
                      <span>
                        {capsule.updated_at
                          ? new Date(capsule.updated_at).toLocaleDateString()
                          : '—'}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      ) : null}

      {view === 'compose' ? (
        <section className="compose-layout">
          <form className="glass compose-form" onSubmit={(event) => void runCompose(event)}>
            <h2>Compose context</h2>
            <p className="header-sub">Build a token-budgeted window for an agent session.</p>
            <div className="input-group">
              <label htmlFor="compose-query">Query</label>
              <input
                id="compose-query"
                className="input"
                value={composeQuery}
                onChange={(event) => setComposeQuery(event.target.value)}
                placeholder="auth middleware"
              />
            </div>
            <div className="input-group">
              <label htmlFor="compose-tags">Tags (comma separated)</label>
              <input
                id="compose-tags"
                className="input"
                value={composeTags}
                onChange={(event) => setComposeTags(event.target.value)}
                placeholder="auth, staging"
              />
            </div>
            <div className="compose-row">
              <div className="input-group">
                <label htmlFor="compose-min">Minimum confidence</label>
                <select
                  id="compose-min"
                  className="input"
                  value={composeMin}
                  onChange={(event) => setComposeMin(event.target.value)}
                >
                  <option value="hearsay">Hearsay</option>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                </select>
              </div>
              <div className="input-group">
                <label htmlFor="compose-tokens">Max tokens</label>
                <input
                  id="compose-tokens"
                  className="input"
                  type="number"
                  min={50}
                  max={32000}
                  value={composeTokens}
                  onChange={(event) => setComposeTokens(Number(event.target.value))}
                />
              </div>
            </div>
            <button className="btn btn-primary" type="submit" disabled={loading}>
              Compose
            </button>
          </form>
          <div className="glass compose-output">
            <div className="modal-header">
              <h2>Output</h2>
              <button className="btn btn-ghost" type="button" onClick={() => void copyContext()} disabled={!composed?.context}>
                <Copy size={16} />
                Copy
              </button>
            </div>
            {composed ? (
              <>
                <p className="header-sub">
                  {composed.capsule_count} capsules · ~{composed.token_estimate} tokens
                  {composed.truncated ? ' · truncated' : ''}
                </p>
                <pre className="compose-pre">{composed.context || '(empty)'}</pre>
              </>
            ) : (
              <p className="header-sub">Run compose to fill an agent context window.</p>
            )}
          </div>
        </section>
      ) : null}

      {view === 'stale' ? (
        <section>
          <h2>Stale capsules</h2>
          <p className="header-sub">Not updated in 90 days. Archive or refresh them.</p>
          {stale.length === 0 ? (
            <div className="empty-state glass">
              <Clock size={48} color="var(--text-secondary)" />
              <h2>Nothing stale</h2>
              <p>Every indexed capsule has been touched recently.</p>
            </div>
          ) : (
            <div className="capsule-grid">
              {stale.map((capsule) => (
                <div key={capsule.id} className="capsule-card glass" onClick={() => openEdit(capsule)}>
                  <h3 className="capsule-title">{capsule.topic}</h3>
                  <p className="capsule-content">{capsule.content}</p>
                  <div className="capsule-footer">
                    <span>{capsule.updated_at ? new Date(capsule.updated_at).toLocaleDateString() : 'unknown'}</span>
                    <button className="btn-ghost" onClick={(event) => void archiveCapsule(capsule.id, event)}>
                      Archive
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      ) : null}

      {modalOpen ? (
        <div className="modal-overlay" onClick={() => setModalOpen(false)}>
          <div className="modal-content glass" onClick={(event) => event.stopPropagation()}>
            <div className="modal-header">
              <h2>{draft.id ? 'Edit Capsule' : 'New Capsule'}</h2>
              <button className="btn-ghost icon" onClick={() => setModalOpen(false)}>
                <X size={20} />
              </button>
            </div>
            <form onSubmit={(event) => void saveDraft(event)}>
              <div className="input-group">
                <label htmlFor="topic">Topic</label>
                <input
                  id="topic"
                  className="input"
                  value={draft.topic}
                  onChange={(event) => setDraft({ ...draft, topic: event.target.value })}
                  required
                  minLength={3}
                  placeholder="Auth bypass in staging"
                />
              </div>
              <div className="input-group">
                <label htmlFor="content">Content</label>
                <textarea
                  id="content"
                  className="textarea"
                  rows={7}
                  value={draft.content}
                  onChange={(event) => setDraft({ ...draft, content: event.target.value })}
                  required
                  minLength={10}
                  placeholder="One fact, fully qualified."
                />
              </div>
              <div className="input-group">
                <label htmlFor="tags">Tags (comma separated)</label>
                <input
                  id="tags"
                  className="input"
                  value={draft.tags}
                  onChange={(event) => setDraft({ ...draft, tags: event.target.value })}
                  placeholder="security, auth, bug"
                />
              </div>
              <div className="input-group">
                <label htmlFor="confidence">Confidence</label>
                <select
                  id="confidence"
                  className="input"
                  value={draft.confidence}
                  onChange={(event) => setDraft({ ...draft, confidence: event.target.value })}
                >
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                  <option value="hearsay">Hearsay</option>
                </select>
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Save Capsule
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default App
