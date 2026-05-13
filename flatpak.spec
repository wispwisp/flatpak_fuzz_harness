# Build AFL++ fuzzing harnesses (off by default; enable with --with fuzzing).
%bcond_with fuzzing

%global bubblewrap_version 0.4.0
%global ostree_version 2020.8

Name:           flatpak
Version:        1.12.9
Release:        1%{?dist}
Summary:        Application deployment framework for desktop apps

License:        LGPLv2+
URL:            http://flatpak.org/
Source0:        https://github.com/flatpak/flatpak/releases/download/%{version}/%{name}-%{version}.tar.xz

%if 0%{?fedora}
# Add Fedora flatpak repositories
Source1:        flatpak-add-fedora-repos.service
%endif

# https://issues.redhat.com/browse/RHEL-4220
Patch0:         flatpak-Revert-selinux-Permit-using-systemd-userdbd.patch
%if %{with fuzzing}
Patch1:         FUZZ_HARNESS.patch
%endif

BuildRequires:  pkgconfig(appstream-glib)
BuildRequires:  pkgconfig(dconf)
BuildRequires:  pkgconfig(fuse)
BuildRequires:  pkgconfig(gdk-pixbuf-2.0)
BuildRequires:  pkgconfig(gio-unix-2.0)
BuildRequires:  pkgconfig(gobject-introspection-1.0) >= 1.40.0
BuildRequires:  pkgconfig(gpgme)
BuildRequires:  pkgconfig(json-glib-1.0)
BuildRequires:  pkgconfig(libarchive) >= 2.8.0
BuildRequires:  pkgconfig(libseccomp)
BuildRequires:  pkgconfig(libsoup-2.4)
BuildRequires:  pkgconfig(libsystemd)
BuildRequires:  pkgconfig(libxml-2.0) >= 2.4
BuildRequires:  pkgconfig(libzstd) >= 0.8.1
BuildRequires:  pkgconfig(ostree-1) >= %{ostree_version}
BuildRequires:  pkgconfig(polkit-gobject-1)
BuildRequires:  pkgconfig(xau)
%if %{with fuzzing}
BuildRequires:  american-fuzzy-lop
# clang / compiler-rt / llvm were originally needed for afl-clang-fast.
# We now use afl-gcc-fast (a GCC plugin) — these are no longer required
# for the harness build itself but kept until a separate cleanup confirms
# nothing else in the build pulls them in transitively.
BuildRequires:  clang
BuildRequires:  compiler-rt
BuildRequires:  llvm
# afl-gcc-fast + AFL_USE_ASAN/UBSAN links -static-libasan / -static-libubsan,
# which need the static archives Fedora ships in separate subpackages.
BuildRequires:  libasan-static
BuildRequires:  libubsan-static
# autoreconf -fi in %prep needs gtkdocize (GTK_DOC_CHECK is in configure.ac).
BuildRequires:  gtk-doc
%endif
BuildRequires:  bison
BuildRequires:  bubblewrap >= %{bubblewrap_version}
BuildRequires:  docbook-dtds
BuildRequires:  docbook-style-xsl
BuildRequires:  gettext
BuildRequires:  libassuan-devel
BuildRequires:  libcap-devel
BuildRequires:  python3-devel
BuildRequires:  python3-pyparsing
BuildRequires:  systemd
BuildRequires:  /usr/bin/xmlto
BuildRequires:  /usr/bin/xsltproc

Requires:       bubblewrap >= %{bubblewrap_version}
Requires:       librsvg2%{?_isa}
Requires:       ostree-libs%{?_isa} >= %{ostree_version}
# https://fedoraproject.org/wiki/SELinux/IndependentPolicy
Requires:       (flatpak-selinux = %{?epoch:%{epoch}:}%{version}-%{release} if selinux-policy-targeted)
Requires:       %{name}-session-helper%{?_isa} = %{?epoch:%{epoch}:}%{version}-%{release}
Recommends:     p11-kit-server
%if %{with fuzzing}
Requires:       american-fuzzy-lop
%endif

# Make sure the document portal is installed
%if 0%{?fedora} || 0%{?rhel} > 7
Recommends:     xdg-desktop-portal > 0.10
# Remove in F30.
Conflicts:      xdg-desktop-portal < 0.10
%else
Requires:       xdg-desktop-portal > 0.10
%endif

