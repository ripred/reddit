#!/usr/bin/env python3
"""
reddit_cache_v2.py

This script uses PRAW (Python Reddit API Wrapper) to fetch and cache the newest 1000 posts 
from one or more subreddits, and generates various reports based on the local cache.
It is a new version that replaces direct HTTP requests with PRAW for more robust, 
authenticated interactions with Reddit's API.

Features:
  - Fetch posts using PRAW (supports OAuth-based authentication via praw.ini or environment variables).
  - Caches posts locally under "caches/<subreddit>" as JSON files.
  - Generates reports (flair, monthly digest, show posts) from the cached data.
  - Checks for unformatted code in post selftexts and prompts the moderator interactively.
  - Retrieves the number of posts waiting in the mod queue and the number of unread modmail conversations.
  - Supports multiple output formats: machine-readable JSON, human-readable ANSI-colored report, and Markdown-formatted report.
  
Configuration:
  - PRAW will load credentials from praw.ini or from environment variables:
      REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT.
  - For moderation actions, you can also supply REDDIT_USERNAME and REDDIT_PASSWORD.
"""

import os
import sys
import json
import praw
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

# Custom help formatter for colored output
class ColoredHelpFormatter(argparse.RawTextHelpFormatter):
    def format_usage(self) -> str:
        usage = super().format_usage()
        return f"{Fore.WHITE}{usage}{Style.RESET_ALL}"
    def format_help(self) -> str:
        help_text = super().format_help()
        return help_text

# Initialize PRAW Reddit instance using environment variables or praw.ini
reddit = praw.Reddit(
    client_id=os.environ.get("REDDIT_CLIENT_ID"),
    client_secret=os.environ.get("REDDIT_CLIENT_SECRET"),
    user_agent=os.environ.get("REDDIT_USER_AGENT", "reddit_cache_v2 script by /u/yourusername"),
    username=os.environ.get("REDDIT_USERNAME"),
    password=os.environ.get("REDDIT_PASSWORD")
)

# -- Configuration and File I/O Helpers --

def get_cache_folder(subreddit: str) -> str:
    """Return the cache folder path for a given subreddit under 'caches'."""
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

