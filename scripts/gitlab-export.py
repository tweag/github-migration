#!/usr/bin/env python3
# gitlab-export.py
#
# Run to create a csv file with an export of the statistics for all projects in a provided group.
# Requires some Required arguments:
# --server: GitLab server URL
# --token: Personal access token with api scope
# --group: Gitlab group name/path
# And optionals:
# --output: Output filename

# Usage:
#     scripts/gitlab-export.py --server https://gitlab.com --token xxxx --group xxxx

import argparse
import csv
from datetime import datetime

import gitlab
import utils

logger = utils.getLogger()


def is_cicd_enabled(project):
    """
    Check if CI/CD is enabled by checking for cicd file,
    using the project's default branch.
    """
    try:
        # Get the CI/CD settings for the project
        custom_path = project.ci_config_path


        standard_paths = [
            '.gitlab-ci.yml'
        ]
        
        if custom_path is not None:
            standard_paths.append(custom_path)
        
        default_branch = project.default_branch
        
        for path in standard_paths:
            try:
                project.files.get(file_path=path, ref=default_branch)
                return (True, path)
            except gitlab.exceptions.GitlabGetError:
                continue
        
        # No CI config file found
        return (False, None)
        
    except Exception as e:
        print(f"Error checking CI/CD config for project {project.id}: {str(e)}")
        return (False, None)

def analyze_gitlab_group(  # noqa: C901
    server_url, private_token, group_name, output_file=None
):
    """Analyze GitLab group using statistics endpoint for sizes"""
    gl = gitlab.Gitlab(server_url, private_token=private_token)

    try:
        gl.auth()
        logger.info("✓ Connected to GitLab server")
    except Exception as e:
        logger.error(f"✗ Connection failed: {e}")
        return

    try:
        group = gl.groups.get(group_name)
        logger.info(f"✓ Found group: {group.full_path}")
    except gitlab.exceptions.GitlabGetError:
        logger.error(f"✗ Group '{group_name}' not found")
        return

    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = (
            f'./data/gitlab_size_analysis_{group_name.replace("/", "_")}_{timestamp}.csv'
        )

    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(
            [
                "Project Name",
                "Project Path",
                "ID",
                "Repo Size (B)",
                "Repo Size (KB)",
                "Wiki Size (KB)",
                "LFS Size (KB)",
                "Storage Size (KB)",
                "Last Active",
                "Web URL",
                "wiki_size (B)",
                "package_size (B)",
                "lfs_objects_size (B)",
                "container_registry_size (B)",
                "CICD enabled",
                "CICD file path"
            ]
        )

        projects = list(
            group.projects.list(iterator=True, include_subgroups=True, all=True)
        )
        logger.info(f"Found {len(projects)} projects. Starting analysis...")

        for i, project in enumerate(projects, 1):
            try:
                # Get project with statistics in a single API call
                full_project = gl.projects.get(project.id, statistics=True)

                # Extract all statistics at once
                stats = (
                    full_project.statistics
                    if hasattr(full_project, "statistics")
                    else {}
                )

                writer.writerow(
                    [
                        full_project.name,
                        full_project.path_with_namespace,
                        full_project.id,
                        stats.get("repository_size", 0),
                        f"{stats.get('repository_size', 0)/1024:.2f}",
                        stats.get("wiki_size", 0),
                        stats.get("lfs_objects_size", 0),
                        stats.get("storage_size", 0),
                        full_project.last_activity_at,
                        full_project.web_url,
                        stats.get("wiki_size", 0),
                        stats.get("packages_size", 0),
                        stats.get("lfs_objects_size", 0),
                        stats.get("container_registry_size", 0),
                        is_cicd_enabled(full_project)[0],
                        is_cicd_enabled(full_project)[1]
                    ]
                )

                logger.info(
                    f"[{i}/{len(projects)}] {full_project.path_with_namespace.ljust(60)} "
                    f"{stats.get('repository_size', 0)/1024:.2f} KB"
                )

            except Exception as e:
                logger.error(
                    f"[{i}/{len(projects)}] Error on {getattr(project, 'path_with_namespace', 'unknown')}: {str(e)}"
                )
                continue

    logger.info(f"✓ Analysis complete. Results saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="GitLab Repository Size Analyzer (Statistics Endpoint)"
    )
    parser.add_argument(
        "--server", required=True, help="GitLab server URL (e.g., https://gitlab.com)"
    )
    parser.add_argument(
        "--token",
        required=True,
        help="Personal access token with read_api and read_repository scopes",
    )
    parser.add_argument("--group", required=True, help="Group name/path")
    parser.add_argument("--output", help="Custom output filename")
    args = parser.parse_args()

    analyze_gitlab_group(
        server_url=args.server,
        private_token=args.token,
        group_name=args.group,
        output_file=args.output,
    )
