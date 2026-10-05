# Security policy

This is the security policy of every repository of [humanfia](https://github.com/humanfia) that
has no SECURITY.md of its own. Much of what is here runs coding agents, or code they wrote, on
your machine and with your logins; a flaw in it is worth reporting privately, and this file says
how.

## Supported versions

A security fix lands on `main` first and, where the repository has releases, ships in the next
one; it is not backported. Only `main` and the latest release are supported.

## Reporting a vulnerability

**Do not report a vulnerability in a public issue, pull request or discussion.**

Report it privately on GitHub: open the repository's **Security** tab and choose
**Report a vulnerability**, or go to `https://github.com/humanfia/<repository>/security/advisories/new`.
Private vulnerability reporting is on for every repository of the organization. Only you and the
repository's maintainers see the report and what is said about it.

Say what you can of:

- what an attacker gains, and what they need first;
- the version or commit, and the operating system;
- the steps, or a proof of concept, that show it;
- a fix, if you have one in mind.

If you cannot tell which repository the flaw is in, report it on the one you found it through:
its maintainers will move it.

## What happens next

| When | What |
| --- | --- |
| within 3 working days | a maintainer acknowledges the report |
| within 10 working days | whether it is accepted, how severe it is, and the plan |
| within 90 days of the report | the fix is released, sooner for something severe |

We fix it in a private fork, release, then publish a GitHub security advisory on the repository,
with a CVE where one is warranted. You are credited in the advisory unless you would rather not
be.

Please keep the details private until the advisory is out, or until 90 days have passed,
whichever comes first. If a fix needs longer, we will say why and agree a date with you.

## Scope

Some reports belong elsewhere:

- a coding agent CLI itself, such as Claude Code or Codex: its vendor;
- a dependency of a repository: the dependency's own project, though tell us too if we use it in
  a way that makes it worse;
- [humanize](https://github.com/humanfia/humanize) and
  [flowverse](https://github.com/humanfia/flowverse): their own SECURITY.md, which says what is
  and is not a vulnerability there.