%description
flatpak is a system for building, distributing and running sandboxed desktop
applications on Linux. See https://wiki.gnome.org/Projects/SandboxedApps for
more information.

%package devel
Summary:        Development files for %{name}
License:        LGPLv2+
Requires:       %{name}%{?_isa} = %{version}-%{release}
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}

%description devel
This package contains the pkg-config file and development headers for %{name}.

%package libs
Summary:        Libraries for %{name}
License:        LGPLv2+
Requires:       bubblewrap >= %{bubblewrap_version}
Requires:       ostree%{?_isa} >= %{ostree_version}
Requires(pre):  /usr/sbin/useradd

%description libs
This package contains libflatpak.

%package selinux
Summary:        SELinux policy module for %{name}
License:        LGPLv2+
BuildRequires:  selinux-policy
BuildRequires:  selinux-policy-devel
BuildArch:      noarch
%{?selinux_requires}

%description selinux
This package contains the SELinux policy module for %{name}.

%package session-helper
Summary:        User D-Bus service used by %{name} and others
License:        LGPLv2+
Conflicts:      flatpak < 1.4.1-2
Requires:       systemd

%description session-helper
This package contains the org.freedesktop.Flatpak user D-Bus service
that's used by %{name} and other packages.

%if !%{with fuzzing}
%package tests
Summary:        Tests for %{name}
License:        LGPLv2+
Requires:       %{name}%{?_isa} = %{version}-%{release}
Requires:       %{name}-libs%{?_isa} = %{version}-%{release}
Requires:       %{name}-session-helper%{?_isa} = %{version}-%{release}
Requires:       bubblewrap >= %{bubblewrap_version}
Requires:       ostree%{?_isa} >= %{ostree_version}

%description tests
This package contains installed tests for %{name}.
%endif

%prep
%autosetup -p1
%if %{with fuzzing}
# FUZZ_HARNESS.patch adds `include fuzz/Makefile.am.inc` to Makefile.am
# and adds the --enable-fuzzing AC_ARG_ENABLE to configure.ac. Regenerate
# aclocal.m4 / configure / config.h.in / Makefile.in with the chroot's
# autotools (autoconf 2.72, automake 1.18) so the new fuzz subdir is
# wired into the top-level Makefile and the aclocal-1.NN baked into the
# shipped Makefile.in is replaced — otherwise make either skips the fuzz
# targets entirely or tries to invoke an aclocal that doesn't exist.
autoreconf -fi
%endif
# Make sure to use the RHEL-lifetime supported Python and no other
%py3_shebang_fix scripts/* subprojects/variant-schema-compiler/* tests/*


%build
%if %{with fuzzing}
# AFL env vars must be at script-level scope so they reach both %configure
# (inside the subshell below) AND %make_build (outside it). AFL_USE_ASAN /
# AFL_USE_UBSAN tell afl-gcc-fast to inject sanitizer flags on every
# compile, and AFL_GCC_DISABLE_VERSION_CHECK is needed by the plugin at
# every compile (not just configure).
export CC=afl-gcc-fast
export AFL_USE_ASAN=1
export AFL_USE_UBSAN=1
# Fedora ships GCC point updates without rebuilding the AFL package;
# the plugin then aborts on a datestamp mismatch even though basever
# matches. Plugin ABI is stable across point releases — bypass is safe.
export AFL_GCC_DISABLE_VERSION_CHECK=1
# Strip -flto / -ffat-lto-objects from CFLAGS. AFL-instrumented binaries
# don't meaningfully benefit from LTO inlining (the AFL pass dominates
# exec cost), and afl-gcc-fast + ASan + UBSan + LTO together exhaust
# memory on typical build hosts, causing silent build-time thrash.
export CFLAGS="$(echo "%{optflags}" | sed -E 's/-flto[^ ]*//g; s/-ffat-lto-objects//g; s/ +/ /g')"
%endif
(if ! test -x configure; then NOCONFIGURE=1 ./autogen.sh; CONFIGFLAGS=--enable-gtk-doc; fi;
 # Generate consistent IDs between runs to avoid multilib problems.
 export XMLTO_FLAGS="--stringparam generate.consistent.ids=1"
%if %{with fuzzing}
 # g-ir-scanner's probe binary fails to resolve auto-generated
 # *_get_type / *_quark symbols when linking against an AFL-instrumented
 # libflatpak. Fuzz harnesses don't use introspection — disable it.
 CONFIGFLAGS="$CONFIGFLAGS --enable-fuzzing --disable-introspection"
%endif
 %configure \
            --enable-docbook-docs \
%if !%{with fuzzing}
            --enable-installed-tests \
%else
            --disable-installed-tests \
%endif
            --enable-selinux-module \
            --with-priv-mode=none \
            --with-system-bubblewrap \
            $CONFIGFLAGS)
