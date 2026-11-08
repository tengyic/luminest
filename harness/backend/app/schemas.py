import math
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Login(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=10, max_length=128)

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        value = value.strip().casefold()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Invalid email address')
        return value

    @field_validator('password', mode='before')
    @classmethod
    def preserve_password(cls, value):
        return value


class Register(Login):
    name: str = Field(min_length=1, max_length=100)
    #: Beta access. Optional so a self-hosted or development instance needs no code.
    invite_code: str | None = Field(default=None, max_length=64)
    #: Launch gate. Required in production (see ``Settings.require_launch_gate``); the
    #: schema keeps them optional so local development and tests stay simple.
    age_confirmed: bool | None = Field(default=None, strict=True)
    accept_terms: bool | None = Field(default=None, strict=True)

    @field_validator('name')
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError('Name must not be blank')
        return value.strip()


class WaitlistJoin(Input):
    email: str = Field(min_length=3, max_length=254)
    name: str | None = Field(default=None, max_length=100)
    source: Literal['landing', 'referral', 'teacher', 'partner', 'event', 'import'] = 'landing'
    referrer_code: str | None = Field(default=None, max_length=16)
    consent_marketing: bool = Field(default=False, strict=True)

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        value = value.strip().casefold()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Invalid email address')
        return value


class TokenOnly(Input):
    token: str = Field(min_length=10, max_length=200)


class ForgotPassword(Input):
    email: str = Field(min_length=3, max_length=254)

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        return value.strip().casefold()


