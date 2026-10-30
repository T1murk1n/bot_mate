#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    printf '%s\n' 'Run this installer as root.' >&2
    exit 1
fi

source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
app_root=/opt/bot-mate
env_file=/etc/bot-mate/bot.env
unit_file=/etc/systemd/system/bot-mate.service

if [[ ! -s $env_file ]] || ! grep -q '^BOT_TOKEN=' "$env_file"; then
    printf '%s\n' 'Configure BOT_TOKEN in /etc/bot-mate/bot.env first.' >&2
    exit 1
fi
if [[ -e $app_root && ! -f $app_root/.managed-by-bot-mate ]]; then
    printf '%s\n' 'The deployment directory already exists and is not managed by this installer.' >&2
    exit 1
fi
if [[ -e $unit_file && ! -f $app_root/.managed-by-bot-mate ]]; then
    printf '%s\n' 'An unmanaged bot-mate service already exists.' >&2
    exit 1
fi

if ! dpkg-query -W -f='${Status}' python3-venv 2>/dev/null | grep -q '^install ok installed$'; then
    apt-get update -qq
    NEEDRESTART_MODE=l DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3-venv
fi
if ! id -u bot-mate >/dev/null 2>&1; then
    useradd --system --user-group --home-dir /nonexistent --no-create-home --shell /usr/sbin/nologin bot-mate
fi
chown root:root "$env_file"
chmod 600 "$env_file"
install -d -m 755 "$app_root/releases"
touch "$app_root/.managed-by-bot-mate"
release_dir=$(mktemp -d "$app_root/releases/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")
chmod 755 "$release_dir"
install -d -m 755 "$release_dir/deploy"
for filename in bot.py input_service.py schedule_service.py schedules_all.json schedule_details.json requirements.txt; do
    install -m 644 "$source_dir/$filename" "$release_dir/$filename"
done
install -m 644 "$source_dir/deploy/check_bot.py" "$release_dir/deploy/check_bot.py"
python3 -m venv "$release_dir/.venv"
"$release_dir/.venv/bin/python" -m pip install --disable-pip-version-check --no-cache-dir -r "$release_dir/requirements.txt"
"$release_dir/.venv/bin/python" -m pip check
"$release_dir/.venv/bin/python" -m pip freeze > "$release_dir/requirements.lock.txt"

# systemd reads the root-only environment file before dropping privileges.
systemd-run --quiet --wait --pipe --collect \
    --unit="bot-mate-check-$(date +%s)" \
    --uid=bot-mate --gid=bot-mate \
    --property="WorkingDirectory=$release_dir" \
    --property="EnvironmentFile=$env_file" \
    --property=Environment=TZ=Asia/Tbilisi \
    --property=Environment=PYTHONDONTWRITEBYTECODE=1 \
    "$release_dir/.venv/bin/python" "$release_dir/deploy/check_bot.py"

previous_release=$(readlink -f "$app_root/current" || true)
verify_dir=$(mktemp -d /tmp/bot-mate-unit-XXXXXX)
sed "s|/opt/bot-mate/current|$release_dir|g" "$source_dir/deploy/bot-mate.service" > "$verify_dir/bot-mate.service"
systemd-analyze verify "$verify_dir/bot-mate.service"
rm -- "$verify_dir/bot-mate.service"
rmdir -- "$verify_dir"
install -m 644 "$source_dir/deploy/bot-mate.service" "$unit_file"
ln -s "$release_dir" "$app_root/current.next"
mv -Tf "$app_root/current.next" "$app_root/current"
systemctl daemon-reload
systemctl enable bot-mate.service
systemctl restart bot-mate.service
sleep 5
if ! systemctl is-active --quiet bot-mate.service; then
    if [[ -n $previous_release && -d $previous_release ]]; then
        ln -s "$previous_release" "$app_root/current.rollback"
        mv -Tf "$app_root/current.rollback" "$app_root/current"
        systemctl restart bot-mate.service
        printf '%s\n' 'Startup failed; the previous release was restored.' >&2
    else
        systemctl stop bot-mate.service
        systemctl disable bot-mate.service
        printf '%s\n' 'Startup failed. Review the service journal.' >&2
    fi
    exit 1
fi
printf 'Deployed release: %s\n' "$release_dir"
systemctl show bot-mate.service -p ActiveState -p SubState -p MainPID -p NRestarts -p User
