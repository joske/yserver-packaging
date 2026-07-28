# RPM spec for yserver — a modern X11 server written from scratch in Rust.
## In honor of Seth Vidal https://www.redhat.com/it/blog/thank-you-seth-vidal
#
# Originally contributed by John Boero <boeroboy@gmail.com> as
# https://github.com/joske/yserver/pull/13, reworked to consume the
# upstream `just install` contract (yserver >= 1.4.0).
#
# ── Local build ──────────────────────────────────────────────────────────────
#   spectool -g -R fedora/yserver.spec
#   rpmbuild -ba fedora/yserver.spec
#
# Or from a working tree, without a published tag:
#   git archive --format=tar.gz --prefix=yserver-1.4.0/ -o \
#       ~/rpmbuild/SOURCES/yserver-1.4.0.tar.gz HEAD
#
# ── COPR ─────────────────────────────────────────────────────────────────────
#   Upload this spec; COPR fetches Source0 from GitHub and builds for every
#   enabled chroot/arch. The BuildRequires below are all arch-neutral package
#   names present on every Fedora arch (x86_64, aarch64, …), so no %%ifarch
#   guards are needed.
#
#   IMPORTANT: cargo downloads crate dependencies from crates.io during %%build.
#   COPR builds run in mock with networking DISABLED by default, so you must
#   tick "Enable internet access during builds" in the COPR project settings
#   (or `copr-cli modify <project> --enable-net on`). Alternatively, ship a
#   `cargo vendor` tree in the tarball and build with `--offline`; see the
#   commented block in %%build.

%global crate_name yserver

Name:           yserver
Version:        1.4.0
Release:        1%{?dist}
Summary:        A modern X11 server written from scratch in Rust (DRM/KMS + Vulkan)

License:        MIT
URL:            https://github.com/joske/yserver
Source0:        %{url}/archive/v%{version}/%{crate_name}-%{version}.tar.gz

# ── Build dependencies ───────────────────────────────────────────────────────
# Rust toolchain. edition = "2024" / resolver = "3" require Rust/Cargo >= 1.85.
BuildRequires:  rust >= 1.85
BuildRequires:  cargo >= 1.85
BuildRequires:  gcc
BuildRequires:  pkgconf-pkg-config

# The install contract itself: `just man` renders the scdoc man page sources,
# `just install` stages the tree. Both are upstream recipes; see the
# "Packaging" section of the shipped docs/setup.md.
BuildRequires:  just
BuildRequires:  scdoc

# build.rs compiles the GLSL composite shaders to SPIR-V by invoking the glslc
# BINARY on PATH (overridable with GLSLC=), not by linking shaderc.
BuildRequires:  glslc

# C libraries linked by the native crates: xshmfence (an explicit
# #[link(name = "xshmfence")] in kms/xshmfence.rs for the DRI3 fence path),
# input, xkbcommon, freetype-rs, fontconfig, gbm, and libudev via the `input`
# stack. pkg-config files come from the matching -devel packages.
BuildRequires:  libxshmfence-devel
BuildRequires:  libxkbcommon-devel
BuildRequires:  libinput-devel
BuildRequires:  fontconfig-devel
BuildRequires:  freetype-devel
BuildRequires:  mesa-libgbm-devel
BuildRequires:  systemd-devel

# %%{_tmpfilesdir} and the %%tmpfiles_create scriptlet macro.
BuildRequires:  systemd-rpm-macros

# NOTE: libseat-devel was a BuildRequires in the original submission. yserver
# has since dropped libseat entirely — it opens /dev/dri and /dev/input
# directly and has no seat manager — so it must NOT be listed here.

# ── Runtime dependencies ─────────────────────────────────────────────────────
# The shared libraries linked above are picked up automatically by RPM's ELF
# dependency generator. What follows is only what the generator CANNOT see.

# yserver renders through Vulkan via `ash`, which dlopen()s libvulkan.so.1 at
# runtime — invisible to the ELF dependency generator, so require it here.
Requires:       vulkan-loader

# starty(1) execs both of these to mint and install the per-session
# MIT-MAGIC-COOKIE-1. It checks for them at startup and refuses to run without.
Requires:       xorg-x11-xauth
Requires:       util-linux

# XKB rules/keymaps are read from the filesystem at runtime by xkbcommon.
Requires:       xkeyboard-config

# A Vulkan ICD is needed for actual rendering. Mesa covers virtio-gpu, AMD,
# Intel and (via NVK) Nouveau; proprietary drivers ship their own ICD, so this
# is a Recommends rather than a hard Requires.
Recommends:     mesa-vulkan-drivers

# Core X11 bitmap fonts, for legacy clients that use the server-side font
# path. Recommends only: a fontless system falls back to the built-ins.
Recommends:     xorg-x11-fonts-misc
Recommends:     xorg-x11-fonts-100dpi
Recommends:     xorg-x11-fonts-75dpi

# Optional: lightdm is the documented graphical-login path. The example
# drop-in is shipped (inactive) under %%{_docdir}/yserver/examples/.
Suggests:       lightdm

