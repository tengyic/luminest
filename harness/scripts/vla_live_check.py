"""Live end-to-end check of the VLA layer against the configured endpoint.

Not part of the suite: it costs tokens and needs a funded key. Run by hand:

    HARNESS_TUTOR_PROVIDER=openai HARNESS_TUTOR_MODEL=deepseek-flash \
    python scripts/vla_live_check.py
"""

import base64
import json
import os
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

from app.config import Settings                      # noqa: E402
from app.harness import agent_loop, attention, vla   # noqa: E402
from app.harness.toolbox import ToolResult           # noqa: E402


def png(width: int, height: int, rgb=(220, 30, 30)) -> bytes:
    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)

    row = b'\x00' + bytes(rgb) * width
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(row * height))
            + chunk(b'IEND', b''))


def main() -> int:
    settings = Settings.from_env()
    print('model        ', settings.provider, settings.provider_model)
    posture = vla.describe(settings)
    print('vla          ', posture['vla'], '| vision:', posture['vision']['ready'],
          '| action:', posture['action']['ready'])

    image = 'data:image/png;base64,' + base64.b64encode(png(32, 32)).decode()

    usage = {}
    seen = vla.observe(settings, [image], 'What colour is this square? One word.',
                       usage_out=usage)
    print('observe      ', 'None' if seen is None else repr(seen['text'])[:80],
          '| tokens', usage.get('total_tokens'))

    # see -> act -> see: a tool hands back a picture, the loop re-injects it.
    def find_learner_work(arguments, ctx):
        return ToolResult('find_learner_work', True,
                          {'note': 'A snapshot of the page the learner is on.'},
                          images=[image])

    messages = [{'role': 'user', 'content': 'Look at my screen and tell me what is on it.'}]
    events = list(agent_loop.run_agent(settings, messages,
                                       {'find_learner_work': find_learner_work},
                                       object(), max_steps=3))
    kinds = [event['type'] for event in events]
    print('agent events ', kinds)
    print('agent answer ', repr(events[-1].get('content'))[:160])

    reading = attention.assess(settings, task='finish the fraction question',
                               snapshot=image,
                               signals={'idle_seconds': 20, 'attempts': 1,
                                        'window_seconds': 300})
    print('attention    ', reading['state'], reading['confidence'],
          '| visual:', (reading['dimensions']['visual'] or {}).get('state'))
    print('privacy      ', json.dumps(reading['privacy']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