%if %{with fuzzing}
# Drop test-libflatpak from the noinst_PROGRAMS list. It's a small ABI
# smoke binary that links against libflatpak.la; under the AFL-instrumented
# build the lib's exported *_get_type / *_quark / public ref helpers were
# historically not findable by the linker even though they exist at
# runtime. The fuzz harnesses link against libflatpak-common.la (internal
# convenience archive) instead and are unaffected.
sed -i 's|test-libflatpak\$(EXEEXT) ||' Makefile
%endif
%make_build V=1


%install
%make_install
install -pm 644 NEWS README.md %{buildroot}/%{_pkgdocdir}
# The system repo is not installed by the flatpak build system.
install -d %{buildroot}%{_localstatedir}/lib/flatpak
install -d %{buildroot}%{_sysconfdir}/flatpak/remotes.d
rm -f %{buildroot}%{_libdir}/libflatpak.la

%if 0%{?fedora}
install -D -t %{buildroot}%{_unitdir} %{SOURCE1}
%endif

%if %{with fuzzing}
install -d %{buildroot}%{_libexecdir}/flatpak/fuzz/{corpus,dict,scripts}
install -m 0755 fuzz/fuzz-ref            %{buildroot}%{_libexecdir}/flatpak/fuzz/
install -m 0755 fuzz/fuzz-oci-versioned  %{buildroot}%{_libexecdir}/flatpak/fuzz/
install -m 0755 fuzz/fuzz-oci-image      %{buildroot}%{_libexecdir}/flatpak/fuzz/
install -m 0755 fuzz/fuzz-repofile       %{buildroot}%{_libexecdir}/flatpak/fuzz/
install -m 0755 fuzz/fuzz-filter         %{buildroot}%{_libexecdir}/flatpak/fuzz/
install -m 0755 fuzz/fuzz-metadata       %{buildroot}%{_libexecdir}/flatpak/fuzz/
install -m 0755 fuzz/fuzz-oci-registry-local %{buildroot}%{_libexecdir}/flatpak/fuzz/
install -m 0755 fuzz/fuzz-smoke          %{buildroot}%{_libexecdir}/flatpak/fuzz/
cp -a fuzz/corpus/* %{buildroot}%{_libexecdir}/flatpak/fuzz/corpus/
cp -a fuzz/dict/*   %{buildroot}%{_libexecdir}/flatpak/fuzz/dict/
install -m 0755 fuzz/scripts/*.sh        %{buildroot}%{_libexecdir}/flatpak/fuzz/scripts/
%endif

%find_lang %{name}

# Work around selinux denials, see
# https://github.com/flatpak/flatpak/issues/4128 for details. Note that we are
# going to need the system env generator if we should enable malcontent support
# in the future.
rm %{buildroot}%{_systemd_system_env_generator_dir}/60-flatpak-system-only

%pre
getent group flatpak >/dev/null || groupadd -r flatpak
getent passwd flatpak >/dev/null || \
    useradd -r -g flatpak -d / -s /sbin/nologin \
     -c "User for flatpak system helper" flatpak
exit 0


%if 0%{?fedora}
%post
%systemd_post flatpak-add-fedora-repos.service
%endif


%post selinux
%selinux_modules_install %{_datadir}/selinux/packages/flatpak.pp.bz2


%if 0%{?fedora}
%preun
%systemd_preun flatpak-add-fedora-repos.service
%endif


%if 0%{?fedora}
%postun
%systemd_postun_with_restart flatpak-add-fedora-repos.service
%endif


%postun selinux
if [ $1 -eq 0 ]; then
    %selinux_modules_uninstall %{_datadir}/selinux/packages/flatpak.pp.bz2
fi


%ldconfig_scriptlets libs


%files -f %{name}.lang
%license COPYING
# Comply with the packaging guidelines about not mixing relative and absolute
# paths in doc.
%doc %{_pkgdocdir}
%{_bindir}/flatpak
%{_bindir}/flatpak-bisect
%{_bindir}/flatpak-coredumpctl
%{_datadir}/bash-completion
%{_datadir}/dbus-1/interfaces/org.freedesktop.portal.Flatpak.xml
%{_datadir}/dbus-1/interfaces/org.freedesktop.Flatpak.Authenticator.xml
%{_datadir}/dbus-1/services/org.flatpak.Authenticator.Oci.service
%{_datadir}/dbus-1/services/org.freedesktop.portal.Flatpak.service
%{_datadir}/dbus-1/system-services/org.freedesktop.Flatpak.SystemHelper.service
%{_datadir}/fish
%{_datadir}/%{name}
%{_datadir}/polkit-1/actions/org.freedesktop.Flatpak.policy
%{_datadir}/polkit-1/rules.d/org.freedesktop.Flatpak.rules
%{_datadir}/zsh/site-functions
%{_libexecdir}/flatpak-dbus-proxy
%{_libexecdir}/flatpak-oci-authenticator
%{_libexecdir}/flatpak-portal
%{_libexecdir}/flatpak-system-helper
%{_libexecdir}/flatpak-validate-icon
%{_libexecdir}/revokefs-fuse
%dir %{_localstatedir}/lib/flatpak
%{_mandir}/man1/%{name}*.1*
%{_mandir}/man5/%{name}-metadata.5*
%{_mandir}/man5/flatpak-flatpakref.5*
%{_mandir}/man5/flatpak-flatpakrepo.5*
%{_mandir}/man5/flatpak-installation.5*
%{_mandir}/man5/flatpak-remote.5*
%{_sysconfdir}/dbus-1/system.d/org.freedesktop.Flatpak.SystemHelper.conf
%dir %{_sysconfdir}/flatpak
%{_sysconfdir}/flatpak/remotes.d
%{_sysconfdir}/profile.d/flatpak.sh
%{_sysusersdir}/flatpak.conf
%{_unitdir}/flatpak-system-helper.service
%{_userunitdir}/flatpak-oci-authenticator.service
%{_userunitdir}/flatpak-portal.service
%{_systemd_user_env_generator_dir}/60-flatpak

%if 0%{?fedora}
%{_unitdir}/flatpak-add-fedora-repos.service
%endif

%if %{with fuzzing}
%{_libexecdir}/flatpak/fuzz/
%endif

%files devel
%if !%{with fuzzing}
%{_datadir}/gir-1.0/Flatpak-1.0.gir
%endif
%{_datadir}/gtk-doc/
%{_includedir}/%{name}/
%{_libdir}/libflatpak.so
%{_libdir}/pkgconfig/%{name}.pc

%files libs
%license COPYING
%if !%{with fuzzing}
%{_libdir}/girepository-1.0/Flatpak-1.0.typelib
%endif
%{_libdir}/libflatpak.so.*

%files selinux
%{_datadir}/selinux/packages/flatpak.pp.bz2
%{_datadir}/selinux/devel/include/contrib/flatpak.if

%files session-helper
%license COPYING
%{_datadir}/dbus-1/interfaces/org.freedesktop.Flatpak.xml
%{_datadir}/dbus-1/services/org.freedesktop.Flatpak.service
%{_libexecdir}/flatpak-session-helper
%{_userunitdir}/flatpak-session-helper.service

%if !%{with fuzzing}
%files tests
%{_datadir}/installed-tests
%{_libexecdir}/installed-tests
%endif

%changelog
* Tue Apr 30 2024 Kalev Lember <klember@redhat.com> - 1.12.9-1
- Update to 1.12.9 (CVE-2024-32462)

* Mon Nov 06 2023 Debarshi Ray <rishi@fedoraproject.org> - 1.12.8-1
- Rebase to 1.12.8 (RHEL-4220)

* Mon Nov 06 2023 Debarshi Ray <rishi@fedoraproject.org> - 1.10.8-3
- Let flatpak own %%{_sysconfdir}/flatpak (RHEL-15822)

* Mon Sep 04 2023 Miro Hrončok <mhroncok@redhat.com> - 1.10.8-2
- Make sure to use the RHEL-lifetime supported Python and no other (RHEL-2225)

* Tue Jul 11 2023 Debarshi Ray <rishi@fedoraproject.org> - 1.10.8-1
- Rebase to 1.10.8 (#2222103)
- Fix CVE-2023-28100 and CVE-2023-28101 (#2180311)

* Wed Mar 09 2022 Debarshi Ray <rishi@fedoraproject.org> - 1.10.7-1
- Rebase to 1.10.7 (#2062417)

* Thu Feb 03 2022 Debarshi Ray <rishi@fedoraproject.org> - 1.8.7-1
- Rebase to 1.8.7 (#2041972)

* Tue Jan 25 2022 Debarshi Ray <rishi@fedoraproject.org> - 1.8.6-1
- Rebase to 1.8.6 (#2010533)

* Tue Oct 26 2021 Debarshi Ray <rishi@fedoraproject.org> - 1.8.5-6
- Fix CVE-2021-41133 (#2012869)

* Tue Oct 05 2021 Debarshi Ray <rishi@fedoraproject.org> - 1.8.5-5
- Disable gvfs plugins when listing flatpak installations (#1980438)

* Wed Jul 28 2021 Tomas Popela <tpopela@redhat.com> - 1.8.5-4
- Ship flatpak-devel in CRB (#1938064)

* Mon Mar 22 2021 David King <dking@redhat.com> - 1.8.5-3
- Fix CVE-2021-21381 (#1938064)

* Mon Jan 25 2021 David King <dking@redhat.com> - 1.8.5-2
- Apply post-release CVE fixes (#1918776)

* Thu Jan 14 2021 David King <dking@redhat.com> - 1.8.5-1
- Rebase to 1.8.5 (#1851958)

* Tue Nov 17 2020 David King <dking@redhat.com> - 1.8.3-1
- Rebase to 1.8.3 (#1851958)

* Mon Oct 05 2020 David King <dking@redhat.com> - 1.8.2-1
- Rebase to 1.8.2 (#1851958)

* Mon Sep 14 2020 Kalev Lember <klember@redhat.com> - 1.6.2-4
- OCI: extract appstream data for runtimes (#1878231)

* Wed Jun 17 2020 David King <dking@redhat.com> - 1.6.2-3
- Further fixes for OCI authenticator (#1847201)

* Fri Mar 20 2020 David King <dking@redhat.com> - 1.6.2-2
- Fixes for OCI authenticator (#1814045)

* Thu Feb 13 2020 David King <dking@redhat.com> - 1.6.2-1
- Rebase to 1.6.2 (#1775339)

* Thu Jan 23 2020 David King <dking@redhat.com> - 1.6.1-1
- Rebase to 1.6.1 (#1775339)

* Fri Jan 17 2020 David King <dking@redhat.com> - 1.6.0-2
- Remove broken python3 sed hack (#1775339)

* Sat Dec 21 2019 David King <dking@redhat.com> - 1.6.0-1
- Rebase to 1.6.0 (#1775339)

* Fri Nov 08 2019 David King <dking@redhat.com> - 1.4.3-2
- Use %%{?selinux_requires} for proper install ordering

* Tue Oct 08 2019 David King <dking@redhat.com> - 1.4.3-1
- Rebase to 1.4.3 (#1748276)

* Fri Sep 20 2019 Kalev Lember <klember@redhat.com> - 1.0.9-1
- Update to 1.0.9 (#1753613)

* Tue May 14 2019 David King <dking@redhat.com> - 1.0.6-4
- Bump release (#1700654)

* Mon Apr 29 2019 David King <dking@redhat.com> - 1.0.6-3
- Fix IOCSTI sandbox bypass (#1700654)

* Wed Feb 13 2019 David King <dking@redhat.com> - 1.0.6-2
- Do not mount /proc in root sandbox (#1675776)

* Tue Dec 18 2018 Kalev Lember <klember@redhat.com> - 1.0.6-1
- Update to 1.0.6 (#1630249)
- Recommend p11-kit-server instead of just p11-kit (#1649049)

* Mon Dec 10 2018 David King <dking@redhat.com> - 1.0.4-2
- Backport patches to improve OCI support (#1657306)

* Fri Oct 12 2018 Kalev Lember <klember@redhat.com> - 1.0.4-1
- Update to 1.0.4 (#1630249)

* Thu Sep 13 2018 Kalev Lember <klember@redhat.com> - 1.0.2-1
- Update to 1.0.2 (#1630249)

* Tue Aug 28 2018 David King <dking@redhat.com> - 1.0.1-1
- Update to 1.0.1 (#1621401)

* Wed Aug 01 2018 David King <dking@redhat.com> - 0.99.3-1
- Update to 0.99.3

* Wed May 23 2018 Adam Jackson <ajax@redhat.com> - 0.11.7-2
- Remove Requires: kernel >= 4.0.4-202, which corresponds to rawhide
  somewhere before Fedora 22 which this spec file certainly no longer
  supports.

* Thu May 03 2018 Kalev Lember <klember@redhat.com> - 0.11.7-1
- Update to 0.11.7

* Wed May 02 2018 Kalev Lember <klember@redhat.com> - 0.11.6-1
- Update to 0.11.6

* Wed May 02 2018 Kalev Lember <klember@redhat.com> - 0.11.5-2
- Backport a fix for a gnome-software crash installing .flatpakref files

* Mon Apr 30 2018 David King <amigadave@amigadave.com> - 0.11.5-1
- Update to 0.11.5

* Thu Apr 26 2018 Kalev Lember <klember@redhat.com> - 0.11.4-1
- Update to 0.11.4

* Mon Feb 19 2018 David King <amigadave@amigadave.com> - 0.11.3-1
- Update to 0.11.3

* Mon Feb 19 2018 David King <amigadave@amigadave.com> - 0.11.2-1
- Update to 0.11.2

* Wed Feb 14 2018 David King <amigadave@amigadave.com> - 0.11.1-1
- Update to 0.11.1 (#1545224)

* Wed Feb 07 2018 Fedora Release Engineering <releng@fedoraproject.org> - 0.10.3-3
- Rebuilt for https://fedoraproject.org/wiki/Fedora_28_Mass_Rebuild

* Fri Feb 02 2018 Igor Gnatenko <ignatenkobrain@fedoraproject.org> - 0.10.3-2
- Switch to %%ldconfig_scriptlets

* Tue Jan 30 2018 Kalev Lember <klember@redhat.com> - 0.10.3-1
- Update to 0.10.3

* Thu Dec 21 2017 David King <amigadave@amigadave.com> - 0.10.2.1-1
- Update to 0.10.2.1

* Fri Dec 15 2017 Kalev Lember <klember@redhat.com> - 0.10.2-1
- Update to 0.10.2

* Fri Nov 24 2017 David King <amigadave@amigadave.com> - 0.10.1-1
- Update to 0.10.1

* Thu Oct 26 2017 Kalev Lember <klember@redhat.com> - 0.10.0-1
- Update to 0.10.0

* Mon Oct 09 2017 Kalev Lember <klember@redhat.com> - 0.9.99-1
- Update to 0.9.99

* Tue Sep 26 2017 Kalev Lember <klember@redhat.com> - 0.9.98.2-1
- Update to 0.9.98.2

* Tue Sep 26 2017 Kalev Lember <klember@redhat.com> - 0.9.98.1-1
- Update to 0.9.98.1

* Mon Sep 25 2017 Kalev Lember <klember@redhat.com> - 0.9.98-1
- Update to 0.9.98

* Thu Sep 14 2017 Kalev Lember <klember@redhat.com> - 0.9.12-1
- Update to 0.9.12

* Wed Sep 13 2017 Kalev Lember <klember@redhat.com> - 0.9.11-1
- Update to 0.9.11

* Mon Sep 04 2017 Kalev Lember <klember@redhat.com> - 0.9.10-1
- Update to 0.9.10
- Split out flatpak-builder to a separate source package

* Fri Aug 25 2017 Kalev Lember <klember@redhat.com> - 0.9.8-2
- Backport a patch to fix regression in --devel

* Mon Aug 21 2017 David King <amigadave@amigadave.com> - 0.9.8-1
- Update to 0.9.8

* Wed Aug 02 2017 Fedora Release Engineering <releng@fedoraproject.org> - 0.9.7-5
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Binutils_Mass_Rebuild

* Sun Jul 30 2017 Florian Weimer <fweimer@redhat.com> - 0.9.7-4
- Rebuild with binutils fix for ppc64le (#1475636)

* Thu Jul 27 2017 Owen Taylor <otaylor@redhat.com> - 0.9.7-3
- Add a patch to fix OCI refname annotation

* Wed Jul 26 2017 Fedora Release Engineering <releng@fedoraproject.org> - 0.9.7-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_27_Mass_Rebuild

* Sat Jul 01 2017 David King <amigadave@amigadave.com> - 0.9.7-1
- Update to 0.9.7 (#1466970)

* Tue Jun 20 2017 David King <amigadave@amigadave.com> - 0.9.6-1
- Update to 0.9.6

* Sat Jun 10 2017 David King <amigadave@amigadave.com> - 0.9.5-1
- Update to 0.9.5 (#1460437)

* Tue May 23 2017 David King <amigadave@amigadave.com> - 0.9.4-1
- Update to 0.9.4 (#1454750)

* Mon Apr 24 2017 David King <amigadave@amigadave.com> - 0.9.3-1
- Update to 0.9.3

* Fri Apr 07 2017 David King <amigadave@amigadave.com> - 0.9.2-2
- Add eu-strip dependency for flatpak-builder

* Wed Apr 05 2017 Kalev Lember <klember@redhat.com> - 0.9.2-1
- Update to 0.9.2

* Wed Mar 15 2017 Kalev Lember <klember@redhat.com> - 0.9.1-1
- Update to 0.9.1

* Fri Mar 10 2017 Kalev Lember <klember@redhat.com> - 0.8.4-1
- Update to 0.8.4

* Sun Feb 19 2017 David King <amigadave@amigadave.com> - 0.8.3-3
- Make flatpak-builder require bzip2 (#1424857)

* Wed Feb 15 2017 Kalev Lember <klember@redhat.com> - 0.8.3-2
- Avoid pulling in all of ostree and only depend on ostree-libs subpackage

* Tue Feb 14 2017 Kalev Lember <klember@redhat.com> - 0.8.3-1
- Update to 0.8.3

* Fri Feb 10 2017 Fedora Release Engineering <releng@fedoraproject.org> - 0.8.2-2
- Rebuilt for https://fedoraproject.org/wiki/Fedora_26_Mass_Rebuild

* Fri Jan 27 2017 Kalev Lember <klember@redhat.com> - 0.8.2-1
- Update to 0.8.2

* Wed Jan 18 2017 David King <amigadave@amigadave.com> - 0.8.1-1
- Update to 0.8.1

* Tue Dec 20 2016 Kalev Lember <klember@redhat.com> - 0.8.0-1
- Update to 0.8.0

* Tue Nov 29 2016 David King <amigadave@amigadave.com> - 0.6.14-2
- Add a patch to fix a GNOME Software crash
- Silence repository listing during post

* Tue Nov 29 2016 Kalev Lember <klember@redhat.com> - 0.6.14-1
- Update to 0.6.14

* Wed Oct 26 2016 David King <amigadave@amigadave.com> - 0.6.13-2
- Add empty /etc/flatpak/remotes.d

* Tue Oct 25 2016 David King <amigadave@amigadave.com> - 0.6.13-1
- Update to 0.6.13

* Thu Oct 06 2016 David King <amigadave@amigadave.com> - 0.6.12-1
- Update to 0.6.12

* Tue Sep 20 2016 Kalev Lember <klember@redhat.com> - 0.6.11-1
- Update to 0.6.11
- Set minimum ostree and bubblewrap versions

* Mon Sep 12 2016 David King <amigadave@amigadave.com> - 0.6.10-1
- Update to 0.6.10

* Tue Sep 06 2016 David King <amigadave@amigadave.com> - 0.6.9-2
- Look for bwrap in PATH

* Thu Aug 25 2016 David King <amigadave@amigadave.com> - 0.6.9-1
- Update to 0.6.9

* Mon Aug 01 2016 David King <amigadave@amigadave.com> - 0.6.8-1
- Update to 0.6.8 (#1361823)

* Thu Jul 21 2016 David King <amigadave@amigadave.com> - 0.6.7-2
- Use system bubblewrap

* Fri Jul 01 2016 David King <amigadave@amigadave.com> - 0.6.7-1
- Update to 0.6.7

* Thu Jun 23 2016 David King <amigadave@amigadave.com> - 0.6.6-1
- Update to 0.6.6

* Fri Jun 10 2016 David King <amigadave@amigadave.com> - 0.6.5-1
- Update to 0.6.5

* Wed Jun 01 2016 David King <amigadave@amigadave.com> - 0.6.4-1
- Update to 0.6.4

* Tue May 31 2016 David King <amigadave@amigadave.com> - 0.6.3-1
- Update to 0.6.3
- Move bwrap to main package

* Tue May 24 2016 David King <amigadave@amigadave.com> - 0.6.2-1
- Rename from xdg-app to flatpak (#1337434)
