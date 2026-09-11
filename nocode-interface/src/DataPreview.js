import React, { useState, useEffect } from 'react';
import { Table2, X, User, Landmark, Building2, CreditCard, AlertCircle, Download } from 'lucide-react';
import { downloadFile } from './download';
import './DataPreview.css';

const TABLES = [
  { schema: 'staging', table: 'clients',      label: 'Clients',      Icon: User },
  { schema: 'staging', table: 'comptes',      label: 'Accounts',     Icon: Landmark },
  { schema: 'staging', table: 'agences',      label: 'Branches',     Icon: Building2 },
  { schema: 'staging', table: 'transactions', label: 'Transactions', Icon: CreditCard },
  { schema: 'datawarehouse', table: 'dim_client',        label: 'dim_client',        Icon: User },
  { schema: 'datawarehouse', table: 'dim_compte',        label: 'dim_compte',        Icon: Landmark },
  { schema: 'datawarehouse', table: 'dim_agence',        label: 'dim_agence',        Icon: Building2 },
  { schema: 'datawarehouse', table: 'fait_transactions', label: 'fait_transactions', Icon: CreditCard },
];

export default function DataPreview({ token, onClose }) {
  const [selected, setSelected] = useState(TABLES[0]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      await downloadFile(
        `/export/table/${selected.schema}/${selected.table}`,
        token,
        `${selected.table}.csv`
      );
    } catch (e) {
      setExportError(e.message);
    }
    setExporting(false);
  };

  const loadData = async (tbl) => {
    setLoading(true);
    setData(null);
    try {
      const res = await fetch(
        `http://localhost:8000/preview/${tbl.schema}/${tbl.table}?limit=25`
      );
      setData(await res.json());
    } catch {
      setData({ error: 'Could not load data' });
    }
    setLoading(false);
  };

  useEffect(() => {
    loadData(selected);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const Group = ({ title, schema }) => (
    <>
      <div className="preview-group-label">{title}</div>
      {TABLES.filter((t) => t.schema === schema).map((t) => (
        <div
          key={`${t.schema}.${t.table}`}
          className={`preview-table-btn ${
            selected.table === t.table && selected.schema === t.schema ? 'active' : ''
          }`}
          onClick={() => setSelected(t)}
        >
          <t.Icon size={14} />
          <span>{t.label}</span>
        </div>
      ))}
    </>
  );

  return (
    <div className="preview-overlay" onClick={onClose}>
      <div className="preview-modal" onClick={(e) => e.stopPropagation()}>

        <div className="preview-header">
          <div className="preview-title">
            <Table2 size={19} />
            <div>
              <h2>Data Preview</h2>
              <p>Inspect any table in the platform</p>
            </div>
          </div>
          <button className="preview-close" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="preview-body">
          <div className="preview-sidebar">
            <Group title="Staging Layer" schema="staging" />
            <Group title="Data Warehouse" schema="datawarehouse" />
          </div>

          <div className="preview-content">
            <div className="preview-content-header">
              <span className="preview-table-name">
                {selected.schema}.{selected.table}
              </span>
              <div className="preview-header-right">
                {data && !data.error && (
                  <span className="preview-count">
                    Showing {data.showing} of {data.total} rows
                  </span>
                )}
                <button className="export-btn" onClick={handleExport} disabled={exporting}>
                  <Download size={14} />
                  <span>{exporting ? 'Exporting…' : 'Export CSV'}</span>
                </button>
              </div>
            </div>

            {exportError && (
              <div className="preview-error"><AlertCircle size={15} /> {exportError}</div>
            )}

            {loading && <div className="preview-loading">Loading data…</div>}

            {data?.error && (
              <div className="preview-error"><AlertCircle size={15} /> {data.error}</div>
            )}

            {data && !data.error && data.rows.length > 0 && (
              <div className="preview-table-wrap">
                <table className="preview-table">
                  <thead>
                    <tr>{data.columns.map((c) => <th key={c}>{c}</th>)}</tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row, i) => (
                      <tr key={i}>
                        {data.columns.map((c) => (
                          <td key={c}>{String(row[c] ?? '—')}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {data && !data.error && data.rows.length === 0 && (
              <div className="preview-empty">This table is empty.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}