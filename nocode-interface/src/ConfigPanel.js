import React, { useState, useEffect, useRef } from 'react';
import {
  User, Landmark, Building2, CreditCard,
  Filter, Eraser, Wand2, X, Check,
} from 'lucide-react';
import './ConfigPanel.css';

const SOURCE_TABLES = [
  { value: 'clients',      Icon: User,       label: 'Clients',      desc: 'Staging client records' },
  { value: 'comptes',      Icon: Landmark,   label: 'Accounts',     desc: 'Staging account records' },
  { value: 'agences',      Icon: Building2,  label: 'Branches',     desc: 'Staging branch records' },
  { value: 'transactions', Icon: CreditCard, label: 'Transactions', desc: 'Staging transaction records' },
];

const DESTINATION_TABLES = [
  { value: 'dim_client',        Icon: User,       label: 'dim_client',        desc: 'Client dimension table' },
  { value: 'dim_compte',        Icon: Landmark,   label: 'dim_compte',        desc: 'Account dimension table' },
  { value: 'dim_agence',        Icon: Building2,  label: 'dim_agence',        desc: 'Branch dimension table' },
  { value: 'fait_transactions', Icon: CreditCard, label: 'fait_transactions', desc: 'Transactions fact table' },
];

const SOURCE_COLUMNS = {
  clients:      ['id_client', 'nom', 'prenom', 'date_naissance', 'ville', 'solde'],
  comptes:      ['id_compte', 'id_client', 'type_compte', 'date_ouverture', 'solde', 'statut'],
  agences:      ['id_agence', 'nom_agence', 'ville', 'region', 'telephone'],
  transactions: ['id_transaction', 'id_compte', 'date_transaction', 'montant', 'type_operation', 'description'],
};
const ALL_COLUMNS = [...new Set(Object.values(SOURCE_COLUMNS).flat())];

const TRANSFORM_KINDS = [
  { value: 'filter',          Icon: Filter, label: 'Filter Rows',      desc: 'Keep only rows matching a condition' },
  { value: 'clean_nulls',     Icon: Eraser, label: 'Clean Nulls',      desc: 'Drop or replace empty values' },
  { value: 'transform_value', Icon: Wand2,  label: 'Transform Values', desc: 'Modify column values' },
];

const FILTER_OPERATORS = ['=', '!=', '>', '<', '>=', '<=', 'contains'];
const VALUE_OPERATIONS = [
  { value: 'uppercase', label: 'UPPERCASE' },
  { value: 'lowercase', label: 'lowercase' },
  { value: 'trim',      label: 'Trim spaces' },
  { value: 'round',     label: 'Round (2 decimals)' },
];

const GLOW = { source: '#1D9E75', transform: '#7F77DD', destination: '#378ADD' };

