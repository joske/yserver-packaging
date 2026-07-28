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

## Things no dependency scanner can find

None of these appear in the ELF headers, so every recipe declares them by
hand. Getting one wrong produces a package that installs cleanly and fails at
runtime.

| Need | Why it is invisible | Fedora | Debian | Alpine |
| --- | --- | --- | --- | --- |
| Vulkan loader | `libvulkan.so.1` is dlopened by `ash` | `vulkan-loader` | `libvulkan1` | `vulkan-loader` |
| A Vulkan ICD | runtime driver, not linked | `mesa-vulkan-drivers` | `mesa-vulkan-drivers` | `mesa-vulkan-*` |
| `xauth` | `starty` execs it, and refuses to start without | `xorg-x11-xauth` | `xauth` | `xauth` |
| `mcookie` | `starty` execs it, same check | `util-linux` | `util-linux` | `util-linux` |
| XKB data | keymap rules read at runtime | `xkeyboard-config` | `xkb-data` | `xkeyboard-config` |
| X core fonts | *recommend only* — falls back to built-ins | `xorg-x11-fonts-*` | `xfonts-base` | `font-misc-misc` |

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

## Status

Written against yserver 1.4.0, the first release with the install contract.
Nothing here has been through a real distro build yet — the checksums in
`alpine/APKBUILD` are empty pending a published `v1.4.0` tarball, and
`fedora/`, `debian/` and `alpine/` still need a `mock`/`sbuild`/`abuild` run
plus `rpmlint`/`lintian`/`abuild sanitycheck` before they are trustworthy.
