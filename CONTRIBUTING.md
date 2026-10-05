# Contributing

Thank you for helping. This file is how a change gets from an idea to `main` in any repository
of [humanfia](https://github.com/humanfia) that has no CONTRIBUTING.md of its own: where to
raise it, what a pull request needs, and how it is reviewed. How to build and test a repository
is in its README.

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to help

| To | Do this |
| --- | --- |
| report a bug | open an issue on the repository, with the Bug Report form |
| report a vulnerability | follow [SECURITY.md](SECURITY.md), never a public issue |
| suggest a feature | open an issue on the repository, with the Feature Request form |
| ask a question | see [SUPPORT.md](SUPPORT.md) |
| fix or build something | a pull request, as below |

Say so on an issue before you start on it, so that two people do not do the same work.

## Before you write code

- **A small fix** (a bug, a typo, a broken link, a missing test): open the pull request.
- **Anything larger** (a feature, a new option, anything that breaks what works today): open an
  issue first, and agree the approach with a maintainer before you build it. A large pull
  request nobody asked for may be closed, however good it is.

## Pull requests

1. Branch from `main`, on a fork unless you have push access. Name the branch
   `<type>/<short-slug>`, such as `fix/empty-report`.
2. Make the change, with its tests and with the docs that describe it, in the same pull request.
3. Run the repository's checks until they pass. Its README says what they are; for a Python
   repository built with [uv](https://docs.astral.sh/uv/), they are usually:

   ```bash
   uv lock --check
   uv run ruff check
   uv run ruff format --check
   uv run pytest
   ```

4. Open the pull request against `main`, and fill in the template.

### Title and commits

The pull request's title is a [Conventional Commit](https://www.conventionalcommits.org/en/v1.0.0/):
`type(scope): what it does`, in the imperative, with `!` before the colon if it breaks
something. For example, `fix(report): keep the last row when the log is empty`.

- **Types:** `feat`, `fix`, `docs`, `perf`, `refactor`, `test`, `ci`, `build`, `chore`,
  `style`, `revert`.
- **Scope:** the part of the repository it changes. Optional.

No sign-off or CLA is asked for. What you contribute is under the license of the repository you
contribute to, as it is offered: for Apache-2.0, its section 5 says so.

## Review

- GitHub asks the code owners of what you changed, in the repository's `.github/CODEOWNERS`, to
  review it.
- A pull request merges once a maintainer approves it and CI passes. A maintainer merges it.
  [GOVERNANCE.md](GOVERNANCE.md#conflicts-of-interest) covers a maintainer's own pull requests.
- Expect a first answer within a week. If a week passes without one, comment on the pull
  request to ask.
- Answer each comment, by a change or a reply. Push fixes as new commits rather than rewriting
  what was reviewed, so the reviewer sees what changed.
- A pull request that waits on its author for a month may be closed. Reopen it when you come
  back to it.

## Working with coding agents

Much of what humanfia publishes is built with coding agents, and you may use them too. Where a
repository has an AGENTS.md, it is the rules they work under there, and the rules are the same
for people. You are the author of what you send: read it, run it, and be ready to answer for
every line.

## More

- [GOVERNANCE.md](GOVERNANCE.md): who decides, and how to become a reviewer or maintainer.
- [SUPPORT.md](SUPPORT.md): where to ask.
