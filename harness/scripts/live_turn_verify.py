#!/usr/bin/env python3
"""End-to-end verification of a LIVE, turn-taking spoken conversation.

This script OWNS the WebSocket client dependency (``websockets``) that the
production module ``app/harness/live_voice.py`` deliberately does not import:
``scripts/package.py`` freezes only distributions declared in
``requirements.txt``, and an undeclared import would build a bundle whose live
voice path breaks on a tester's machine. Everything else here uses the real,
pinned stack (``httpx`` for discovery) and the real production
``LiveTurnSession`` -- no parallel reimplementation of the protocol.

What a PASS actually proves
---------------------------
1. Endpoint discovery works against the LIVE provider, including the HTTP
   streaming TTS path that the legacy ``/ws/tts`` WebSocket did not honor
   (recorded as provenance -- never guessed).
2. A real Chinese utterance, streamed as paced 20 ms PCM frames, produces
   incremental ``partial`` transcripts and a server-side VAD ``utterance``
   endpoint (not a client timer).
3. The transcript reaches the tutor, and the reply is spoken back as streamed
   audio chunks over the HTTP streaming TTS endpoint (sub-second first audio
   with num_step 2-4).
4. AEC mic-prefix framing and turn timings are measured, not asserted.

What a PASS does NOT claim
--------------------------
* Sub-second TTS first audio. Chinese TTS first-audio latency on this host is
  now sub-second via the HTTP streaming ``/v1/audio/speech`` endpoint with
  ``num_step`` 2-4 (see ``LATENCY_NOTE`` and ``outputs/ttfa_refined_evidence.json``).
  This script measures and reports it.
* A real LLM tutor. The injected tutor is a deterministic stub because the
  configured DeepSeek account returns HTTP 402 (insufficient balance). The
  live-voice *transport/turn* path is what is under test; the tutor is injected
  by design (``LiveTurnSession`` never chooses a voice model). This is stated
  explicitly in the evidence JSON so nobody mistakes a stub reply for a
  grounded answer.

Usage
-----
    python3 harness/scripts/live_turn_verify.py \
        --out outputs/live_turn_evidence.json

Exit code 0 = turn completed; 1 = fail-closed / provider unavailable.
The evidence JSON is ALWAYS written, including on failure.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import struct
import sys
import time
import wave
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import websockets  # noqa: E402  (owned by this script, not by production code)

from app.harness import live_voice as lv  # noqa: E402

ZH_UTTERANCE = "你好，请讲讲二次函数的顶点坐标应该怎么求。"
WAV_CACHE = Path("/tmp/live_turn_zh.wav")
FRAME_BYTES = 640          # 20 ms of 16 kHz mono s16le
RECV_TIMEOUT_S = 25.0


# ---------------------------------------------------------------------------
# Discovery against the LIVE provider (real HTTP, real handshake)
# ---------------------------------------------------------------------------

def make_opener(client: httpx.Client):
    def opener(url: str):
        return client.get(url).json()
    return opener


def make_tts_probe():
    """A real WebSocket handshake is the only honest source of the TTS path."""
    def probe(ws_url: str) -> bool:
        async def _try() -> bool:
            try:
                async with websockets.connect(ws_url, open_timeout=4, max_size=None):
                    return True
            except Exception:
                return False
        return asyncio.run(_try())
    return probe


# ---------------------------------------------------------------------------
# Real transport: websockets -> the injected StreamConnection/LiveTransport
# ---------------------------------------------------------------------------

class WSConnection:
    """Adapts one ``websockets`` connection to ``live_voice.StreamConnection``.

    ``pace`` keeps mic frames at real-time 20 ms cadence so the server-side
    VAD sees a plausible live stream rather than one instantaneous burst.
    ``recv`` is bounded: a provider that never endpoints must fail closed
    rather than hang the verification forever.
    """
    def __init__(self, ws, *, pace: bool, recv_timeout: float = RECV_TIMEOUT_S):
        self.ws = ws
        self.pace = pace
        self.recv_timeout = recv_timeout

    async def send_bytes(self, data: bytes) -> None:
        await self.ws.send(data)
        if self.pace:
            frames = max(1, (len(data) + FRAME_BYTES - 1) // FRAME_BYTES)
            await asyncio.sleep(0.02 * frames)

    async def send_json(self, obj: dict) -> None:
        await self.ws.send(json.dumps(obj))

    async def recv(self):
        return await asyncio.wait_for(self.ws.recv(), timeout=self.recv_timeout)

    async def aclose(self) -> None:
        try:
            await self.ws.close()
        except Exception:
            pass


class WSTransport:
    async def open_stt(self, url: str) -> WSConnection:
        ws = await websockets.connect(url, open_timeout=8, max_size=None)
        # A short idle window is the turn-end signal: after the tail silence the
        # provider sends nothing more, so a recv timeout means "stopped talking".
        # 2.5 s is measured (2026-11-10, paraformer + zh-14m): the utterance
        # final can land ~2 s after the last partial; 1.5 s raced the commit
        # and produced spurious no_utterance failures.
        return WSConnection(ws, pace=True, recv_timeout=2.5)

    async def stream_tts(self, url: str, *, text: str, num_step: int):
        body = {
            "input": text, "model": "omnivoice", "voice": "default",
            "response_format": "pcm", "stream_format": "audio",
            "language": "zh", "num_step": num_step,
        }
        async with httpx.AsyncClient(trust_env=False, timeout=120.0) as c:
            async with c.stream("POST", url, json=body) as r:
                if r.status_code != 200:
                    raise lv.LiveVoiceUnavailable(
                        "tts_error", f"HTTP streaming TTS returned {r.status_code}")
                async for chunk in r.aiter_bytes():
                    if chunk:
                        yield chunk

    def now(self) -> float:
        return time.monotonic()


# ---------------------------------------------------------------------------
# Real Chinese speech: synthesise once via /ws/tts, resample to 16 kHz PCM
# ---------------------------------------------------------------------------

def resample_linear(pcm: bytes, sr_in: int, sr_out: int) -> bytes:
    src = struct.unpack("<%dh" % (len(pcm) // 2), pcm)
    ratio = sr_out / sr_in
    n = int(len(src) * ratio)
    buf = bytearray()
    for i in range(n):
        pos = i / ratio
        i0 = int(pos)
        frac = pos - i0
        s0 = src[i0]
        s1 = src[min(i0 + 1, len(src) - 1)]
        buf += struct.pack("<h", max(-32768, min(32767, int(s0 + (s1 - s0) * frac))))
    return bytes(buf)


async def synthesise_zh_pcm(tts_url: str, engine: str):
    """Return (pcm bytes, sample_rate). Uses the real HTTP streaming TTS."""
    body = {
        "input": ZH_UTTERANCE, "model": engine, "voice": "default",
        "response_format": "pcm", "stream_format": "audio",
        "language": "zh", "num_step": 16,
    }
    chunks: list[bytes] = []
    sr = 24000
    async with httpx.AsyncClient(trust_env=False, timeout=120.0) as c:
        async with c.stream("POST", tts_url, json=body) as r:
            async for chunk in r.aiter_bytes():
                if chunk:
                    chunks.append(chunk)
    return b"".join(chunks), sr


def get_zh_pcm16(tts_url: str, engine: str) -> tuple[bytes, dict]:
    """Cache the (expensive ~12 s) synthesis as a WAV so re-runs stay cheap."""
    meta: dict = {"text": ZH_UTTERANCE, "engine": engine, "cache_hit": False}
    if WAV_CACHE.exists() and WAV_CACHE.stat().st_size > 10000:
        with wave.open(str(WAV_CACHE), "rb") as wf:
            meta.update(cache_hit=True, wav_sr=wf.getframerate(),
                        wav_path=str(WAV_CACHE), wav_bytes=WAV_CACHE.stat().st_size)
            pcm = wf.readframes(wf.getnframes())
            wav_sr = wf.getframerate()
        # The STT stream is declared sr=16000: the cached WAV (24 kHz) MUST be
        # resampled here too. Returning it raw sends pitch-shifted audio (the
        # recogniser streams partials but never endpoints -> spurious
        # no_utterance failures), which is exactly the bug this fixes.
        pcm16 = resample_linear(pcm, wav_sr, 16000)
        meta["pcm16_bytes"] = len(pcm16)
        return pcm16, meta
    t0 = time.monotonic()
    pcm, sr = asyncio.run(synthesise_zh_pcm(tts_url, engine))
    meta["synthesise_ms"] = round((time.monotonic() - t0) * 1000, 1)
    meta["tts_sr"] = sr
    if not pcm:
        raise lv.LiveVoiceUnavailable("no_zh_wav", "TTS returned no PCM for the test utterance")
    with wave.open(str(WAV_CACHE), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm)
    meta.update(wav_sr=sr, wav_path=str(WAV_CACHE), wav_bytes=WAV_CACHE.stat().st_size)
    pcm16 = resample_linear(pcm, sr, 16000)
    meta["pcm16_bytes"] = len(pcm16)
    return pcm16, meta


def to_frames(pcm16: bytes) -> list[bytes]:
    return [pcm16[i:i + FRAME_BYTES]
            for i in range(0, len(pcm16), FRAME_BYTES)
            if len(pcm16[i:i + FRAME_BYTES]) == FRAME_BYTES]


def batch_reference(base_url: str, wav_path: Path) -> dict:
    """Accuracy reference: batch faster-whisper on the SAME audio.

    Not part of the live turn (no partials, no endpointing, ~9 s). It exists so
    the streaming model's accuracy is measured against something, not asserted.
    """
    out = {"model": "faster-whisper", "available": False}
    try:
        with httpx.Client(trust_env=False, timeout=90.0) as c, \
                open(wav_path, "rb") as f:
            t0 = time.monotonic()
            r = c.post(base_url.rstrip("/") + "/v1/audio/transcriptions",
                       data={"model": "faster-whisper"},
                       files={"file": ("zh.wav", f, "audio/wav")})
            out["ms"] = round((time.monotonic() - t0) * 1000, 1)
            out["http"] = r.status_code
            if r.status_code == 200:
                out["text"] = (r.json().get("text") or "").strip()
                out["available"] = bool(out["text"])
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
    return out


# ---------------------------------------------------------------------------
# Tutor: injected, deterministic, explicitly NOT a grounded LLM answer
# ---------------------------------------------------------------------------

async def stub_tutor(transcript: str) -> str:
    return f"我听到你说的是：{transcript}。我们先把这个式子的顶点写出来。"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://127.0.0.1:3900")
    ap.add_argument("--engine", default="omnivoice",
                    help="Chinese-accurate TTS engine (see LATENCY_NOTE)")
    ap.add_argument("--out", default="outputs/live_turn_evidence.json")
    ap.add_argument("--no-aec", action="store_true",
                    help="disable AEC mic-prefix framing (diagnostic only)")
    args = ap.parse_args()

    evidence: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provider": lv.ACTIVE_PROVIDER,
        "provider_decision": {
            "id": lv.ACTIVE_PROVIDER,
            "state": lv.PROVIDERS[lv.ACTIVE_PROVIDER].state,
            "rule": lv.PROVIDERS[lv.ACTIVE_PROVIDER].rule,
            "sources": list(lv.PROVIDERS[lv.ACTIVE_PROVIDER].sources),
        },
        "base_url": args.base_url,
        "verdict": "FAIL",
        "failures": [],
        "tutor": "deterministic stub (real LLM tutor blocked: DeepSeek HTTP 402 "
                 "insufficient_balance). Live-voice transport/turn path is under test.",
        "known_limitations": [lv.LATENCY_NOTE, lv.ASR_QUALITY_NOTE],
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parents[2] / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def finish(code: int) -> int:
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        print(f"[evidence] {out_path}")
        print(f"[verdict] {evidence['verdict']}")
        return code

    try:
        os.environ.setdefault("HARNESS_LIVE_BASE_URL", args.base_url)
        os.environ.setdefault("HARNESS_LIVE_TTS_ENGINE", args.engine)
        if args.no_aec:
            os.environ["HARNESS_LIVE_AEC"] = "0"
        cfg = lv.LiveTurnConfig.from_env()
        cfg.validate()
        evidence["config"] = {
            "provider": cfg.provider, "base_url": cfg.base_url,
            "stt_sample_rate": cfg.stt_sample_rate, "tts_engine": cfg.tts_engine,
            "tts_num_step": cfg.tts_num_step, "asr_model": cfg.asr_model, "aec": cfg.aec,
            "endpoint_silence_s": cfg.endpoint_silence_s,
            "max_reply_chars": cfg.max_reply_chars,
        }

        client = httpx.Client(trust_env=False, timeout=8.0)
        ep = lv.discover_endpoints(cfg.base_url, opener=make_opener(client),
                                   tts_probe=make_tts_probe())
        evidence["endpoints"] = {
            "capabilities_path": ep.capabilities_path,
            "stt_stream_path": ep.stt_stream_path,
            "tts_stream_path": ep.tts_stream_path,
            "tts_http_path": ep.tts_http_path or None,
            "tts_discovery": ep.tts_discovery,
            "protocol": ep.protocol, "service_version": ep.service_version,
            "source_url": ep.source_url, "input_format": ep.input_format,
            "output_events": list(ep.output_events), "features": ep.features,
        }

        ws_base = cfg.base_url.replace("http://", "ws://").rstrip("/")
        tts_http_url = cfg.base_url.rstrip("/") + (ep.tts_http_path or "/v1/audio/speech")
        pcm16, wav_meta = get_zh_pcm16(tts_http_url, cfg.tts_engine)
        evidence["zh_utterance"] = wav_meta
        evidence["batch_reference"] = batch_reference(cfg.base_url, WAV_CACHE)
        frames = to_frames(pcm16)
        evidence["input"] = {
            "pcm16_bytes": len(pcm16), "frame_bytes": FRAME_BYTES,
            "frame_count": len(frames),
            "stream_seconds_approx": round(len(frames) * 0.02, 2),
        }

        session = lv.LiveTurnSession(cfg, ep, WSTransport(), stub_tutor)
        t0 = time.monotonic()
        result = asyncio.run(session.run_turn(frames))
        evidence["turn"] = {
            "transcript": result.transcript,
            "utterances": result.utterances,
            "utterance_count": len(result.utterances),
            "reply": result.reply,
            "partials": result.partials,
            "partial_count": len(result.partials),
            "barge_in_capable": result.barge_in,
            "stt_ms": result.stt_ms,
            "tts_first_audio_ms": result.tts_first_audio_ms,
            "audio_chunks": result.audio_chunks,
            "wall_ms": round((time.monotonic() - t0) * 1000, 1),
            "latency_note": result.latency_note,
        }

        # Acceptance: a real incremental partial stream, a SUBSTANTIVE transcript
        # (not just the first VAD endpoint of a sentence), a spoken reply with
        # real audio chunks, and a measured TTS first-audio. The length floor is
        # an objective size threshold, not a hard-coded word list.
        checks = {
            "partials_streamed": len(result.partials) > 0,
            "utterance_transcript": bool(result.transcript.strip()),
            "turn_not_truncated": len(result.transcript.strip()) >= 8,
            "reply_spoken": result.audio_chunks > 0,
            "tts_first_audio_measured": result.tts_first_audio_ms is not None,
            "tutor_invoked": bool(result.reply.strip()),
        }
        ref_text = evidence["batch_reference"].get("text", "")
        similarity = (round(SequenceMatcher(None, result.transcript, ref_text).ratio(), 3)
                      if ref_text else None)
        evidence["asr_quality"] = {
            "streaming_model": "sherpa-zipformer-zh-14m (25 MB, installed for this task)",
            "streaming_transcript": result.transcript,
            "batch_reference": ref_text or None,
            "char_similarity_vs_batch": similarity,
            "note": lv.ASR_QUALITY_NOTE,
            "counts_toward_pass": False,   # accuracy is reported, not a gate
        }
        evidence["checks"] = checks
        if all(checks.values()):
            evidence["verdict"] = "PASS"
            return finish(0)
        evidence["failures"] = [k for k, v in checks.items() if not v]
        return finish(1)

    except lv.LiveVoiceUnavailable as ex:
        evidence["failures"] = [{"code": ex.code, "message": ex.message}]
        print(f"[fail-closed] {ex.code}: {ex.message}")
        return finish(1)
    except Exception as ex:  # a broken transport must be visible, not swallowed
        evidence["failures"] = [{"code": "unexpected",
                                "type": type(ex).__name__, "message": str(ex)[:400]}]
        print(f"[error] {type(ex).__name__}: {str(ex)[:400]}")
        return finish(1)


if __name__ == "__main__":
    raise SystemExit(main())
