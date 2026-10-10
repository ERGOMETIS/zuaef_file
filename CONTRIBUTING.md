# Contributing

Please open an issue describing one observed research or execution failure and the smallest fix.

Prefer improvements that shorten the path from a real product URL to a useful, verifiable report.
Never commit client reports, user data, scraped third-party pictures, credentials or private-source code.

Before proposing a pull request:

```bash
python -m pytest -q
python -m compileall -q src
```

Business success is judged with new live research cases, direct source inspection, image/SKU matching, and human report review. Mocked unit tests are mechanical, not business proof.
