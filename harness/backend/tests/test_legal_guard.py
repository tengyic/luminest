"""Legal shippability guard (audit finding L-1).

The documents in ``backend/legal/`` are templates carrying bracket placeholders.
These tests pin the guard's behaviour: it catches every placeholder class the audit
listed, tolerates legitimate Markdown, refuses production startup while unfilled,
and gates the packaging script.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import Settings, legal_dir
from app.legal_guard import PLACEHOLDER_RE, assert_shippable, unfilled_placeholders

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / 'scripts' / 'check_legal.py'


def _stage(tmp_path, body='Terms text. Contact **[LEGAL ENTITY NAME]**, [ADDRESS].'):
    directory = tmp_path / 'legal'
    directory.mkdir()
    (directory / 'terms.md').write_text(body, encoding='utf-8')
    return directory


def test_regex_catches_every_placeholder_class_from_the_audit():
    for placeholder in ('[LEGAL ENTITY NAME]', '[ADDRESS]', '[DOMAIN]', '[DPO / PRIVACY CONTACT]',
                        '[HOSTING PROVIDER]', '[DATABASE PROVIDER]', '[EMAIL PROVIDER]',
                        '[LLM PROVIDER]', '[ERROR MONITORING]', '[12] months', '[30] days',
                        '[90] days', '[JURISDICTION]', '[VENUE]', '[AMOUNT]', '[10] business days',
                        '[REGION]', '[COUNTRY]', '[Standard Contractual Clauses / adequacy decision]'):
        assert PLACEHOLDER_RE.search(f'text {placeholder} more text'), placeholder


def test_regex_tolerates_markdown_links_and_prose_brackets():
    assert not PLACEHOLDER_RE.search('see [the privacy policy](privacy.md) for detail')
    assert not PLACEHOLDER_RE.search('a lowercase aside [like this] stays')
    assert PLACEHOLDER_RE.search('[2026] edition')  # digits count too


def test_scan_reports_each_file_and_line(tmp_path):
    directory = _stage(tmp_path)
    (directory / 'privacy.md').write_text('Data controller: **[LEGAL ENTITY NAME]**.', encoding='utf-8')
    found = unfilled_placeholders(directory)
    assert set(found) == {'terms.md', 'privacy.md'}
    assert found['privacy.md'] == ['line 1: [LEGAL ENTITY NAME]']
    assert any('[LEGAL ENTITY NAME]' in token for token in found['terms.md'])


def test_clean_bundle_passes(tmp_path):
    directory = tmp_path / 'legal'
    directory.mkdir()
    (directory / 'terms.md').write_text(
        'Governing law is set out in section 9. See [section 9](#governing-law).', encoding='utf-8')
    assert unfilled_placeholders(directory) == {}
    assert_shippable(directory)  # must not raise


def test_missing_legal_directory_is_not_shippable(tmp_path):
    assert '<missing>' in unfilled_placeholders(tmp_path / 'nowhere')


def test_assert_shippable_raises_with_guidance(tmp_path):
    directory = _stage(tmp_path)
    with pytest.raises(ValueError) as exc:
        assert_shippable(directory)
    assert '[LEGAL ENTITY NAME]' in str(exc.value)
    assert 'FILL_IN_SHEET' in str(exc.value)


def _production_env(tmp_path, legal_dir_path):
    return {
        'HARNESS_ENV': 'production',
        'HARNESS_DATABASE_URL': 'postgresql+psycopg://user:pass@db.internal:5432/luminfest',
        'HARNESS_SECRET': 'luminfest-production-secret-0123456789-abcdef',
        'HARNESS_ALLOWED_HOSTS': 'api.example.test',
        'HARNESS_LEGAL_DIR': str(legal_dir_path),
        # Production refuses to boot without a language model; the legal gate is
        # exercised with a valid one so a provider error cannot mask a legal failure.
        'HARNESS_TUTOR_PROVIDER': 'openai',
        'HARNESS_TUTOR_URL': 'https://api.example.test/v1',
        'HARNESS_TUTOR_MODEL': 'test-model',
        'HARNESS_TUTOR_KEY': 'test-key',
    }


def test_production_startup_refuses_unfilled_legal_bundle(tmp_path, monkeypatch):
    directory = _stage(tmp_path)
    for name, value in _production_env(tmp_path, directory).items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('HARNESS_LEGAL_TEMPLATE_OK', raising=False)
    with pytest.raises(ValueError) as exc:
        Settings.from_env()
    assert 'placeholder' in str(exc.value)


def test_production_startup_passes_clean_bundle(tmp_path, monkeypatch):
    directory = tmp_path / 'legal'
    directory.mkdir()
    (directory / 'terms.md').write_text('Fully agreed terms, no blanks.', encoding='utf-8')
    for name, value in _production_env(tmp_path, directory).items():
        monkeypatch.setenv(name, value)
    assert Settings.from_env().environment == 'production'


def test_template_opt_out_is_explicit(tmp_path, monkeypatch):
    directory = _stage(tmp_path)
    for name, value in _production_env(tmp_path, directory).items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv('HARNESS_LEGAL_TEMPLATE_OK', '1')
    assert Settings.from_env().environment == 'production'


def test_current_repository_bundle_is_reported_honestly():
    """The repo bundle is a template; the CLI must say so (exit 1), never lie."""
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    if unfilled_placeholders(legal_dir()):
        assert result.returncode == 1
        assert 'LEGAL NOT SHIPPABLE' in result.stdout
    else:
        assert result.returncode == 0
        assert 'LEGAL OK' in result.stdout


def test_cli_allow_template_reports_without_failing(tmp_path):
    directory = _stage(tmp_path)
    result = subprocess.run([sys.executable, str(SCRIPT), '--legal-dir', str(directory),
                             '--allow-template'], capture_output=True, text=True)
    assert result.returncode == 0
    assert 'must not be released' in result.stdout


def test_cli_fails_loudly_on_unfilled_bundle(tmp_path):
    directory = _stage(tmp_path)
    result = subprocess.run([sys.executable, str(SCRIPT), '--legal-dir', str(directory)],
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert '[LEGAL ENTITY NAME]' in result.stdout
