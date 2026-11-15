import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';
import type { AttemptResult, Question } from '../api/types';
import { useAuth } from '../auth/AuthContext';

export default function Quiz() {
  const [params] = useSearchParams();
  const conceptId = params.get('concept_id') || undefined;
  const { user } = useAuth();

  const [question, setQuestion] = useState<Question | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const startedAt = useRef<number>(Date.now());

  const next = useCallback(async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setSelected(null);
    startedAt.current = Date.now();
    try {
      const q = await api.questionsNext({ mode: 'practice', concept_id: conceptId });
      setQuestion(q);
    } catch (err: any) {
      setError(err?.message || 'No questions available');
    } finally {
      setLoading(false);
    }
  }, [conceptId]);

  useEffect(() => {
    next();
  }, [next]);

  async function submit() {
    if (!question || !selected) return;
    setLoading(true);
    setError(null);
    const elapsed_seconds = Math.max(0, (Date.now() - startedAt.current) / 1000);
    try {
      const res = await api.submitAttempt({
        question_id: question.id,
        option_id: selected,
        receipt: question.receipt,
        client_event_id:
          typeof crypto !== 'undefined' && 'randomUUID' in crypto
            ? crypto.randomUUID()
            : `ce_${Date.now()}_${Math.random().toString(36).slice(2)}`,
        elapsed_seconds,
      });
      setResult(res);
    } catch (err: any) {
      setError(err?.message || 'Could not submit answer');
    } finally {
      setLoading(false);
    }
  }

  if (loading && !question) return <div className="center-note">Loading question…</div>;
  if (error && !question) return <div className="card error">{error}</div>;
  if (!question) return <div className="center-note">No question.</div>;

  return (
    <div className="quiz card">
      {question.concept_title && <p className="muted small">{question.concept_title}</p>}
      <h2 className="prompt">{question.prompt}</h2>

      <div className="options">
        {question.options.map((opt) => {
          const isSelected = selected === opt.id;
          const wasCorrect = result?.correct && selected === opt.id;
          const wasWrong = result && !result.correct && selected === opt.id;
          return (
            <button
              key={opt.id}
              className={`option ${isSelected ? 'selected' : ''} ${wasCorrect ? 'right' : ''} ${wasWrong ? 'wrong' : ''}`}
              disabled={!!result || loading}
              onClick={() => setSelected(opt.id)}
            >
              {opt.text}
            </button>
          );
        })}
      </div>

      {!result && (
        <button className="primary" disabled={!selected || loading} onClick={submit}>
          Submit
        </button>
      )}

      {result && (
        <div className={`result ${result.correct ? 'ok' : 'fail'}`}>
          {result.correct ? 'Correct!' : 'Not quite.'}
        </div>
      )}

      {error && <div className="error">{error}</div>}

      {result && (
        <button className="secondary" onClick={next} disabled={loading}>
          Next question
        </button>
      )}

      {user && (
        <p className="muted small">
          Signed in as {user.email}. Answers are graded server-side and feed spaced-repetition.
        </p>
      )}
    </div>
  );
}
