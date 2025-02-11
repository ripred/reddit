[![Python Tests and Coverage](https://github.com/ripred/reddit/actions/workflows/python-app.yml/badge.svg)](https://github.com/ripred/reddit/actions/workflows/python-app.yml)

# Reddit Cache Utility for Moderators

## Version Information

**Current Version: `reddit_cache_v2.py`**  
This version uses the [PRAW (Python Reddit API Wrapper)](https://praw.readthedocs.io/) for robust, authenticated interactions with Reddit's API. It offers improved reliability, reduced network calls (by caching data locally), and additional features such as interactive code formatting checks and multiple output formats (JSON, ANSI-colored report, Markdown).

**Legacy Version: `reddit_cache.py` (Deprecated)**  
The old version of this tool (using direct HTTP requests via `requests`) is still available for backward compatibility but is now deprecated. We recommend using the new version for a better, more feature-rich experience.

## Getting Started: Creating a Reddit App and Generating Keys

To use `reddit_cache_v2.py`, you must supply Reddit API credentials. Follow these steps to create a Reddit app and obtain the required keys:

1. **Sign in to your Reddit account.**

2. **Visit the Reddit App Preferences page:**  
   Go to [https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps).

3. **Create a New App:**  
   - Scroll down to the **Developed Applications** section.  
   - Click the **"Create App"** or **"Create Another App"** button.
   
4. **Fill in the Application Details:**  
   - **Name:** Give your app a descriptive name (e.g., "Reddit Cache Utility").
   - **App type:** Select **"script"** (this is recommended for personal use and for command-line utilities).
   - **Description:** (Optional) Provide a brief description.
   - **Redirect URI:** You can enter a placeholder such as `http://localhost:8080` (this is required but not used by the script).
   - **Other fields:** Leave other fields as default unless instructed otherwise.

5. **Save the Application:**  
   After creating the app, you will see a new app entry under your Developed Applications.

6. **Obtain Your Credentials:**  
   - **Client ID:** This is the string just under the app name (a 14-character alphanumeric string).
   - **Client Secret:** This is the secret key provided for the app.
   - **User Agent:** Create a user agent string (e.g., `"reddit_cache_v2 script by /u/yourusername"`). This is used to identify your application in API requests.

7. **Set Up Your Environment:**  
   You can provide these credentials to the script via a `praw.ini` file or by setting environment variables:
   
   - **Using Environment Variables:**  
     ```bash
     export REDDIT_CLIENT_ID=<your_client_id>
     export REDDIT_CLIENT_SECRET=<your_client_secret>
     export REDDIT_USER_AGENT="reddit_cache_v2 script by /u/yourusername"
     ```
     
   - **Using a `praw.ini` File:**  
     Create a file named `praw.ini` in your project directory with the following content:
     ```ini
     [DEFAULT]
     client_id=<your_client_id>
     client_secret=<your_client_secret>
     user_agent=reddit_cache_v2 script by /u/yourusername
     ```

Once your credentials are set up, `reddit_cache_v2.py` will be able to authenticate with Reddit and retrieve posts as expected.

## Overview

The **Reddit Cache Utility** is a command-line tool designed to help moderators quickly fetch, cache, and analyze the latest posts from one or more subreddits. The tool minimizes network traffic by caching posts locally and provides various reports and an interactive code formatting check to help you easily identify posts that may need further review or formatting corrections.

## Features

- **Caching:**  
  Retrieves and caches the latest 100 posts from a subreddit. On subsequent runs, only new posts are fetched to reduce network calls.

- **Flair Reports:**  
  Generate reports summarizing unique flair counts from cached posts.

- **Show Posts:**  
  Display detailed information (title, author, full selftext, and flair) for a specified number of cached posts.

- **Monthly Digest:**  
  Automatically compile a digest from posts with titles containing "Monthly Digest" (including a header, narrative summary, and list of digest posts).

- **Interactive Code Format Check:**  
  Scans cached posts for unformatted source code (e.g., Arduino/C/C++ code that isn’t properly fenced or indented). When a violation is detected, the full, untruncated post body is printed for review, and you are prompted to flag, skip, or cancel further checks.
  
- **ANSI Colored Output:**  
  The output is colorized using ANSI escape sequences for clarity:
  - **Blue:** Subreddit names  
  - **Green:** Summary statistics  
  - **Magenta:** Report headers  
  - **Yellow:** Warnings and applied filters

*Note: The screenshot below is a simulated representation of the expected ANSI-colored terminal output.*

![ANSI Output Screenshot](https://via.placeholder.com/800x200?text=ANSI+Colored+Output+Screenshot)

## Usage

Run the utility from the command line using the new version:

```bash
./reddit_cache_v2.py --help
```

The help output is as follows:

```
usage: reddit_cache_v2.py [-h] [-r {flair}] [-l N] [-L M] [-D] [--check-code-format]
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

Example: ./reddit_cache_v2.py arduino arduino_ai --check-code-format --output report
```

### How It Works

1. **Caching:**  
   The tool checks the local `caches/` folder for stored post data. If data exists, only new posts are fetched from Reddit.

2. **Reporting:**  
   Based on the provided options, the utility generates various reports (flair, show posts, monthly digest) using cached data, reducing redundant network calls.

3. **Interactive Code Check:**  
   When the `--check-code-format` flag is used, the utility scans each post’s selftext (after unescaping HTML entities) for blocks of 3+ consecutive non-empty lines that resemble code (ignoring properly formatted code blocks). If a violation is found, the complete post body is printed for review, and you are prompted to flag, skip, or cancel further checks.

4. **ANSI Colors:**  
   Output is colorized using ANSI escape sequences to improve readability (e.g., summary stats in green, report headers in magenta).

## Example Use Cases

Below are some usage examples using the new version:

```bash
# 1. Fetch and cache posts from the default subreddit (r/arduino)
$ ./reddit_cache_v2.py
--- Result ---
Filters applied: {'limit_report': 'None', 'report': 'None', 'show': 'None', 'digest': 'None', 'check_code_format': 'None', 'output': 'json'}
[ANSI-colored output showing summary stats for 100 posts fetched from r/arduino]

# 2. Generate a flair report for r/arduino (using cached data)
$ ./reddit_cache_v2.py arduino -r flair
--- Result ---
Filters applied: {'limit_report': 'None', 'report': 'flair', 'show': 'None', 'digest': 'None', 'check_code_format': 'None', 'output': 'json'}
[ANSI-colored output: flair report in magenta, with flair counts]

# 3. Show detailed information for the last 5 cached posts from r/programming
$ ./reddit_cache_v2.py programming -l 5
--- Result ---
Filters applied: {'limit_report': 'None', 'report': 'None', 'show': 5, 'digest': 'None', 'check_code_format': 'None', 'output': 'json'}
[ANSI-colored output: Detailed info (title, author, selftext, flair) for 5 posts]

# 4. Generate a Monthly Digest report for r/arduino in Markdown format
$ ./reddit_cache_v2.py arduino -D --output markdown
--- Result ---
Filters applied: {'limit_report': 'None', 'report': 'None', 'show': 'None', 'digest': 'Enabled', 'check_code_format': 'None', 'output': 'markdown'}
[Markdown output: Monthly Digest report with header, narrative, and digest posts]

# 5. Interactively check for unformatted code in r/ripred
$ ./reddit_cache_v2.py ripred --check-code-format --output report
Processing subreddits: [ANSI progress bar]
Potential Code Format Violation Detected:
Post ID: abc123
Title: "Test Post # 1 – Should FAIL Formatting Check"
Author: ripred3
Complete Selftext:
[Full, untruncated post body with improperly formatted source code]
Does this post contain unformatted code? (y/n/s/c):
[Interactive prompt with ANSI-colored text]
```

## Quick Command Examples

```bash
# Fetch posts from r/arduino (default)
$ ./reddit_cache_v2.py

# Generate a flair report for r/arduino
$ ./reddit_cache_v2.py arduino -r flair

# Show detailed info for the last 5 posts from r/programming
$ ./reddit_cache_v2.py programming -l 5

# Generate a Monthly Digest report for r/arduino in Markdown format
$ ./reddit_cache_v2.py arduino -D --output markdown

# Interactively check for unformatted code in r/ripred
$ ./reddit_cache_v2.py ripred --check-code-format --output report
```

## Additional Notes

- **Non-interactive Mode:**  
  For automated testing, set the environment variable `TEST_NONINTERACTIVE=1` to simulate an automatic "y" response during code format checks.

- **ANSI Color Output:**  
  The utility’s output is colorized using ANSI escape sequences for enhanced readability in the terminal.

- **Deprecated Legacy Version:**  
  The legacy version (`reddit_cache.py`) is still available but is now deprecated. It uses direct HTTP requests via `requests` and is maintained only for backward compatibility. We recommend using `reddit_cache_v2.py` for a more robust and feature-rich experience.

- **Reddit API Credentials:**  
  To use `reddit_cache_v2.py`, you must create a Reddit app and obtain your API credentials:
  1. Sign in to your Reddit account.
  2. Go to [https://www.reddit.com/prefs/apps](https://www.reddit.com/prefs/apps).
  3. Click **"Create App"** or **"Create Another App"**.
  4. Fill in the details:
     - **Name:** (e.g., "Reddit Cache Utility")
     - **App type:** Select **"script"**.
     - **Redirect URI:** Use a placeholder like `http://localhost:8080`.
  5. Save your app.
  6. Note your **Client ID** (displayed under your app name) and **Client Secret**.
  7. Set these as environment variables or in a `praw.ini` file:
     - Environment variables:
       ```bash
       export REDDIT_CLIENT_ID=<your_client_id>
       export REDDIT_CLIENT_SECRET=<your_client_secret>
       export REDDIT_USER_AGENT="reddit_cache_v2 script by /u/yourusername"
       ```
     - Or create a `praw.ini` file with:
       ```ini
       [DEFAULT]
       client_id=<your_client_id>
       client_secret=<your_client_secret>
       user_agent=reddit_cache_v2 script by /u/yourusername
       ```

- **Feedback and Contributions:**  
  Please test the utility on your subreddits and share any issues or feature suggestions. Your feedback is highly appreciated!
