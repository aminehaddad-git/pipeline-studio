import React, { useState, useRef, useEffect } from 'react';
import { Bot, X, Send, Sparkles } from 'lucide-react';
import './ChatBot.css';

const SUGGESTIONS = [
  'Give me a summary',
  'How many clients?',
  'Total transaction volume?',
  'Transactions by type',
  'Which region has the most branches?',
];

export default function ChatBot({ token }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    { from: 'bot', text: "Hi! I'm your data assistant. Ask me anything about your warehouse, or pick a suggestion below." },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  const send = async (text) => {
    const msg = text || input;
    if (!msg.trim()) return;
    setMessages((p) => [...p, { from: 'user', text: msg }]);
    setInput('');
    setLoading(true);
    try {
      const res = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: msg }),
      });
      const data = await res.json();
      setMessages((p) => [...p, { from: 'bot', text: data.reply }]);
    } catch {
      setMessages((p) => [...p, { from: 'bot', text: 'Could not reach the assistant.' }]);
    }
    setLoading(false);
  };

  const render = (text) =>
    text.split('\n').map((line, i, arr) => (
      <span key={i}>
        {line.split('**').map((seg, j) => (j % 2 === 1 ? <strong key={j}>{seg}</strong> : seg))}
        {i < arr.length - 1 && <br />}
      </span>
    ));

  return (
    <>
      <button className={`chatbot-fab ${open ? 'open' : ''}`} onClick={() => setOpen(!open)}
              title="Data Assistant">
        {open ? <X size={20} /> : <Bot size={22} />}
      </button>

      {open && (
        <div className="chatbot-window">
          <div className="chatbot-header">
            <div className="chatbot-header-info">
              <span className="chatbot-avatar"><Bot size={18} /></span>
              <div>
                <span className="chatbot-title">Data Assistant</span>
                <span className="chatbot-status">Online</span>
              </div>
            </div>
          </div>

          <div className="chatbot-messages">
            {messages.map((m, i) => (
              <div key={i} className={`chatbot-msg ${m.from}`}>
                {m.from === 'bot' && <span className="chatbot-msg-avatar"><Bot size={15} /></span>}
                <div className="chatbot-bubble">{render(m.text)}</div>
              </div>
            ))}
            {loading && (
              <div className="chatbot-msg bot">
                <span className="chatbot-msg-avatar"><Bot size={15} /></span>
                <div className="chatbot-bubble chatbot-typing"><span /><span /><span /></div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <div className="chatbot-suggestions">
            <span className="sug-label"><Sparkles size={11} /> Try</span>
            {SUGGESTIONS.map((s) => (
              <button key={s} className="chatbot-suggestion" onClick={() => send(s)}>{s}</button>
            ))}
          </div>

          <div className="chatbot-input-area">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && send()}
              placeholder="Ask about your data…"
            />
            <button onClick={() => send()} disabled={loading}><Send size={15} /></button>
          </div>
        </div>
      )}
    </>
  );
}