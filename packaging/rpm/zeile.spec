# Build with: packaging/rpm/build-rpm.sh (version is passed in from pyproject.toml).
Name:           zeile
Version:        %{zeile_version}
Release:        1%{?dist}
Summary:        Small, fast GTK4 markdown viewer with live reload
License:        GPL-3.0-or-later
URL:            https://github.com/DnaMes/zeile
Source0:        zeile-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  gettext
Requires:       python3 >= 3.11
Requires:       python3-gobject
# provides the cairo typelib that gi needs; python3-gobject does not pull it in
Requires:       gobject-introspection
Requires:       gtk4
Requires:       webkitgtk6.0
Requires:       python3-markdown
Requires:       python3-pygments
Requires:       python3-pymdown-extensions
Requires:       python3-nh3
Recommends:     librsvg2
Recommends:     xdg-utils

%description
zeile renders a markdown file, reloads it on save and has 17 themes, syntax
highlighting and optional Mermaid diagrams. Document JavaScript is disabled,
the HTML is sanitized and there is no network access.

%prep
%autosetup -n zeile-%{version}

%install
packaging/stage.sh %{buildroot} %{_prefix}

%files
%license LICENSE
%doc README.md
%{_bindir}/zeile
%{_datadir}/zeile
%{_datadir}/applications/zeile.desktop
%{_datadir}/icons/hicolor/*/apps/zeile.*
%{_mandir}/man1/zeile.1*
%{_mandir}/de/man1/zeile.1*
%{_datadir}/bash-completion/completions/zeile
%{_datadir}/zsh/site-functions/_zeile
%{_datadir}/fish/vendor_completions.d/zeile.fish

%changelog
* Mon Oct 26 2026 erdlabs <https://erdlabs.com> - %{version}-1
- Packaged from the upstream release, see CHANGELOG.md
