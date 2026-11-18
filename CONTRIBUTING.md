# Contributing

1. Create a branch for the change.
2. Keep credentials and real personal/job-search data out of fixtures and commits.
3. Run `ruff check src tests scripts` and `pytest` before opening a pull request.
4. Add tests for behavior changes, especially idempotency and approval boundaries.
5. Do not add automatic job submission, recruiter messaging or CAPTCHA bypass without
   an explicit design discussion and a mandatory human approval boundary.

