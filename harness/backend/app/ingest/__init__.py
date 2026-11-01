"""Concept ingestion: fetch, classify and validate curriculum structure.

Entry points
------------
``app.ingest.pipeline``   command-line orchestration
``app.ingest.classify``   the classification engine
``app.ingest.policy``     the licence gate every source must pass
``app.ingest.sources``    pluggable fetch adapters
"""

from .classify import ClassificationReport, ClassificationRules, Classifier, classify
from .policy import IngestionRefused, LicenceClass, SourcePolicy, assert_ingestible, registry

__all__ = ['Classifier', 'ClassificationRules', 'ClassificationReport', 'classify',
           'SourcePolicy', 'LicenceClass', 'IngestionRefused', 'assert_ingestible', 'registry']
