#!/bin/bash

USER=ubuntu

sudo chown -R ${USER}:${USER} /etc/netbox/scripts
sudo chown -R ${USER}:${USER} /home/${USER}/.config
sudo chown -R ${USER}:${USER} /home/${USER}/.claude
sudo chown ${USER}:${USER} /home/${USER}/.claude.json 2>/dev/null || true

# Reconfigure User id if set by user
if [ ! -z "${USER_UID}" ] && [ "${USER_UID}" != "`id -u ${USER}`" ] ; then
  echo -n "Update uid for user ${USER} with ${USER_UID}"
  usermod -u ${USER_UID} ${USER}
  echo "... updated"
else
  echo "skipping UID configuration"
fi

if [ -n "${USER_GID}" ] && [ "${USER_GID}" != "`id -g ${USER}`" ] ; then
  echo -n "Update gid for group ${USER} with ${USER_GID}"
  usermod -u ${USER_UID} ${USER}
  echo "... updated"
else
  echo "skipping GID configuration"
fi

# Install netbox-pathways from mounted source (editable)
if [ -d /opt/netbox-pathways ]; then
  uv pip install --no-cache-dir -e /opt/netbox-pathways
fi

# Re-install netbox-fms in case source changed
uv pip install --no-cache-dir -e /opt/netbox-fms

exec "$@"
