#!/usr/bin/env python3
# getReposList.py
import os

import requests
import utils
from openpyxl import Workbook, styles
from utils import DEFAULT_ORG, DEFAULT_TIMEOUT, GHEC_API_URL

token = utils.assertGetenv(
    "GH_SOURCE_PAT", "Provide a personal access token from the source GHES instance"
)
logger = utils.getLogger()
org = os.getenv("GH_ORG", DEFAULT_ORG)

headers = utils.ghHeaders(token)
url = f"{GHEC_API_URL}/orgs/{org}/repos"
excluded_repos_file_path = "./data/repo-batches/excludedRepos.txt"
excel_file_path = f"./data/repo-batches/{org}_repositories.xlsx"

with open(excluded_repos_file_path, "r") as file:
    excluded_repos = [line.strip() for line in file if line.strip()]

# Create a new workbook
workbook = Workbook()
sheet = workbook.active
sheet.title = "Repositories"
sheet.append(["Batch", "Name", "Description", "URL", "Migration Status", "Comments"])
boldFont = styles.Font(bold=True)
sheet["A1"].font = boldFont
sheet["B1"].font = boldFont
sheet["C1"].font = boldFont
sheet["D1"].font = boldFont
sheet["E1"].font = boldFont
sheet["F1"].font = boldFont

page = 1
while True:
    logger.info(f"Fetching page: {page}")

    # Fetch the list of repositories from GitHub API (paginated)
    params = {"page": page, "per_page": 100}
    response = requests.get(
        url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT
    )

    if response.status_code != 200:
        logger.warning(
            f"Failed to fetch repositories. Status code: {response.status_code}"
        )
        break

    current_page_repos = response.json()

    # Exclude repositories in the input list
    filtered_repos = [
        repo for repo in current_page_repos if repo["html_url"] not in excluded_repos
    ]

    for repo in filtered_repos:
        sheet.append([" ", repo["name"], repo["description"], repo["html_url"]])

    # Check if there are more pages
    if "Link" in response.headers:
        links = response.headers["Link"].split(", ")
        next_link = next((link for link in links if 'rel="next"' in link), None)
        if next_link:
            page += 1
        else:
            break
    else:
        break

batchRow = 1
for x in range(1, page):
    for cell in sheet["A"][batchRow : batchRow + 100]:
        cell.value = x
    batchRow = batchRow + 100

# Save the workbook to the specified file path
workbook.save(excel_file_path)
