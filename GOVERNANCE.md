# Governance

Who decides what happens to a repository of [humanfia](https://github.com/humanfia), how they
decide, and how you join them. The organization is small and this file is kept small to match:
it grows when the organization does.

It covers every repository of the organization. A repository can add rules of its own in a
GOVERNANCE.md at its root, as [humanfia/humanize](https://github.com/humanfia/humanize/blob/main/GOVERNANCE.md)
does; where the two disagree, the repository's own file wins for that repository.

## Roles

### Contributors

Anyone who opens an issue, answers one, reviews a pull request or sends one. Nothing to apply
for. [CONTRIBUTING.md](CONTRIBUTING.md), or the repository's own, is how.

### Reviewers

Contributors trusted to review one part of a repository. A reviewer is listed against the paths
they review in that repository's `.github/CODEOWNERS`, so GitHub asks them to review every pull
request that touches those paths. A reviewer's approval tells a maintainer the change is ready;
a maintainer still approves before it merges.

### Maintainers

Each repository is run by its maintainers: the people its `.github/CODEOWNERS` names for every
path, on the `*` line. They:

- review and merge pull requests, and decide what is in scope;
- triage issues and set priorities;
- cut releases, where the repository has them;
- handle vulnerability reports, as [SECURITY.md](SECURITY.md) says;
- enforce the [Code of Conduct](CODE_OF_CONDUCT.md);
- grant and remove access to the repository.

The maintainers of [humanfia/humanize](https://github.com/humanfia/humanize) also steward what
belongs to the whole organization: this repository, [humanfia/.github](https://github.com/humanfia/.github),
with the default files and shared workflows every repository inherits, and the organization's
settings.

## How decisions are made

Decisions are made in public, on issues and pull requests, so that the reasoning is there for
whoever comes next.

- **Lazy consensus.** A proposal goes ahead when nobody with a stake objects in reasonable time.
  For anything bigger than a bug fix, a maintainer waits at least a week before taking silence
  as agreement.
- **A maintainer decides when consensus fails.** With more than one maintainer, by simple
  majority of those who vote; a tie keeps things as they are.
- **Some changes need a maintainer's explicit approval**, never silence:
  - a breaking change to what the repository offers others: a command, an API, a file format;
  - a new runtime dependency;
  - adding or removing a reviewer or maintainer;
  - a change to a repository's governance, its code of conduct or its license.
- **Security fixes are decided in private**, then published, as [SECURITY.md](SECURITY.md)
  says.

## Becoming a reviewer

You are ready when you have had several substantial pull requests merged in one part of a
repository, and have reviewed others' pull requests there in a way their authors found useful.

Open a pull request that adds you to that repository's `.github/CODEOWNERS` for those paths,
linking the work that shows it, or ask a maintainer to nominate you. A maintainer approves it.

## Becoming a maintainer

You are ready when you have been a reviewer for at least three months, have contributed across
more than one part of the repository, and your judgment on what belongs in it has proved sound.

An existing maintainer nominates you with a pull request that adds you to the `*` line of the
repository's `.github/CODEOWNERS`. It stays open for two weeks, and merges if a majority of the
maintainers approve it and none objects.

## Stepping down

Anyone may step down at any time, with a pull request that removes them. A reviewer or
maintainer who has been inactive for six months is asked whether they want to stay; without an
answer in a month, they are removed. Coming back is the same process as joining, made shorter by
the record you already have.

## Conflicts of interest

A maintainer does not decide a Code of Conduct report about themselves. A maintainer's own pull
request is reviewed by another maintainer; while there is only one, it merges on green CI, in
public, where anyone can still object.

## Changing this file

A pull request, approved by a majority of the maintainers of
[humanfia/humanize](https://github.com/humanfia/humanize).
