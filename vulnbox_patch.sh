set -e

sshpass -V > /dev/null

mkdir -p services
sshpass -p *** \
  rsync -r --exclude 'ctffarm' \
  --exclude 'packmate' \
  --exclude 'snap' \
  --exclude '.*' \
  ./services/* root@vulnbox:/root

ssh
