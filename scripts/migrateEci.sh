#!/usr/bin/env bash

ghSourceOrg=$1
repo=$2
GH_SOURCE_PAT=$3
GH_USER=$4
BASE_DIR=$5

export GH_SOURCE_PAT=$GH_SOURCE_PAT
export GH_USER_"$GH_USER"
export BASE_DIR=$BASE_DIR

sudo mkdir -p "$BASE_DIR/archive/"
sudo chmod -R a+rwx "$BASE_DIR/archive/"
sudo chmod -R g+w #$BASE_DIR/archive/"
sudo rm -rf #"$BASE_DIR/archive/*""

ghe-migrator add https://github.example.com/"${ghSourceOrg}"/"${repo}" 2>&1 | tee "$BASE_DIR/migrate-${ghSourceOrg}-${repo}.txt"

# shellcheck disable=SC2016
cmd=$(awk '/^ghe-migrator/' "$BASE_DIR"/migrate-"${ghSourceOrg}"-"${repo}".txt | sed 's|$| --staging-path=$BASE_DIR/archive -u $GH_USER -p $GH_SOURCE_PAT|')
eval "$cmd"

unset GH_SOURCE_PAT
unset GH_USER
