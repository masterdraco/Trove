from __future__ import annotations

import yaml as _yaml

from trove.indexers.cardigann import expand_template, load_definition


def test_load_definition_parses_settings_defaults() -> None:
    raw = _yaml.safe_load("""
id: test
name: test
links: [https://test.local]
type: public
settings:
  - name: sort
    type: select
    default: time
  - name: disablesort
    type: checkbox
    default: False
  - name: no_default_item
    type: text
caps:
  categorymappings: []
search:
  paths:
    - path: /
  rows:
    selector: tr
  fields: {}
""")
    d = load_definition(raw)
    assert d.config_defaults["sort"] == "time"
    assert d.config_defaults["disablesort"] == "False"
    assert "no_default_item" not in d.config_defaults


def test_expand_keywords_substitution() -> None:
    assert expand_template("search/{{ .Keywords }}/1/", keywords="ubuntu") == "search/ubuntu/1/"


def test_expand_if_keywords_else() -> None:
    tmpl = "{{ if .Keywords }}search/{{ .Keywords }}{{ else }}latest{{ end }}"
    assert expand_template(tmpl, keywords="ubuntu") == "search/ubuntu"
    assert expand_template(tmpl, keywords="") == "latest"


def test_expand_config_substitution() -> None:
    cfg = {"sort": "time", "apiurl": "example.com"}
    assert expand_template("{{ .Config.sort }}", config=cfg) == "time"
    assert expand_template("https://{{ .Config.apiurl }}/x", config=cfg) == "https://example.com/x"
    assert expand_template("{{ .Config.missing }}", config=cfg) == ""


def test_expand_query_imdb_is_empty() -> None:
    assert expand_template("id:{{ .Query.IMDBID }}", keywords="x") == "id:"


def test_expand_range_categories_is_empty() -> None:
    tmpl = "path/{{ range .Categories }}:cat:{{.}}{{ end }}"
    assert expand_template(tmpl, keywords="x") == "path/"


def test_expand_join_categories_is_empty() -> None:
    assert expand_template('cats={{ join .Categories "," }}', keywords="x") == "cats="


def test_expand_complex_1337x_path() -> None:
    # Sample pulled from 1337x.yml
    cfg = {"sort": "time", "type": "desc", "disablesort": "False"}
    tmpl = (
        "{{ if and (.Keywords) (eq .Config.disablesort .False) }}sort-{{ else }}{{ end }}"
        "{{ if .Keywords }}search/{{ .Keywords }}{{ else }}cat/Movies{{ end }}"
        "{{ if and (.Keywords) (eq .Config.disablesort .False) }}/{{ .Config.sort }}/{{ .Config.type }}{{ else }}{{ end }}"
        "/1/"
    )
    result = expand_template(tmpl, keywords="ubuntu", config=cfg)
    # Expected: "sort-search/ubuntu/time/desc/1/"
    assert result == "sort-search/ubuntu/time/desc/1/"


def test_expand_no_template_passes_through() -> None:
    assert expand_template("/") == "/"
    assert expand_template("search/static/path") == "search/static/path"


def test_expand_returns_unchanged_on_unknown_directive() -> None:
    # Unknown pipeline -> untouched
    assert "{{ weird_directive" in expand_template("{{ weird_directive }}", keywords="x")


def test_1337x_url_construction_uses_expanded_template() -> None:
    from trove.indexers.cardigann import CardigannIndexer, load_definition_yaml
    from trove.services import catalog

    catalog.reset_cache_for_tests()
    d = load_definition_yaml(catalog.read_yaml("1337x"))
    drv = CardigannIndexer(d, base_url="https://1337x.to")
    path = expand_template(d.search_path, keywords="ubuntu", config=d.config_defaults)
    assert "{{" not in path, f"path still has templates: {path}"
    assert "ubuntu" in path
    assert path.startswith("/") or "search" in path or "sort-" in path
