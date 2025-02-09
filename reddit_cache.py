#!/usr/bin/env python3
"""
reddit_cache.py

This script fetches and caches the newest 100 posts from one or more subreddits,
and generates various reports based on the local cache.

Features:
  - Positional arguments: one or more subreddit names (default: "arduino")
  - Option -r/--report: generate a report; available option: "flair"
  - Option -l/--show N: show title, selftext, author, and flair for the last N cached posts
  - Option -L/--limit-report M: limit the number of cached posts scanned for reports to M posts
  - Option -D/--digest: include a Monthly Digest report section by scanning cached posts
       whose titles contain "Monthly Digest"
  - Option --output: choose output format:
         "json"       - machine-readable JSON output,
         "report"     - human-readable ANSI colored report,
         "markdown"   - human-readable report formatted as Markdown

All report operations use the local cache to minimize network traffic.
"""

import os
import sys
import json
import requests
import argparse
from tqdm import tqdm
from colorama import init, Fore, Style

# Initialize colorama for ANSI color support with auto-reset.
init(autoreset=True)

class ColoredHelpFormatter(argparse.RawTextHelpFormatter):
    """Custom help formatter to display usage/help text in color."""
    def format_usage(self):
        usage = super().format_usage()
        return f"{Fore.WHITE}{usage}{Style.RESET_ALL}"
    def format_help(self):
        help_text = super().format_help()
        return help_text

def fetch_posts(subreddit):
    """
    Fetch the newest 100 posts for the given subreddit using Reddit's public JSON endpoint.
    
    Parameters:
        subreddit (str): Name of the subreddit.
        
    Returns:
        list: List of post objects (each containing a 'data' key), or None on error.
    """
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=100"
    headers = {"User-Agent": "python:reddit.cache.script:v1.0 (by /u/yourusername)"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"{Fore.RED}Error fetching r/{subreddit}: HTTP {resp.status_code}{Style.RESET_ALL}", file=sys.stderr)
            return None
        data = resp.json()
        posts = data.get("data", {}).get("children", [])
        if not posts:
            print(f"{Fore.RED}No posts found for r/{subreddit}.{Style.RESET_ALL}", file=sys.stderr)
            return None
        return posts
    except Exception as e:
        print(f"{Fore.RED}Exception fetching r/{subreddit}: {e}{Style.RESET_ALL}", file=sys.stderr)
        return None

def cache_post(subreddit, post_data):
    """
    Cache a post's data locally in a folder named after the subreddit.
    
    Parameters:
        subreddit (str): Subreddit name.
        post_data (dict): JSON data for a single post.
        
    Returns:
        tuple: (cached_data, is_new) where is_new is True if the file was newly created.
    """
    folder = subreddit
    os.makedirs(folder, exist_ok=True)
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
            print(f"{Fore.RED}Error reading cache file {filename}: {e}{Style.RESET_ALL}", file=sys.stderr)
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(post_data, f, indent=2)
    except Exception as e:
        print(f"{Fore.RED}Error writing cache file {filename}: {e}{Style.RESET_ALL}", file=sys.stderr)
    return post_data, True

def generate_flair_report(subreddit, report_limit=None):
    """
    Generate a summary report of unique flair texts from the cached posts.
    
    Parameters:
        subreddit (str): Subreddit name.
        report_limit (int, optional): Limit the number of cached posts scanned (most recent M posts).
        
    Returns:
        dict: Mapping of flair texts to their occurrence counts.
    """
    flair_counts = {}
    folder = subreddit
    if not os.path.isdir(folder):
        print(f"{Fore.RED}No cache folder for subreddit {subreddit} found.{Style.RESET_ALL}", file=sys.stderr)
        return flair_counts
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if f.endswith(".json") and f != "custom_flairs.json"]
    posts = []
    for file_path in files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            posts.append(data)
        except Exception as e:
            print(f"{Fore.RED}Error processing {file_path}: {e}{Style.RESET_ALL}", file=sys.stderr)
    posts.sort(key=lambda x: x.get("created_utc", 0), reverse=True)
    if report_limit is not None:
        posts = posts[:report_limit]
    for post in posts:
        flair = post.get("link_flair_text") or "None"
        flair_counts[flair] = flair_counts.get(flair, 0) + 1
    return flair_counts

