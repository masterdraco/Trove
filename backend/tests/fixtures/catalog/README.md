# Catalog fixture HTML

One `<slug>-search.html` file per site, containing a real search-results page captured from the site's response to a benign query (e.g. "ubuntu", "debian", "linux").

## How to capture

```bash
# Example: TPB
curl -sL 'https://thepiratebay.org/search/ubuntu/0/99/0' \
  -H 'User-Agent: Mozilla/5.0' \
  > thepiratebay-search.html
```

Pick a query whose results are unambiguous and stable (distro ISOs, commonly-seeded old scene releases). The fixture is committed — keep it small (<500 KB) by trimming or using a narrow query.

Re-capture whenever `scripts/update-catalog.py diff` shows the upstream YAML has changed *and* the corresponding fixture test starts failing.
