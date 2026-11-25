# Security policy

## Scope

This project edits local mpv configuration files. It does not run a remote
service, does not ship third-party binaries, and does not require an account.
The relevant risks are local file handling, download-centre integrity, and the
desktop shell’s process boundary.

## Reporting a vulnerability

Please do **not** open a public issue for a vulnerability that could put users
at risk. Contact the maintainer privately through the repository owner’s
profile, with:

- the affected version / commit;
- a minimal reproduction;
- impact (what an attacker could read, write, or execute);
- any suggested fix.

You will get an acknowledgement when the report is reviewed. Please allow time
for a fix before public disclosure.

## Known gaps

- Runtime downloads from upstream projects are not hash-pinned. The download
  centre fetches from official addresses, but a rolling `latest` URL can change.
  Treat downloaded shaders/fonts/scripts as third-party content.
- The bundled option descriptions come from mpv_doc-CN (GPL-3.0); they are data,
  not executable code.
- The Tauri shell is pinned to a pre-release (`3.0.0-alpha.6`). Do not assume
  stable-channel security patches until the version decision changes.

## Safe defaults

- Back up before every write; the tool does this automatically.
- Do not run the tool with elevated privileges unless you are debugging a
  permission problem.
- Keep `core.hooksPath` enabled in clones you use for contributions; the hook is
  a local guard, not a security boundary.
