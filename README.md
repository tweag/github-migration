# github-migration

[![Checked with mypy](https://img.shields.io/badge/mypy-checked-blue)](http://mypy-lang.org/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-black.svg)](https://github.com/psf/black)

This repository hosts scripts and data files related to migrating from GitHub Enterprise Server (GHES)
to GitHub Enterprise Cloud (GHEC).

The main migration tool used
for this is [gh-gei](https://github.com/github/gh-gei), and a secondary tool is a GitHub internal and
tool called the [Enterprise Cloud Importer](https://eci.github.com/). In an enterprise environment 
some custom tooling helps fill the gaps that both these tools leave in migrating repositories.

## Development

To work on this app, you need a Macbook, Linux or Windows system.

The scripts are Python 3 scripts, in the `scripts` directory. They require some environment variables to be set for 
them to work, see each script for details.

This file has some Git LFS files, see 
[GitHub's documentation on working with large files](https://docs.github.com/en/repositories/working-with-files/managing-large-files/configuring-git-large-file-storage)
for how to enable LFS on your workstation.

Copy the [`env-sample`](env-sample) file to `.env` and customize it with tokens according to the directions within, 
then source it with:

    set -o allexport && source .env && set +o allexport

### Git LFS

This repository requires Git LFS to be installed on any system that clones the repository.  See 
[GitHub's documentation on installing LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/installing-git-large-file-storage)
for guidance on installing this for your operating system.

### Windows compatiblitiy

Please refrain from using Windows-incompatible characters in filenames in this project. This will help team members who use Windows development systems. 

You can use the `iso8601_win_safe_ts` function from [common.sh](scripts/common.sh) to get a Windows-safe timestamp 
for use in filenames.

### Data files

This repo contains not only the scripts to retrieve key metadata from the existing GHES installation 
and other sources, but also the _results_ of those scripts.

See the [data](data/) directory for data files enumerating users, webhooks, and domains related to the effort.

### Linting

This uses a variety of linters to help ensure high code quality.

1. Run the linter suite.
    scripts/lint.sh

1. If there are formatting problems, run the formatter suite.
-   scripts/fmt.sh

This uses these tools:

- PyTest: [https://docs.pytest.org/en/latest/contents.html](https://docs.pytest.org/en/latest/contents.html)
- MyPy: [https://mypy.readthedocs.io/en/latest/](https://mypy.readthedocs.io/en/latest/)
- Black: [https://black.readthedocs.io/en/stable/](https://black.readthedocs.io/en/stable/)
- Flake8: [http://flake8.pycqa.org/en/latest/](http://flake8.pycqa.org/en/latest/)
- Bandit: [https://bandit.readthedocs.io/en/latest/](https://bandit.readthedocs.io/en/latest/)
- Shellcheck: (optional) [https://shellcheck.net](https://shellcheck.net/)

### Troubleshooting

#### Buildkite VCS Fixup

If _all_ of the Buildkite VCS migrations fail during a migration run, you might not have an admin-level Buildkite 
token. 

You can re-run the Buildkite patching once you have Admin credentials with this series of commands, substituting your
repoList file in `REPO_LIST`:

    REPO_LIST=data/repoList_GHCM-207.txt
    while read slug; do scripts/patchBuildkitePipeline.sh <<<"$slug"; done < "$REPO_LIST"

### Requirements

-   **requirements.txt**
    All first level dependencies should be declared in `requirements.txt`.
-   **requirements-test.txt**
    All requirements needed to run the application's test/lint suite should be declared in `requirements-test.txt`.

## Documentation

## ECI migration

To migrate repos using the [GitHub Enterprise Cloud Importer (ECI)](https://eci.github.com/) follow the steps below:

* You will need to conduct this on a workstation with a web browser, not the shared Linux migration host.
* You must be an organization owner, and have a personal access token from GitHub.com with scopes for repos, teams, 
and from your account - the [same scopes required for gh-gei][1]. 
*Important*: to use this tool GitHub has to put you on a special per-organization, 
per-user access control list, please make the ask via a GitHub partner.
* With your repos saved in a text file, run the triggerMigrateECI.sh script 
which will initiate a migration export on the GHES server:

    scripts/triggerMigrateECI.sh < data/repoList.txt

* Once complete, this script downloads the archive to data/migrations/archive folder.
* Sign into https://eci.github.com/ with your organization owner personal access token
* Upload this archive to the ECI tool: https://eci.github.com and note the migration GUID and ID. 
Save that in a scratch notes file on your system.
* Wait until upload completes and using the GUID and ID from the above tool, run the setEciImports.py script.

    GH_MIGRATION_GUID=****** GH_MIGRATION_ID=**** GH_ORG=example-org scripts/setEciImports.py

* This script will output a csv file in the data/ folder with format user_conflicts_[org name]_[migration guid].
* Upload this file to the ECI tool, click on skip until you see the "Perform Import" button, 
click on this and continue with the import.
* Once the import has been completed and the repository has been migrated succesfuly and unlocked,
run the decoupledMigrate.sh script to perform all post migration tasks.

    scripts/decoupledMigrate.sh < data/repoList.txt
* Once the migration has been completed first confirm that no ECI migrations are running org wide,
then navigate to the github.com org(s) that the repos were migrated to, delete the team named `migration_dummy_team`.

## Editing the documentation

If you are editing the documentation, please put at most one sentence on each line.
This helps keep the diffs clean.
It's recommended that you turn soft-wraps on for markdown files in your editor.
All markdown in your project will be linted as part of the Buildkite pipeline.
You may run linting locally by using the `mdlint` service in your project's docker-compose file.
`docker-compose run --rm mdlint` will lint all markdown files using Python Platform's
style guide and automatically fix violations when possible.

## Authors

`github-migration` was written by `Uzoma Nwoko <uzoma.nwoko@wayfair.com>` and `Richard Bullington-McGuire <rbullingtonmcguire@wayfair.com>`.

[1] https://docs.github.com/en/migrations/using-github-enterprise-importer/migrating-between-github-products/managing-access-for-a-migration-between-github-products#required-scopes-for-personal-access-tokens
