from __future__ import annotations

from functools import lru_cache

import pytest
from case_data import NameCase, all_cases

from namespec import Catalog

CASES = all_cases()


@lru_cache
def load_catalog(path):
    return Catalog.from_file(path)


@pytest.fixture(params=CASES, ids=lambda case: case.id)
def name_case(request) -> NameCase:
    return request.param


@pytest.fixture
def case_catalog(name_case):
    return load_catalog(name_case.schema)


@pytest.fixture
def valid_case() -> NameCase:
    return next(case for case in CASES if case.id == "assets/donut_alembic")


@pytest.fixture
def invalid_case() -> NameCase:
    return next(case for case in CASES if case.id == "assets/unknown_lod")


@pytest.fixture
def catalog(valid_case):
    return load_catalog(valid_case.schema)
