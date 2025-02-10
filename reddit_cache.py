#!/usr/bin/env python3
"""
reddit_cache.py

This script fetches and caches the newest 100 posts from one or more subreddits,
and generates various reports based on the local cache.

All cached data is stored under the "caches" folder, with each subreddit having its own subfolder.
A configuration file (caches/app.ini) stores state (e.g. posts that were manually marked as 
not containing unformatted code) so they are not flagged again in future runs.

Features:
  - Positional arguments: one or more subreddit names (default: "arduino")
  - Option -r/--report: generate a report; available option: "flair"
  - Option -l/--show N: show title, selftext, author, and flair for the last N cached posts
  - Option -L/--limit-report M: limit the number of cached posts scanned for reports to M posts
  - Option -D/--digest: include a Monthly Digest report section by scanning cached posts
       whose titles contain "Monthly Digest"
  - Option --check-code-format: interactively check cached posts for code formatting violations.
       For each post, any code outside properly formatted blocks (either fenced with ``` or indented by 4 spaces)
       is examined. If a contiguous block of 3 or more non-empty lines (ignoring blank lines) that appear to be
       Arduino/C/C++ code is detected, the full post body is printed (without truncation) and the moderator is
       prompted with:
            y: Yes, it contains unformatted code (flag it).
            n: No, it does not contain unformatted code (record in config so it isn’t flagged again).
            s: Skip this post.
            c: Cancel further checking.
       In non-interactive mode (if the environment variable TEST_NONINTERACTIVE is set),
       the response is automatically "y".
  - Option --output: choose output format:
         "json"       - machine-readable JSON output,
         "report"     - human-readable ANSI colored report,
         "markdown"   - human-readable report formatted as Markdown

All report operations use the local cache to minimize network traffic.
A new global stat, 'global_network_hits', indicates the number of network calls made.
"""

import os
import sys
import json
import requests
import argparse
import configparser
import re
import html
import logging
from tqdm import tqdm
from colorama import init, Fore, Style
from typing import Tuple, Optional, List, Dict, Any

# Initialize colorama for ANSI color support with auto-reset.
init(autoreset=True)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def get_cache_folder(subreddit: str) -> str:
    """Return the cache folder path for a given subreddit under 'caches'."""
    # Sanitize subreddit name to avoid directory traversal issues.
    safe_subreddit = re.sub(r'[^\w-]', '_', subreddit)
    folder = os.path.join("caches", safe_subreddit)
    os.makedirs(folder, exist_ok=True)
    return folder

def get_config() -> Tuple[configparser.ConfigParser, str]:
    """Load the configuration file (caches/app.ini). Create it if it doesn't exist."""
    config = configparser.ConfigParser()
    config_path = os.path.join("caches", "app.ini")
    if os.path.exists(config_path):
        config.read(config_path)
    else:
        config["CodeFormat"] = {}
    return config, config_path

def save_config(config: configparser.ConfigParser, config_path: str) -> None:
    """Save the configuration to the specified config_path."""
    with open(config_path, "w", encoding="utf-8") as configfile:
        config.write(configfile)

class ColoredHelpFormatter(argparse.RawTextHelpFormatter):
    """Custom help formatter to display usage/help text in color."""
    def format_usage(self) -> str:
        usage = super().format_usage()
        return f"{Fore.WHITE}{usage}{Style.RESET_ALL}"
    def format_help(self) -> str:
        help_text = super().format_help()
        return help_text