export default function ConfigPanel({ node, position, onClose, onSave }) {
  const [config, setConfig] = useState(node.data.config || {});
  const panelRef = useRef(null);

  useEffect(() => {
    const handle = (e) => {
      if (panelRef.current && !panelRef.current.contains(e.target)) onClose();
    };
    setTimeout(() => document.addEventListener('mousedown', handle), 100);
    return () => document.removeEventListener('mousedown', handle);
  }, [onClose]);

  const type = node.data.type;

  const isDisabled = (() => {
    if (type === 'source') return !config.source_table;
    if (type === 'destination') return !config.destination_table;
    if (type === 'transform') {
      const k = config.transform_kind;
      if (!k) return true;
      if (k === 'filter') return !config.column || !config.operator || !config.value;
      if (k === 'clean_nulls') return !config.column || !config.action ||
        (config.action === 'replace' && !config.default_value);
      if (k === 'transform_value') return !config.column || !config.operation;
    }
    return false;
  })();

  const panelStyle = {
    top:  Math.min(position.y, window.innerHeight - 480),
    left: Math.min(position.x + 20, window.innerWidth - 340),
  };

  const OptionList = ({ items, selected, onPick, kind }) => (
    <>
      {items.map(({ value, Icon, label, desc }) => (
        <div
          key={value}
          className={`config-option ${kind}-option ${selected === value ? 'selected' : ''}`}
          onClick={() => onPick(value)}
        >
          <span className="option-icon"><Icon size={17} /></span>
          <div className="option-text">
            <span className="option-label">{label}</span>
            <span className="option-desc">{desc}</span>
          </div>
        </div>
      ))}
    </>
  );

  const renderSource = () => (
    <div className="config-group">
      <label className="config-label">Select data source</label>
      <p className="config-hint">Which staging table to extract from</p>
      <OptionList
        items={SOURCE_TABLES}
        selected={config.source_table}
        onPick={(v) => setConfig({ source_table: v })}
        kind="source"
      />
    </div>
  );

  const renderDestination = () => (
    <div className="config-group">
      <label className="config-label">Select destination</label>
      <p className="config-hint">Which DWH table to load into</p>
      <OptionList
        items={DESTINATION_TABLES}
        selected={config.destination_table}
        onPick={(v) => setConfig({ destination_table: v })}
        kind="destination"
      />
    </div>
  );

  const renderTransform = () => (
    <div className="config-group">
      <label className="config-label">Transformation type</label>
      <p className="config-hint">Choose what this block does</p>
      <OptionList
        items={TRANSFORM_KINDS}
        selected={config.transform_kind}
        onPick={(v) => setConfig({ transform_kind: v })}
        kind="transform"
      />

      {config.transform_kind === 'filter' && (
        <div className="config-sub">
          <label className="config-sublabel">Condition</label>
          <select className="config-select" value={config.column || ''}
            onChange={(e) => setConfig({ ...config, column: e.target.value })}>
            <option value="">Select column</option>
            {ALL_COLUMNS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className="config-select" value={config.operator || ''}
            onChange={(e) => setConfig({ ...config, operator: e.target.value })}>
            <option value="">Operator</option>
            {FILTER_OPERATORS.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          <input className="config-input" placeholder="Value (e.g. Actif or 1000)"
            value={config.value || ''}
            onChange={(e) => setConfig({ ...config, value: e.target.value })} />
          {config.column && config.operator && config.value && (
            <div className="config-preview">
              WHERE {config.column} {config.operator} {config.value}
            </div>
          )}
        </div>
      )}

      {config.transform_kind === 'clean_nulls' && (
        <div className="config-sub">
          <label className="config-sublabel">Clean empty values in</label>
          <select className="config-select" value={config.column || ''}
            onChange={(e) => setConfig({ ...config, column: e.target.value })}>
            <option value="">Select column</option>
            {ALL_COLUMNS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className="config-select" value={config.action || ''}
            onChange={(e) => setConfig({ ...config, action: e.target.value })}>
            <option value="">Action</option>
            <option value="drop">Drop rows with empty value</option>
            <option value="replace">Replace empty with default</option>
          </select>
          {config.action === 'replace' && (
            <input className="config-input" placeholder="Default value"
              value={config.default_value || ''}
              onChange={(e) => setConfig({ ...config, default_value: e.target.value })} />
          )}
        </div>
      )}

      {config.transform_kind === 'transform_value' && (
        <div className="config-sub">
          <label className="config-sublabel">Apply operation to column</label>
          <select className="config-select" value={config.column || ''}
            onChange={(e) => setConfig({ ...config, column: e.target.value })}>
            <option value="">Select column</option>
            {ALL_COLUMNS.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select className="config-select" value={config.operation || ''}
            onChange={(e) => setConfig({ ...config, operation: e.target.value })}>
            <option value="">Operation</option>
            {VALUE_OPERATIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
      )}
    </div>
  );

  return (
    <div className="config-overlay">
      <div className="config-panel" style={panelStyle} ref={panelRef}>
        <div className="config-glow" style={{ background: GLOW[type] }} />

        <div className="config-header">
          <div className="config-header-left">
            <h3>{node.data.label}</h3>
            <span className={`config-type-badge badge-${type}`}>{type}</span>
          </div>
          <button className="config-close" onClick={onClose}><X size={14} /></button>
        </div>

        <div className="config-body">
          {type === 'source' && renderSource()}
          {type === 'destination' && renderDestination()}
          {type === 'transform' && renderTransform()}
        </div>

        <div className="config-footer">
          <button className="config-cancel-btn" onClick={onClose}>Cancel</button>
          <button
            className="config-save-btn"
            onClick={() => { onSave(node.id, config); onClose(); }}
            disabled={isDisabled}
          >
            <span><Check size={14} /> Save</span>
          </button>
        </div>
      </div>
    </div>
  );
}