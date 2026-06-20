set -e

sshpass -V > /dev/null

mkdir -p services
sshpass -p *** \
  rsync -r --exclude '/root/ctffarm' \
  --exclude '/root/packmate' \
  --exclude '/root/snap' \
  --exclude '/root/.*' \
  root@vulnbox:/root/* ./services --progress
