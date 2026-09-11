import React, { useState, useEffect } from 'react';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, PieChart, Pie, Cell, BarChart,
} from 'recharts';
import {
  BarChart3, X, RefreshCw, TrendingUp, TrendingDown, Minus,
  Users, Landmark, CreditCard, Wallet, Activity, Download,
} from 'lucide-react';
import { downloadFile } from './download';
import './Dashboard.css';

const COLORS = ['#1D9E75', '#378ADD', '#7F77DD', '#EF9F27', '#E5484D', '#4FC3F7'];
const PERIODS = [
  { key: 6,  label: '6 months' },
  { key: 12, label: '12 months' },
  { key: 24, label: '24 months' },
  { key: 0,  label: 'All time' },
];

export default function Dashboard({ token, onClose }) {
  const [months, setMonths] = useState(12);
  const [ov, setOv] = useState(null);
  const [evo, setEvo] = useState([]);
  const [byType, setByType] = useState([]);
  const [accTypes, setAccTypes] = useState([]);
  const [byCity, setByCity] = useState([]);
  const [topAcc, setTopAcc] = useState([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      await downloadFile(`/export/dashboard?months=${months}`, token, 'dashboard.xlsx');
    } catch (e) {
      alert(e.message);
    }
    setExporting(false);
  };

  const auth = { Authorization: `Bearer ${token}` };
  const get = (url) => fetch(`http://localhost:8000${url}`, { headers: auth }).then((r) => r.json());

  const loadAll = async () => {
    setLoading(true);
    try {
      const [o, e, t, a, c, ta] = await Promise.all([
        get(`/dashboard/overview?months=${months}`),
        get(`/dashboard/evolution?months=${months}`),
        get('/dashboard/transactions-by-type'),
        get('/dashboard/account-types'),
        get('/dashboard/clients-by-city'),
        get('/dashboard/top-accounts?limit=8'),
      ]);
      if (!o.error) setOv(o);
      if (e.data) setEvo(e.data);
      if (t.data) setByType(t.data);
      if (a.data) setAccTypes(a.data);
      if (c.data) setByCity(c.data);
      if (ta.data) setTopAcc(ta.data);
    } catch { /* silent */ }
    setLoading(false);
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [months]);

  const nf = (v, d = 0) =>
    new Intl.NumberFormat('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }).format(v || 0);

  const money = (v) => {
    if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
    if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
    return nf(v);
  };

  const Delta = ({ value }) => {
    if (value == null) return <span className="delta flat"><Minus size={11} /> n/a</span>;
    if (value > 0) return <span className="delta up"><TrendingUp size={11} /> +{value}%</span>;
    if (value < 0) return <span className="delta down"><TrendingDown size={11} /> {value}%</span>;
    return <span className="delta flat"><Minus size={11} /> 0%</span>;
  };

  const tip = {
    contentStyle: {
      background: '#11152A', border: '1px solid rgba(255,255,255,0.12)',
      borderRadius: 10, color: '#E8EAF2', fontSize: 12,
    },
  };

  return (
    <div className="dash-overlay" onClick={onClose}>
      <div className="dash-modal" onClick={(e) => e.stopPropagation()}>

        <div className="dash-head">
          <div className="dash-title">
            <BarChart3 size={19} />
            <div>
              <h2>Analytics Dashboard</h2>
              <p>Live insights from the data warehouse</p>
            </div>
          </div>
          <div className="dash-head-actions">
            <div className="seg">
              {PERIODS.map((p) => (
                <button key={p.key}
                        className={months === p.key ? 'on' : ''}
                        onClick={() => setMonths(p.key)}>{p.label}</button>
              ))}
            </div>
            <button className="export-btn" onClick={handleExport} disabled={exporting}>
              <Download size={14} />
              <span>{exporting ? 'Exporting…' : 'Export Excel'}</span>
            </button>
            <button className="dash-icon" onClick={loadAll}><RefreshCw size={15} /></button>
            <button className="dash-icon danger" onClick={onClose}><X size={16} /></button>
          </div>
        </div>

        <div className="dash-body">
          {loading ? (
            <div className="dash-msg">Loading analytics…</div>
          ) : (
            <>
              {/* KPI ROW */}
              {ov && (
                <div className="kpis">
                  <div className="kpi k-green">
                    <div className="kpi-top"><Users size={16} /><span>Clients</span></div>
                    <div className="kpi-val">{nf(ov.clients)}</div>
                    <div className="kpi-sub">{nf(ov.branches)} branches</div>
                  </div>
                  <div className="kpi k-blue">
                    <div className="kpi-top"><Landmark size={16} /><span>Accounts</span></div>
                    <div className="kpi-val">{nf(ov.accounts)}</div>
                    <div className="kpi-sub">{ov.active_rate}% active</div>
                  </div>
                  <div className="kpi k-purple">
                    <div className="kpi-top"><CreditCard size={16} /><span>Transactions</span></div>
                    <div className="kpi-val">{nf(ov.transactions)}</div>
                    <div className="kpi-sub"><Delta value={ov.growth_transactions} /> vs prev.</div>
                  </div>
                  <div className="kpi k-amber">
                    <div className="kpi-top"><Wallet size={16} /><span>Volume</span></div>
                    <div className="kpi-val">{money(ov.volume)}<small> TND</small></div>
                    <div className="kpi-sub"><Delta value={ov.growth_volume} /> vs prev.</div>
                  </div>
                  <div className="kpi k-cyan">
                    <div className="kpi-top"><Activity size={16} /><span>Avg / transaction</span></div>
                    <div className="kpi-val">{nf(ov.avg_transaction, 0)}<small> TND</small></div>
                    <div className="kpi-sub">across the period</div>
                  </div>
                </div>
              )}

              {/* EVOLUTION */}
              <div className="dash-card wide">
                <h3>Monthly evolution</h3>
                <ResponsiveContainer width="100%" height={260}>
                  <ComposedChart data={evo}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" />
                    <XAxis dataKey="period" stroke="#626B87" fontSize={10.5}
                           tickFormatter={(t) => t.slice(2)} />
                    <YAxis yAxisId="l" stroke="#626B87" fontSize={10.5} />
                    <YAxis yAxisId="r" orientation="right" stroke="#626B87" fontSize={10.5}
                           tickFormatter={money} />
                    <Tooltip {...tip} formatter={(v, n) => [n === 'Amount' ? nf(v, 2) : nf(v), n]} />
                    <Legend wrapperStyle={{ fontSize: 11.5, color: '#9AA3BF' }} />
                    <Bar yAxisId="l" dataKey="count" name="Transactions"
                         fill="#378ADD" radius={[5, 5, 0, 0]} maxBarSize={26} />
                    <Line yAxisId="r" type="monotone" dataKey="amount" name="Amount"
                          stroke="#EF9F27" strokeWidth={2.2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>

              {/* GRID */}
              <div className="dash-grid">
                <div className="dash-card">
                  <h3>Transactions by type</h3>
                  <ResponsiveContainer width="100%" height={215}>
                    <BarChart data={byType}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" />
                      <XAxis dataKey="name" stroke="#626B87" fontSize={10.5} />
                      <YAxis stroke="#626B87" fontSize={10.5} />
                      <Tooltip {...tip} />
                      <Bar dataKey="count" fill="#1D9E75" radius={[5, 5, 0, 0]} maxBarSize={44} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div className="dash-card">
                  <h3>Account distribution</h3>
                  <ResponsiveContainer width="100%" height={215}>
                    <PieChart>
                      <Pie data={accTypes} dataKey="count" nameKey="name"
                           cx="50%" cy="50%" innerRadius={44} outerRadius={74} paddingAngle={3}>
                        {accTypes.map((e, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                      </Pie>
                      <Tooltip {...tip} />
                      <Legend wrapperStyle={{ fontSize: 11.5, color: '#9AA3BF' }} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                <div className="dash-card">
                  <h3>Clients by city</h3>
                  <ResponsiveContainer width="100%" height={215}>
                    <BarChart data={byCity} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" />
                      <XAxis type="number" stroke="#626B87" fontSize={10.5} />
                      <YAxis type="category" dataKey="name" stroke="#626B87" fontSize={10.5} width={62} />
                      <Tooltip {...tip} />
                      <Bar dataKey="count" fill="#7F77DD" radius={[0, 5, 5, 0]} maxBarSize={16} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <div className="dash-card">
                  <h3>Transactions by region</h3>
                  <ResponsiveContainer width="100%" height={215}>
                    <BarChart data={byCity.slice(0, 6)}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" />
                      <XAxis dataKey="name" stroke="#626B87" fontSize={10} />
                      <YAxis stroke="#626B87" fontSize={10.5} />
                      <Tooltip {...tip} />
                      <Bar dataKey="count" fill="#4FC3F7" radius={[5, 5, 0, 0]} maxBarSize={38} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* TOP ACCOUNTS */}
              <div className="dash-card wide">
                <h3>Top accounts by volume</h3>
                <table className="dash-table">
                  <thead>
                    <tr>
                      <th>#</th><th>Account</th><th>Client</th><th>City</th>
                      <th>Type</th><th>Status</th><th>Transactions</th><th>Total (TND)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topAcc.map((a, i) => (
                      <tr key={a.id_compte}>
                        <td className="dim">{i + 1}</td>
                        <td className="mono">{a.id_compte}</td>
                        <td>{a.client || '—'}</td>
                        <td className="dim">{a.ville || '—'}</td>
                        <td>{a.type_compte}</td>
                        <td>
                          <span className={`pill ${a.statut === 'Actif' ? 'ok' : 'off'}`}>{a.statut}</span>
                        </td>
                        <td>{nf(a.tx_count)}</td>
                        <td><b>{nf(a.total, 2)}</b></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}