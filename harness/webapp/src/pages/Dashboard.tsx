import { FormEvent, useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/client';
import type { CapabilitiesResponse, Concept, CurriculumResponse } from '../api/types';
import { useAuth } from '../auth/AuthContext';

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [caps, setCaps] = useState<CapabilitiesResponse | null>(null);
  const [curriculum, setCurriculum] = useState<CurriculumResponse | null>(null);
  const [text, setText] = useState('');
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const c = await api.curriculum();
      setCurriculum(c);
    } catch (err: any) {
      setError(err?.message || 'Could not load your course');
    }
  }, []);

  useEffect(() => {
    api
      .capabilities()
      .then(setCaps)
      .catch(() => undefined);
    load();
  }, [load]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!text.trim()) return;
    setBusy(true);
    try {
      const res = await api.createCourse({ text: text.trim(), title: title.trim() || undefined });
      if (!res.enrolled && res.course?.id) {
        await api.enrol(res.course.id);
      }
      setText('');
      setTitle('');
      await load();
    } catch (err: any) {
      setError(err?.message || 'Could not build the course');
    } finally {
      setBusy(false);
    }
  }

  const concepts: Concept[] = curriculum?.concepts ?? [];
  const enabledCount = (caps?.capabilities ?? []).filter((c) => c.state === 'enabled' || c.state === 'alpha_free').length;

  return (
    <div className="dash">
      <section className="card">
        <h2>Welcome{user?.name ? `, ${user.name}` : ''}</h2>
        <p className="muted">
          This is the cross-platform web client for Luminest. It talks to the same backend as the macOS app.
        </p>
        {caps && (
          <p className="muted small">
            {enabledCount}/{caps.capabilities.length} capabilities enabled for this build.
          </p>
        )}
      </section>

      <section className="card">
        <h3>Build a course from your notes</h3>
        <form onSubmit={handleCreate}>
          <label>
            Title <span className="muted small">(optional)</span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Algebra basics" />
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={7}
            placeholder="Paste a chapter, article, or your own notes. Luminest extracts concepts, orders them, and writes quiz questions."
          />
          {error && <div className="error">{error}</div>}
          <button className="primary" disabled={busy} type="submit">
            {busy ? 'Building…' : 'Build course'}
          </button>
        </form>
      </section>

      <section className="card">
        <h3>Your course</h3>
        {concepts.length === 0 ? (
          <p className="muted">No concepts yet — build a course above to populate your curriculum.</p>
        ) : (
          <ul className="concept-list">
            {concepts.map((c) => (
              <li key={c.id} className="concept">
                <button className="linkish" onClick={() => navigate(`/lesson/${encodeURIComponent(c.id)}`)}>
                  {c.title}
                </button>
                <div className="meta">
                  {c.unit && <span className="tag">{c.unit}</span>}
                  {typeof c.mastery === 'number' && <span className="tag">mastery {Math.round(c.mastery * 100)}%</span>}
                  {typeof c.recall === 'number' && <span className="tag">recall {Math.round(c.recall * 100)}%</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
