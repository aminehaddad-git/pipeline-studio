import React, { useState, useEffect } from 'react';
import './PipelineLibrary.css';
import { Library, X, FolderOpen, Play, RotateCcw, Trash2,
         Inbox, Workflow, AlertCircle, CheckCircle2 } from 'lucide-react';

export default function PipelineLibrary({ token, onClose, onLoad }) {
  const [pipelines, setPipelines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);
  const [runningId, setRunningId] = useState(null);

  const fetchPipelines = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/pipelines', {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.pipelines) setPipelines(data.pipelines);
    } catch (e) {
      setMessage({ error: 'Could not load pipelines' });
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchPipelines();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleLoad = async (id) => {
    try {
      const res = await fetch(`http://localhost:8000/pipelines/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.pipeline) {
        onLoad(data.pipeline.definition);
        onClose();
      }
    } catch (e) {
      setMessage({ error: 'Could not load pipeline' });
    }
  };

  const handleRun = async (id, mode) => {
    setRunningId(id);
    setMessage(null);
    try {
      const res = await fetch(`http://localhost:8000/pipelines/${id}/run`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ mode }),
      });
      const data = await res.json();
      setMessage({
        success: `${data.message} — ${data.records_loaded} records loaded in ${data.duration}`
      });
    } catch (e) {
      setMessage({ error: 'Could not run pipeline' });
    }
    setRunningId(null);
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Delete this pipeline?')) return;
    try {
      await fetch(`http://localhost:8000/pipelines/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      fetchPipelines();
    } catch (e) {
      setMessage({ error: 'Could not delete pipeline' });
    }
  };

  const formatDate = (iso) => {
    if (!iso) return '';
    try {
      return new Date(iso).toLocaleString('en-GB', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
      });
    } catch { return iso; }
  };

  return (
    <div className="lib-overlay" onClick={onClose}>
      <div className="lib-modal" onClick={(e) => e.stopPropagation()}>

        <div className="lib-header">
          <div>
            <h2><Library size={18} /> Pipeline Library</h2>
            <p>Your saved pipelines — load, run, or manage them</p>
          </div>
          <button className="lib-close" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="lib-body">
          {message && (
            <div className={`lib-message ${message.error ? 'error' : 'success'}`}>
              {message.error
                ? <><AlertCircle size={15} /> {message.error}</>
                : <><CheckCircle2 size={15} /> {message.success}</>}
            </div>
          )}

          {loading ? (
            <div className="lib-loading">Loading pipelines...</div>
          ) : pipelines.length === 0 ? (
            <div className="lib-empty">
              <span className="lib-empty-icon"><Inbox size={38} /></span>
              <p>No saved pipelines yet.</p>
              <span>Build a pipeline on the canvas and click "Save Pipeline" to store it here.</span>
            </div>
          ) : (
            <div className="lib-list">
              {pipelines.map((p) => (
                <div key={p.id} className="lib-item">
                  <div className="lib-item-info">
                    <span className="lib-item-name"><Workflow size={15} /> {p.name}</span>
                    {p.description && <span className="lib-item-desc">{p.description}</span>}
                    <span className="lib-item-meta">
                      by {p.created_by} · {formatDate(p.created_at)}
                    </span>
                  </div>
                  <div className="lib-item-actions">
                    <button
                      className="lib-btn lib-load"
                      onClick={() => handleLoad(p.id)}
                      title="Load onto canvas"
                    >
                      <FolderOpen size={13} /> Load
                    </button>
                    <button
                      className="lib-btn lib-run"
                      onClick={() => handleRun(p.id, 'incremental')}
                      disabled={runningId === p.id}
                      title="Run — add new rows only"
                    >
                      {runningId === p.id ? '…' : <><Play size={13} /> Run</>}
                    </button>
                    <button
                      className="lib-btn lib-refresh"
                      onClick={() => handleRun(p.id, 'full_refresh')}
                      disabled={runningId === p.id}
                      title="Full refresh — reprocess all data (applies transformations to everything)"
                    >
                      <RotateCcw size={13} /> Refresh
                    </button>
                    <button
                      className="lib-btn lib-delete"
                      onClick={() => handleDelete(p.id)}
                      title="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}