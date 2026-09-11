import React from 'react';
import { Handle, Position } from 'reactflow';
import { Database, Filter, HardDrive, CheckCircle2, AlertCircle } from 'lucide-react';
import './CustomNode.css';

const ICONS = {
  source: Database,
  transform: Filter,
  destination: HardDrive,
};

export default function CustomNode({ data }) {
  const Icon = ICONS[data.type] || Database;
  const configured = data.configured;

  return (
    <div className={`cnode cnode-${data.type} ${configured ? 'is-configured' : ''}`}>
      {/* incoming connection point (not on source blocks) */}
      {data.type !== 'source' && (
        <Handle type="target" position={Position.Left} className="cnode-handle" />
      )}

      <div className="cnode-icon" style={{ background: data.color }}>
        <Icon size={16} strokeWidth={2.2} color="#fff" />
      </div>

      <div className="cnode-body">
        <span className="cnode-type">{data.type}</span>
        <span className="cnode-label">{data.label}</span>
      </div>

      <div className="cnode-status">
        {configured
          ? <CheckCircle2 size={14} className="cnode-ok" />
          : <AlertCircle size={14} className="cnode-warn" />}
      </div>

      {/* outgoing connection point (not on destination blocks) */}
      {data.type !== 'destination' && (
        <Handle type="source" position={Position.Right} className="cnode-handle" />
      )}
    </div>
  );
}