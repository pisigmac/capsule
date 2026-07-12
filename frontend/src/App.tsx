import { useState, useEffect } from 'react';
import { Search, Plus, Sparkles, Clock, Target, X, Edit2, Trash2 } from 'lucide-react';

const API_URL = 'http://localhost:9000/api/v1';

function App() {
  const [capsules, setCapsules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [currentCapsule, setCurrentCapsule] = useState({ topic: '', content: '', tags: '', confidence: 'medium' });

  const fetchCapsules = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/capsules`);
      if (res.ok) {
        const data = await res.json();
        setCapsules(data);
      }
    } catch (err) {
      console.error('Failed to fetch capsules', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCapsules();
  }, []);

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      fetchCapsules();
      return;
    }
    
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery })
      });
      if (res.ok) {
        const data = await res.json();
        setCapsules(data);
      }
    } catch (err) {
      console.error('Search failed', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    const tagsArray = currentCapsule.tags.split(',').map(t => t.trim()).filter(Boolean);
    const payload = { ...currentCapsule, tags: tagsArray };
    
    try {
      const url = currentCapsule.id ? `${API_URL}/capsules/${currentCapsule.id}` : `${API_URL}/capsules`;
      const method = currentCapsule.id ? 'PATCH' : 'POST';
      
      await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      setIsModalOpen(false);
      fetchCapsules();
      setCurrentCapsule({ topic: '', content: '', tags: '', confidence: 'medium' });
    } catch (err) {
      console.error('Save failed', err);
    }
  };

  const handleDelete = async (id, e) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to delete this capsule?')) return;
    
    try {
      await fetch(`${API_URL}/capsules/${id}`, { method: 'DELETE' });
      fetchCapsules();
    } catch (err) {
      console.error('Delete failed', err);
    }
  };

  const openEditModal = (capsule) => {
    setCurrentCapsule({
      ...capsule,
      tags: capsule.tags ? capsule.tags.join(', ') : ''
    });
    setIsModalOpen(true);
  };

  return (
    <div className="app-container">
      <header className="header">
        <div className="header-title">
          <Sparkles size={32} className="text-gradient" />
          <h1 className="text-gradient" style={{ margin: 0, fontSize: '2.5rem' }}>Capsule</h1>
        </div>
        
        <form onSubmit={handleSearch} className="search-bar">
          <Search size={20} color="var(--text-secondary)" />
          <input 
            type="text" 
            placeholder="Search your knowledge base..." 
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </form>

        <button 
          className="btn btn-primary" 
          onClick={() => {
            setCurrentCapsule({ topic: '', content: '', tags: '', confidence: 'medium' });
            setIsModalOpen(true);
          }}
        >
          <Plus size={20} />
          New Capsule
        </button>
      </header>

      {loading ? (
        <div className="loading-state">
          <div className="spinner"><Sparkles size={40} /></div>
          <p>Decrypting knowledge...</p>
        </div>
      ) : capsules.length === 0 ? (
        <div className="empty-state glass">
          <Sparkles size={64} color="var(--text-secondary)" opacity={0.5} />
          <h2>No capsules found</h2>
          <p>Create your first atomic unit of knowledge.</p>
        </div>
      ) : (
        <div className="capsule-grid">
          {capsules.map(capsule => (
            <div key={capsule.id} className="capsule-card glass" onClick={() => openEditModal(capsule)}>
              <div className="capsule-header">
                <h3 className="capsule-title">{capsule.topic}</h3>
                <button 
                  className="btn-ghost" 
                  style={{ padding: '4px', borderRadius: '8px' }}
                  onClick={(e) => handleDelete(capsule.id, e)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              
              <div className="capsule-content">{capsule.content}</div>
              
              {capsule.tags && capsule.tags.length > 0 && (
                <div className="tag-list">
                  {capsule.tags.map(tag => (
                    <span key={tag} className="tag">#{tag}</span>
                  ))}
                </div>
              )}
              
              <div className="capsule-footer">
                <div className="confidence-badge">
                  <Target size={14} className={`confidence-${capsule.confidence}`} />
                  <span style={{ textTransform: 'capitalize' }}>{capsule.confidence}</span>
                </div>
                <div className="confidence-badge">
                  <Clock size={14} />
                  <span>{new Date(capsule.updated_at).toLocaleDateString()}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {isModalOpen && (
        <div className="modal-overlay" onClick={() => setIsModalOpen(false)}>
          <div className="modal-content glass" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{currentCapsule.id ? 'Edit Capsule' : 'New Capsule'}</h2>
              <button className="btn-ghost" style={{ padding: '8px', borderRadius: '50%' }} onClick={() => setIsModalOpen(false)}>
                <X size={20} />
              </button>
            </div>
            
            <form onSubmit={handleSave}>
              <div className="input-group">
                <label>Topic</label>
                <input 
                  className="input" 
                  value={currentCapsule.topic}
                  onChange={e => setCurrentCapsule({...currentCapsule, topic: e.target.value})}
                  required
                  placeholder="e.g., Auth bypass vulnerability"
                />
              </div>
              
              <div className="input-group">
                <label>Content</label>
                <textarea 
                  className="textarea" 
                  rows={6}
                  value={currentCapsule.content}
                  onChange={e => setCurrentCapsule({...currentCapsule, content: e.target.value})}
                  required
                  placeholder="Detailed knowledge..."
                />
              </div>
              
              <div className="input-group">
                <label>Tags (comma separated)</label>
                <input 
                  className="input" 
                  value={currentCapsule.tags}
                  onChange={e => setCurrentCapsule({...currentCapsule, tags: e.target.value})}
                  placeholder="security, auth, bug"
                />
              </div>
              
              <div className="input-group">
                <label>Confidence Level</label>
                <select 
                  className="input" 
                  value={currentCapsule.confidence}
                  onChange={e => setCurrentCapsule({...currentCapsule, confidence: e.target.value})}
                >
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
              
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '24px' }}>
                <button type="button" className="btn btn-ghost" onClick={() => setIsModalOpen(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Save Capsule</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