def fetch_posts(subreddit: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch the newest 100 posts for the given subreddit using Reddit's public JSON endpoint.
    
    Parameters:
        subreddit (str): Name of the subreddit.
        
    Returns:
        Optional[List[Dict[str, Any]]]: List of post objects, or None on error.
    """
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=100"
    headers = {"User-Agent": "python:reddit.cache.script:v1.0 (by /u/yourusername)"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.error(f"Error fetching r/{subreddit}: HTTP {resp.status_code}")
            return None
        data = resp.json()
        posts = data.get("data", {}).get("children", [])
        if not posts:
            logger.error(f"No posts found for r/{subreddit}.")
            return None
        return posts
    except Exception as e:
        logger.error(f"Exception fetching r/{subreddit}: {e}")
        return None

def cache_post(subreddit: str, post_data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Cache a post's data locally in a folder under "caches" corresponding to the subreddit.
    
    Parameters:
        subreddit (str): Subreddit name.
        post_data (Dict[str, Any]): JSON data for a single post.
        
    Returns:
        Tuple[Dict[str, Any], bool]: Cached data and a flag indicating if it was newly created.
    """
    folder = get_cache_folder(subreddit)
    post_id = post_data.get("id")
    if not post_id:
        return post_data, False
    filename = os.path.join(folder, f"{post_id}.json")
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                cached = json.load(f)
            return cached, False
        except Exception as e:
            logger.error(f"Error reading cache file {filename}: {e}")
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(post_data, f, indent=2)
    except Exception as e:
        logger.error(f"Error writing cache file {filename}: {e}")
    return post_data, True

def generate_flair_report(subreddit: str, report_limit: Optional[int] = None) -> Dict[str, int]:
    """
    Generate a summary report of unique flair texts from the cached posts.
    
    Parameters:
        subreddit (str): Subreddit name.
        report_limit (Optional[int]): Limit the number of cached posts scanned.
        
    Returns:
        Dict[str, int]: Mapping of flair texts to occurrence counts.
    """
    flair_counts: Dict[str, int] = {}
    folder = get_cache_folder(subreddit)
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.endswith(".json") and f != "custom_flairs.json"]
    posts = []
    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            posts.append(data)
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
    posts.sort(key=lambda x: x.get("created_utc", 0), reverse=True)
    if report_limit is not None:
        posts = posts[:report_limit]
    for post in posts:
        flair = post.get("link_flair_text") or "None"
        flair_counts[flair] = flair_counts.get(flair, 0) + 1
    return flair_counts

