import React, { useState, useRef } from 'react';
import Papa from 'papaparse';
import './SmartUpload.css';
import { Upload, X, User, Landmark, Building2, CreditCard,
         ArrowUp, AlertCircle, CheckCircle2, ArrowLeft } from 'lucide-react';

const TARGET_TABLES = [
  { value: 'clients',      Icon: User,       label: 'Clients',      cols: ['id_client', 'nom', 'prenom', 'date_naissance', 'ville', 'solde'] },
  { value: 'comptes',      Icon: Landmark,   label: 'Accounts',     cols: ['id_compte', 'id_client', 'type_compte', 'date_ouverture', 'solde', 'statut'] },
  { value: 'agences',      Icon: Building2,  label: 'Branches',     cols: ['id_agence', 'nom_agence', 'ville', 'region', 'telephone'] },
  { value: 'transactions', Icon: CreditCard, label: 'Transactions', cols: ['id_transaction', 'id_compte', 'date_transaction', 'montant', 'type_operation', 'description'] },
];

export default function SmartUpload({ token, onClose, onUploadSuccess }) {
  const [step, setStep] = useState(1); // 1=choose table+file, 2=map columns, 3=done
  const [target, setTarget] = useState(null);
  const [file, setFile] = useState(null);
  const [fileColumns, setFileColumns] = useState([]);
  const [fileRows, setFileRows] = useState([]);
  const [mapping, setMapping] = useState({});
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const fileInputRef = useRef(null);

  const selectedTable = TARGET_TABLES.find(t => t.value === target);

  // Parse the file locally with PapaParse (CSV) to get columns + rows
  const handleFile = (f) => {
    const name = f.name.toLowerCase();
    if (!name.endsWith('.csv')) {
      setResult({ error: 'For smart mapping, please use a .csv file' });
      return;
    }
    setFile(f);
    setResult(null);
    Papa.parse(f, {
      header: true,
      skipEmptyLines: true,
      complete: (res) => {
        const cols = res.meta.fields || [];
        setFileColumns(cols);
        setFileRows(res.data);
        // Auto-map: if a file column matches a system column exactly, pre-fill it
        if (selectedTable) {
          const autoMap = {};
          selectedTable.cols.forEach((sysCol) => {
            const match = cols.find(
              (fc) => fc.toLowerCase().trim() === sysCol.toLowerCase().trim()
            );
            if (match) autoMap[sysCol] = match;
          });
          setMapping(autoMap);
        }
        setStep(2);
      },
      error: () => setResult({ error: 'Could not parse the CSV file' }),
    });
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
  };

  const handleImport = async () => {
    // Validate all system columns are mapped
    const unmapped = selectedTable.cols.filter((c) => !mapping[c]);
    if (unmapped.length > 0) {
      setResult({ error: `Please map all columns. Missing: ${unmapped.join(', ')}` });
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const res = await fetch('http://localhost:8000/upload/import-mapped', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          target_table: target,
          mapping,
          rows: fileRows,
        }),
      });
      const data = await res.json();
      if (data.status === 'success') {
        setResult({ success: data.message });
        setStep(3);
        if (onUploadSuccess) onUploadSuccess();
      } else {
        setResult({ error: data.error || data.detail || 'Import failed' });
      }
    } catch (e) {
      setResult({ error: 'Could not connect to backend' });
    }
    setLoading(false);
  };

  const reset = () => {
    setStep(1);
    setTarget(null);
    setFile(null);
    setFileColumns([]);
    setFileRows([]);
    setMapping({});
    setResult(null);
  };

  return (
    <div className="su-overlay" onClick={onClose}>
      <div className="su-modal" onClick={(e) => e.stopPropagation()}>

        <div className="su-header">
          <div>
            <h2><Upload size={18} /> Smart Data Import</h2>
            <p>Upload any CSV — map its columns to your tables</p>
          </div>
          <button className="su-close" onClick={onClose}><X size={16} /></button>
        </div>

        {/* Step indicator */}
        <div className="su-steps">
          <div className={`su-step ${step >= 1 ? 'active' : ''}`}>1. Choose</div>
          <div className="su-step-line"></div>
          <div className={`su-step ${step >= 2 ? 'active' : ''}`}>2. Map</div>
          <div className="su-step-line"></div>
          <div className={`su-step ${step >= 3 ? 'active' : ''}`}>3. Done</div>
        </div>

        <div className="su-body">
          {/* STEP 1 — choose table + file */}
          {step === 1 && (
            <>
              <label className="su-label">Target table</label>
              <div className="su-targets">
                {TARGET_TABLES.map((t) => (
                  <div
                    key={t.value}
                    className={`su-target ${target === t.value ? 'selected' : ''}`}
                    onClick={() => setTarget(t.value)}
                  >
                    <span className="su-target-icon"><t.Icon size={18} /></span>
                    <span className="su-target-label">{t.label}</span>
                  </div>
                ))}
              </div>

              {target && (
                <>
                  <label className="su-label">Upload CSV file</label>
                  <div
                    className={`su-dropzone ${dragOver ? 'dragover' : ''}`}
                    onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current.click()}
                  >
                    <input
                      type="file"
                      ref={fileInputRef}
                      style={{ display: 'none' }}
                      accept=".csv"
                      onChange={(e) => e.target.files[0] && handleFile(e.target.files[0])}
                    />
                    <span className="su-drop-icon"><ArrowUp size={26} /></span>
                    <span className="su-drop-text">Drag & drop your CSV, or click to browse</span>
                    <span className="su-drop-hint">Any column names — you'll map them next</span>
                  </div>
                </>
              )}
            </>
          )}

          {/* STEP 2 — map columns */}
          {step === 2 && selectedTable && (
            <>
              <div className="su-map-intro">
                Match each <strong>system column</strong> to a column from your file <span className="su-filename">📄 {file?.name}</span>
              </div>
              <div className="su-mapping">
                <div className="su-mapping-head">
                  <span>System Column (required)</span>
                  <span>Your File Column</span>
                </div>
                {selectedTable.cols.map((sysCol) => (
                  <div className="su-map-row" key={sysCol}>
                    <span className="su-sys-col">{sysCol}</span>
                    <span className="su-arrow">←</span>
                    <select
                      className={mapping[sysCol] ? 'mapped' : 'unmapped'}
                      value={mapping[sysCol] || ''}
                      onChange={(e) => setMapping({ ...mapping, [sysCol]: e.target.value })}
                    >
                      <option value="">— Select a column —</option>
                      {fileColumns.map((fc) => (
                        <option key={fc} value={fc}>{fc}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>

              <div className="su-preview-note">
                {fileRows.length} rows ready to import
              </div>
            </>
          )}

          {/* STEP 3 — done */}
          {step === 3 && (
            <div className="su-done">
              <span className="su-done-icon"><CheckCircle2 size={42} /></span>
              <h3>Import Complete!</h3>
              <p>{result?.success}</p>
            </div>
          )}

          {/* Result message */}
          {result && step !== 3 && (
            <div className={`su-result ${result.error ? 'error' : 'success'}`}>
              {result.error
                ? <><AlertCircle size={15} /> {result.error}</>
                : <><CheckCircle2 size={15} /> {result.success}</>}
            </div>
          )}
        </div>

        <div className="su-footer">
          {step === 1 && (
            <button className="su-cancel" onClick={onClose}>Cancel</button>
          )}
          {step === 2 && (
            <>
              <button className="su-cancel" onClick={reset}><ArrowLeft size={14} /> Back</button>
              <button className="su-submit" onClick={handleImport} disabled={loading}>
                {loading ? 'Importing…' : <><CheckCircle2 size={15} /> Import Data</>}
              </button>
            </>
          )}
          {step === 3 && (
            <>
              <button className="su-cancel" onClick={reset}>Import Another</button>
              <button className="su-submit" onClick={onClose}>Done</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}