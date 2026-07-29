# yserver-packaging

Distro packaging recipes for [yserver](https://github.com/joske/yserver), a
modern X11 server written from scratch in Rust.

These live outside the main repository on purpose: package names, policy and
tooling differ per distro and rot on a different schedule than the server
does. What upstream guarantees instead is an **install contract** — `just man`
and `just install` — so each recipe here is a thin wrapper rather than a
hand-maintained file list.

| Directory | Target | Owner |
| --- | --- | --- |
| `fedora/` | Fedora, EL, and anything COPR builds | originally [@jboero](https://github.com/jboero) |
| `debian/` | Debian and Ubuntu | this repo |
| `alpine/` | Alpine (musl) | this repo |

Arch is **not** here. The tagged `yserver` AUR package lives in its own
repository; the third-party `yserver-git` (tracking `master`) is maintained
separately by [@openglfreak](https://github.com/openglfreak) and already
declares `provides`/`conflicts` against `yserver`, so the two coexist.

There is no FreeBSD port here either. GitHub Actions cannot build one, so a
`Makefile`/`pkg-plist` in this repo would be unbuildable and untested — worse
than absent. FreeBSD is handled through the ports tree directly. The install
contract itself stays FreeBSD-clean (portable `install -d`/`install -m`, a
`ttyv*` guard in `starty`) so a ports maintainer can consume it unmodified.

## Installing a built package

Release artifacts are loose package files, not repositories, so each format
needs its local-file form. The wrong invocation looks like a broken package
rather than a usage error:

```sh
sudo apt install ./yserver_*.deb   # a bare filename is parsed as a package NAME
sudo dnf install ./yserver-*.rpm   # rpm -Uvh only CHECKS deps, it never fetches them
sudo apk add --allow-untrusted ./yserver-*.apk
```

`--allow-untrusted` is required and expected. `abuild` cannot build without a
signing key, so CI generates a throwaway one per run and discards the private
half; the signature is a build artifact, not a trust anchor, and there is no
stable public key to install into `/etc/apk/keys`. If distro maintainers ever
package yserver themselves, their own signing keys make the question moot.

## The install contract

Every recipe here does the same three things. Full reference: the "Packaging"
section of `docs/setup.md` in the yserver tree, which is also installed to
`$PREFIX/share/doc/yserver/setup.md`.

```sh
cargo build --locked --release --bin yserver     # build
PREFIX=/usr just man                             # render scdoc -> roff
DESTDIR="$stage" PREFIX=/usr just install        # stage; compiles nothing
```

Configuration is by environment variable or `just` assignment — **never** by
positional recipe arguments. `just install PREFIX=/usr` would bind the literal
string `PREFIX=/usr` to a positional parameter and silently install to the
default prefix.

| Variable | Default | Purpose |
| --- | --- | --- |
| `PREFIX` | `/usr/local` | install prefix |
| `DESTDIR` | empty | staging root |
| `TARGETDIR` | `${CARGO_TARGET_DIR:-target}/release` | where the built binaries are |
| `TMPFILESDIR` | `$PREFIX/lib/tmpfiles.d` | set empty to skip the tmpfiles snippet |

What gets staged: `bin/yserver`, `bin/starty`, both man pages uncompressed,
`share/doc/yserver/{setup.md,LICENSE,examples/lightdm-99-yserver.conf}`, and
the tmpfiles.d snippet. Only `bin/` and `share/man/man1/` are stable —
everything under `share/doc/` may be relocated or dropped to match distro
policy, and each recipe here does exactly that for its licence file.

Binaries are staged unstripped and man pages uncompressed; stripping,
debuginfo extraction and compression belong to distro tooling.

## Rust toolchain

yserver needs **Rust >= 1.87**, not 1.85. Edition 2024 only accounts for
1.85; the real floor comes from two library features stabilised in 1.87 —
`u32::is_multiple_of` (`unsigned_is_multiple_of`) and `cast_unsigned`
(`integer_sign_cast`). Upstream's `rust-toolchain.toml` pins
`channel = "stable"`, so developers always have a new enough compiler and
this only shows up when packaging.

Consequences per distro:

- **Fedora 43** — distro `rust`/`cargo` are new enough. Nothing special.
- **Debian trixie** — ships 1.85, so the build uses a rustup-supplied
  toolchain and `debian/control` does *not* Build-Depend on `cargo`/`rustc`
  (`rustc (>= 1.87)` would be unsatisfiable there and `dpkg-buildpackage`
  would refuse to start).
- **Alpine** — uses the distro `cargo`, so the image has to be new enough;
  3.21 ships 1.83 and is not; 3.24 ships 1.96.

This matters for *building*, never for *installing*: the packages contain a
compiled binary, so users need no Rust toolchain whatever their distro ships.

It does mean the Debian package is **not** archive-policy clean — Debian
proper requires offline builds from declared build-dependencies only. Getting
into the archive would first need the MSRV lowered to whatever stable ships
(replacing those two APIs with `% n == 0` and `as u32` is mechanical, ~67
sites), ideally with `msrv` set in a `clippy.toml` so
`clippy::incompatible_msrv` — on by default — fails CI on any future
too-new API.

## Things no dependency scanner can find

None of these appear in the ELF headers, so every recipe declares them by
hand. Getting one wrong produces a package that installs cleanly and fails at
runtime.

| Need | Why it is invisible | Fedora | Debian | Alpine |
| --- | --- | --- | --- | --- |
| Vulkan loader | `libvulkan.so.1` is dlopened by `ash` | `vulkan-loader` | `libvulkan1` | `vulkan-loader` |
| A Vulkan ICD | runtime driver, not linked | `mesa-vulkan-drivers` | `mesa-vulkan-drivers` | `mesa-vulkan-*` |
| `xauth` | `starty` execs it, and refuses to start without | `xorg-x11-xauth` | `xauth` | `xauth` |
| `mcookie` | `starty` execs it, same check | `util-linux` | *none — Essential* | `mcookie` |
| XKB data | keymap rules read at runtime | `xkeyboard-config` | `xkb-data` | `xkeyboard-config` |
| X core fonts | not linked; xterm's default `fixed` lives here | `xorg-x11-fonts-*` (weak) | `xfonts-base` (weak) | `font-misc-misc`, `font-cursor-misc` (hard — apk has no weak deps) |

The ICD is a *recommend*, not a dependency: a proprietary NVIDIA driver
satisfies it just as well as Mesa.

`libseat` is **not** a dependency. yserver dropped it — there is no seat
manager, and it opens `/dev/dri` and `/dev/input` directly. Anything still
listing `seatd` is stale.

## Version stamping

A release tarball has no `.git`, so `build.rs` stamps the literal string
`unknown` into `yserver --version` unless told otherwise. Every recipe here
exports `YSERVER_GIT_COMMIT` before building. Substitute the real release
commit if you have it; the tag is the next-best truthful answer.

## CI

`.github/workflows/build.yml` builds all three packages, each inside its own
distro container (`fedora:43`, `debian:trixie`, `alpine:3.24`), so each uses
that distro's real toolchain and policy checker.

It runs **on demand or on release only**, through a single `workflow_dispatch`
entry point taking the upstream ref. yserver's release workflow calls the same
one with `gh workflow run build.yml -f ref=<tag>` and waits for it to succeed
before publishing, so a package that does not build cannot leave a published
release behind. Deliberately not on push: every run is three full release
builds of the whole workspace, far too expensive for an ordinary commit.

`rpmlint` and `lintian` are **blocking**. Both were once
`continue-on-error` and both duly reported real problems while the job stayed
green — a tmpfiles path missing from `%files`, unescaped macros in spec
comments, and an unversioned dependency on Debian's Essential `util-linux`.
Known-irrelevant tags are filtered by name (`fedora/rpmlint.toml`, and
`--suppress-tags` for lintian) so they cannot mask anything else.

The source tarball is generated once with `git archive` from the upstream
checkout and shared by all three jobs, rather than downloaded from a release.
That means packaging can be validated *before* a tag exists, and all three
build identical sources. A job also fails the run if the version in any recipe
disagrees with upstream's `Cargo.toml` — a stale recipe version otherwise
surfaces as a confusing "directory not found" from `%prep`.

**What CI does not prove.** It shows the recipes build and lint. It cannot
show the packages *run*: no runner has a GPU, KMS or input devices, and
neither `rpmlint` nor `lintian` models `dlopen`. A missing Vulkan loader or a
stale `seatd` dependency passes CI and fails on a user's machine. Runtime
dependency correctness needs a real install on real hardware.

## Source archives and checksums

All recipes take their source from GitHub's auto-generated tag archive,
`github.com/.../archive/refs/tags/v$ver.tar.gz`.

Up to v1.4.0 the release also uploaded its own `git archive` tarball plus
`SHA256SUMS`/`SHA512SUMS`, so that checksummed recipes could pin bytes GitHub
would never regenerate — it changed archive compression once in 2023 and broke
pinned hashes across the AUR. That was dropped afterwards: GitHub already
publishes "Source code (tar.gz)" for every release, so the release page carried
two source downloads of the same tree with different bytes, and only one
matched the published checksums. The duplication caused more confusion than the
stability bought.

The trade-off is accepted knowingly: if GitHub ever changes archive generation
again, bump `pkgrel` and re-run `abuild checksum` / `updpkgsums`.

After each release the Release workflow prints the archive's sha256 and sha512
in its job summary, ready to paste into `alpine/APKBUILD` and the AUR PKGBUILD.
Fedora needs no checksum — RPM does not verify source hashes.

**The committed sha512 is for users, not CI.** The Alpine job runs
`abuild -F checksum`, regenerating it at build time, so CI passes regardless of
what is committed. A stale committed hash only breaks someone building from
this repo with `abuild`.

## Status

Written against yserver 1.4.0, the first release with the install contract.
Nothing here has been through a real distro build yet — the checksums in
`alpine/APKBUILD` are empty pending a published `v1.4.0` tarball, and
`fedora/`, `debian/` and `alpine/` still need a `mock`/`sbuild`/`abuild` run
plus `rpmlint`/`lintian`/`abuild sanitycheck` before they are trustworthy.
