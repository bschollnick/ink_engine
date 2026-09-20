# Repository hooks

Git does not install these automatically, and `core.hooksPath` is local
to each clone. After cloning, run once:

```bash
git config core.hooksPath .githooks
```

Check it took with `git config core.hooksPath` — it should print
`.githooks`.

## `pre-commit`

Refuses a staged modification, deletion or rename inside
`docs/inkles-ink-standard/`, apart from that directory's own
`README.md`. Those files are verbatim copies of inkle's documentation,
pinned to the version this engine was written against.

Adding a new `retrieved-<date>/` directory is **not** blocked — that is
how a newer upstream version is taken, alongside the old one rather than
over it.

To override deliberately, `git commit --no-verify`. In VS Code that
means committing from the terminal, or enabling
`git.allowNoVerifyCommit`, which is off by default.

The snapshot files are also checked out read-only (`chmod a-w`), which
stops an edit before it happens rather than at commit time. That is a
working-copy permission, so it does not survive a fresh clone; restore
it with:

```bash
chmod a-w docs/inkles-ink-standard/retrieved-*/*
```
