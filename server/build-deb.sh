#!/bin/sh
# Baut herbstchat-server_<VERSION>_all.deb aus herbstchat_server.py + debian/
# Aufruf: ./build-deb.sh            (Version wird aus herbstchat_server.py gelesen)
set -eu
cd "$(dirname "$0")"
VERSION=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' herbstchat_server.py)
[ -n "$VERSION" ] || { echo "VERSION nicht gefunden" >&2; exit 1; }
OUT="herbstchat-server_${VERSION}_all.deb"
R=$(mktemp -d); chmod 755 "$R"; trap 'rm -rf "$R"' EXIT
install -d "$R/DEBIAN" "$R/usr/bin" "$R/usr/lib/herbstchat-server" "$R/etc/herbstchat" \
           "$R/lib/systemd/system" "$R/usr/share/doc/herbstchat-server"
sed "s/@VERSION@/$VERSION/" debian/control > "$R/DEBIAN/control"
install -m 644 debian/conffiles "$R/DEBIAN/conffiles"
install -m 755 debian/postinst debian/prerm debian/postrm "$R/DEBIAN/"
install -m 644 herbstchat_server.py "$R/usr/lib/herbstchat-server/herbstchat_server.py"
printf '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/herbstchat-server/herbstchat_server.py "$@"\n' > "$R/usr/bin/herbstchat-server"
chmod 755 "$R/usr/bin/herbstchat-server"
install -m 644 debian/server.conf "$R/etc/herbstchat/server.conf"
install -m 644 debian/herbstchat-server.service "$R/lib/systemd/system/herbstchat-server.service"
printf 'Herbstchat Server %s\nSiehe INSTALLATION.md\n' "$VERSION" > "$R/usr/share/doc/herbstchat-server/README"
dpkg-deb --root-owner-group --build "$R" "$OUT" >/dev/null
echo "$OUT"
