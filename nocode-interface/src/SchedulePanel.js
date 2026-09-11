import React, { useState, useEffect } from 'react';
import './SchedulePanel.css';
import { Clock, X, Plus, CalendarClock, CalendarDays, Timer,
         Play, Pause, Trash2, AlertCircle, CheckCircle2 } from 'lucide-react';

const FREQUENCIES = [
  { value: 'hourly', Icon: Timer,         label: 'Every Hour', desc: 'Runs at the start of every hour' },
  { value: 'daily',  Icon: CalendarClock, label: 'Every Day',  desc: 'Runs once a day at a set time' },
  { value: 'weekly', Icon: CalendarDays,  label: 'Every Week', desc: 'Runs once a week on a set day' },
];

const DAYS = [
  { value: 'mon', label: 'Monday' },
  { value: 'tue', label: 'Tuesday' },
  { value: 'wed', label: 'Wednesday' },
  { value: 'thu', label: 'Thursday' },
  { value: 'fri', label: 'Friday' },
  { value: 'sat', label: 'Saturday' },
  { value: 'sun', label: 'Sunday' },
];

export default function SchedulePanel({ token, onClose }) {
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [message, setMessage] = useState(null);
  const [form, setForm] = useState({
    name: '',
    frequency: 'daily',
    run_time: '08:00',
    day_of_week: 'mon',
    pipeline_id: '',
  });
  const [availablePipelines, setAvailablePipelines] = useState([]);

  const fetchSchedules = async () => {
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/schedules', {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.schedules) setSchedules(data.schedules);
    } catch (e) {
      setMessage({ error: 'Could not load schedules' });
    }
    setLoading(false);
  };

  const fetchAvailablePipelines = async () => {
    try {
      const res = await fetch('http://localhost:8000/pipelines', {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (data.pipelines) setAvailablePipelines(data.pipelines);
    } catch (e) {
      console.error('Could not load pipelines');
    }
  };

  useEffect(() => {
    fetchSchedules();
    fetchAvailablePipelines();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCreate = async () => {
    if (!form.name) {
      setMessage({ error: 'Please enter a schedule name' });
      return;
    }
    try {
      const res = await fetch('http://localhost:8000/schedules', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          ...form,
          pipeline_id: form.pipeline_id ? parseInt(form.pipeline_id) : null,
        }),
      });
      const data = await res.json();
      if (res.ok) {
        setMessage({ success: data.message });
        setForm({ name: '', frequency: 'daily', run_time: '08:00', day_of_week: 'mon', pipeline_id: '' });
        setShowForm(false);
        fetchSchedules();
      } else {
        const errMsg = typeof data.detail === 'string'
          ? data.detail
          : 'Failed to create schedule (validation error)';
        setMessage({ error: errMsg });
      }
    } catch (e) {
      setMessage({ error: 'Could not create schedule' });
    }
  };

  const toggleSchedule = async (id) => {
    try {
      await fetch(`http://localhost:8000/schedules/${id}/toggle`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      fetchSchedules();
    } catch (e) {
      setMessage({ error: 'Could not toggle schedule' });
    }
  };

  const deleteSchedule = async (id) => {
    if (!window.confirm('Delete this schedule?')) return;
    try {
      await fetch(`http://localhost:8000/schedules/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      fetchSchedules();
    } catch (e) {
      setMessage({ error: 'Could not delete schedule' });
    }
  };

  const describeSchedule = (s) => {
    let freq = s.frequency;
    if (s.frequency === 'hourly') freq = 'Every hour';
    else if (s.frequency === 'daily') freq = `Every day at ${s.run_time}`;
    else if (s.frequency === 'weekly') {
      const day = DAYS.find(d => d.value === s.day_of_week)?.label || s.day_of_week;
      freq = `Every ${day} at ${s.run_time}`;
    }
    const pname = availablePipelines.find(p => Number(p.id) === Number(s.pipeline_id))?.name;
    return pname ? `${freq} · runs "${pname}"` : `${freq} · runs Full ETL`;
  };

  const formatDate = (iso) => {
    if (!iso) return 'Never';
    try {
      return new Date(iso).toLocaleString('en-GB', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'
      });
    } catch { return iso; }
  };

  return (
    <div className="sched-overlay" onClick={onClose}>
      <div className="sched-modal" onClick={(e) => e.stopPropagation()}>

        <div className="sched-header">
          <div>
            <h2><Clock size={18} /> Pipeline Scheduler</h2>
            <p>Automate your pipelines to run on a schedule</p>
          </div>
          <button className="sched-close" onClick={onClose}><X size={16} /></button>
        </div>

        <div className="sched-body">
          {message && (
            <div className={`sched-message ${message.error ? 'error' : 'success'}`}>
              {message.error
                ? <><AlertCircle size={15} /> {message.error}</>
                : <><CheckCircle2 size={15} /> {message.success}</>}
            </div>
          )}

          <div className="sched-toolbar">
            <span className="sched-count">{schedules.length} schedule(s)</span>
            <button className="sched-add-btn" onClick={() => setShowForm(!showForm)}>
              {showForm ? <><X size={14} /> Cancel</> : <><Plus size={14} /> New Schedule</>}
            </button>
          </div>

          {showForm && (
            <div className="sched-form">
              <div className="sched-field">
                <label>Schedule Name</label>
                <input
                  placeholder="e.g. Daily morning load"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </div>

            <div className="sched-field">
                <label>Pipeline to Run</label>
                <select
                  value={form.pipeline_id}
                  onChange={(e) => setForm({ ...form, pipeline_id: e.target.value })}
                >
                  <option value="">⚡ Full ETL (all tables)</option>
                  {availablePipelines.map((p) => (
                    <option key={p.id} value={p.id}>📊 {p.name}</option>
                  ))}
                </select>
              </div>

              <div className="sched-field">
                <label>Frequency</label>
                <div className="sched-freq-options">
                  {FREQUENCIES.map((f) => (
                    <div
                      key={f.value}
                      className={`sched-freq ${form.frequency === f.value ? 'selected' : ''}`}
                      onClick={() => setForm({ ...form, frequency: f.value })}
                    >
                      <span className="sched-freq-icon"><f.Icon size={20} /></span>
                      <span className="sched-freq-label">{f.label}</span>
                      <span className="sched-freq-desc">{f.desc}</span>
                    </div>
                  ))}
                </div>
              </div>

              {(form.frequency === 'daily' || form.frequency === 'weekly') && (
                <div className="sched-field">
                  <label>Time</label>
                  <input
                    type="time"
                    value={form.run_time}
                    onChange={(e) => setForm({ ...form, run_time: e.target.value })}
                  />
                </div>
              )}

              {form.frequency === 'weekly' && (
                <div className="sched-field">
                  <label>Day of Week</label>
                  <select
                    value={form.day_of_week}
                    onChange={(e) => setForm({ ...form, day_of_week: e.target.value })}
                  >
                    {DAYS.map((d) => (
                      <option key={d.value} value={d.value}>{d.label}</option>
                    ))}
                  </select>
                </div>
              )}

              <button className="sched-create-btn" onClick={handleCreate}>
                <CheckCircle2 size={15} /> Create Schedule
              </button>
            </div>
          )}

          {loading ? (
            <div className="sched-loading">Loading schedules...</div>
          ) : schedules.length === 0 ? (
            <div className="sched-empty">
              No schedules yet. Create one to automate your pipelines!
            </div>
          ) : (
            <div className="sched-list">
              {schedules.map((s) => (
                <div key={s.id} className={`sched-item ${!s.is_active ? 'paused' : ''}`}>
                  <div className="sched-item-left">
                    <div className="sched-item-status">
                      <span className={`sched-dot ${s.is_active ? 'active' : 'paused'}`}></span>
                    </div>
                    <div className="sched-item-info">
                      <span className="sched-item-name">{s.name}</span>
                      <span className="sched-item-desc">{describeSchedule(s)}</span>
                      <span className="sched-item-meta">
                        Last run: {formatDate(s.last_run)} · by {s.created_by}
                      </span>
                    </div>
                  </div>
                  <div className="sched-item-actions">
                    <button
                      className="sched-toggle-btn"
                      onClick={() => toggleSchedule(s.id)}
                      title={s.is_active ? 'Pause' : 'Resume'}
                    >
                      {s.is_active ? <Pause size={15} /> : <Play size={15} />}
                    </button>
                    <button
                      className="sched-delete-btn"
                      onClick={() => deleteSchedule(s.id)}
                      title="Delete"
                    >
                      <Trash2 size={15} />
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