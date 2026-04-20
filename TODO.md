# TODO

## Catalog fixtures

- [ ] Capture `<slug>-search.html` fixtures for the 11 remaining catalog slugs.
  Pattern: `backend/tests/fixtures/catalog/<slug>-search.html`.
  Extraction test lives in `backend/tests/test_catalog_fixtures.py` and
  is parametrized over whichever fixtures are present. When captured,
  the test runs `_extract_release` against each row and asserts ≥1 result.