def load_cached_posts(subreddit: str) -> List[Dict[str, Any]]:
    """Load cached posts from the given subreddit's cache folder."""
    folder = get_cache_folder(subreddit)
    posts = []
    for filename in os.listdir(folder):
        if filename.endswith(".json") and filename != "custom_flairs.json":
            file_path = os.path.join(folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                posts.append(data)
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
    posts.sort(key=lambda x: x.get("created_utc", 0), reverse=True)
    return posts

# -- PRAW API Wrappers --

def submission_to_dict(submission: praw.models.Submission) -> Dict[str, Any]:
    """Convert a PRAW submission object into a dictionary with selected fields."""
    return {
        "id": submission.id,
        "title": submission.title,
        "author": submission.author.name if submission.author else "None",
        "created_utc": submission.created_utc,
        "selftext": submission.selftext,
        "link_flair_text": submission.link_flair_text
    }

def fetch_posts(subreddit: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch the newest 1000 posts for the given subreddit using PRAW.
    Returns a list of post dictionaries or None if an error occurs.
    """
    try:
        submissions = reddit.subreddit(subreddit).new(limit=1000)
        posts = [submission_to_dict(sub) for sub in submissions]
        if not posts:
            logger.error(f"No posts found for r/{subreddit}.")
            return None
        return posts
    except Exception as e:
        logger.error(f"Exception fetching r/{subreddit}: {e}")
        return None

def cache_post(subreddit: str, post_data: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    """
    Cache a post's data locally under caches/<subreddit>.
    Returns the post data and a flag indicating whether it was newly cached.
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

def fetch_modqueue_count(subreddit: str) -> int:
    """Return the number of posts currently waiting in the moderator queue for the given subreddit."""
    try:
        mod_items = list(reddit.subreddit(subreddit).mod.modqueue(limit=None))
        return len(mod_items)
    except Exception as e:
        logger.error(f"Error fetching mod queue for r/{subreddit}: {e}")
        return 0

def fetch_modmail_count(subreddit: str) -> int:
    """Return the number of unread modmail conversations for the given subreddit."""
    try:
        conversations = list(reddit.subreddit(subreddit).modmail.conversations(limit=None))
        unread_count = sum(1 for conv in conversations if conv.state == "new")
        return unread_count
    except Exception as e:
        logger.error(f"Error fetching modmail for r/{subreddit}: {e}")
        return 0

# -- Report Generation --

def generate_flair_report(subreddit: str, report_limit: Optional[int] = None) -> Dict[str, int]:
    """Generate a summary report of unique flair texts from the cached posts."""
    posts = load_cached_posts(subreddit)
    if report_limit is not None:
        posts = posts[:report_limit]
    flair_counts: Dict[str, int] = {}
    for post in posts:
        flair = post.get("link_flair_text") or "None"
        flair_counts[flair] = flair_counts.get(flair, 0) + 1
    return flair_counts

def generate_show_report(subreddit: str, n: int) -> List[Dict[str, Any]]:
    """Generate a report showing selected fields for the last n cached posts."""
    posts_list = load_cached_posts(subreddit)
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
    Returns a dictionary containing the header, narrative, and digest posts, or a message if none are found.
    """
    posts_list = load_cached_posts(subreddit)
    pattern = re.compile(digest_pattern, re.IGNORECASE)
    posts_list = [post for post in posts_list if pattern.search(post.get("title", ""))]
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

# -- Code Formatting Helpers --

def remove_fenced_code(text: str) -> str:
    """
    Remove fenced code blocks (delimited by lines starting with ```) from text.
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
    """
    lines = text.splitlines()
    result_lines = []
    for line in lines:
        if line.startswith("    ") or line.startswith("\t"):
            continue
        result_lines.append(line)
    return "\n".join(result_lines)

def remove_inline_code(text: str) -> str:
    """
    Remove inline code spans (enclosed in single backticks) from text.
    """
    return re.sub(r"`[^`]+`", "", text)

def clean_text(text: str) -> str:
    """
    Unescape HTML entities and remove fenced, indented, and inline code blocks from text.
    """
    unescaped = html.unescape(text)
    cleaned = remove_fenced_code(unescaped)
    cleaned = remove_indented_code(cleaned)
    cleaned = remove_inline_code(cleaned)
    return cleaned

# List of inline code patterns (not anchored to the start) for detecting code anywhere in a line.
inline_code_patterns = [
    re.compile(r'(?:#\s*)?include\s*<[^>]+>', re.IGNORECASE),
    re.compile(r'\bvoid\s+\w+\s*\([^)]*\)\s*{', re.IGNORECASE),
    re.compile(r'\bfor\s*\([^)]*\)', re.IGNORECASE),
    re.compile(r'\bwhile\s*\([^)]*\)', re.IGNORECASE),
    re.compile(r'\bif\s*\([^)]*\)', re.IGNORECASE),
    re.compile(r'\bSerial\.println\s*\(', re.IGNORECASE),
    re.compile(r'\bpinMode\s*\(', re.IGNORECASE),
    re.compile(r'\bdigitalWrite\s*\(', re.IGNORECASE),
    re.compile(r'\banalogRead\s*\(', re.IGNORECASE),
    re.compile(r'\banalogWrite\s*\(', re.IGNORECASE),
    re.compile(r'printf\s*\(', re.IGNORECASE)
]

def count_inline_code_patterns(line: str) -> int:
    """
    Count the number of occurrences of code-like patterns in a line.
    """
    count = 0
    for pattern in inline_code_patterns:
        count += len(pattern.findall(line))
    return count

def is_code_line(line: str) -> bool:
    """
    Check if a line likely contains Arduino/C/C++ code using common patterns.
    """
    for pattern in inline_code_patterns:
        if pattern.search(line):
            return True
    return False

def has_unformatted_code(text: str, inline_threshold: int = 3, multiline_threshold: int = 3) -> bool:
    """
    Determine if text contains unformatted code.
    
    This function now checks in two ways:
      1. **Inline Check:**  
         If any single non-empty line contains at least `inline_threshold` matches of code-like patterns,
         it is flagged as unformatted.
      2. **Multiline Check:**  
         If there are at least `multiline_threshold` consecutive lines that look like code, it is flagged.
    
    **Additional Heuristic:**  
      If the total number of non-empty lines exceeds 50 and less than 30% of them look like code, then
      the text is presumed to be well-formatted (even if some lines match) and will not be flagged.
    
    The thresholds can be adjusted via parameters.
    """
    cleaned = clean_text(text)
    lines = [line for line in cleaned.splitlines() if line.strip() != ""]

    # Heuristic: For long posts, if only a small fraction of lines appear as code, assume it is well formatted.
    total_lines = len(lines)
    if total_lines > 50:
        code_lines = sum(1 for line in lines if is_code_line(line))
        if (code_lines / total_lines) < 0.3:
            return False

    # Inline check: Each non-empty line is checked for inline code pattern occurrences.
    for line in lines:
        if count_inline_code_patterns(line) >= inline_threshold:
            return True

    # Multiline check: Check for consecutive lines that look like code.
    consecutive = 0
    for line in lines:
        if is_code_line(line):
            consecutive += 1
            if consecutive >= multiline_threshold:
                return True
        else:
            consecutive = 0
    return False

# -- Output Functions --

def print_markdown(final_output: Dict[str, Any], filters_applied: Dict[str, Any]) -> None:
    """
    Print a Markdown-formatted report of the final output.
    """
    md_lines = []
    md_lines.append("# Monthly Digest Report\n")
    for subreddit, result in final_output["results"].items():
        md_lines.append(f"## Subreddit: {subreddit}\n")
        summary = result.get("summary", {})
        md_lines.append(f"**Total posts checked:** {summary.get('total_posts_checked', 0)}")
        md_lines.append(f"**New posts retrieved:** {summary.get('new_posts_retrieved', 0)}\n")
        if "modqueue_count" in result:
            md_lines.append(f"**Mod Queue Count:** {result['modqueue_count']}\n")
        if "modmail_count" in result:
            md_lines.append(f"**Modmail Count:** {result['modmail_count']}\n")
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
    for key, value in final_output.get("filters_applied", {}).items():
        md_lines.append(f"- **{key}:** {value}")
    print("\n".join(md_lines))

def print_human_readable(final_output: Dict[str, Any], filters_applied: Dict[str, Any]) -> None:
    """
    Print a human-readable, colorful, ANSI report of the final output.
    """
    print(f"{Fore.GREEN}=== Human Readable Report ==={Style.RESET_ALL}")
    for subreddit, result in final_output["results"].items():
        print(f"{Fore.BLUE}Subreddit: {subreddit}{Style.RESET_ALL}")
        summary = result.get("summary", {})
        print(f"  {Fore.LIGHTGREEN_EX}Total posts checked: {summary.get('total_posts_checked', 0)}{Style.RESET_ALL}")
        print(f"  {Fore.LIGHTGREEN_EX}New posts retrieved: {summary.get('new_posts_retrieved', 0)}{Style.RESET_ALL}")
        if "modqueue_count" in result:
            print(f"  {Fore.LIGHTGREEN_EX}Mod Queue Count: {result['modqueue_count']}{Style.RESET_ALL}")
        if "modmail_count" in result:
            print(f"  {Fore.LIGHTGREEN_EX}Modmail Count: {result['modmail_count']}{Style.RESET_ALL}")
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
    for key, value in final_output.get("filters_applied", {}).items():
        print(f"  {key}: {value}")

# -- Code Formatting Check --

def check_code_format_violations(subreddit: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Interactively scan cached posts for code formatting violations.
    
    For each post, any code outside properly formatted blocks is inspected.
    A violation is flagged if either:
      - A single non-empty line contains at least `inline_threshold` occurrences of code-like patterns, or
      - There are at least `multiline_threshold` consecutive lines that look like code.
      
    An additional heuristic prevents flagging if the post is very long (more than 50 non-empty lines)
    and less than 30% of lines appear as code, assuming the code is well formatted.
    
    In non-interactive mode (if the environment variable TEST_NONINTERACTIVE is set),
    the response is automatically "y" (flagging the post).
    """
    inline_threshold = 3
    multiline_threshold = 3

    config, config_path = get_config()
    no_violation_ids = config["CodeFormat"] if "CodeFormat" in config else {}
    violations: List[Dict[str, Any]] = []
    posts = load_cached_posts(subreddit)
    if limit is not None:
        posts = posts[:limit]
    for post in posts:
        post_id = post.get("id", "")
        if post_id in no_violation_ids:
            continue
        selftext = post.get("selftext", "")
        if has_unformatted_code(selftext, inline_threshold, multiline_threshold):
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
                no_violation_ids[post_id] = "flagged"
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

# -- Main Program --

def main() -> None:
    help_description = (
        f"{Fore.CYAN}Fetch and cache the newest 1000 posts from one or more subreddits using PRAW, displaying only new posts and summary stats.\n"
        "If multiple subreddits are specified, a global summary is also provided.\n\n"
        "Positional arguments:\n"
        f"  {Fore.MAGENTA}subreddits{Style.RESET_ALL}  : One or more subreddit names to fetch posts from (default: arduino).\n\n"
        "Optional arguments:\n"
        f"  {Fore.MAGENTA}-r, --report REPORT{Style.RESET_ALL} : Generate a report. Available option: flair\n"
        f"  {Fore.MAGENTA}-l, --show N{Style.RESET_ALL}      : Show title, selftext, author, and flair for the last N cached posts\n"
        f"  {Fore.MAGENTA}-L, --limit-report M{Style.RESET_ALL} : Limit the number of cached posts scanned for reports to M posts (default: no limit)\n"
        f"  {Fore.MAGENTA}-D, --digest{Style.RESET_ALL}         : Include a Monthly Digest report section (scans cached posts with titles containing 'Monthly Digest')\n"
        f"  {Fore.MAGENTA}--check-code-format{Style.RESET_ALL}    : Check cached posts for code formatting violations interactively\n"
        f"  {Fore.MAGENTA}--modqueue{Style.RESET_ALL}             : Include the number of posts waiting in the mod queue\n"
        f"  {Fore.MAGENTA}--modmail{Style.RESET_ALL}              : Include the number of unread modmail conversations\n"
        f"  {Fore.MAGENTA}--output OUTPUT{Style.RESET_ALL}      : Output format: 'json', 'report', or 'markdown' (default: json)\n"
    )
    help_epilog = f"{Fore.YELLOW}Example: ./reddit_cache_v2.py arduino --check-code-format --modqueue --modmail --output report{Style.RESET_ALL}"
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
        "--modqueue",
        action="store_true",
        help=f"{Fore.MAGENTA}Include the number of posts waiting in the mod queue for each subreddit{Style.RESET_ALL}"
    )
    parser.add_argument(
        "--modmail",
        action="store_true",
        help=f"{Fore.MAGENTA}Include the number of unread modmail conversations for each subreddit{Style.RESET_ALL}"
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
        "modqueue": "Enabled" if args.modqueue else "None",
        "modmail": "Enabled" if args.modmail else "None",
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
            cached, is_new = cache_post(sub, post)
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
        if args.modqueue:
            modqueue_count = fetch_modqueue_count(sub)
            sub_result["modqueue_count"] = modqueue_count

        if args.modmail:
            modmail_count = fetch_modmail_count(sub)
            sub_result["modmail_count"] = modmail_count

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