def generate_show_report(subreddit, n):
    """
    Generate a report showing the title, selftext, author, and flair for the last n cached posts.
    
    Parameters:
        subreddit (str): Subreddit name.
        n (int): Number of posts to include.
        
    Returns:
        list: List of dicts with keys 'title', 'selftext', 'author', and 'flair'.
    """
    posts_list = []
    folder = subreddit
    if not os.path.isdir(folder):
        print(f"{Fore.RED}No cache folder for subreddit {subreddit} found.{Style.RESET_ALL}", file=sys.stderr)
        return []
    for filename in os.listdir(folder):
        if filename.endswith(".json") and filename != "custom_flairs.json":
            file_path = os.path.join(folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                posts_list.append(data)
            except Exception as e:
                print(f"{Fore.RED}Error processing {file_path}: {e}{Style.RESET_ALL}", file=sys.stderr)
    posts_list.sort(key=lambda x: x.get("created_utc", 0), reverse=True)
    selected = posts_list[:n]
    report_list = []
    for post in selected:
        report_list.append({
            "title": post.get("title", ""),
            "selftext": post.get("selftext", ""),
            "author": post.get("author", ""),
            "flair": post.get("link_flair_text") or "None"
        })
    return report_list

def generate_monthly_digest_report(subreddit, digest_pattern="Monthly Digest", limit=None):
    """
    Generate a Monthly Digest report section by scanning cached posts whose titles contain
    the given digest_pattern (case-insensitive) and synthesizing a digest-style summary.
    
    Parameters:
        subreddit (str): Subreddit name.
        digest_pattern (str): Pattern to search for in titles (default: "Monthly Digest").
        limit (int, optional): Limit the number of cached posts scanned for the digest report.
        
    Returns:
        dict: A digest report with keys 'header', 'narrative', and 'digest_posts'.
              If no digest posts are found, returns a dict with a message.
    """
    import re
    posts_list = []
    folder = subreddit
    if not os.path.isdir(folder):
        print(f"{Fore.RED}No cache folder for subreddit {subreddit} found.{Style.RESET_ALL}", file=sys.stderr)
        return {"message": "No cache folder found."}
    pattern = re.compile(digest_pattern, re.IGNORECASE)
    for filename in os.listdir(folder):
        if filename.endswith(".json") and filename != "custom_flairs.json":
            file_path = os.path.join(folder, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                title = data.get("title", "")
                if pattern.search(title):
                    posts_list.append(data)
            except Exception as e:
                print(f"{Fore.RED}Error processing {file_path}: {e}{Style.RESET_ALL}", file=sys.stderr)
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
        f"{header}\n\n"
        f"During this period, {count} digest post(s) were identified. "
        f"Highlights include: {highlights}.\n\n"
        "This digest summarizes key community highlights and statistics for the period."
    )
    digest_posts = []
    for post in posts_list:
        digest_posts.append({
            "title": post.get("title", ""),
            "selftext": post.get("selftext", ""),
            "author": post.get("author", ""),
            "flair": post.get("link_flair_text") or "None"
        })
    return {
        "header": header,
        "narrative": narrative,
        "digest_posts": digest_posts
    }

def print_human_readable(final_output, filters_applied):
    """
    Print a human-readable, colorful, ANSI report of the final output.
    """
    print(f"{Fore.GREEN}=== Human Readable Report ==={Style.RESET_ALL}")
    for subreddit, result in final_output["results"].items():
        print(f"\n{Fore.BLUE}Subreddit: {subreddit}{Style.RESET_ALL}")
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
                    selftext = post.get("selftext", "")
                    if len(selftext) > 100:
                        selftext = selftext[:100] + "..."
                    print(f"      Selftext: {selftext}")
            if "show_posts" in report:
                print(f"\n  {Fore.MAGENTA}Show Posts Report:{Style.RESET_ALL}")
                for idx, post in enumerate(report["show_posts"], 1):
                    print(f"    Post {idx}:")
                    print(f"      Title  : {post.get('title')}")
                    print(f"      Author : {post.get('author')}")
                    print(f"      Flair  : {post.get('flair')}")
                    selftext = post.get("selftext", "")
                    if len(selftext) > 100:
                        selftext = selftext[:100] + "..."
                    print(f"      Selftext: {selftext}")
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
                        selftext = post.get("selftext", "")
                        if len(selftext) > 100:
                            selftext = selftext[:100] + "..."
                        print(f"        Selftext: {selftext}")
    if "global_summary" in final_output:
        gs = final_output["global_summary"]
        print(f"\n{Fore.CYAN}Global Summary:{Style.RESET_ALL}")
        print(f"  {Fore.LIGHTGREEN_EX}Total network retrievals: {gs.get('global_network_retrievals', 0)}{Style.RESET_ALL}")
        print(f"  {Fore.LIGHTGREEN_EX}Total cached posts (global): {gs.get('global_cached_posts', 0)}{Style.RESET_ALL}")
    print(f"\n{Fore.YELLOW}Filters applied:{Style.RESET_ALL}")
    for key, value in filters_applied.items():
        print(f"  {key}: {value}")

def print_markdown(final_output, filters_applied):
    """
    Print a Markdown-formatted report of the final output.
    """
    md_lines = []
    md_lines.append("# Monthly Digest Report\n")
    for subreddit, result in final_output["results"].items():
        md_lines.append(f"## Subreddit: {subreddit}\n")
        summary = result.get("summary", {})
        md_lines.append(f"**Total posts checked:** {summary.get('total_posts_checked', 0)}  ")
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
                    selftext = post.get("selftext", "")
                    if len(selftext) > 100:
                        selftext = selftext[:100] + "..."
                    md_lines.append(f"- Selftext: {selftext}\n")
            if "show_posts" in report:
                md_lines.append("### Show Posts Report")
                for idx, post in enumerate(report["show_posts"], 1):
                    md_lines.append(f"**Post {idx}:**")
                    md_lines.append(f"- Title: {post.get('title')}")
                    md_lines.append(f"- Author: {post.get('author')}")
                    md_lines.append(f"- Flair: {post.get('flair')}")
                    selftext = post.get("selftext", "")
                    if len(selftext) > 100:
                        selftext = selftext[:100] + "..."
                    md_lines.append(f"- Selftext: {selftext}\n")
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
                        selftext = post.get("selftext", "")
                        if len(selftext) > 100:
                            selftext = selftext[:100] + "..."
                        md_lines.append(f"    - Selftext: {selftext}")
                    md_lines.append("")
    if "global_summary" in final_output:
        gs = final_output["global_summary"]
        md_lines.append("## Global Summary")
        md_lines.append(f"- **Total network retrievals:** {gs.get('global_network_retrievals', 0)}")
        md_lines.append(f"- **Total cached posts (global):** {gs.get('global_cached_posts', 0)}\n")
    md_lines.append("## Filters applied")
    for key, value in filters_applied.items():
        md_lines.append(f"- **{key}:** {value}")
    print("\n".join(md_lines))

def main():
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
        f"  {Fore.MAGENTA}--output OUTPUT{Style.RESET_ALL}      : Output format: 'json', 'report', or 'markdown' (default: json)\n"
    )
    help_epilog = f"{Fore.YELLOW}Example: ./reddit_cache.py programming arduino_ai -r flair -l 5 -L 50 -D --output markdown{Style.RESET_ALL}"
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
        "--output",
        type=str,
        choices=["json", "report", "markdown"],
        default="json",
        help=f"{Fore.MAGENTA}Output format: 'json' for JSON output, 'report' for human-readable ANSI report, 'markdown' for Markdown-formatted report (default: json){Style.RESET_ALL}"
    )
    args = parser.parse_args()

    # Gather applied filters for output.
    filters_applied = {
        "limit_report": args.limit_report if args.limit_report is not None else "None",
        "report": args.report if args.report is not None else "None",
        "show": args.show if args.show is not None else "None",
        "digest": "Enabled" if args.digest else "None",
        "output": args.output
    }

    global_network_retrievals = 0
    global_cached_posts = 0
    overall_results = {}

    for sub in tqdm(args.subreddits, desc="Processing subreddits", unit="subreddit"):
        print(f"{Fore.BLUE}Checking subreddit: {sub}{Style.RESET_ALL}", file=sys.stderr)
        posts = fetch_posts(sub)
        if posts is None or len(posts) == 0:
            print(f"{Fore.RED}Subreddit '{sub}' does not exist or returned no posts. Skipping.{Style.RESET_ALL}", file=sys.stderr)
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
            total_cached = len([f for f in os.listdir(sub) if f.endswith(".json") and f != "custom_flairs.json"])
        except Exception as e:
            print(f"{Fore.RED}Error counting cached posts in {sub}: {e}{Style.RESET_ALL}", file=sys.stderr)
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

        overall_results[sub] = sub_result
        global_network_retrievals += len(posts)
        global_cached_posts += total_cached

    if not overall_results:
        print(f"{Fore.RED}No valid subreddits were provided or found.{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(1)

    final_output = {"results": overall_results, "filters_applied": filters_applied}
    if len(args.subreddits) > 1:
        final_output["global_summary"] = {
            "global_network_retrievals": global_network_retrievals,
            "global_cached_posts": global_cached_posts
        }

    print(f"{Fore.GREEN}--- Result ---{Style.RESET_ALL}")
    print(f"{Fore.WHITE}Filters applied: {filters_applied}{Style.RESET_ALL}")
    if args.output == "json":
        print(json.dumps(final_output, indent=2))
    elif args.output == "markdown":
        print_markdown(final_output, filters_applied)
    else:
        print_human_readable(final_output, filters_applied)

if __name__ == '__main__':
    main()

