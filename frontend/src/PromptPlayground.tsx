import { useState, useEffect, useCallback, useId } from 'react'
import {
  Sparkles,
  Zap,
  Brain,
  Globe,
  Copy,
  Check,
  Layers,
  AlertCircle,
  Sliders,
  Download,
  ShieldCheck,
  FileText,
  Tag,
  Gauge,
  Maximize2,
  Minimize2,
  RefreshCw,
} from 'lucide-react'
import { api, type ComposeResult, type TagCount } from './api'

interface PromptPlaygroundProps {
  initialTags?: TagCount[]
  onSelectCapsule?: (id: string) => void
}

const TOKEN_PRESETS = [
  { label: '1k (Fast Hook)', tokens: 1000 },
  { label: '2k (Standard)', tokens: 2000 },
  { label: '4k (Deep Context)', tokens: 4000 },
  { label: '8k (Extended)', tokens: 8000 },
  { label: '16k (Massive)', tokens: 16000 },
]

export function PromptPlayground({ initialTags = [], onSelectCapsule }: PromptPlaygroundProps) {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<'fts' | 'semantic' | 'hybrid'>('hybrid')
  const [confidenceMin, setConfidenceMin] = useState('medium')
  const [maxTokens, setMaxTokens] = useState(4000)
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [availableTags, setAvailableTags] = useState<TagCount[]>(initialTags)
  const [tagInput, setTagInput] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [composed, setComposed] = useState<ComposeResult | null>(null)
  const [copied, setCopied] = useState(false)
  const [activeTab, setActiveTab] = useState<'knapsack' | 'preview'>('knapsack')
  const [rawView, setRawView] = useState(false)
  const [autoCompose, setAutoCompose] = useState(true)

  const tokenSliderId = useId()

  const fetchTags = useCallback(async () => {
    try {
      const data = await api.tags()
      setAvailableTags(data)
    } catch {
      // fallback to initialTags
    }
  }, [])

  useEffect(() => {
    if (initialTags.length === 0) {
      void fetchTags()
    }
  }, [fetchTags, initialTags.length])

  const executeCompose = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.compose({
        query: query.trim() || undefined,
        tags: selectedTags.length > 0 ? selectedTags : undefined,
        confidence_min: confidenceMin,
        max_tokens: maxTokens,
        mode: mode,
      })
      setComposed(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Context composition failed')
    } finally {
      setLoading(false)
    }
  }, [query, selectedTags, confidenceMin, maxTokens, mode])

  // Run initial compose and debounced auto-compose
  useEffect(() => {
    if (!autoCompose) return
    const timer = setTimeout(() => {
      void executeCompose()
    }, 300)
    return () => clearTimeout(timer)
  }, [executeCompose, autoCompose])

  const handleCopy = async () => {
    if (!composed?.context) return
    try {
      await navigator.clipboard.writeText(composed.context)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy context:', err)
    }
  }

  const handleDownload = () => {
    if (!composed?.context) return
    const blob = new Blob([composed.context], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `capsule-context-${new Date().toISOString().slice(0, 10)}.md`
    link.click()
    URL.revokeObjectURL(url)
  }

  const toggleTag = (tagName: string) => {
    setSelectedTags((prev) =>
      prev.includes(tagName) ? prev.filter((t) => t !== tagName) : [...prev, tagName],
    )
  }

  const addCustomTag = () => {
    const cleaned = tagInput.trim().toLowerCase()
    if (cleaned && !selectedTags.includes(cleaned)) {
      setSelectedTags([...selectedTags, cleaned])
      setTagInput('')
    }
  }

  // Calculate Knapsack Token Gauge percentages & color
  const tokenEstimate = composed?.token_estimate ?? 0
  const tokenPercentage = Math.min(100, Math.round((tokenEstimate / maxTokens) * 100))
  const gaugeColor =
    tokenPercentage > 90
      ? '#ef4444' // red/rose
      : tokenPercentage > 70
        ? '#f59e0b' // amber
        : '#10b981' // emerald green

  const included = composed?.included_capsules ?? []
  const excluded = composed?.excluded_capsules ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%' }}>
      {/* Header Deck */}
      <div
        className="glass"
        style={{
          padding: '1.5rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '1.25rem',
          border: '1px solid rgba(139, 92, 246, 0.25)',
          background: 'radial-gradient(ellipse at top left, rgba(139, 92, 246, 0.08) 0%, rgba(15, 23, 42, 0.6) 100%)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '8px',
                  background: 'linear-gradient(135deg, #8b5cf6, #3b82f6)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 0 15px rgba(139, 92, 246, 0.4)',
                }}
              >
                <Sparkles size={18} color="#fff" />
              </div>
              <h2 style={{ fontSize: '1.4rem', margin: 0, fontWeight: 700 }}>
                Context Composer & Knapsack Playground
              </h2>
            </div>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', margin: '4px 0 0 40px' }}>
              Simulate agent prompt construction with 0/1 Knapsack optimization and hybrid multi-modal retrieval.
            </p>
          </div>

          {/* Quick Actions */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => void executeCompose()}
              disabled={loading}
              style={{ padding: '8px 14px', fontSize: '0.85rem' }}
            >
              <RefreshCw size={14} className={loading ? 'spin' : ''} />
              {loading ? 'Composing...' : 'Re-Compose'}
            </button>
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '0.8rem',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
                marginLeft: '6px',
              }}
            >
              <input
                type="checkbox"
                checked={autoCompose}
                onChange={(e) => setAutoCompose(e.target.checked)}
                style={{ accentColor: '#8b5cf6' }}
              />
              Live Update
            </label>
          </div>
        </div>

        {/* Input Parameters Deck */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
            gap: '1rem',
            paddingTop: '0.5rem',
            borderTop: '1px solid rgba(255, 255, 255, 0.06)',
          }}
        >
          {/* Query Input */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Brain size={14} color="#8b5cf6" />
              User Query / Intent
            </label>
            <input
              className="input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. Authentication bypass, database connection pool, rate limiting..."
              style={{ background: 'rgba(0, 0, 0, 0.4)', borderColor: 'rgba(139, 92, 246, 0.3)' }}
            />
          </div>

          {/* Search Mode Selector */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Sliders size={14} color="#38bdf8" />
              Retrieval Mode
            </label>
            <div style={{ display: 'flex', gap: '6px' }}>
              <button
                type="button"
                onClick={() => setMode('fts')}
                style={{
                  flex: 1,
                  padding: '8px 10px',
                  borderRadius: '8px',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  border: '1px solid',
                  borderColor: mode === 'fts' ? '#38bdf8' : 'rgba(255, 255, 255, 0.08)',
                  background: mode === 'fts' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(0, 0, 0, 0.3)',
                  color: mode === 'fts' ? '#38bdf8' : '#94a3b8',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '4px',
                  transition: 'all 0.2s ease',
                }}
              >
                <Zap size={13} />
                FTS5
              </button>
              <button
                type="button"
                onClick={() => setMode('semantic')}
                style={{
                  flex: 1,
                  padding: '8px 10px',
                  borderRadius: '8px',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  border: '1px solid',
                  borderColor: mode === 'semantic' ? '#a855f7' : 'rgba(255, 255, 255, 0.08)',
                  background: mode === 'semantic' ? 'rgba(168, 85, 247, 0.15)' : 'rgba(0, 0, 0, 0.3)',
                  color: mode === 'semantic' ? '#c084fc' : '#94a3b8',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '4px',
                  transition: 'all 0.2s ease',
                }}
              >
                <Brain size={13} />
                Semantic
              </button>
              <button
                type="button"
                onClick={() => setMode('hybrid')}
                style={{
                  flex: 1,
                  padding: '8px 10px',
                  borderRadius: '8px',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  border: '1px solid',
                  borderColor: mode === 'hybrid' ? '#10b981' : 'rgba(255, 255, 255, 0.08)',
                  background: mode === 'hybrid' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(0, 0, 0, 0.3)',
                  color: mode === 'hybrid' ? '#34d399' : '#94a3b8',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '4px',
                  transition: 'all 0.2s ease',
                }}
              >
                <Globe size={13} />
                Hybrid (RRF)
              </button>
            </div>
          </div>

          {/* Confidence Filter */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ShieldCheck size={14} color="#f59e0b" />
              Min Confidence Gate
            </label>
            <select
              className="input"
              value={confidenceMin}
              onChange={(e) => setConfidenceMin(e.target.value)}
              style={{ background: 'rgba(0, 0, 0, 0.4)', padding: '9px 12px' }}
            >
              <option value="high">High Confidence Only</option>
              <option value="medium">Medium + High (Recommended)</option>
              <option value="low">Low + Medium + High</option>
              <option value="hearsay">All (Include Hearsay)</option>
            </select>
          </div>
        </div>

        {/* Token Budget Slider & Fast Presets */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingTop: '0.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <label
              htmlFor={tokenSliderId}
              style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Gauge size={14} color="#ec4899" />
              Token Budget (Knapsack Limit): <span style={{ color: '#fff', fontWeight: 700 }}>{maxTokens.toLocaleString()} tokens</span>
            </label>
            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
              {TOKEN_PRESETS.map((preset) => (
                <button
                  key={preset.tokens}
                  type="button"
                  onClick={() => setMaxTokens(preset.tokens)}
                  style={{
                    padding: '3px 8px',
                    borderRadius: '6px',
                    fontSize: '0.72rem',
                    cursor: 'pointer',
                    background: maxTokens === preset.tokens ? 'rgba(236, 72, 153, 0.2)' : 'rgba(255, 255, 255, 0.04)',
                    border: '1px solid',
                    borderColor: maxTokens === preset.tokens ? 'rgba(236, 72, 153, 0.6)' : 'rgba(255, 255, 255, 0.08)',
                    color: maxTokens === preset.tokens ? '#f472b6' : '#94a3b8',
                    transition: 'all 0.15s ease',
                  }}
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </div>
          <input
            id={tokenSliderId}
            type="range"
            min={200}
            max={16000}
            step={100}
            value={maxTokens}
            onChange={(e) => setMaxTokens(Number(e.target.value))}
            style={{ width: '100%', accentColor: '#ec4899', cursor: 'pointer' }}
          />
        </div>

        {/* Tag Filters */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <label style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Tag size={14} color="#a855f7" />
              Filter by Tags {selectedTags.length > 0 && `(${selectedTags.length} active)`}
            </label>
            {selectedTags.length > 0 && (
              <button
                type="button"
                onClick={() => setSelectedTags([])}
                style={{ background: 'none', border: 'none', color: '#ef4444', fontSize: '0.75rem', cursor: 'pointer' }}
              >
                Clear tags
              </button>
            )}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', alignItems: 'center' }}>
            {availableTags.slice(0, 15).map((t) => {
              const active = selectedTags.includes(t.name)
              return (
                <button
                  key={t.name}
                  type="button"
                  onClick={() => toggleTag(t.name)}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '16px',
                    fontSize: '0.75rem',
                    fontWeight: 500,
                    cursor: 'pointer',
                    border: '1px solid',
                    borderColor: active ? '#a855f7' : 'rgba(255, 255, 255, 0.08)',
                    background: active ? 'rgba(168, 85, 247, 0.25)' : 'rgba(255, 255, 255, 0.03)',
                    color: active ? '#e9d5ff' : '#94a3b8',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    transition: 'all 0.15s ease',
                  }}
                >
                  #{t.name} <span style={{ opacity: 0.6, fontSize: '0.7rem' }}>({t.count})</span>
                </button>
              )
            })}
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <input
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addCustomTag()
                  }
                }}
                placeholder="+ Custom tag"
                style={{
                  padding: '4px 10px',
                  borderRadius: '16px',
                  fontSize: '0.75rem',
                  background: 'rgba(0, 0, 0, 0.3)',
                  border: '1px dashed rgba(255, 255, 255, 0.15)',
                  color: '#fff',
                  width: '110px',
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Live Knapsack Gauge & Metric Dashboard */}
      {composed && (
        <div
          className="glass"
          style={{
            padding: '1.25rem 1.5rem',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '1.25rem',
            alignItems: 'center',
            border: `1px solid ${gaugeColor}40`,
            background: 'rgba(15, 23, 42, 0.5)',
          }}
        >
          {/* Progress Gauge */}
          <div style={{ gridColumn: 'span 2', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Gauge size={16} color={gaugeColor} />
                0/1 Knapsack Capacity Utilization
              </span>
              <span style={{ fontSize: '0.9rem', fontWeight: 700, color: gaugeColor }}>
                {tokenEstimate.toLocaleString()} / {maxTokens.toLocaleString()} tokens ({tokenPercentage}%)
              </span>
            </div>
            <div
              style={{
                width: '100%',
                height: '10px',
                background: 'rgba(255, 255, 255, 0.08)',
                borderRadius: '5px',
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <div
                style={{
                  width: `${tokenPercentage}%`,
                  height: '100%',
                  background: `linear-gradient(90deg, #10b981 0%, ${gaugeColor} 100%)`,
                  borderRadius: '5px',
                  transition: 'width 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
                  boxShadow: `0 0 10px ${gaugeColor}80`,
                }}
              />
            </div>
            {composed.truncated && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.75rem', color: '#fbbf24' }}>
                <AlertCircle size={13} />
                <span>Token budget reached. Lower-priority candidate capsules were truncated to prevent prompt overflow.</span>
              </div>
            )}
          </div>

          {/* Stat 1: Capsules Packed */}
          <div style={{ padding: '8px 12px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Packed Units</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#38bdf8' }}>
              {composed.capsule_count} <span style={{ fontSize: '0.8rem', color: '#64748b' }}>capsules</span>
            </div>
          </div>

          {/* Stat 2: Candidates Evaluated */}
          <div style={{ padding: '8px 12px', background: 'rgba(255, 255, 255, 0.03)', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
            <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>Candidates Evaluated</div>
            <div style={{ fontSize: '1.3rem', fontWeight: 700, color: '#a855f7' }}>
              {composed.total_candidates ?? (included.length + excluded.length)}{' '}
              <span style={{ fontSize: '0.8rem', color: '#64748b' }}>({excluded.length} excluded)</span>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="glass" style={{ padding: '1rem', color: '#ef4444', borderColor: 'rgba(239, 68, 68, 0.3)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* Main Results View with Tabs */}
      <div className="glass" style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Tab Navigation & Toolbar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '0.75rem 1.25rem',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            background: 'rgba(0, 0, 0, 0.2)',
            flexWrap: 'wrap',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              type="button"
              onClick={() => setActiveTab('knapsack')}
              style={{
                padding: '6px 14px',
                borderRadius: '8px',
                fontSize: '0.85rem',
                fontWeight: 600,
                cursor: 'pointer',
                border: 'none',
                background: activeTab === 'knapsack' ? 'rgba(139, 92, 246, 0.25)' : 'transparent',
                color: activeTab === 'knapsack' ? '#c084fc' : '#94a3b8',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <Layers size={15} />
              Knapsack Breakdown ({included.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('preview')}
              style={{
                padding: '6px 14px',
                borderRadius: '8px',
                fontSize: '0.85rem',
                fontWeight: 600,
                cursor: 'pointer',
                border: 'none',
                background: activeTab === 'preview' ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                color: activeTab === 'preview' ? '#38bdf8' : '#94a3b8',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <FileText size={15} />
              Assembled Prompt Context
            </button>
          </div>

          {/* Action Toolbar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {activeTab === 'preview' && (
              <button
                type="button"
                className="btn btn-ghost"
                onClick={() => setRawView(!rawView)}
                style={{ padding: '6px 10px', fontSize: '0.78rem' }}
              >
                {rawView ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                {rawView ? 'Formatted' : 'Raw Text'}
              </button>
            )}
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => void handleCopy()}
              disabled={!composed?.context}
              style={{ padding: '6px 12px', fontSize: '0.8rem', color: copied ? '#10b981' : undefined }}
            >
              {copied ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
              {copied ? 'Copied!' : 'Copy Context'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleDownload}
              disabled={!composed?.context}
              style={{ padding: '6px 12px', fontSize: '0.8rem' }}
            >
              <Download size={14} />
              Export .md
            </button>
          </div>
        </div>

        {/* Tab 1: Knapsack Breakdown */}
        {activeTab === 'knapsack' && (
          <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            {/* Included Capsules */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.75rem' }}>
                <span
                  style={{
                    padding: '2px 8px',
                    borderRadius: '4px',
                    background: 'rgba(16, 185, 129, 0.2)',
                    color: '#34d399',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                  }}
                >
                  ✓ SELECTED ({included.length})
                </span>
                <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
                  Packed within token budget ordered by knapsack utility
                </span>
              </div>

              {included.length === 0 ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: '#64748b' }}>
                  No capsules matched the current search criteria or confidence threshold.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {included.map((cap, idx) => (
                    <div
                      key={cap.id}
                      onClick={() => onSelectCapsule?.(cap.id)}
                      style={{
                        padding: '12px 16px',
                        background: 'rgba(255, 255, 255, 0.02)',
                        border: '1px solid rgba(255, 255, 255, 0.06)',
                        borderRadius: '10px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        gap: '12px',
                        cursor: onSelectCapsule ? 'pointer' : 'default',
                        transition: 'all 0.15s ease',
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.borderColor = 'rgba(139, 92, 246, 0.4)')}
                      onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.06)')}
                    >
                      <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start', flex: 1 }}>
                        <span
                          style={{
                            width: '24px',
                            height: '24px',
                            borderRadius: '50%',
                            background: 'rgba(139, 92, 246, 0.15)',
                            color: '#c084fc',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '0.75rem',
                            fontWeight: 700,
                            flexShrink: 0,
                          }}
                        >
                          {idx + 1}
                        </span>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                            <span style={{ fontWeight: 600, fontSize: '0.95rem', color: '#f1f5f9' }}>
                              {cap.topic}
                            </span>
                            <span
                              style={{
                                fontSize: '0.7rem',
                                padding: '1px 6px',
                                borderRadius: '4px',
                                background:
                                  cap.confidence === 'high'
                                    ? 'rgba(16, 185, 129, 0.2)'
                                    : cap.confidence === 'medium'
                                      ? 'rgba(56, 189, 248, 0.2)'
                                      : 'rgba(245, 158, 11, 0.2)',
                                color:
                                  cap.confidence === 'high'
                                    ? '#34d399'
                                    : cap.confidence === 'medium'
                                      ? '#38bdf8'
                                      : '#fbbf24',
                                fontWeight: 600,
                              }}
                            >
                              {cap.confidence}
                            </span>
                            {cap.source && (
                              <span style={{ fontSize: '0.72rem', color: '#64748b', fontFamily: 'monospace' }}>
                                {cap.source}
                              </span>
                            )}
                          </div>
                          <p
                            style={{
                              fontSize: '0.82rem',
                              color: '#94a3b8',
                              margin: 0,
                              lineHeight: 1.4,
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical',
                              overflow: 'hidden',
                            }}
                          >
                            {cap.content}
                          </p>
                          {cap.tags && cap.tags.length > 0 && (
                            <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '2px' }}>
                              {cap.tags.map((t) => (
                                <span
                                  key={t}
                                  style={{
                                    fontSize: '0.68rem',
                                    color: '#a855f7',
                                    background: 'rgba(168, 85, 247, 0.1)',
                                    padding: '1px 6px',
                                    borderRadius: '4px',
                                  }}
                                >
                                  #{t}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Token Cost Badge */}
                      <div
                        style={{
                          padding: '4px 8px',
                          borderRadius: '6px',
                          background: 'rgba(0, 0, 0, 0.4)',
                          border: '1px solid rgba(255, 255, 255, 0.08)',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          color: '#38bdf8',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        ~{cap.token_estimate} tokens
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Excluded / Truncated Capsules */}
            {excluded.length > 0 && (
              <div style={{ paddingTop: '1rem', borderTop: '1px solid rgba(255, 255, 255, 0.06)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '0.75rem' }}>
                  <span
                    style={{
                      padding: '2px 8px',
                      borderRadius: '4px',
                      background: 'rgba(239, 68, 68, 0.2)',
                      color: '#f87171',
                      fontSize: '0.75rem',
                      fontWeight: 700,
                    }}
                  >
                    ✕ EXCLUDED ({excluded.length})
                  </span>
                  <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
                    Candidate facts that exceeded the remaining token budget
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', opacity: 0.75 }}>
                  {excluded.map((cap) => (
                    <div
                      key={cap.id}
                      style={{
                        padding: '10px 14px',
                        background: 'rgba(0, 0, 0, 0.25)',
                        border: '1px dashed rgba(239, 68, 68, 0.3)',
                        borderRadius: '8px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        gap: '12px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '0.85rem', fontWeight: 500, color: '#94a3b8' }}>
                          {cap.topic}
                        </span>
                        <span style={{ fontSize: '0.7rem', color: '#f87171', background: 'rgba(239, 68, 68, 0.1)', padding: '1px 6px', borderRadius: '4px' }}>
                          {cap.reason || 'Token limit reached'}
                        </span>
                      </div>
                      <span style={{ fontSize: '0.75rem', color: '#64748b' }}>
                        +{cap.token_estimate} tokens
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Assembled Context Prompt Preview */}
        {activeTab === 'preview' && (
          <div style={{ padding: '1.25rem' }}>
            {composed?.context ? (
              <div style={{ position: 'relative' }}>
                <pre
                  style={{
                    background: 'rgba(0, 0, 0, 0.5)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '10px',
                    padding: '1.25rem',
                    color: '#e2e8f0',
                    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                    fontSize: '0.85rem',
                    lineHeight: 1.5,
                    maxHeight: '600px',
                    overflowY: 'auto',
                    whiteSpace: rawView ? 'pre-wrap' : 'pre-wrap',
                  }}
                >
                  {composed.context}
                </pre>
              </div>
            ) : (
              <div style={{ padding: '3rem', textAlign: 'center', color: '#64748b' }}>
                <FileText size={32} style={{ marginBottom: '8px', opacity: 0.5 }} />
                <p>Run context composition to assemble prompt memory.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
