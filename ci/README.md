# CI workflows (parked)

These are the GitHub Actions workflows, parked here because the token that pushed the bootstrap
couldn't write `.github/workflows/` (fine-grained PAT without the **Workflows** permission).

To enable them, from a machine whose GitHub credentials can push workflows:
```bash
mkdir -p .github && git mv ci/github-workflows .github/workflows && git rm ci/README.md
```
- `backend.yml`: pytest against a TimescaleDB service container
- `ios.yml`: `xcodegen generate` + `xcodebuild test` on a macOS runner (free for public repos)
