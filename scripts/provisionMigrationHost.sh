#!/usr/bin/env bash
# provisionMigrationHost.sh
#
# Provision the host used for migration with # tools required for the GitHub enterprise migration.
# Run this on that host from a sudo-capable account.
#
# This should be idempotent.
#
# This assumes a Debian 10 host.
#
# This can be run in a 2 stage bootstrap, where it is run from another host first, then
#
#  ssh luser@192.0.2.222 '/usr/bin/env bash' < ~/Documents/github-migration/scripts/provisionMigrationHost.sh

# Set bash unofficial strict mode http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail
IFS=$'\n\t'

scratch=$(mktemp -t provisionMigrationHost.XXXXXXXXXX)
function finish {
    rm -rf "$scratch"
}
trap finish EXIT
DEBUG=${DEBUG:-false}
# Set DEBUG to true for enhanced debugging: run prefixed with "DEBUG=true"
${DEBUG:-false} && set -vx

BASE_PACKAGES='
at
build-essential
ca-certificates
curl
git
gfortran
gpg
jq
python3
python3-dev
python3-venv
tmux
unzip
parallel
'

INTERNAL_CA=/usr/local/share/ca-certificates/Examplee-Root-Certification-Authority-G2.crt

# Ensure this is running on the right OS distribution
ACCEPTABLE_OS="Debian 10"
if ! which lsb_release > /dev/null; then
	echo "ERROR: no lsb_release found, is this running on Linux?"
	exit 2
fi
LSB_DISTRIBUTOR=$(lsb_release -i | cut -f 2)
LSB_VERSION=$(lsb_release -r | cut -f 2)
if [[ "${LSB_DISTRIBUTOR} ${LSB_VERSION}" != "$ACCEPTABLE_OS" ]]; then
	echo "ERROR: This script will only run on $ACCEPTABLE_OS"
	exit 3
fi

# Install base packages
sudo apt-get -qq update
#shellcheck disable=SC2086
sudo apt-get install -qq -y $BASE_PACKAGES

# Install htmlq
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
# shellcheck disable=SC1091
source "$HOME/.cargo/env"
cargo install htmlq
sudo install "$HOME/.cargo/bin/htmlq" /usr/local/bin

# Install GitHub CLI per https://github.com/cli/cli/blob/trunk/docs/install_linux.md
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg 2>/dev/null
sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt-get update -qq
sudo apt-get install -qq -y gh

sudo dd of="$INTERNAL_CA" <<EOF 2>/dev/null
-----BEGIN CERTIFICATE-----
TODO insert certificate here
-----END CERTIFICATE-----
EOF
sudo update-ca-certificates

# Install Vault CLI
if [[ -z "$(which vault)" ]]; then
    cd /tmp
    wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
    sudo apt update && sudo apt install vault
    cd -
fi

# Detect whether this is being run in initial boostrap mode
if [[ ${GH_PAT:-} != '' ]]; then
    GH_TOKEN="$GH_PAT"
fi
if [[ ${GH_TOKEN:-} = '' ]]; then
    echo "WARNING: GH_TOKEN not set, assuming this is being run in bootstrap mode."
    if [[ ! -d ~/Documents/github-migration ]]; then
        echo "INFO: attempting to clone migration repo"
        mkdir -p ~/Documents/
        cd ~/Documents/
        git clone git@github.example.com:org1/github-migration.git
    fi
    echo "WARNING: ssh to the migration host, set GH_TOKEN,"
    echo "WARNING: and re-run this script from ~/Documents/github-migration"
    exit 0
fi

# Install GitHub GEI CLI per gh extension install github/gh-gei
## Note, this might not be fully reliable unless you have set a GH_TOKEN
## environment variable.
gh extension install github/gh-gei && true

# Install Sourcegraph CLI
sudo curl -L https://sourcegraph.com/.api/src-cli/src_linux_amd64 -o /usr/local/bin/src
sudo chmod +x /usr/local/bin/src
