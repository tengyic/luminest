import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '../api/client';
import type { Lesson, LessonBlock, LessonMedia } from '../api/types';

function Media({ media }: { media: LessonMedia }) {
  if (media.embed) {
    return (
      <div className="media-embed">
        <iframe title={media.caption || 'media'} src={media.embed} allowFullScreen sandbox="" />
      </div>
    );
  }
  if (media.url) {
    if (media.kind === 'image' || (media.type || '').includes('image')) {
      return (
        <div className="media-image">
          <img src={media.url} alt={media.caption || ''} loading="lazy" />
          {media.caption && <p className="caption">{media.caption}</p>}
        </div>
      );
    }
    return (
      <a className="media-link" href={media.url} target="_blank" rel="noreferrer">
        {media.caption || media.url}
      </a>
    );
  }
  return null;
}

function Block({ block }: { block: LessonBlock }) {
  if (block.media) {
    return (
      <div className="block">
        <Media media={block.media} />
        {block.caption && <p className="caption">{block.caption}</p>}
      </div>
    );
  }
  if (block.html) {
    return <div className="block" dangerouslySetInnerHTML={{ __html: block.html }} />;
  }
  if (block.text) {
    return <div className="block prose">{block.text}</div>;
  }
  return null;
}

export default function Lesson() {
  const { conceptId } = useParams<{ conceptId: string }>();
  const navigate = useNavigate();
  const [lesson, setLesson] = useState<Lesson | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!conceptId) return;
    setLoading(true);
    setError(null);
    try {
      const l = await api.lesson(conceptId);
      setLesson(l);
    } catch (err: any) {
      setError(err?.message || 'Could not load this lesson');
    } finally {
      setLoading(false);
    }
  }, [conceptId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <div className="center-note">Loading lesson…</div>;
  if (error) return <div className="card error">{error}</div>;
  if (!lesson) return <div className="center-note">No lesson.</div>;

  return (
    <div className="lesson">
      <div className="card">
        <div className="lesson-head">
          <h2>{lesson.title}</h2>
          <div className="meta">
            {lesson.unit && <span className="tag">{lesson.unit}</span>}
            {lesson.strand && <span className="tag">{lesson.strand}</span>}
            {lesson.generated && <span className="tag">generated</span>}
          </div>
        </div>

        {(lesson.blocks ?? []).map((b, i) => (
          <Block key={i} block={b} />
        ))}

        {lesson.media && lesson.media.length > 0 && (
          <div className="media-row">
            {lesson.media.map((m, i) => (
              <Media key={i} media={m} />
            ))}
          </div>
        )}

        {lesson.summary && (
          <div className="summary">
            <h3>Summary</h3>
            <p>{lesson.summary}</p>
          </div>
        )}
        {lesson.hint && (
          <p className="hint">
            <strong>Hint:</strong> {lesson.hint}
          </p>
        )}
      </div>

      <div className="row">
        {conceptId && (
          <button className="primary" onClick={() => navigate(`/quiz?concept_id=${encodeURIComponent(conceptId)}`)}>
            Practice this concept
          </button>
        )}
      </div>
    </div>
  );
}
