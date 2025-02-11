[![Python Tests and Coverage](https://github.com/ripred/reddit/actions/workflows/python-app.yml/badge.svg)](https://github.com/ripred/reddit/actions/workflows/python-app.yml)

# Reddit Cache Utility for Moderators

## Overview

The **Reddit Cache Utility** is a command-line tool designed to help moderators quickly fetch, cache, and analyze the latest posts from one or more subreddits. The tool minimizes network traffic by caching posts locally and provides various reports and an interactive code formatting check. This helps moderators easily identify posts that may need further review or formatting corrections.

## Features

- **Caching:**  
  Retrieves and caches the latest 100 posts from a subreddit. On subsequent runs, only new posts are fetched to reduce network calls.

- **Flair Reports:**  
  Generate reports that summarize unique flair counts from cached posts.

- **Show Posts:**  
  Display detailed information (title, author, full selftext, and flair) for a specified number of cached posts.

- **Monthly Digest:**  
  Automatically compile a digest from posts with titles containing "Monthly Digest" that includes a header, narrative summary, and a list of digest posts.

- **Interactive Code Format Check:**  
  Scans cached posts for unformatted source code (e.g., Arduino/C/C++ code that isn’t properly fenced or indented). If a violation is detected, the complete, untruncated post body is printed, and you are prompted to flag, skip, or cancel further checks.  
  *Tip: For automated testing, set the environment variable `TEST_NONINTERACTIVE=1` to simulate an automatic "y" response.*

- **ANSI Colored Output:**  
  The utility uses ANSI color codes to make the output more readable. For example:
  - **Blue:** Subreddit names
  - **Green:** Summary statistics
  - **Magenta:** Report headers
  - **Yellow:** Warnings and applied filters

*Note: The screenshot below simulates the expected colorized output in a terminal.*

![ANSI Output Screenshot](https://via.placeholder.com/800x200?text=ANSI+Colored+Output+Screenshot)

## Usage

Run the utility from the command line. Below is the basic help output:

```
./reddit_cache.py --help
usage: reddit_cache.py [-h] [-r {flair}] [-l N] [-L M] [-D] [--check-code-format]
                       [--output {json,report,markdown}] [subreddits ...]

Fetch and cache the newest 100 posts from one or more subreddits, displaying only new posts
       and summary stats.
If multiple subreddits are specified, a global summary is also provided.

Positional arguments:
  subreddits            One or more subreddit names to fetch posts from (default: arduino).

Optional arguments:
  -h, --help            show this help message and exit
  -r {flair}, --report {flair}
                        Generate a report. Available option: flair
  -l N, --show N        Show title, selftext, author, and flair for the last N cached posts
  -L M, --limit-report M
                        Limit the number of cached posts scanned for reports to M posts (default:
                        no limit)
  -D, --digest          Include a Monthly Digest report section (scans cached posts with titles containing
                        'Monthly Digest')
  --check-code-format   Check cached posts for code formatting violations interactively
  --output {json,report,markdown}
                        Output format: 'json' for JSON output, 'report' for human-readable ANSI report,
                        'markdown' for Markdown-formatted report (default: json)

Example: ./reddit_cache.py arduino arduino_ai --check-code-format --output report
```

### How It Works

1. **Caching:**  
   The tool checks the local `caches/` folder for stored post data. If found, it only fetches new posts from Reddit to reduce redundant network calls.

2. **Reporting:**  
   Based on the options provided, the utility generates various reports (flair, show posts, monthly digest) using the local cache. This helps minimize network usage and speeds up data processing.

3. **Interactive Code Check:**  
   When the `--check-code-format` flag is used, the utility scans each post’s selftext (after unescaping HTML entities) for blocks of 3 or more consecutive non-empty lines that appear to be code (ignoring properly formatted code blocks). If a violation is detected, the complete post body is printed for review, and you are prompted to flag, skip, or cancel the check.

4. **ANSI Colored Output:**  
   The output is colorized using ANSI escape sequences. For example, subreddit names appear in blue, summary statistics in green, and report headers in magenta. This makes the terminal output easier to read.

## Example Use Cases

Below are some common usage examples. These examples simulate a bash session with example (colorized) outputs.

```bash
# 1. Fetch and cache posts from the default subreddit (r/arduino)
$ ./reddit_cache.py
--- Result ---
Filters applied: {'limit_report': 'None', 'report': 'None', 'show': 'None', 'digest': 'None', 'check_code_format': 'None', 'output': 'json'}
[ANSI output with summary stats in green and white, showing 100 posts fetched from r/arduino]

# 2. Generate a flair report for r/arduino (using cached data)
$ ./reddit_cache.py arduino -r flair
--- Result ---
Filters applied: {'limit_report': 'None', 'report': 'flair', 'show': 'None', 'digest': 'None', 'check_code_format': 'None', 'output': 'json'}
[ANSI output: flair report in magenta, showing counts for each flair]

# 3. Display detailed information for the last 5 cached posts from r/programming
$ ./reddit_cache.py programming -l 5
--- Result ---
Filters applied: {'limit_report': 'None', 'report': 'None', 'show': 5, 'digest': 'None', 'check_code_format': 'None', 'output': 'json'}
[ANSI output: Detailed information for 5 posts including title, author, full selftext, and flair]

# 4. Generate a Monthly Digest report for r/arduino in Markdown format
$ ./reddit_cache.py arduino -D --output markdown
--- Result ---
Filters applied: {'limit_report': 'None', 'report': 'None', 'show': 'None', 'digest': 'Enabled', 'check_code_format': 'None', 'output': 'markdown'}
[Markdown output: Monthly Digest report with headers, narrative, and digest posts]

# 5. Interactively check for unformatted code in r/ripred
$ ./reddit_cache.py ripred --check-code-format --output report
Processing subreddits: [ANSI progress bar]
Potential Code Format Violation Detected:
Post ID: abc123
Title: "Test Post # 1 – Should FAIL Formatting Check"
Author: ripred3
Complete Selftext:
[Full, untruncated post body with improperly formatted source code]
Does this post contain unformatted code? (y/n/s/c): 
[Interactive prompt with ANSI colored text]
```

## Quick Commands

```bash
# Fetch posts from r/arduino (default)
$ ./reddit_cache.py

# Generate a flair report for r/arduino
$ ./reddit_cache.py arduino -r flair

# Show detailed info for the last 5 posts from r/programming
$ ./reddit_cache.py programming -l 5

# Generate a Monthly Digest report for r/arduino in Markdown
$ ./reddit_cache.py arduino -D --output markdown

# Interactively check for unformatted code in r/ripred
$ ./reddit_cache.py ripred --check-code-format --output report
```

## Additional Notes

- **Non-interactive Mode:**  
  For automated testing, set the environment variable `TEST_NONINTERACTIVE=1` to simulate an automatic "y" response during code format checks.

- **ANSI Color Output:**  
  The tool's output is colorized using ANSI escape sequences for improved readability in the terminal.

- **Feedback and Contributions:**  
  Please test the utility with your subreddits and let us know if you encounter any issues or have suggestions for new features. Your feedback is welcome!
