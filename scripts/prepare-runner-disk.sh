#!/usr/bin/env bash
# Move Docker's storage to the runner's large ephemeral volume.
#
# arize.sh pull-images stages 26 images through the local Docker daemon.
# ubuntu-latest has ~14 GB free on / but ~65 GB on /mnt.
set -euo pipefail

echo "▶ Disk before:"
df -h / /mnt

sudo systemctl stop docker.socket docker || sudo systemctl stop docker

sudo mkdir -p /mnt/docker
printf '{\n  "data-root": "/mnt/docker"\n}\n' | sudo tee /etc/docker/daemon.json

sudo systemctl start docker
sudo systemctl is-active --quiet docker

root_dir="$(docker info --format '{{.DockerRootDir}}')"
echo "▶ Docker root: ${root_dir}"
if [ "${root_dir}" != "/mnt/docker" ]; then
  echo "🛑 Docker did not adopt /mnt/docker; aborting before the image pull" >&2
  exit 1
fi

echo "▶ Disk after:"
df -h /mnt
