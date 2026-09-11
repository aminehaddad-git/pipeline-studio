import React, { useState, useEffect } from 'react';
import {
  ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { TrendingUp, X, RefreshCw, Award, Info, Download } from 'lucide-react';
import { downloadFile } from './download';
import './Forecast.css';

const METRICS = [
  { key: 'transactions_count',  label: 'Transaction Volume' },
  { key: 'transactions_amount', label: 'Transaction Amount' },
  { key: 'account_openings',    label: 'New Accounts' },
];

const METHODS = [
  { key: 'auto',              label: 'Auto (best)' },
  { key: 'moving_average',    label: 'Moving Average' },
  { key: 'linear_regression', label: 'Linear Regression' },
  { key: 'holt_linear',       label: 'Holt Linear' },
  { key: 'holt_winters',      label: 'Holt-Winters' },
];

export default function Forecast({ token, onClose }) {
  const [metric, setMetric] = useState('transactions_amount');
  const [horizon, setHorizon] = useState(6);
  const [method, setMethod] = useState('auto');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    setExporting(true);
    try {
      await downloadFile(
        `/export/forecast/${metric}?horizon=${horizon}&method=${method}`,
        token,
        'forecast.xlsx'
      );
    } catch (e) {
      setError(e.message);
    }
    setExporting(false);
  };

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const res = await fetch(
        `http://localhost:8000/forecast/${metric}?horizon=${horizon}&method=${method}`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const json = await res.json();
      if (json.error) { setError(json.error); setData(null); }
      else setData(json);
    } catch (e) {
      setError('Could not reach the backend.');
    }
    setLoading(false);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric, horizon, method]);

  // Merge history + forecast into one chart series
  const chartData = data ? (() => {
    const hist = data.history.map((h) => ({
      period: h.period, actual: h.value,
    }));
    if (hist.length) {
      // bridge the two lines
      hist[hist.length - 1].forecast = data.history[data.history.length - 1].value;
      hist[hist.length - 1].lower = data.history[data.history.length - 1].value;
      hist[hist.length - 1].upper = data.history[data.history.length - 1].value;
    }
    const fut = data.forecast.map((f) => ({
      period: f.period, forecast: f.value, lower: f.lower, upper: f.upper,
      band: [f.lower, f.upper],
    }));
    hist.forEach((h) => { h.band = [h.lower, h.upper]; });
    return [...hist, ...fut];
  })() : [];

  const fmt = (v) => {
    if (v == null) return '—';
    if (Math.abs(v) >= 1000) return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(v);
    return Math.round(v * 100) / 100;
  };

  const lastHist = data?.history?.[data.history.length - 1]?.period;

  return (
    <div className="fc-overlay" onClick={onClose}>
      <div className="fc-modal" onClick={(e) => e.stopPropagation()}>

        <div className="fc-head">
          <div className="fc-title">
            <TrendingUp size={19} />
            <div>
              <h2>Forecasting</h2>
              <p>Predictive analysis on warehouse time series</p>
            </div>
          </div>
          <div className="fc-head-actions">
            <button className="export-btn" onClick={handleExport} disabled={exporting || !data}>
              <Download size={14} />
              <span>{exporting ? 'Exporting…' : 'Export Excel'}</span>
            </button>
            <button className="fc-icon" onClick={load} title="Recompute"><RefreshCw size={15} /></button>
            <button className="fc-icon danger" onClick={onClose}><X size={16} /></button>
          </div>
        </div>

        <div className="fc-controls">
          <div className="fc-field">
            <label>Series</label>
            <select value={metric} onChange={(e) => setMetric(e.target.value)}>
              {METRICS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>
          <div className="fc-field">
            <label>Horizon</label>
            <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
              {[3, 6, 9, 12].map((h) => <option key={h} value={h}>{h} months</option>)}
            </select>
          </div>
          <div className="fc-field">
            <label>Method</label>
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              {METHODS.map((m) => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>
        </div>

        <div className="fc-body">
          {loading && <div className="fc-msg">Computing forecast…</div>}
          {error && <div className="fc-msg err"><Info size={15} /> {error}</div>}

          {data && !loading && (
            <>
              <div className="fc-summary">
                <div className="fc-chip">
                  <Award size={14} />
                  <span>Selected: <b>{data.selected_label}</b></span>
                  {data.auto_selected && <em>auto-chosen</em>}
                </div>
                <div className="fc-chip muted">
                  {data.months_available} months history · train {data.train_size} / test {data.test_size}
                </div>
              </div>

              <div className="fc-chart">
                <ResponsiveContainer width="100%" height={300}>
                  <ComposedChart data={chartData} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.07)" />
                    <XAxis dataKey="period" stroke="#626B87" fontSize={10.5}
                           tickFormatter={(t) => t.slice(2)} />
                    <YAxis stroke="#626B87" fontSize={10.5} tickFormatter={fmt} width={58} />
                    <Tooltip
                      contentStyle={{ background: '#11152A', border: '1px solid rgba(255,255,255,0.12)',
                                      borderRadius: 10, color: '#E8EAF2', fontSize: 12 }}
                      formatter={(v, n) => [fmt(v), n]}
                    />
                    <Legend wrapperStyle={{ fontSize: 11.5, color: '#9AA3BF' }} />
                    {lastHist && <ReferenceLine x={lastHist} stroke="#EF9F27"
                                   strokeDasharray="4 4" label={{ value: 'now', fill: '#EF9F27', fontSize: 10 }} />}
                    <Area type="monotone" dataKey="band" name="Confidence"
                          stroke="none" fill="#378ADD" fillOpacity={0.16} />
                    <Line type="monotone" dataKey="actual" name="Actual"
                          stroke="#1D9E75" strokeWidth={2.2} dot={false} />
                    <Line type="monotone" dataKey="forecast" name="Forecast"
                          stroke="#4FC3F7" strokeWidth={2.2} strokeDasharray="6 4" dot={{ r: 2.5 }} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>

              <div className="fc-section-label">Method comparison (evaluated on held-out test set)</div>
              <table className="fc-table">
                <thead>
                  <tr>
                    <th>Method</th><th>Models</th>
                    <th>MAE</th><th>RMSE</th><th>MAPE</th><th>R²</th>
                  </tr>
                </thead>
                <tbody>
                  {data.comparison.map((c) => (
                    <tr key={c.method} className={c.method === data.selected_method ? 'best' : ''}>
                      <td>
                        {c.method === data.selected_method && <Award size={12} />}
                        {c.label}
                      </td>
                      <td className="dim">{c.models}</td>
                      <td>{fmt(c.MAE)}</td>
                      <td>{fmt(c.RMSE)}</td>
                      <td>{c.MAPE != null ? `${c.MAPE}%` : '—'}</td>
                      <td className={c.R2 > 0.5 ? 'good' : c.R2 < 0 ? 'bad' : ''}>{c.R2}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <div className="fc-section-label">Forecast values</div>
              <table className="fc-table">
                <thead>
                  <tr><th>Period</th><th>Forecast</th><th>Lower bound</th><th>Upper bound</th></tr>
                </thead>
                <tbody>
                  {data.forecast.map((f) => (
                    <tr key={f.period}>
                      <td>{f.period}</td>
                      <td><b>{fmt(f.value)}</b> <span className="dim">{data.unit}</span></td>
                      <td className="dim">{fmt(f.lower)}</td>
                      <td className="dim">{fmt(f.upper)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </div>
    </div>
  );
}