def generate_show_report(subreddit: str, n: int) -> List[Dict[str, Any]]:
    """
    Generate a report showing selected fields for the last n cached posts.
    
    Parameters:
        subreddit (str): Subreddit name.
        n (int): Number of posts.
        
    Returns:
        List[Dict[str, Any]]: List of posts with title, selftext, author, and flair.
    """
    posts_list = []
    folder = get_cache_folder(subreddit)
    for filename in os.listdir(folder):
        if filename.endswith(".json") and filename != "custom_flairs.json":
            file_path = os.path.join(folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                posts_list.append(data)
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
    posts_list.sort(key=lambda x: x.get("created_utc", 0), reverse=True)
    selected = posts_list[:n]
    return [
        {
            "title": post.get("title", ""),
            "selftext": post.get("selftext", ""),
            "author": post.get("author", ""),
            "flair": post.get("link_flair_text") or "None"
        }
        for post in selected
    ]

def generate_monthly_digest_report(subreddit: str, digest_pattern: str = "Monthly Digest", 
                                   limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Generate a Monthly Digest report section by scanning cached posts whose titles match a pattern.
    
    Parameters:
        subreddit (str): Subreddit name.
        digest_pattern (str): Pattern to search for (default "Monthly Digest").
        limit (Optional[int]): Limit the posts scanned.
        
    Returns:
        Dict[str, Any]: Digest report with header, narrative, and digest_posts, or a message if none found.
    """
    posts_list = []
    folder = get_cache_folder(subreddit)
    pattern = re.compile(digest_pattern, re.IGNORECASE)
    for filename in os.listdir(folder):
        if filename.endswith(".json") and filename != "custom_flairs.json":
            file_path = os.path.join(folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if pattern.search(data.get("title", "")):
                    posts_list.append(data)
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
    posts_list.sort(key=lambda x: x.get("created_utc", 0), reverse=True)
    if limit is not None:
        posts_list = posts_list[:limit]
    if not posts_list:
        return {"message": "No Monthly Digest posts found."}
    header = posts_list[0].get("title", "Monthly Digest")
    count = len(posts_list)
    titles = [post.get("title", "") for post in posts_list]
    highlights = "; ".join(titles[:3]) if titles else "None"
    narrative = (
        f"{header}\n\nDuring this period, {count} digest post(s) were identified. "
        f"Highlights include: {highlights}.\n\nThis digest summarizes key community highlights and statistics for the period."
    )
    digest_posts = [
        {
            "title": post.get("title", ""),
            "selftext": post.get("selftext", ""),
            "author": post.get("author", ""),
            "flair": post.get("link_flair_text") or "None"
        }
        for post in posts_list
    ]
    return {"header": header, "narrative": narrative, "digest_posts": digest_posts}

def remove_fenced_code(text: str) -> str:
    """
    Remove fenced code blocks (delimited by lines starting with ```) from text.
    
    Parameters:
        text (str): Raw markdown text.
        
    Returns:
        str: Text with fenced code blocks removed.
    """
    lines = text.splitlines()
    result_lines = []
    inside = False
    for line in lines:
        if line.strip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            result_lines.append(line)
    return "\n".join(result_lines)

def remove_indented_code(text: str) -> str:
    """
    Remove indented code blocks (lines indented by 4+ spaces or a tab) from text.
    
    Parameters:
        text (str): Raw markdown text.
        
    Returns:
        str: Text with indented code blocks removed.
    """
    lines = text.splitlines()
    result_lines = []
    for line in lines:
        if line.startswith("    ") or line.startswith("\t"):
            continue
        result_lines.append(line)
    return "\n".join(result_lines)

def clean_text(text: str) -> str:
    """
    Remove properly formatted code blocks (both fenced and indented) from text.
    Also unescape HTML entities so that code detection works on HTML-escaped content.
    
    Parameters:
        text (str): Raw markdown text.
        
    Returns:
        str: Cleaned text.
    """
    unescaped = html.unescape(text)
    return remove_indented_code(remove_fenced_code(unescaped))

def is_code_line(line: str) -> bool:
    """
    Check if a line likely contains Arduino/C/C++ code using common patterns,
    allowing for optional leading whitespace.
    
    Parameters:
        line (str): A single line of text.
        
    Returns:
        bool: True if the line appears to be code, False otherwise.
    """
    code_patterns = [
        re.compile(r'^\s*(?:#\s*)?include\s*<[^>]+>', re.IGNORECASE),
        re.compile(r'^\s*\bvoid\s+\w+\s*\([^)]*\)\s*{', re.IGNORECASE),
        re.compile(r'^\s*\bfor\s*\([^)]*\)', re.IGNORECASE),
        re.compile(r'^\s*\bwhile\s*\([^)]*\)', re.IGNORECASE),
        re.compile(r'^\s*\bif\s*\([^)]*\)', re.IGNORECASE),
        re.compile(r'^\s*\bSerial\.println\s*\(', re.IGNORECASE),
        re.compile(r'^\s*\bpinMode\s*\(', re.IGNORECASE),
        re.compile(r'^\s*\bdigitalWrite\s*\(', re.IGNORECASE),
        re.compile(r'^\s*\banalogRead\s*\(', re.IGNORECASE),
        re.compile(r'^\s*\banalogWrite\s*\(', re.IGNORECASE),
        re.compile(r'^\s*printf\s*\(', re.IGNORECASE)
    ]
    for pattern in code_patterns:
        if pattern.search(line):
            return True
    return False

def has_unformatted_code(text: str) -> bool:
    """
    Determine if text contains a contiguous block of 3 or more non-empty lines (ignoring blank lines)
    that appear to contain Arduino/C/C++ source code, ignoring properly formatted code blocks.
    
    Parameters:
        text (str): Raw markdown text.
        
    Returns:
        bool: True if such a block is detected, False otherwise.
    """
    cleaned = clean_text(text)
    lines = cleaned.splitlines()
    code_run = 0
    for line in lines:
        if line.strip() == "":
            continue
        if is_code_line(line):
            code_run += 1
            if code_run >= 3:
                return True
        else:
            code_run = 0
    return False

def print_markdown(final_output: Dict[str, Any], filters_applied: Dict[str, Any]) -> None:
    """
    Print a Markdown-formatted report of the final output.
    (Full post body text is displayed without truncation.)
    """
    md_lines = []
    md_lines.append("# Monthly Digest Report\n")
    for subreddit, result in final_output["results"].items():
        md_lines.append(f"## Subreddit: {subreddit}\n")
        summary = result.get("summary", {})
        md_lines.append(f"**Total posts checked:** {summary.get('total_posts_checked', 0)}")
        md_lines.append(f"**New posts retrieved:** {summary.get('new_posts_retrieved', 0)}\n")
        if "report" in result:
            report = result["report"]
            if "flair_summary" in report:
                md_lines.append("### Flair Report")
                for flair, count in report["flair_summary"].items():
                    md_lines.append(f"- **{flair}**: {count}")
                md_lines.append(f"- **Total unique flairs:** {report.get('total_unique_flairs', 0)}")
                md_lines.append(f"- **Total cached posts (scanned for report):** {report.get('total_cached_posts', 0)}\n")
            if "limited_scan_posts" in report:
                md_lines.append(f"### Limited Scan Report (Limit: {filters_applied.get('limit_report')})")
                for idx, post in enumerate(report["limited_scan_posts"], 1):
                    md_lines.append(f"**Post {idx}:**")
                    md_lines.append(f"- Title: {post.get('title')}")
                    md_lines.append(f"- Author: {post.get('author')}")
                    md_lines.append(f"- Flair: {post.get('flair')}")
                    md_lines.append(f"- Selftext: {post.get('selftext', '')}\n")
            if "show_posts" in report:
                md_lines.append("### Show Posts Report")
                for idx, post in enumerate(report["show_posts"], 1):
                    md_lines.append(f"**Post {idx}:**")
                    md_lines.append(f"- Title: {post.get('title')}")
                    md_lines.append(f"- Author: {post.get('author')}")
                    md_lines.append(f"- Flair: {post.get('flair')}")
                    md_lines.append(f"- Selftext: {post.get('selftext', '')}\n")
            if "monthly_digest" in report:
                digest = report["monthly_digest"]
                md_lines.append("### Monthly Digest Report")
                if "message" in digest:
                    md_lines.append(f"{digest['message']}\n")
                else:
                    md_lines.append(f"**Header:** {digest.get('header')}")
                    md_lines.append(f"**Narrative Summary:** {digest.get('narrative')}\n")
                    md_lines.append("**Digest Posts:**")
                    for idx, post in enumerate(digest.get("digest_posts", []), 1):
                        md_lines.append(f"  - **Digest Post {idx}:**")
                        md_lines.append(f"    - Title: {post.get('title')}")
                        md_lines.append(f"    - Author: {post.get('author')}")
                        md_lines.append(f"    - Flair: {post.get('flair')}")
                        md_lines.append(f"    - Selftext: {post.get('selftext', '')}")
                    md_lines.append("")
            if "code_format_violations" in report:
                md_lines.append("### Code Format Violations")
                for idx, violation in enumerate(report["code_format_violations"], 1):
                    md_lines.append(f"- **Violation {idx}:**")
                    md_lines.append(f"  - Post ID: {violation.get('id')}")
                    md_lines.append(f"  - Title: {violation.get('title')}")
                    md_lines.append(f"  - Message: {violation.get('violation')}")
        md_lines.append("\n")
    if "global_summary" in final_output:
        gs = final_output["global_summary"]
        md_lines.append("## Global Summary")
        md_lines.append(f"- **Total network retrievals (over time):** {gs.get('global_network_retrievals', 0)}")
        md_lines.append(f"- **Total cached posts (global):** {gs.get('global_cached_posts', 0)}\n")
    md_lines.append("## Filters and options applied")
    for key, value in filters_applied.items():
        md_lines.append(f"- **{key}:** {value}")
    print("\n".join(md_lines))

def print_human_readable(final_output: Dict[str, Any], filters_applied: Dict[str, Any]) -> None:
    """
    Print a human-readable, colorful, ANSI report of the final output.
    (Full post body text is displayed without truncation.)
    """
    print(f"{Fore.GREEN}=== Human Readable Report ==={Style.RESET_ALL}")
    for subreddit, result in final_output["results"].items():
        print(f"{Fore.BLUE}Subreddit: {subreddit}{Style.RESET_ALL}")
        summary = result.get("summary", {})
        print(f"  {Fore.LIGHTGREEN_EX}Total posts checked: {summary.get('total_posts_checked', 0)}{Style.RESET_ALL}")
        print(f"  {Fore.LIGHTGREEN_EX}New posts retrieved: {summary.get('new_posts_retrieved', 0)}{Style.RESET_ALL}")
        if "report" in result:
            report = result["report"]
            if "flair_summary" in report:
                print(f"\n  {Fore.MAGENTA}Flair Report:{Style.RESET_ALL}")
                for flair, count in report["flair_summary"].items():
                    print(f"    {flair}: {count}")
                print(f"    {Fore.LIGHTGREEN_EX}Total unique flairs: {report.get('total_unique_flairs', 0)}{Style.RESET_ALL}")
                print(f"    {Fore.LIGHTGREEN_EX}Total cached posts (scanned for report): {report.get('total_cached_posts', 0)}{Style.RESET_ALL}")
            if "limited_scan_posts" in report:
                print(f"\n  {Fore.MAGENTA}Limited Scan Report (Limit: {filters_applied.get('limit_report')}):{Style.RESET_ALL}")
                for idx, post in enumerate(report["limited_scan_posts"], 1):
                    print(f"    Post {idx}:")
                    print(f"      Title  : {post.get('title')}")
                    print(f"      Author : {post.get('author')}")
                    print(f"      Flair  : {post.get('flair')}")
                    print(f"      Selftext: {post.get('selftext', '')}")
            if "show_posts" in report:
                print(f"\n  {Fore.MAGENTA}Show Posts Report:{Style.RESET_ALL}")
                for idx, post in enumerate(report["show_posts"], 1):
                    print(f"    Post {idx}:")
                    print(f"      Title  : {post.get('title')}")
                    print(f"      Author : {post.get('author')}")
                    print(f"      Flair  : {post.get('flair')}")
                    print(f"      Selftext: {post.get('selftext', '')}")
            if "monthly_digest" in report:
                digest = report["monthly_digest"]
                print(f"\n  {Fore.MAGENTA}Monthly Digest Report:{Style.RESET_ALL}")
                if "message" in digest:
                    print(f"    {digest['message']}")
                else:
                    print(f"    {Fore.YELLOW}Header: {digest.get('header')}{Style.RESET_ALL}")
                    print(f"    {Fore.YELLOW}Narrative Summary:{Style.RESET_ALL} {digest.get('narrative')}")
                    print(f"    {Fore.YELLOW}Digest Posts:{Style.RESET_ALL}")
                    for idx, post in enumerate(digest.get("digest_posts", []), 1):
                        print(f"      Digest Post {idx}:")
                        print(f"        Title  : {post.get('title')}")
                        print(f"        Author : {post.get('author')}")
                        print(f"        Flair  : {post.get('flair')}")
                        print(f"        Selftext: {post.get('selftext', '')}")
                    print("")
            if "code_format_violations" in report:
                print(f"\n  {Fore.MAGENTA}Code Format Violations:{Style.RESET_ALL}")
                for idx, violation in enumerate(report["code_format_violations"], 1):
                    print(f"    Violation {idx}:")
                    print(f"      Post ID: {violation.get('id')}")
                    print(f"      Title  : {violation.get('title')}")
                    print(f"      Message: {violation.get('violation')}")
        print()
    if "global_summary" in final_output:
        gs = final_output["global_summary"]
        print(f"{Fore.CYAN}Global Summary:{Style.RESET_ALL}")
        print(f"  {Fore.LIGHTGREEN_EX}Total network retrievals (over time): {gs.get('global_network_retrievals', 0)}{Style.RESET_ALL}")
        print(f"  {Fore.LIGHTGREEN_EX}Total cached posts (global): {gs.get('global_cached_posts', 0)}{Style.RESET_ALL}")
    print(f"\n{Fore.YELLOW}Filters applied:{Style.RESET_ALL}")
    for key, value in filters_applied.items():
        print(f"  {key}: {value}")

def check_code_format_violations(subreddit: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Interactively scan cached posts for code formatting violations.
    
    A violation is defined as a contiguous block of 3 or more non-empty lines (ignoring blank lines)
    that appear to contain Arduino/C/C++ source code, ignoring properly formatted code blocks.
    
    For each post meeting the criteria and not already recorded as "no violation", the full post body is printed,
    and the user is prompted:
        y: Yes, it contains unformatted code (flag it).
        n: No, it does not contain unformatted code (record in config so it isn’t flagged again).
        s: Skip this post.
        c: Cancel further checking.
    
    In non-interactive mode (if the environment variable TEST_NONINTERACTIVE is set), the response is automatically "y".
    
    Parameters:
        subreddit (str): Subreddit name.
        limit (Optional[int]): Limit the number of posts to scan.
        
    Returns:
        List[Dict[str, Any]]: List of posts with confirmed code formatting violations.
    """
    config, config_path = get_config()
    no_violation_ids = config["CodeFormat"] if "CodeFormat" in config else {}
    violations: List[Dict[str, Any]] = []
    folder = get_cache_folder(subreddit)
    if not os.path.isdir(folder):
        return violations
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.endswith(".json") and f != "custom_flairs.json"]
    posts: List[Dict[str, Any]] = []
    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            posts.append(data)
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
    posts.sort(key=lambda x: x.get("created_utc", 0), reverse=True)
    if limit is not None:
        posts = posts[:limit]
    for post in posts:
        post_id = post.get("id", "")
        if post_id in no_violation_ids:
            continue
        selftext = post.get("selftext", "")
        if has_unformatted_code(selftext):
            print(f"\n{Fore.CYAN}Potential Code Format Violation Detected:{Style.RESET_ALL}")
            print(f"Post ID: {post_id}")
            print(f"Title: {post.get('title', '')}")
            print(f"Author: {post.get('author', '')}")
            print("Complete Selftext:")
            print(selftext)
            if os.environ.get("TEST_NONINTERACTIVE"):
                response = "y"
                print("[DEBUG] TEST_NONINTERACTIVE is set; automatically flagging this post.")
            else:
                response = input("Does this post contain unformatted code? (y/n/s/c): ").strip().lower()
            if response == "y":
                violations.append({
                    "id": post_id,
                    "title": post.get("title", ""),
                    "violation": "Post contains unformatted source code. Please format your code in proper code blocks."
                })
            elif response == "n":
                no_violation_ids[post_id] = "n"
            elif response == "s":
                continue
            elif response == "c":
                print("Cancelling code format check.")
                break
    config["CodeFormat"] = no_violation_ids
    save_config(config, config_path)
    return violations

def main() -> None:
    help_description = (
        f"{Fore.CYAN}Fetch and cache the newest 100 posts from one or more subreddits, displaying only new posts and summary stats.\n"
        "If multiple subreddits are specified, a global summary is also provided.\n\n"
        "Positional arguments:\n"
        f"  {Fore.MAGENTA}subreddits{Style.RESET_ALL}  : One or more subreddit names to fetch posts from (default: arduino).\n\n"
        "Optional arguments:\n"
        f"  {Fore.MAGENTA}-r, --report REPORT{Style.RESET_ALL} : Generate a report. Available option: flair\n"
        f"  {Fore.MAGENTA}-l, --show N{Style.RESET_ALL}      : Show title, selftext, author, and flair for the last N cached posts\n"
        f"  {Fore.MAGENTA}-L, --limit-report M{Style.RESET_ALL} : Limit the number of cached posts scanned for reports to M posts (default: no limit)\n"
        f"  {Fore.MAGENTA}-D, --digest{Style.RESET_ALL}         : Include a Monthly Digest report section (scans cached posts with titles containing 'Monthly Digest')\n"
        f"  {Fore.MAGENTA}--check-code-format{Style.RESET_ALL}    : Check cached posts for code formatting violations interactively\n"
        f"  {Fore.MAGENTA}--output OUTPUT{Style.RESET_ALL}      : Output format: 'json', 'report', or 'markdown' (default: json)\n"
    )
    help_epilog = f"{Fore.YELLOW}Example: ./reddit_cache.py arduino arduino_ai --check-code-format --output report{Style.RESET_ALL}"
    parser = argparse.ArgumentParser(
        description=help_description,
        formatter_class=ColoredHelpFormatter,
        epilog=help_epilog
    )
    parser.add_argument(
        "subreddits",
        type=str,
        nargs="*",
        default=["arduino"],
        help=f"{Fore.MAGENTA}Subreddit names (default: arduino){Style.RESET_ALL}"
    )
    parser.add_argument(
        "-r", "--report",
        type=str,
        choices=["flair"],
        help=f"{Fore.MAGENTA}Generate a report. Available option: flair{Style.RESET_ALL}"
    )
    parser.add_argument(
        "-l", "--show",
        type=int,
        metavar="N",
        help=f"{Fore.MAGENTA}Show title, selftext, author, and flair for the last N cached posts{Style.RESET_ALL}"
    )
    parser.add_argument(
        "-L", "--limit-report",
        type=int,
        metavar="M",
        help=f"{Fore.MAGENTA}Limit the number of cached posts scanned for reports to M posts (default: no limit){Style.RESET_ALL}"
    )
    parser.add_argument(
        "-D", "--digest",
        action="store_true",
        help=f"{Fore.MAGENTA}Include a Monthly Digest report section (scans cached posts with titles containing 'Monthly Digest'){Style.RESET_ALL}"
    )
    parser.add_argument(
        "--check-code-format",
        action="store_true",
        help=f"{Fore.MAGENTA}Check cached posts for code formatting violations interactively{Style.RESET_ALL}"
    )
    parser.add_argument(
        "--output",
        type=str,
        choices=["json", "report", "markdown"],
        default="json",
        help=f"{Fore.MAGENTA}Output format: 'json' for JSON output, 'report' for human-readable ANSI report, 'markdown' for Markdown-formatted report (default: json){Style.RESET_ALL}"
    )
    args = parser.parse_args()

    filters_applied = {
        "limit_report": args.limit_report if args.limit_report is not None else "None",
        "report": args.report if args.report is not None else "None",
        "show": args.show if args.show is not None else "None",
        "digest": "Enabled" if args.digest else "None",
        "check_code_format": "Enabled" if args.check_code_format else "None",
        "output": args.output
    }

    global_network_retrievals = 0
    global_cached_posts = 0
    overall_results: Dict[str, Any] = {}
    global_network_hits = 0

    for sub in tqdm(args.subreddits, desc="Processing subreddits", unit="subreddit"):
        logger.info(f"Checking subreddit: {sub}")
        posts = fetch_posts(sub)
        if posts is not None:
            global_network_hits += 1
        if posts is None or len(posts) == 0:
            logger.error(f"Subreddit '{sub}' does not exist or returned no posts. Skipping.")
            continue

        new_posts = []
        new_posts_count = 0
        for post in posts:
            post_data = post.get("data", {})
            cached, is_new = cache_post(sub, post_data)
            if is_new:
                new_posts.append(cached)
                new_posts_count += 1

        try:
            folder = get_cache_folder(sub)
            total_cached = len([f for f in os.listdir(folder) if f.endswith(".json")])
        except Exception as e:
            logger.error(f"Error counting cached posts in {sub}: {e}")
            total_cached = 0

        sub_result = {
            "new_posts": new_posts,
            "summary": {
                "subreddit": sub,
                "new_posts_retrieved": new_posts_count,
                "total_posts_checked": len(posts)
            },
            "report": {}
        }
        if args.report == "flair":
            flair_report = generate_flair_report(sub, report_limit=args.limit_report)
            sub_result["report"]["flair_summary"] = flair_report
            sub_result["report"]["total_unique_flairs"] = len(flair_report)
            sub_result["report"]["total_cached_posts"] = total_cached
            if args.limit_report is not None:
                limited_scan = generate_show_report(sub, args.limit_report)
                sub_result["report"]["limited_scan_posts"] = limited_scan

        if args.show is not None:
            show_report = generate_show_report(sub, args.show)
            sub_result["report"]["show_posts"] = show_report

        if args.digest:
            monthly_digest = generate_monthly_digest_report(sub, digest_pattern="Monthly Digest", limit=args.limit_report)
            sub_result["report"]["monthly_digest"] = monthly_digest

        if args.check_code_format:
            code_violations = check_code_format_violations(sub)
            sub_result["report"]["code_format_violations"] = code_violations

        overall_results[sub] = sub_result
        global_network_retrievals += len(posts)
        global_cached_posts += total_cached

    if not overall_results:
        logger.error("No valid subreddits were provided or found.")
        sys.exit(1)

    final_output = {"results": overall_results, "filters_applied": filters_applied}
    if len(args.subreddits) > 1:
        final_output["global_summary"] = {
            "global_network_retrievals": global_network_retrievals,
            "global_network_hits": global_network_hits,
            "global_cached_posts": global_cached_posts
        }

    print(f"{Fore.GREEN}--- Result ---{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Filters and options applied: {filters_applied}{Style.RESET_ALL}")
    if args.output == "json":
        print(json.dumps(final_output, indent=2))
    elif args.output == "markdown":
        print_markdown(final_output, filters_applied)
    else:
        print_human_readable(final_output, filters_applied)

if __name__ == '__main__':
    main()


