import React, { useState, useCallback } from 'react';
import ReactFlow, {
  addEdge, MiniMap, Controls, Background, useNodesState, useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import {
  Database, Filter, HardDrive, Play, RefreshCw, Save, Trash2,
  Upload, Table2, Clock, Library, BarChart3, Users, LogOut,
  User, Landmark, Building2, CreditCard, Eye, Terminal,
  Activity, History, ChevronDown, ChevronUp, Layers, RotateCcw, TrendingUp,
} from 'lucide-react';
import appLogo from './logo-light.png';
import CustomNode from './CustomNode';
import ConfigPanel from './ConfigPanel';
import DataPreview from './DataPreview';
import SmartUpload from './SmartUpload';
import UserManagement from './UserManagement';
import SchedulePanel from './SchedulePanel';
import PipelineLibrary from './PipelineLibrary';
import Dashboard from './Dashboard';
import ChatBot from './ChatBot';
import './PipelineBuilder.css';
import Forecast from './Forecast';

const nodeTypes = { custom: CustomNode };

export default function PipelineBuilder({ token, user, onLogout }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [logs, setLogs] = useState('Ready. Build a pipeline and run it.');
  const [running, setRunning] = useState(false);
  const [stats, setStats] = useState(null);
  const [history, setHistory] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);

  const [showPreview, setShowPreview] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [showUsers, setShowUsers] = useState(false);
  const [showSchedule, setShowSchedule] = useState(false);
  const [showLibrary, setShowLibrary] = useState(false);
  const [showDashboard, setShowDashboard] = useState(false);
  const [showForecast, setShowForecast] = useState(false);

  const [bottomOpen, setBottomOpen] = useState(true);
  const [bottomTab, setBottomTab] = useState('logs');

  const onConnect = useCallback(
    (params) => setEdges((eds) => addEdge({ ...params, animated: true }, eds)),
    [setEdges]
  );

  const onNodeClick = useCallback((event, node) => {
    setSelectedNode({ node, position: { x: event.clientX, y: event.clientY } });
  }, []);

  const addNode = (type) => {
    const labels = { source: 'Source', transform: 'Transformation', destination: 'Destination' };
    const colors = { source: '#1D9E75', transform: '#7F77DD', destination: '#378ADD' };
    setNodes((nds) => nds.concat({
      id: `${type}-${Date.now()}`,
      type: 'custom',
      position: { x: Math.random() * 350 + 120, y: Math.random() * 180 + 100 },
      data: { label: labels[type], type, color: colors[type], config: {}, configured: false },
    }));
  };

  const handleSaveConfig = (nodeId, config) => {
    setNodes((nds) => nds.map((n) => {
      if (n.id !== nodeId) return n;
      const labelMap = {
        clients: 'Source — Clients', comptes: 'Source — Accounts',
        agences: 'Source — Branches', transactions: 'Source — Transactions',
        dim_client: 'Dest — dim_client', dim_compte: 'Dest — dim_compte',
        dim_agence: 'Dest — dim_agence', fait_transactions: 'Dest — fait_transactions',
        filter: 'Filter Rows', clean_nulls: 'Clean Nulls', transform_value: 'Transform Values',
      };
      const key = config.source_table || config.transform_kind || config.destination_table;
      return { ...n, data: { ...n.data, label: labelMap[key] || n.data.label, config, configured: true } };
    }));
  };

  const validatePipeline = () => {
    if (nodes.length === 0) return 'Add at least one block to the canvas.';
    if (nodes.filter((n) => !n.data.configured).length > 0)
      return 'Please configure all blocks first. Click each block.';
    if (edges.length === 0) return 'Please connect the blocks with arrows.';
    return null;
  };

  const runFullETL = async (mode = 'incremental') => {
    setRunning(true);
    setBottomTab('logs');
    setBottomOpen(true);
    setLogs(`Running Full ETL (${mode === 'full_refresh' ? 'Full Rebuild' : 'Incremental'})...`);
    try {
      const res = await fetch('http://localhost:8000/run-full-etl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ mode }),
      });
      const data = await res.json();
      const dur = data.duration ? `\nDuration: ${data.duration}` : '';
      const rec = data.records_loaded != null ? `\nRecords loaded: ${data.records_loaded}` : '';
      setLogs((data.message || 'Done.') + rec + dur);
      fetchStats();
      fetchHistory();
    } catch (e) {
      setLogs('Error: could not connect to backend.\n' + e.message);
    }
    setRunning(false);
  };

  const runPipeline = async (mode = 'incremental') => {
    const err = validatePipeline();
    if (err) { setLogs('⚠ ' + err); setBottomTab('logs'); setBottomOpen(true); return; }

    setRunning(true);
    setBottomTab('logs');
    setBottomOpen(true);
    setLogs(`Launching pipeline (${mode === 'full_refresh' ? 'Full Refresh' : 'Incremental'})...`);
    try {
      const res = await fetch('http://localhost:8000/run-canvas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ nodes, edges, mode }),
      });
      const data = await res.json();
      const dur = data.duration ? `\nDuration: ${data.duration}` : '';
      const rec = data.records_loaded != null ? `\nRecords loaded: ${data.records_loaded}` : '';
      setLogs(data.message + rec + dur);
      fetchStats();
      fetchHistory();
    } catch (e) {
      setLogs('Error: could not connect to backend.\n' + e.message);
    }
    setRunning(false);
  };

  const clearCanvas = () => {
    setNodes([]); setEdges([]); setLogs('Canvas cleared.');
  };

  const savePipeline = async () => {
    if (nodes.length === 0) { setLogs('⚠ Nothing to save. Build a pipeline first.'); return; }
    const name = window.prompt('Enter a name for this pipeline:');
    if (!name) return;
    const description = window.prompt('Enter a description (optional):') || '';
    try {
      const res = await fetch('http://localhost:8000/pipelines', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name, description, definition: { nodes, edges } }),
      });
      const data = await res.json();
      setLogs(res.ok ? `Pipeline "${name}" saved successfully.` : (data.detail || 'Could not save pipeline'));
    } catch { setLogs('Could not connect to backend.'); }
  };

  const loadPipeline = (definition) => {
    if (definition.nodes) setNodes(definition.nodes);
    if (definition.edges) setEdges(definition.edges);
    setLogs('Pipeline loaded onto canvas.');
  };

  const fetchStats = async () => {
    try {
      const res = await fetch('http://localhost:8000/db-stats');
      const data = await res.json();
      setStats(data.stats);
    } catch { /* silent */ }
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch('http://localhost:8000/history?limit=6');
      const data = await res.json();
      if (data.history) setHistory(data.history);
    } catch { /* silent */ }
  };

  React.useEffect(() => { fetchStats(); fetchHistory(); }, []);

  const configuredCount = nodes.filter((n) => n.data.configured).length;
  const totalNodes = nodes.length;
  const role = user?.role || 'viewer';
  const canEdit = role === 'admin' || role === 'operator';
  const isAdmin = role === 'admin';
  const ready = totalNodes > 0 && configuredCount === totalNodes && edges.length > 0;

  const formatDate = (iso) => {
    try {
      return new Date(iso).toLocaleString('en-GB', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
      });
    } catch { return iso; }
  };

  const IC = 15;

  return (
    <div className="app">

      {/* ─────────── TOP BAR ─────────── */}
      <header className="topbar">
        <div className="topbar-left">
                    <img src={appLogo} alt="PIPELINE STUDIO" className="brand-logo-img" />
          <div className="brand-text">
            <span className="brand-name">PIPELINE STUDIO</span>
            <span className="brand-sub">No-Code ETL Platform</span>
          </div>
        </div>

        <nav className="topbar-nav">
          {canEdit && (
            <button className="nav-btn" onClick={() => setShowUpload(true)}>
              <Upload size={IC} /><span>Upload</span>
            </button>
          )}
          <button className="nav-btn" onClick={() => setShowPreview(true)}>
            <Table2 size={IC} /><span>Tables</span>
          </button>
          <button className="nav-btn" onClick={() => setShowDashboard(true)}>
            <BarChart3 size={IC} /><span>Dashboard</span>
          </button>
          <button className="nav-btn" onClick={() => setShowForecast(true)}>
            <TrendingUp size={IC} /><span>Forecast</span>
          </button>
          {canEdit && (
            <button className="nav-btn" onClick={() => setShowLibrary(true)}>
              <Library size={IC} /><span>Library</span>
            </button>
          )}
          {canEdit && (
            <button className="nav-btn" onClick={() => setShowSchedule(true)}>
              <Clock size={IC} /><span>Scheduler</span>
            </button>
          )}
          {isAdmin && (
            <button className="nav-btn" onClick={() => setShowUsers(true)}>
              <Users size={IC} /><span>Users</span>
            </button>
          )}
        </nav>

        <div className="topbar-right">
          <div className="user-chip">
            <div className="user-avatar">{user?.full_name?.charAt(0) || 'U'}</div>
            <div className="user-meta">
              <span className="user-name">{user?.full_name}</span>
              <span className={`user-role role-${role}`}>{role}</span>
            </div>
          </div>
          <button className="icon-btn danger" onClick={onLogout} title="Sign out">
            <LogOut size={16} />
          </button>
        </div>
      </header>

      {/* ─────────── BODY ─────────── */}
      <div className="body">

        {/* SIDEBAR */}
        <aside className="sidebar">
          {canEdit ? (
            <>
              <div className="panel">
                <div className="panel-label">Components</div>
                <button className="block-btn src" onClick={() => addNode('source')}>
                  <span className="block-ico"><Database size={16} /></span>
                  <span className="block-txt"><b>Source</b><small>Extract from staging</small></span>
                </button>
                <button className="block-btn trf" onClick={() => addNode('transform')}>
                  <span className="block-ico"><Filter size={16} /></span>
                  <span className="block-txt"><b>Transformation</b><small>Filter, clean, modify</small></span>
                </button>
                <button className="block-btn dst" onClick={() => addNode('destination')}>
                  <span className="block-ico"><HardDrive size={16} /></span>
                  <span className="block-txt"><b>Destination</b><small>Load to warehouse</small></span>
                </button>
              </div>

              <div className="panel">
                <div className="panel-label">Pipeline</div>
                <div className="metrics">
                  <div className="metric">
                    <span className="metric-num">{totalNodes}</span>
                    <span className="metric-lbl">Blocks</span>
                  </div>
                  <div className="metric">
                    <span className={`metric-num ${configuredCount === totalNodes && totalNodes > 0 ? 'ok' : 'warn'}`}>
                      {configuredCount}/{totalNodes}
                    </span>
                    <span className="metric-lbl">Configured</span>
                  </div>
                  <div className="metric">
                    <span className="metric-num">{edges.length}</span>
                    <span className="metric-lbl">Links</span>
                  </div>
                </div>
                <div className={`ready-pill ${ready ? 'is-ready' : ''}`}>
                  <span className="dot" />
                  {ready ? 'Ready to run' : 'Not ready'}
                </div>
              </div>

              <div className="panel">
                <div className="panel-label">Run</div>
                <button className="btn primary" onClick={() => runPipeline('incremental')} disabled={running}>
                  <Play size={IC} /><span>{running ? 'Running…' : 'Run Pipeline'}</span>
                </button>
                <button className="btn amber" onClick={() => runPipeline('full_refresh')} disabled={running}
                        title="Reprocess all data — applies transformations to everything">
                  <RefreshCw size={IC} /><span>Full Refresh</span>
                </button>
                <div className="btn-row">
                  <button className="btn ghost" onClick={savePipeline}>
                    <Save size={IC} /><span>Save</span>
                  </button>
                  <button className="btn ghost danger" onClick={clearCanvas}>
                    <Trash2 size={IC} /><span>Clear</span>
                  </button>
                </div>
              </div>
              <div className="panel">
                <div className="panel-label">Warehouse</div>
                <p className="panel-hint">Load all staging tables — no canvas needed</p>
                <button className="btn outline" onClick={() => runFullETL('incremental')} disabled={running}>
                  <Layers size={IC} /><span>Run Full ETL</span>
                </button>
                <button className="btn outline danger" onClick={() => {
                  if (window.confirm('Full Rebuild will empty the warehouse tables and reload everything. Continue?'))
                    runFullETL('full_refresh');
                }} disabled={running}>
                  <RotateCcw size={IC} /><span>Full Rebuild</span>
                </button>
              </div>
            </>
          ) : (
            <div className="panel">
              <div className="viewer-note">
                <Eye size={16} />
                <div>
                  <b>View-only mode</b>
                  <p>You can browse tables and dashboards, but cannot modify pipelines.</p>
                </div>
              </div>
            </div>
          )}
        </aside>

        {/* CANVAS + BOTTOM PANEL */}
        <main className="main">
          <div className="canvas">
            {totalNodes === 0 && (
              <div className="empty-state">
                <Database size={30} />
                <b>Your canvas is empty</b>
                <p>Add a Source block from the left to start building a pipeline.</p>
              </div>
            )}
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={onNodeClick}
              nodeTypes={nodeTypes}
              fitView
              proOptions={{ hideAttribution: true }}
            >
              <Controls />
              <MiniMap maskColor="rgba(10,12,25,0.6)" />
              <Background variant="dots" gap={14} size={1} color="#2a2f4a" />
            </ReactFlow>
          </div>

          <section className={`dock ${bottomOpen ? 'open' : ''}`}>
            <div className="dock-head">
              <div className="dock-tabs">
                <button className={bottomTab === 'logs' ? 'on' : ''}
                        onClick={() => { setBottomTab('logs'); setBottomOpen(true); }}>
                  <Terminal size={14} /><span>Logs</span>
                </button>
                <button className={bottomTab === 'stats' ? 'on' : ''}
                        onClick={() => { setBottomTab('stats'); setBottomOpen(true); }}>
                  <Activity size={14} /><span>Warehouse</span>
                </button>
                <button className={bottomTab === 'history' ? 'on' : ''}
                        onClick={() => { setBottomTab('history'); setBottomOpen(true); }}>
                  <History size={14} /><span>History</span>
                </button>
              </div>
              <div className="dock-actions">
                {bottomTab === 'stats' && (
                  <button className="icon-btn" onClick={fetchStats} title="Refresh">
                    <RefreshCw size={14} />
                  </button>
                )}
                <button className="icon-btn" onClick={() => setBottomOpen(!bottomOpen)}>
                  {bottomOpen ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
                </button>
              </div>
            </div>

            {bottomOpen && (
              <div className="dock-body">
                {bottomTab === 'logs' && <pre className="logs">{logs}</pre>}

                {bottomTab === 'stats' && (
                  stats ? (
                    <div className="cards">
                      <div className="card">
                        <User size={16} /><span className="card-num">{stats.dim_client}</span>
                        <span className="card-lbl">Clients</span>
                      </div>
                      <div className="card">
                        <Landmark size={16} /><span className="card-num">{stats.dim_compte}</span>
                        <span className="card-lbl">Accounts</span>
                      </div>
                      <div className="card">
                        <Building2 size={16} /><span className="card-num">{stats.dim_agence}</span>
                        <span className="card-lbl">Branches</span>
                      </div>
                      <div className="card">
                        <CreditCard size={16} /><span className="card-num">{stats.fait_transactions}</span>
                        <span className="card-lbl">Transactions</span>
                      </div>
                    </div>
                  ) : <div className="muted">Loading…</div>
                )}

                {bottomTab === 'history' && (
                  history.length ? (
                    <table className="htable">
                      <thead>
                        <tr><th>Status</th><th>When</th><th>Records</th><th>Duration</th></tr>
                      </thead>
                      <tbody>
                        {history.map((h) => (
                          <tr key={h.id}>
                            <td><span className={`badge b-${h.status}`}>{h.status}</span></td>
                            <td>{formatDate(h.executed_at)}</td>
                            <td>{h.records_loaded}</td>
                            <td>{Number(h.duration_sec).toFixed(2)}s</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : <div className="muted">No runs yet.</div>
                )}
              </div>
            )}
          </section>
        </main>
      </div>

      {/* ─────────── MODALS ─────────── */}
      {selectedNode && canEdit && (
        <ConfigPanel node={selectedNode.node} position={selectedNode.position}
          onClose={() => setSelectedNode(null)} onSave={handleSaveConfig} />
      )}
      {showPreview && <DataPreview token={token} onClose={() => setShowPreview(false)} />}
      {showUpload && canEdit && (
        <SmartUpload token={token} onClose={() => setShowUpload(false)} onUploadSuccess={fetchStats} />
      )}
      {showUsers && isAdmin && <UserManagement token={token} onClose={() => setShowUsers(false)} />}
      {showSchedule && canEdit && <SchedulePanel token={token} onClose={() => setShowSchedule(false)} />}
      {showLibrary && canEdit && (
        <PipelineLibrary token={token} onClose={() => setShowLibrary(false)} onLoad={loadPipeline} />
      )}
      {showDashboard && <Dashboard token={token} onClose={() => setShowDashboard(false)} />}
      {showForecast && <Forecast token={token} onClose={() => setShowForecast(false)} />}

      <ChatBot token={token} />
    </div>
  );
}