class ResetPassword(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(min_length=10, max_length=128)

    @field_validator('password', mode='before')
    @classmethod
    def preserve_password(cls, value):
        return value


class RefreshRequest(Input):
    refresh_token: str = Field(min_length=10, max_length=200)


class InviteRedeem(Input):
    code: str = Field(min_length=4, max_length=64)


class InviteCreate(Input):
    email: str | None = Field(default=None, max_length=254)
    cohort_id: str | None = Field(default=None, max_length=36)
    max_uses: int = Field(default=1, ge=1, le=1000)
    expires_in_days: int | None = Field(default=30, ge=1, le=365)
    count: int = Field(default=1, ge=1, le=200)


class CohortCreate(Input):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    rollout_stage: Literal['internal', 'closed_beta', 'open_beta', 'general'] = 'closed_beta'
    token_quota_monthly: int | None = Field(default=None, ge=0)
    request_quota_daily: int | None = Field(default=None, ge=0)


class FeedbackInput(Input):
    kind: Literal['bug', 'idea', 'praise', 'question', 'nps', 'csat', 'survey', 'accessibility',
                  'content_error']
    message: str = Field(min_length=3, max_length=8000)
    rating: int | None = Field(default=None, ge=0, le=10)
    contact_email: str | None = Field(default=None, max_length=254)
    severity: Literal['low', 'medium', 'high', 'critical'] | None = None
    client_event_id: str | None = Field(default=None, max_length=100)
    context: dict = Field(default_factory=dict)


class PreferencePatch(Input):
    theme: Literal['system', 'light', 'dark', 'high_contrast'] | None = None
    default_modality: Literal['reading', 'visual', 'practice', 'audio'] | None = None
    accessibility: dict | None = None
    notifications: dict | None = None
    ui: dict | None = None

    @field_validator('theme', 'default_modality', 'accessibility', 'notifications', 'ui')
    @classmethod
    def no_null(cls, value):
        if value is None:
            raise ValueError('Explicit null is not supported')
        return value


class Profile(Input):
    goal: str | None = Field(default=None, min_length=1, max_length=500)
    daily_minutes: int | None = Field(default=None, ge=1, le=240)
    telemetry_consent: bool | None = None
    training_consent: bool | None = Field(default=None, strict=True)
    #: Registry id from ``app.courses``. Enrolling switches the learner's whole
    #: course context, so it is validated against the registry before it is stored.
    course_id: str | None = Field(default=None, min_length=1, max_length=40)

    @field_validator('goal', 'daily_minutes', 'telemetry_consent', 'training_consent', 'course_id')
    @classmethod
    def no_null(cls, value):
        if value is None:
            raise ValueError('Explicit null is not supported')
        return value


class AttemptInput(Input):
    question_id: str = Field(max_length=64)
    option_id: str | None = Field(default=None, max_length=10)
    answer_text: str | None = Field(default=None, max_length=2000)
    reasoning: str | None = Field(default=None, max_length=5000)
    receipt: str = Field(min_length=20, max_length=200)
    client_event_id: str = Field(min_length=1, max_length=100)
    elapsed_seconds: float = Field(ge=0, le=7200, allow_inf_nan=False)
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    #: The structured self-explanation (P-3). Optional at the schema level so the
    #: gate can be A/B tested; when the learner's assignment turns the gate on, the
    #: endpoint enforces minimum substance with a 422 rather than a warning.
    self_explanation: str | None = Field(default=None, max_length=2000)


class ExperimentCreate(Input):
    key: str = Field(min_length=3, max_length=80, pattern=r'^[a-z0-9_]+$')
    description: str | None = Field(default=None, max_length=2000)
    variants: list[str] = Field(min_length=2, max_length=10)
    status: Literal['draft', 'running'] = 'running'

    @field_validator('variants')
    @classmethod
    def bounded_variants(cls, value):
        if any(not isinstance(item, str) or not item.strip() or len(item) > 40 for item in value):
            raise ValueError('Each variant must be a non-empty string up to 40 characters.')
        if len({item.strip() for item in value}) != len(value):
            raise ValueError('Variants must be distinct.')
        return [item.strip() for item in value]


class ExperimentStatus(Input):
    status: Literal['draft', 'running', 'paused', 'completed']


class ExperimentExposureInput(Input):
    surface: str = Field(min_length=1, max_length=40)


class TeacherStyleProfile(Input):
    """Optional, reviewed style-only profile. It cannot alter tutor safety or grounding."""

    methodology: list[str] = Field(default_factory=list, max_length=4)
    teaching_style: list[str] = Field(default_factory=list, max_length=4)
    content_procedure: list[str] = Field(default_factory=list, max_length=4)
    interaction_prompts: list[str] = Field(default_factory=list, max_length=4)
    tone: list[str] = Field(default_factory=list, max_length=4)

    @field_validator('methodology', 'teaching_style', 'content_procedure', 'interaction_prompts', 'tone')
    @classmethod
    def bounded_style_notes(cls, value):
        if any(not isinstance(item, str) or not item.strip() or len(item) > 240 for item in value):
            raise ValueError('Teacher style notes must be non-empty strings up to 240 characters.')
        return [item.strip() for item in value]


class TeacherProfileAnalyze(Input):
    transcript: str = Field(min_length=100, max_length=40000)
    authorization: Literal['self', 'explicit_permission']
    student_identifiers_removed: bool = Field(strict=True)
    ai_processing_confirmed: bool = Field(strict=True)


class ChatInput(Input):
    concept_id: str = Field(max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=100)
    teacher_profile: TeacherStyleProfile | None = None


class Submission(Input):
    text: str = Field(min_length=10, max_length=20000)
    ai_disclosure: str = Field(min_length=1, max_length=2000)
    reflection: str = Field(min_length=1, max_length=5000)


class Event(Input):
    id: str = Field(min_length=1, max_length=100)
    # Every type the app can actually emit. `external_simulation_opened` was accepted by the
    # route (it had an allow-list entry and a consumer in harness/loop.py) but was missing
    # here, so Pydantic rejected it with a 422 before the route ran and the native app's
    # recordExternalSimulationOpened() had never once landed. A type belongs in this list the
    # moment anything emits it, not the moment a reader remembers.
    type: Literal['heartbeat', 'lesson_view', 'simulation_interaction', 'modality_selected',
                  'interaction', 'external_simulation_opened']
    occurred_at: datetime
    payload: dict = Field(default_factory=dict)

    @field_validator('occurred_at')
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError('Timestamp must include timezone')
        return value


class Events(Input):
    events: list[Event] = Field(min_length=1, max_length=100)


class TrainingConsentInput(Input):
    enabled: bool = Field(strict=True)


class ExamEnd(Input):
    abandoned: bool = Field(default=True, strict=True)


class DeleteAccount(Input):
    confirmation: Literal['DELETE MY ACCOUNT']


class HarnessOutcome(Input):
    """What actually happened after a harness decision. Feeds the self-improvement loop."""

    progress: float = Field(ge=-1, le=1, allow_inf_nan=False)
    mastery_after: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    accuracy_after: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    engaged_seconds: float | None = Field(default=None, ge=0, le=86400, allow_inf_nan=False)
    note: str | None = Field(default=None, max_length=400)


class HarnessGenerate(Input):
    """A request for one generated artefact."""

    concept_id: str = Field(min_length=1, max_length=64)
    kind: Literal['explanation', 'flashcards', 'quiz', 'slide_deck', 'worked_example', 'figure',
                  'image_brief', 'case_study', 'photo', 'video_lesson', 'presentation']
    count: int = Field(default=8, ge=1, le=20)
    options: dict = Field(default_factory=dict)


class PresentationRequest(Input):
    """A request to assemble a narrated deck.

    ``options`` is passed through rather than enumerated as fields so the deck's switches
    (include a photograph, include a simulation, include the retrieval check, skip the
    model) can grow without a schema migration. The handler applies its own defaults, so an
    empty options object is a valid request for a complete deck.
    """

    concept_id: str = Field(min_length=1, max_length=64)
    options: dict = Field(default_factory=dict)


class HarnessCode(Input):
    """Code for the workspace sandbox. Refused by the guard rather than executed blindly."""

    language: Literal['python']
    code: str = Field(min_length=1, max_length=100000)
    timeout: float = Field(default=5.0, ge=0.5, le=20, allow_inf_nan=False)


class HarnessFile(Input):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=2000000)