%description
yserver is a modern X11 server written from scratch in Rust. The goal is not
to clone Xorg but to provide a practical X11 server that runs real desktop
environments, window managers and applications on modern Linux while dropping
legacy baggage (multiple screens, non-TrueColor visuals, indirect GLX, the DDX
driver ABI, endian-swapped clients, and so on).

It drives the GPU directly through atomic DRM/KMS and composites with Vulkan.
There is no seat manager: it opens /dev/dri and /dev/input directly, so the
user running it needs access to both (see the shipped setup guide). It runs
full MATE/XFCE/Cinnamon/Plasma desktops and window managers such as FVWM3, e16
and wmaker, and implements a broad set of extensions (Composite, DAMAGE, DRI3,
GLX, Present, RANDR, RENDER, SHAPE, SYNC, XFIXES, XInput, and more).

This package provides the standalone DRM/KMS server (yserver) and starty(1),
a startx-style launcher for running it from a console.

%prep
%autosetup -n %{crate_name}-%{version}

%build
# The release profile sets debug = true so `perf record --call-graph dwarf`
# can resolve Rust frames. RPM extracts that into -debuginfo as usual; it
# makes the debuginfo subpackage large, not the installed binary.

# Stamp provenance into `yserver --version`. A release tarball has no .git, so
# without this the build script falls back to the literal string "unknown".
# Substitute the release commit hash here if you have it; the tag is the
# next-best truthful answer.
export YSERVER_GIT_COMMIT=v%{version}

# Online build (default): cargo fetches dependencies from crates.io.
# Requires network access in the build chroot (see the COPR note in the header).
cargo build --locked --release --bin yserver

# ── Offline / vendored alternative ───────────────────────────────────────────
# If you ship a `cargo vendor` tree in the tarball and a .cargo/config.toml
# that points at it, replace the line above with:
#   cargo build --locked --release --offline --bin yserver
# This makes the build fully hermetic and removes the COPR network requirement.

# Render the scdoc man page sources to roff in target/man/. PREFIX is baked
# into the FILES sections, so it must match the %%install prefix.
PREFIX=%{_prefix} just man

%install
# The entire install step. Compiles nothing; every input is verified before
# the first write. See the "Packaging" section of docs/setup.md.
DESTDIR=%{buildroot} PREFIX=%{_prefix} TMPFILESDIR=%{_tmpfilesdir} just install

# `just install` stages a generic upstream copy of the licence into
# %%{_docdir}/yserver/. Fedora policy wants it under %%{_licensedir} via the
# %%license macro, which %%files does below — so drop the staged duplicate.
rm -f %{buildroot}%{_docdir}/%{name}/LICENSE

%post
# Create /tmp/.X11-unix root-owned and sticky, so a user-run server does not
# create it under their own umask.
%tmpfiles_create %{_tmpfilesdir}/%{name}.conf

%files
%license LICENSE
%doc README.md
%{_bindir}/yserver
%{_bindir}/starty
%{_mandir}/man1/yserver.1*
%{_mandir}/man1/starty.1*
%dir %{_docdir}/%{name}
%dir %{_docdir}/%{name}/examples
%{_docdir}/%{name}/setup.md
%{_docdir}/%{name}/examples/lightdm-99-yserver.conf
%{_tmpfilesdir}/%{name}.conf
# /tmp/.X11-unix is deliberately NOT %%ghost-ed here. Listing it makes rpmlint
# emit two errors and two more warnings (dir-or-file-in-tmp,
# non-standard-dir-perm, zero-perms-ghost, hidden-file-or-dir) because it is a
# dotted path under /tmp — strictly worse than the single
# tmpfile-not-in-filelist warning that ghosting it was meant to silence, and
# that warning is filtered with a reason in rpmlint.toml.
#
# It is also the right call regardless of the linter: the directory is a
# volatile, world-writable, shared mount point that any X server may create,
# so no package should claim ownership of it.

%changelog
* Tue Jul 28 2026 Jos Dehaes <jos.dehaes@gmail.com> - 1.4.0-1
- Rework onto the upstream `just install` contract (yserver >= 1.4.0)
- Drop ynest: it is no longer part of the workspace
- Drop the systemd template unit, session launcher and sysconfig; starty(1)
  is shipped upstream and supersedes them
- Drop the bundled lightdm drop-in; upstream ships it as an example
- Drop libseat-devel: libseat was removed upstream
- Add just, scdoc and mesa-libgbm-devel to BuildRequires
- Add xorg-x11-xauth, util-linux and xkeyboard-config: runtime dependencies
  no ELF scanner can see
- Install the tmpfiles.d snippet for /tmp/.X11-unix
- Ship man pages and the setup guide

* Fri Jun 12 2026 John Boero <boeroboy@gmail.com> - 1.0.0-1
- Initial RPM packaging
- Standalone DRM/KMS server (yserver) and nested server (ynest)
- systemd template unit yserver@.service + session launcher
- Example lightdm drop-in for graphical-login integration
