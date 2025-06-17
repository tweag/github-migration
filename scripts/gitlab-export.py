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
# --sleep: Additonal Sleep seconds is default is insufficient

# Usage:
#     scripts/gitlab-export.py --server https://gitlab.com --token xxxx --group xxxx


import gitlab
import csv
from datetime import datetime
import argparse
import time
import requests
from urllib.parse import urljoin

class GitLabRateLimitHandler:
    def __init__(self, gl):
        self.gl = gl
        self.rate_limit_remaining = 1000  # Conservative default
        self.rate_limit_reset = time.time() + 60  # 1 minute default
        self.retry_wait_base = 5  # Base wait time in seconds
        self.max_retries = 3

    def check_rate_limit(self):
        """Check and update rate limit status"""
        try:
            headers = self.gl.http_headers
            response = requests.get(urljoin(self.gl.url, '/api/v4/rate_limit'), 
                                headers=headers)
            if response.status_code == 200:
                limits = response.json()
                self.rate_limit_remaining = limits['rate']['remaining']
                self.rate_limit_reset = limits['rate']['reset']
        except Exception:
            # If we can't get limits, proceed conservatively
            pass

    def wait_if_needed(self):
        """Wait if we're approaching rate limits"""
        if self.rate_limit_remaining < 50:  # Buffer threshold
            reset_time = max(0, self.rate_limit_reset - time.time())
            wait_time = reset_time + 2  # Add 2 seconds buffer
            print(f"⚠️ Approaching rate limit. Waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)
            self.check_rate_limit()  # Refresh rate limit info after waiting

    def make_request(self, func, *args, **kwargs):
        """Wrapper for API calls with retry logic"""
        for attempt in range(self.max_retries):
            try:
                self.wait_if_needed()
                result = func(*args, **kwargs)
                self.rate_limit_remaining -= 1
                return result
            except gitlab.exceptions.GitlabRateLimitError:
                wait_time = self.retry_wait_base * (attempt + 1)
                print(f"⏳ Rate limit hit. Waiting {wait_time} seconds (attempt {attempt + 1}/{self.max_retries})...")
                time.sleep(wait_time)
                self.check_rate_limit()
            except Exception as e:
                print(f"⚠️ API error: {str(e)}")
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_wait_base)
        return None

def analyze_gitlab_group(server_url, private_token, group_name, output_file=None):
    """Analyze GitLab group with comprehensive rate limit handling"""
    gl = gitlab.Gitlab(server_url, private_token=private_token)
    rate_limiter = GitLabRateLimitHandler(gl)
    
    try:
        # Initial rate limit check
        rate_limiter.check_rate_limit()
        print(f"Initial rate limit: {rate_limiter.rate_limit_remaining} requests remaining")
        
        # Verify connection
        rate_limiter.make_request(gl.auth)
        print("✓ Connected to GitLab server")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return

    try:
        group = rate_limiter.make_request(gl.groups.get, group_name)
        print(f"✓ Found group: {group.full_path}")
    except gitlab.exceptions.GitlabGetError:
        print(f"✗ Group '{group_name}' not found")
        return

    if not output_file:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f'gitlab_analysis_{group_name.replace("/", "_")}_{timestamp}.csv'

    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([
            'Project Name', 'Project Path', 'ID', 'Size (B)', 'Size (KB)', 
            'Last Active', 'Web URL'
        ])
        
        try:
            projects = rate_limiter.make_request(group.projects.list, 
                                              iterator=True, 
                                              include_subgroups=True, 
                                              all=True)
            project_list = list(projects)
            print(f"Found {len(project_list)} projects. Starting analysis...")
            
            for i, project in enumerate(project_list, 1):
                try:
                    full_project = rate_limiter.make_request(gl.projects.get, 
                                                           project.id, 
                                                           statistics=True)
                    
                    stats = full_project.statistics if hasattr(full_project, 'statistics') else {}
                    size_kb = stats.get('repository_size', 0)
                    
                    writer.writerow([
                        full_project.name,
                        full_project.path_with_namespace,
                        full_project.id,
                        size_kb,
                        f"{size_kb/1024:.2f}",
                        full_project.last_activity_at,
                        full_project.web_url                    ])
                    
                    print(f"[{i}/{len(project_list)}] {full_project.path_with_namespace.ljust(60)} "
                          f"{size_kb/1024:.2f} KB | Remaining: {rate_limiter.rate_limit_remaining}")
                    
                    # Periodic rate limit check every 20 projects
                    if i % 20 == 0:
                        rate_limiter.check_rate_limit()
                        
                except Exception as e:
                    print(f"[{i}/{len(project_list)}] Error on {getattr(project, 'path_with_namespace', 'unknown')}: {str(e)}")
                    continue

        except Exception as e:
            print(f"✗ Failed to get projects: {str(e)}")
            return

    print(f"\n✓ Analysis complete. Results saved to {output_file}")
    print(f"Final rate limit: {rate_limiter.rate_limit_remaining} requests remaining")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='GitLab Repository Analyzer with Rate Limit Handling')
    parser.add_argument('--server', required=True, help='GitLab server URL')
    parser.add_argument('--token', required=True, help='Personal access token with api scope')
    parser.add_argument('--group', required=True, help='Group name/path')
    parser.add_argument('--output', help='Output filename')
    parser.add_argument('--sleep', type=float, default=0.1, 
                       help='Additional sleep between requests (seconds)')
    args = parser.parse_args()
    
    analyze_gitlab_group(
        server_url=args.server,
        private_token=args.token,
        group_name=args.group,
        output_file=args.output
    )