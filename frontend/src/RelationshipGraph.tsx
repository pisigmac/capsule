import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Link2,
  Maximize2,
  Minimize2,
  Plus,
  RefreshCw,
  Search,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { api, type Capsule, type Relationship } from './api'

type GraphNode = {
  id: string
  topic: string
  confidence: string
  tags: string[]
  x: number
  y: number
  vx: number
  vy: number
  radius: number
}

type GraphEdge = {
  id: string
  from: string
  to: string
  type: string
}

const CONFIDENCE_COLORS: Record<string, string> = {
  high: '#10b981',
  medium: '#f59e0b',
  low: '#ef4444',
}

const REL_COLORS: Record<string, string> = {
  relates_to: '#38bdf8',
  depends_on: '#c084fc',
  supersedes: '#fb7185',
  verifies: '#34d399',
  calls: '#f59e0b',
  imports: '#06b6d4',
  defines: '#10b981',
  inherits: '#a855f7',
  contract_http: '#ec4899',
  implements: '#84cc16',
  implemented_by: '#10b981',
}

export function RelationshipGraph({
  capsules,
  onSelectCapsule,
}: {
  capsules: Capsule[]
  onSelectCapsule?: (cap: Capsule) => void
}) {
  const [edges, setEdges] = useState<GraphEdge[]>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [graphMode, setGraphMode] = useState<'all' | 'knowledge' | 'code'>('all')
  const [filterType, setFilterType] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [isLinking, setIsLinking] = useState(false)
  const [targetCapId, setTargetCapId] = useState('')
  const [relType, setRelType] = useState('relates_to')
  const [statusMsg, setStatusMsg] = useState('')
  const [zoomLevel, setZoomLevel] = useState(1)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const containerRef = useRef<HTMLDivElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const nodesRef = useRef<GraphNode[]>([])
  const isDraggingRef = useRef<string | null>(null)
  const isPanningRef = useRef(false)
  const panOffsetRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 })
  const panStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 })
  const mousePosRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 })
  const animFrameRef = useRef<number | null>(null)

  // Load all relationships via bulk endpoint or per-capsule fallback
  const loadAllRelationships = async () => {
    try {
      const bulkRels = await api.listRelationships()
      if (Array.isArray(bulkRels) && bulkRels.length > 0) {
        setEdges(
          bulkRels.map((r) => ({
            id: r.id || `${r.from_capsule_id}->${r.to_capsule_id}`,
            from: r.from_capsule_id,
            to: r.to_capsule_id,
            type: r.relationship_type || 'relates_to',
          })),
        )
        return
      }
    } catch {
      // fallback to per-capsule query
    }

    const allEdges: GraphEdge[] = []
    await Promise.all(
      capsules.map(async (cap) => {
        try {
          const relData = await api.relationships(cap.id)
          if (relData?.outgoing) {
            relData.outgoing.forEach((r: Relationship) => {
              allEdges.push({
                id: r.id || `${r.from_capsule_id}->${r.to_capsule_id}`,
                from: r.from_capsule_id,
                to: r.to_capsule_id,
                type: r.relationship_type || 'relates_to',
              })
            })
          }
        } catch {
          // ignore individual error
        }
      }),
    )
    setEdges(allEdges)
  }

  useEffect(() => {
    if (capsules.length > 0) {
      void loadAllRelationships()
    }
  }, [capsules])

  const visibleCapsules = useMemo(() => {
    if (graphMode === 'knowledge') {
      return capsules.filter((c) => !c.tags?.includes('code'))
    }
    if (graphMode === 'code') {
      return capsules.filter((c) => c.tags?.includes('code'))
    }
    return capsules
  }, [capsules, graphMode])

  // Initialize nodes layout dynamically
  useEffect(() => {
    const width = 1000
    const height = 650
    const center = { x: width / 2, y: height / 2 }
    const radius = Math.min(width, height) * 0.4

    nodesRef.current = visibleCapsules.map((cap, i) => {
      const angle = (i / Math.max(visibleCapsules.length, 1)) * 2 * Math.PI
      const existing = nodesRef.current.find((n) => n.id === cap.id)
      const isFile = cap.tags?.includes('file')
      const isClass = cap.tags?.includes('class') || cap.tags?.includes('interface')
      const isFunction = cap.tags?.includes('function')
      const nodeRadius = isFile ? 24 : isClass ? 21 : isFunction ? 17 : 20

      return {
        id: cap.id,
        topic: cap.topic,
        confidence: cap.confidence || 'medium',
        tags: cap.tags || [],
        x: existing ? existing.x : center.x + radius * Math.cos(angle) + (Math.random() * 60 - 30),
        y: existing ? existing.y : center.y + radius * Math.sin(angle) + (Math.random() * 60 - 30),
        vx: 0,
        vy: 0,
        radius: nodeRadius,
      }
    })
  }, [visibleCapsules])

  const visibleIdSet = useMemo(() => new Set(visibleCapsules.map((c) => c.id)), [visibleCapsules])

  const filteredEdges = useMemo(() => {
    const scoped = edges.filter((e) => visibleIdSet.has(e.from) && visibleIdSet.has(e.to))
    if (filterType === 'all') return scoped
    return scoped.filter((e) => e.type === filterType)
  }, [edges, filterType, visibleIdSet])

  const selectedCapsule = useMemo(() => {
    if (!selectedNodeId) return null
    return visibleCapsules.find((c) => c.id === selectedNodeId) || null
  }, [selectedNodeId, visibleCapsules])

  const connectedEdges = useMemo(() => {
    if (!selectedNodeId) return []
    return filteredEdges.filter((e) => e.from === selectedNodeId || e.to === selectedNodeId)
  }, [selectedNodeId, filteredEdges])

  // Global pointer up listener so dragging NEVER gets stuck
  useEffect(() => {
    const handleGlobalPointerUp = () => {
      isDraggingRef.current = null
      isPanningRef.current = false
    }

    window.addEventListener('pointerup', handleGlobalPointerUp)
    window.addEventListener('mouseup', handleGlobalPointerUp)
    return () => {
      window.removeEventListener('pointerup', handleGlobalPointerUp)
      window.removeEventListener('mouseup', handleGlobalPointerUp)
    }
  }, [])

  // Physics Simulation & Render Loop
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let isRunning = true

    const updatePhysics = () => {
      const nodes = nodesRef.current
      const width = canvas.width
      const height = canvas.height
      const center = { x: width / 2, y: height / 2 }

      // 1. Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const n1 = nodes[i]
          const n2 = nodes[j]
          const dx = n2.x - n1.x
          const dy = n2.y - n1.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          if (dist < 180) {
            const force = ((180 - dist) / dist) * 0.2
            n1.vx -= dx * force
            n1.vy -= dy * force
            n2.vx += dx * force
            n2.vy += dy * force
          }
        }
      }

      // 2. Spring attraction along connected edges
      filteredEdges.forEach((edge) => {
        const fromNode = nodes.find((n) => n.id === edge.from)
        const toNode = nodes.find((n) => n.id === edge.to)
        if (fromNode && toNode) {
          const dx = toNode.x - fromNode.x
          const dy = toNode.y - fromNode.y
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          const desired = 130
          const force = (dist - desired) * 0.007
          fromNode.vx += (dx / dist) * force
          fromNode.vy += (dy / dist) * force
          toNode.vx -= (dx / dist) * force
          toNode.vy -= (dy / dist) * force
        }
      })

      // 3. Center gravity, damping & bounds
      nodes.forEach((node) => {
        if (isDraggingRef.current === node.id) {
          node.x = mousePosRef.current.x
          node.y = mousePosRef.current.y
          node.vx = 0
          node.vy = 0
          return
        }

        const dx = center.x - node.x
        const dy = center.y - node.y
        node.vx += dx * 0.0015
        node.vy += dy * 0.0015

        node.vx *= 0.86
        node.vy *= 0.86
        node.x += node.vx
        node.y += node.vy

        node.x = Math.max(25, Math.min(width - 25, node.x))
        node.y = Math.max(25, Math.min(height - 25, node.y))
      })
    }

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.save()

      // Apply zoom & pan transform
      ctx.translate(panOffsetRef.current.x, panOffsetRef.current.y)
      ctx.scale(zoomLevel, zoomLevel)

      // Draw subtle grid
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)'
      ctx.lineWidth = 1
      for (let x = -500; x < canvas.width + 500; x += 40) {
        ctx.beginPath()
        ctx.moveTo(x, -500)
        ctx.lineTo(x, canvas.height + 500)
        ctx.stroke()
      }
      for (let y = -500; y < canvas.height + 500; y += 40) {
        ctx.beginPath()
        ctx.moveTo(-500, y)
        ctx.lineTo(canvas.width + 500, y)
        ctx.stroke()
      }

      const nodes = nodesRef.current

      // Draw Edges
      filteredEdges.forEach((edge) => {
        const fromNode = nodes.find((n) => n.id === edge.from)
        const toNode = nodes.find((n) => n.id === edge.to)
        if (!fromNode || !toNode) return

        const isHighlighted =
          selectedNodeId === edge.from || selectedNodeId === edge.to
        const edgeColor = REL_COLORS[edge.type] || '#38bdf8'

        ctx.beginPath()
        ctx.moveTo(fromNode.x, fromNode.y)
        ctx.lineTo(toNode.x, toNode.y)
        ctx.strokeStyle = isHighlighted
          ? edgeColor
          : selectedNodeId
          ? 'rgba(255, 255, 255, 0.06)'
          : `${edgeColor}99` // Vibrant semi-opaque color matching relationship type
        ctx.lineWidth = isHighlighted ? 4 : 2.5
        ctx.stroke()

        // Draw directional arrow head
        const angle = Math.atan2(toNode.y - fromNode.y, toNode.x - fromNode.x)
        const arrowDist = toNode.radius + 8
        const arrowX = toNode.x - arrowDist * Math.cos(angle)
        const arrowY = toNode.y - arrowDist * Math.sin(angle)
        const arrowLength = isHighlighted ? 15 : 12

        ctx.beginPath()
        ctx.moveTo(arrowX, arrowY)
        ctx.lineTo(
          arrowX - arrowLength * Math.cos(angle - Math.PI / 7),
          arrowY - arrowLength * Math.sin(angle - Math.PI / 7),
        )
        ctx.lineTo(
          arrowX - arrowLength * Math.cos(angle + Math.PI / 7),
          arrowY - arrowLength * Math.sin(angle + Math.PI / 7),
        )
        ctx.closePath()
        ctx.fillStyle = isHighlighted
          ? edgeColor
          : selectedNodeId
          ? 'rgba(255, 255, 255, 0.1)'
          : edgeColor
        ctx.fill()
      })

      // Draw Nodes
      nodes.forEach((node) => {
        const isSelected = selectedNodeId === node.id
        const isHovered = hoveredNodeId === node.id
        const isConnected =
          connectedEdges.some((e) => e.from === node.id || e.to === node.id) ||
          isSelected
        const isMatched =
          searchQuery.trim() === '' ||
          node.topic.toLowerCase().includes(searchQuery.toLowerCase())

        const isCode = node.tags.includes('code')
        const isFile = node.tags.includes('file')
        const isClass = node.tags.includes('class') || node.tags.includes('interface')
        const isFunction = node.tags.includes('function')

        let nodeBorderColor = CONFIDENCE_COLORS[node.confidence] || '#f59e0b'
        if (isCode) {
          if (isFile) nodeBorderColor = '#06b6d4'
          else if (isClass) nodeBorderColor = '#a855f7'
          else if (isFunction) nodeBorderColor = '#f59e0b'
        }

        // Outer Glow Halo
        if (isSelected || isHovered) {
          ctx.beginPath()
          ctx.arc(node.x, node.y, node.radius + (isSelected ? 9 : 6), 0, Math.PI * 2)
          ctx.fillStyle = isSelected
            ? 'rgba(16, 185, 129, 0.35)'
            : 'rgba(56, 189, 248, 0.25)'
          ctx.fill()
        }

        // Main Node Circle
        ctx.beginPath()
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)
        ctx.fillStyle = isSelected
          ? '#1e293b'
          : isConnected
          ? '#0f172a'
          : selectedNodeId
          ? '#080c14'
          : '#0f172a'
        ctx.fill()

        ctx.strokeStyle = isSelected
          ? '#10b981'
          : isHovered
          ? '#38bdf8'
          : isMatched
          ? nodeBorderColor
          : 'rgba(255, 255, 255, 0.15)'
        ctx.lineWidth = isSelected || isHovered ? 3 : 1.8
        ctx.stroke()

        // Inner Confidence / Symbol Dot
        ctx.beginPath()
        ctx.arc(node.x, node.y, 4, 0, Math.PI * 2)
        ctx.fillStyle = nodeBorderColor
        ctx.fill()

        // Node Label
        ctx.font = '12px -apple-system, sans-serif'
        ctx.fillStyle = isSelected
          ? '#ffffff'
          : isHovered
          ? '#38bdf8'
          : isMatched
          ? '#cbd5e1'
          : '#64748b'
        ctx.textAlign = 'center'
        const label =
          node.topic.length > 22 ? node.topic.slice(0, 20) + '…' : node.topic
        ctx.fillText(label, node.x, node.y + node.radius + 16)
      })

      ctx.restore()

      if (isRunning) {
        updatePhysics()
        animFrameRef.current = requestAnimationFrame(render)
      }
    }

    render()

    return () => {
      isRunning = false
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    }
  }, [filteredEdges, selectedNodeId, hoveredNodeId, connectedEdges, searchQuery, zoomLevel])

  // Get accurate coordinates taking CSS client scaling into account
  const getCanvasCoords = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    const scaleX = canvas.width / rect.width
    const scaleY = canvas.height / rect.height
    const clientX = (e.clientX - rect.left) * scaleX
    const clientY = (e.clientY - rect.top) * scaleY

    // Invert zoom and pan
    const x = (clientX - panOffsetRef.current.x) / zoomLevel
    const y = (clientY - panOffsetRef.current.y) / zoomLevel
    return { x, y }
  }

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getCanvasCoords(e)

    const clicked = nodesRef.current.find((n) => {
      const dx = n.x - x
      const dy = n.y - y
      return Math.sqrt(dx * dx + dy * dy) <= n.radius + 8
    })

    if (clicked) {
      isDraggingRef.current = clicked.id
      setSelectedNodeId(clicked.id)
      const cap = capsules.find((c) => c.id === clicked.id)
      if (cap && onSelectCapsule) onSelectCapsule(cap)
    } else {
      // Clicked on empty space: deselect or pan
      setSelectedNodeId(null)
      isPanningRef.current = true
      panStartRef.current = { x: e.clientX - panOffsetRef.current.x, y: e.clientY - panOffsetRef.current.y }
    }
  }

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const { x, y } = getCanvasCoords(e)
    mousePosRef.current = { x, y }

    if (isPanningRef.current) {
      panOffsetRef.current = {
        x: e.clientX - panStartRef.current.x,
        y: e.clientY - panStartRef.current.y,
      }
      return
    }

    const hovered = nodesRef.current.find((n) => {
      const dx = n.x - x
      const dy = n.y - y
      return Math.sqrt(dx * dx + dy * dy) <= n.radius + 8
    })

    setHoveredNodeId(hovered ? hovered.id : null)
    if (canvasRef.current) {
      canvasRef.current.style.cursor = hovered
        ? 'pointer'
        : isPanningRef.current
        ? 'grabbing'
        : 'default'
    }
  }

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault()
    const delta = e.deltaY > 0 ? -0.1 : 0.1
    setZoomLevel((prev) => Math.max(0.5, Math.min(2.5, prev + delta)))
  }

  const handleCreateLink = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedNodeId || !targetCapId) return
    setStatusMsg('')
    try {
      await api.link(selectedNodeId, targetCapId, relType)
      setStatusMsg('Link created successfully!')
      setIsLinking(false)
      setTargetCapId('')
      await loadAllRelationships()
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : 'Failed to create link')
    }
  }

  return (
    <div
      ref={containerRef}
      style={{
        display: 'flex',
        gap: '20px',
        width: '100%',
        minHeight: '650px',
        position: isFullscreen ? 'fixed' : 'relative',
        top: isFullscreen ? 0 : 'auto',
        left: isFullscreen ? 0 : 'auto',
        right: isFullscreen ? 0 : 'auto',
        bottom: isFullscreen ? 0 : 'auto',
        zIndex: isFullscreen ? 9999 : 'auto',
        background: isFullscreen ? '#07090e' : 'transparent',
        padding: isFullscreen ? '24px' : '0',
      }}
    >
      {/* Main Graph Viewport */}
      <div
        style={{
          flex: 1,
          background: '#090d16',
          borderRadius: '16px',
          border: '1px solid rgba(255,255,255,0.1)',
          padding: '18px',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
        }}
      >
        {/* Graph Header / Control Toolbar */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: '14px',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 700, fontSize: '1.1rem', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Link2 size={20} color="#38bdf8" /> {graphMode === 'code' ? 'Code Dependency & Lineage Graph' : graphMode === 'knowledge' ? 'Knowledge Relationship Graph' : 'Unified Knowledge & Code Graph'}
            </span>
            <span
              style={{
                fontSize: '0.8rem',
                background: 'rgba(56, 189, 248, 0.15)',
                color: '#38bdf8',
                padding: '3px 10px',
                borderRadius: '9999px',
                fontWeight: 600,
              }}
            >
              {filteredEdges.length} Edges • {visibleCapsules.length} Nodes
            </span>

            {/* Graph Mode Selector */}
            <div style={{ display: 'flex', background: '#0a0f1d', borderRadius: '9999px', padding: '3px', border: '1px solid rgba(255,255,255,0.1)' }}>
              <button
                onClick={() => { setGraphMode('knowledge'); setSelectedNodeId(null); }}
                style={{
                  background: graphMode === 'knowledge' ? 'rgba(56, 189, 248, 0.25)' : 'transparent',
                  color: graphMode === 'knowledge' ? '#38bdf8' : '#94a3b8',
                  border: 'none',
                  borderRadius: '9999px',
                  padding: '4px 11px',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                🧠 Knowledge
              </button>
              <button
                onClick={() => { setGraphMode('code'); setSelectedNodeId(null); }}
                style={{
                  background: graphMode === 'code' ? 'rgba(245, 158, 11, 0.25)' : 'transparent',
                  color: graphMode === 'code' ? '#f59e0b' : '#94a3b8',
                  border: 'none',
                  borderRadius: '9999px',
                  padding: '4px 11px',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                ⚡ Code Graph
              </button>
              <button
                onClick={() => { setGraphMode('all'); setSelectedNodeId(null); }}
                style={{
                  background: graphMode === 'all' ? 'rgba(16, 185, 129, 0.25)' : 'transparent',
                  color: graphMode === 'all' ? '#10b981' : '#94a3b8',
                  border: 'none',
                  borderRadius: '9999px',
                  padding: '4px 11px',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                🌐 Unified
              </button>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
            {/* Search Filter */}
            <div style={{ position: 'relative' }}>
              <Search
                size={14}
                style={{ position: 'absolute', left: 10, top: 9, color: '#64748b' }}
              />
              <input
                type="text"
                placeholder="Search nodes..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  background: '#0f172a',
                  border: '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '9999px',
                  padding: '6px 14px 6px 30px',
                  color: '#fff',
                  fontSize: '0.82rem',
                  outline: 'none',
                }}
              />
            </div>

            {/* Filter by Relationship Type */}
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              style={{
                background: '#0f172a',
                border: '1px solid rgba(255,255,255,0.15)',
                color: '#cbd5e1',
                padding: '6px 12px',
                borderRadius: '9999px',
                fontSize: '0.82rem',
                cursor: 'pointer',
              }}
            >
              <option value="all">All Relationships</option>
              <option value="relates_to">relates_to</option>
              <option value="depends_on">depends_on</option>
              <option value="supersedes">supersedes</option>
              <option value="verifies">verifies</option>
              <option value="implements">implements (Knowledge ↔ Code)</option>
              <option value="implemented_by">implemented_by (Code ↔ Knowledge)</option>
              <option value="calls">calls</option>
              <option value="imports">imports</option>
              <option value="defines">defines</option>
              <option value="inherits">inherits</option>
              <option value="contract_http">contract_http</option>
            </select>

            {/* Zoom Controls */}
            <div style={{ display: 'flex', background: '#0f172a', borderRadius: '9999px', padding: '2px', border: '1px solid rgba(255,255,255,0.1)' }}>
              <button
                onClick={() => setZoomLevel((z) => Math.max(0.5, z - 0.15))}
                style={{ background: 'transparent', border: 'none', color: '#94a3b8', padding: '5px 8px', cursor: 'pointer' }}
                title="Zoom Out"
              >
                <ZoomOut size={14} />
              </button>
              <span style={{ fontSize: '0.75rem', color: '#64748b', padding: '5px 4px' }}>{Math.round(zoomLevel * 100)}%</span>
              <button
                onClick={() => setZoomLevel((z) => Math.min(2.5, z + 0.15))}
                style={{ background: 'transparent', border: 'none', color: '#94a3b8', padding: '5px 8px', cursor: 'pointer' }}
                title="Zoom In"
              >
                <ZoomIn size={14} />
              </button>
            </div>

            {/* Refresh */}
            <button
              onClick={() => void loadAllRelationships()}
              style={{
                background: '#1e293b',
                border: '1px solid rgba(255,255,255,0.1)',
                color: '#94a3b8',
                borderRadius: '50%',
                width: 32,
                height: 32,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
              title="Refresh Graph"
            >
              <RefreshCw size={14} />
            </button>

            {/* Fullscreen Toggle */}
            <button
              onClick={() => setIsFullscreen(!isFullscreen)}
              style={{
                background: '#1e293b',
                border: '1px solid rgba(255,255,255,0.1)',
                color: '#94a3b8',
                borderRadius: '50%',
                width: 32,
                height: 32,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
              title={isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
            >
              {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
          </div>
        </div>

        {/* Dynamic Responsive Canvas */}
        <div
          style={{
            flex: 1,
            overflow: 'hidden',
            borderRadius: '12px',
            background: '#050811',
            border: '1px solid rgba(255,255,255,0.06)',
            position: 'relative',
          }}
        >
          <canvas
            ref={canvasRef}
            width={1000}
            height={620}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onWheel={handleWheel}
            style={{
              width: '100%',
              height: '100%',
              minHeight: '580px',
              display: 'block',
            }}
          />
        </div>

        {/* Legend */}
        <div
          style={{
            display: 'flex',
            gap: '18px',
            marginTop: '12px',
            fontSize: '0.8rem',
            color: '#64748b',
            alignItems: 'center',
            flexWrap: 'wrap',
          }}
        >
          <span><b>Types:</b></span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#38bdf8' }} /> relates_to
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#c084fc' }} /> depends_on
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#84cc16' }} /> implements
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#f59e0b' }} /> calls
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#06b6d4' }} /> imports
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: 9, height: 9, borderRadius: '50%', background: '#10b981' }} /> defines
          </span>
        </div>
      </div>

      {/* Inspector & Linker Sidebar */}
      <div
        style={{
          width: '340px',
          background: '#0e131f',
          borderRadius: '16px',
          border: '1px solid rgba(255,255,255,0.1)',
          padding: '22px',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 700, fontSize: '1rem', color: '#f8fafc' }}>
            Capsule Inspector
          </span>
          {selectedCapsule && (
            <button
              onClick={() => setIsLinking(!isLinking)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '5px',
                background: isLinking ? '#334155' : 'rgba(16, 185, 129, 0.2)',
                color: isLinking ? '#cbd5e1' : '#34d399',
                border: '1px solid rgba(16, 185, 129, 0.4)',
                borderRadius: '9999px',
                padding: '4px 12px',
                fontSize: '0.8rem',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              <Plus size={13} /> Link Node
            </button>
          )}
        </div>

        {selectedCapsule ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase' }}>Selected Fact</div>
              <div style={{ fontWeight: 700, fontSize: '1.05rem', color: '#ffffff', marginTop: '3px' }}>
                {selectedCapsule.topic}
              </div>
              <div style={{ fontSize: '0.78rem', color: '#94a3b8', marginTop: '4px' }}>
                Confidence: <b style={{ color: CONFIDENCE_COLORS[selectedCapsule.confidence] }}>{selectedCapsule.confidence}</b>
                {selectedCapsule.source && <span> • Source: {selectedCapsule.source}</span>}
              </div>
            </div>

            {/* Link Creator Form */}
            {isLinking && (
              <form
                onSubmit={handleCreateLink}
                style={{
                  background: '#141c2e',
                  padding: '14px',
                  borderRadius: '10px',
                  border: '1px solid rgba(56, 189, 248, 0.3)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px',
                }}
              >
                <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#38bdf8' }}>Create New Relationship</div>
                <select
                  value={targetCapId}
                  onChange={(e) => setTargetCapId(e.target.value)}
                  required
                  style={{
                    background: '#090d16',
                    border: '1px solid rgba(255,255,255,0.15)',
                    color: '#fff',
                    padding: '7px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                  }}
                >
                  <option value="">Select target capsule...</option>
                  {capsules
                    .filter((c) => c.id !== selectedCapsule.id)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.topic.slice(0, 35)}
                      </option>
                    ))}
                </select>

                <select
                  value={relType}
                  onChange={(e) => setRelType(e.target.value)}
                  style={{
                    background: '#090d16',
                    border: '1px solid rgba(255,255,255,0.15)',
                    color: '#fff',
                    padding: '7px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                  }}
                >
                  <option value="relates_to">relates_to</option>
                  <option value="depends_on">depends_on</option>
                  <option value="implements">implements</option>
                  <option value="implemented_by">implemented_by</option>
                  <option value="supersedes">supersedes</option>
                  <option value="verifies">verifies</option>
                  <option value="calls">calls</option>
                  <option value="defines">defines</option>
                </select>

                <div style={{ display: 'flex', gap: '8px', marginTop: '4px' }}>
                  <button
                    type="submit"
                    style={{
                      flex: 1,
                      background: '#10b981',
                      color: '#000',
                      border: 'none',
                      padding: '6px',
                      borderRadius: '6px',
                      fontWeight: 700,
                      fontSize: '0.78rem',
                      cursor: 'pointer',
                    }}
                  >
                    Save Link
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsLinking(false)}
                    style={{
                      background: '#334155',
                      color: '#fff',
                      border: 'none',
                      padding: '6px 10px',
                      borderRadius: '6px',
                      fontSize: '0.78rem',
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </form>
            )}

            {statusMsg && (
              <div style={{ fontSize: '0.8rem', color: '#34d399' }}>{statusMsg}</div>
            )}

            {/* Connected Relationships */}
            <div>
              <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', marginBottom: '8px' }}>
                Connected Relationships ({connectedEdges.length})
              </div>
              {connectedEdges.length === 0 ? (
                <div style={{ fontSize: '0.82rem', color: '#64748b', fontStyle: 'italic' }}>
                  No relationships linked yet. Click "Link Node" above.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '220px', overflowY: 'auto' }}>
                  {connectedEdges.map((e) => {
                    const isOutgoing = e.from === selectedCapsule.id
                    const otherId = isOutgoing ? e.to : e.from
                    const otherCap = capsules.find((c) => c.id === otherId)
                    return (
                      <div
                        key={e.id}
                        onClick={() => otherCap && setSelectedNodeId(otherCap.id)}
                        style={{
                          background: '#141c2e',
                          padding: '8px 12px',
                          borderRadius: '8px',
                          border: '1px solid rgba(255,255,255,0.08)',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          fontSize: '0.82rem',
                          transition: 'background 0.15s ease',
                        }}
                      >
                        <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '190px' }}>
                          <span style={{ color: isOutgoing ? '#38bdf8' : '#c084fc', fontWeight: 700 }}>
                            {isOutgoing ? '→ ' : '← '}
                          </span>
                          <span style={{ color: '#f1f5f9' }}>{otherCap?.topic || otherId.slice(0, 8)}</span>
                        </div>
                        <span
                          style={{
                            fontSize: '0.72rem',
                            color: REL_COLORS[e.type] || '#38bdf8',
                            background: 'rgba(255,255,255,0.06)',
                            padding: '2px 7px',
                            borderRadius: '4px',
                            fontWeight: 600,
                          }}
                        >
                          {e.type}
                        </span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Content Preview */}
            <div style={{ marginTop: '4px' }}>
              <div style={{ fontSize: '0.75rem', color: '#64748b', textTransform: 'uppercase', marginBottom: '6px' }}>Content Preview</div>
              <div
                style={{
                  fontSize: '0.8rem',
                  color: '#94a3b8',
                  background: '#070a12',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  maxHeight: '140px',
                  overflowY: 'auto',
                  lineHeight: '1.5',
                  border: '1px solid rgba(255,255,255,0.05)',
                }}
              >
                {selectedCapsule.content}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '50px 10px', color: '#64748b', fontSize: '0.88rem', lineHeight: '1.6' }}>
            Click on any node in the graph to inspect its relationship graph and link dependencies.<br/><br/>
            <span style={{ fontSize: '0.78rem', color: '#475569' }}>Click empty canvas space to clear selection.</span>
          </div>
        )}
      </div>
    </div>
  )
}