class AttentionCheck(Input):
    """One on-task reading request.

    ``signals`` is passed through rather than enumerated: the client knows its own
    telemetry (idle time, hidden window, blur events, attempts) and the harness should not
    invent fields a platform cannot measure. ``snapshot`` is an optional ``data:`` URL of
    the work area; it is read in this request and never stored.
    """

    task: str = Field(min_length=1, max_length=2000)
    snapshot: str = Field(default='', max_length=2_000_000)
    signals: dict = Field(default_factory=dict)


class PerspectiveObservation(Input):
    """One written rubric observation about a learner's real artifact.

    ``reviewer_role`` is validated against the caller's role in the route: a learner may
    only describe their own work, while a teacher may record an observation about a
    learner they teach. ``group_size`` is required for a collaboration observation,
    because solo work is not collaboration evidence.
    """

    subject_id: str = Field(min_length=1, max_length=36)
    artifact_type: str = Field(min_length=1, max_length=24)
    artifact_id: str = Field(min_length=1, max_length=64)
    dimension: str = Field(min_length=1, max_length=32)
    score: int = Field(ge=0, le=4, strict=True)
    evidence_note: str = Field(min_length=1, max_length=2000)
    reviewer_role: str = Field(default='self', min_length=1, max_length=16)
    group_size: int | None = Field(default=None, ge=2, le=40, strict=True)


class ClassroomTick(Input):
    """One polling tick for the classroom decision engine.

    ``signals`` is passed through for the same reason as ``AttentionCheck.signals``: the
    client measures its own scroll/click/idle telemetry, the current progress and the node
    it is on, and the engine should not invent fields a platform cannot produce. The engine
    is deterministic and offline, so a tick needs no model and stores nothing.
    """

    signals: dict = Field(default_factory=dict)
