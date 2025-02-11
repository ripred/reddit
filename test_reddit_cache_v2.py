#!/usr/bin/env python3
import os
import sys
import tempfile
import shutil
import json
import unittest
from unittest.mock import patch, MagicMock
from io import StringIO
import configparser
import re
import logging

# Import functions (including main) from reddit_cache_v2.py
from reddit_cache_v2 import (
    get_cache_folder,
    get_config,
    save_config,
    load_cached_posts,
    submission_to_dict,
    fetch_posts,
    cache_post,
    fetch_modqueue_count,
    fetch_modmail_count,
    generate_flair_report,
    generate_show_report,
    generate_monthly_digest_report,
    remove_fenced_code,
    remove_indented_code,
    remove_inline_code,
    clean_text,
    is_code_line,
    has_unformatted_code,
    print_markdown,
    print_human_readable,
    check_code_format_violations,
    main
)

# Dummy classes to simulate PRAW objects.
class DummyAuthor:
    def __init__(self, name):
        self.name = name

class DummySubmission:
    def __init__(self, id, title, author, created_utc, selftext, link_flair_text):
        self.id = id
        self.title = title
        self.author = author
        self.created_utc = created_utc
        self.selftext = selftext
        self.link_flair_text = link_flair_text

class DummyConversation:
    def __init__(self, state):
        self.state = state

class TestRedditCacheV2(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory and switch to it so that the "caches" folder is isolated.
        self.original_dir = os.getcwd()
        self.temp_dir = tempfile.mkdtemp()
        os.chdir(self.temp_dir)
        # Silence logging (and tqdm) output to avoid polluting captured stdout.
        logging.getLogger().setLevel(logging.CRITICAL)

    def tearDown(self):
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir)

    # --- Tests for File/Configuration Helpers ---
    def test_get_cache_folder(self):
        folder = get_cache_folder("testsub")
        self.assertTrue(os.path.isdir(folder))
        self.assertIn("caches", folder)
        self.assertIn("testsub", folder)

    def test_get_config_and_save_config(self):
        os.makedirs("caches", exist_ok=True)
        config, config_path = get_config()
        self.assertIn("CodeFormat", config)
        config["CodeFormat"]["dummy"] = "value"
        save_config(config, config_path)
        new_config = configparser.ConfigParser()
        new_config.read(config_path)
        self.assertIn("dummy", new_config["CodeFormat"])
        self.assertEqual(new_config["CodeFormat"]["dummy"], "value")

    def test_load_cached_posts(self):
        folder = get_cache_folder("testsub")
        posts = [
            {"id": "a", "created_utc": 200, "link_flair_text": "News", "title": "Post A", "selftext": "Text A", "author": "userA"},
            {"id": "b", "created_utc": 300, "link_flair_text": None, "title": "Post B", "selftext": "Text B", "author": "userB"},
            {"id": "c", "created_utc": 100, "link_flair_text": "Update", "title": "Post C", "selftext": "Text C", "author": "userC"},
        ]
        for post in posts:
            filename = os.path.join(folder, f"{post['id']}.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(post, f)
        loaded = load_cached_posts("testsub")
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0]["id"], "b")
        self.assertEqual(loaded[1]["id"], "a")
        self.assertEqual(loaded[2]["id"], "c")

    # --- Tests for PRAW API Wrappers & Caching ---
    def test_submission_to_dict(self):
        author = DummyAuthor("dummy_user")
        submission = DummySubmission("xyz", "Test Submission", author, 1234567890, "Submission text", "Flair")
        result = submission_to_dict(submission)
        expected = {
            "id": "xyz",
            "title": "Test Submission",
            "author": "dummy_user",
            "created_utc": 1234567890,
            "selftext": "Submission text",
            "link_flair_text": "Flair"
        }
        self.assertEqual(result, expected)
        submission.author = None
        result = submission_to_dict(submission)
        self.assertEqual(result["author"], "None")

    @patch("reddit_cache_v2.reddit")
    def test_fetch_posts(self, mock_reddit):
        dummy_sub1 = DummySubmission("id1", "Title 1", DummyAuthor("user1"), 111, "Text 1", "News")
        dummy_sub2 = DummySubmission("id2", "Title 2", DummyAuthor("user2"), 222, "Text 2", None)
        fake_subreddit = MagicMock()
        fake_subreddit.new.return_value = [dummy_sub1, dummy_sub2]
        mock_reddit.subreddit.return_value = fake_subreddit
        posts = fetch_posts("testsub")
        self.assertIsNotNone(posts)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["id"], "id1")
        self.assertIsNone(posts[1]["link_flair_text"])

    def test_cache_post(self):
        post_data = {"id": "abc123", "title": "Test Post", "created_utc": 123, "selftext": "Some text", "author": "user", "link_flair_text": "Info"}
        folder = get_cache_folder("testsub")
        filename = os.path.join(folder, "abc123.json")
        cached, is_new = cache_post("testsub", post_data)
        self.assertTrue(is_new)
        self.assertTrue(os.path.exists(filename))
        cached2, is_new2 = cache_post("testsub", post_data)
        self.assertFalse(is_new2)

    @patch("reddit_cache_v2.reddit")
    def test_fetch_modqueue_count(self, mock_reddit):
        fake_subreddit = MagicMock()
        fake_mod = MagicMock()
        fake_mod.modqueue.return_value = [1, 2, 3]
        fake_subreddit.mod = fake_mod
        mock_reddit.subreddit.return_value = fake_subreddit
        count = fetch_modqueue_count("testsub")
        self.assertEqual(count, 3)

    @patch("reddit_cache_v2.reddit")
    def test_fetch_modmail_count(self, mock_reddit):
        conv1 = DummyConversation("new")
        conv2 = DummyConversation("read")
        conv3 = DummyConversation("new")
        fake_subreddit = MagicMock()
        fake_modmail = MagicMock()
        fake_modmail.conversations.return_value = [conv1, conv2, conv3]
        fake_subreddit.modmail = fake_modmail
        mock_reddit.subreddit.return_value = fake_subreddit
        count = fetch_modmail_count("testsub")
        self.assertEqual(count, 2)

    # --- Tests for Report Generation ---
    def test_generate_flair_report(self):
        folder = get_cache_folder("testsub")
        posts = [
            {"id": "1", "created_utc": 100, "link_flair_text": "News", "title": "A", "selftext": "", "author": "a"},
            {"id": "2", "created_utc": 200, "link_flair_text": None, "title": "B", "selftext": "", "author": "b"},
            {"id": "3", "created_utc": 300, "link_flair_text": "News", "title": "C", "selftext": "", "author": "c"},
        ]
        for post in posts:
            filename = os.path.join(get_cache_folder("testsub"), f"{post['id']}.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(post, f)
        report = generate_flair_report("testsub")
        self.assertEqual(report.get("News"), 2)
        self.assertEqual(report.get("None"), 1)

    def test_generate_show_report(self):
        folder = get_cache_folder("testsub")
        posts = [
            {"id": "1", "created_utc": 100, "link_flair_text": "News", "title": "Post1", "selftext": "Text1", "author": "a"},
            {"id": "2", "created_utc": 200, "link_flair_text": "Update", "title": "Post2", "selftext": "Text2", "author": "b"},
        ]
        for post in posts:
            filename = os.path.join(folder, f"{post['id']}.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(post, f)
        show = generate_show_report("testsub", 1)
        self.assertEqual(len(show), 1)
        self.assertEqual(show[0]["title"], "Post2")

    def test_generate_monthly_digest_report(self):
        folder = get_cache_folder("testsub")
        posts = [
            {"id": "1", "created_utc": 100, "link_flair_text": "News", "title": "Monthly Digest - January", "selftext": "Digest1", "author": "a"},
            {"id": "2", "created_utc": 200, "link_flair_text": "Update", "title": "Random Post", "selftext": "Not a digest", "author": "b"},
            {"id": "3", "created_utc": 300, "link_flair_text": "News", "title": "Monthly Digest - February", "selftext": "Digest2", "author": "c"},
        ]
        for post in posts:
            filename = os.path.join(folder, f"{post['id']}.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(post, f)
        digest = generate_monthly_digest_report("testsub", digest_pattern="Monthly Digest")
        self.assertIn("header", digest)
        self.assertIn("digest_posts", digest)
        self.assertEqual(len(digest["digest_posts"]), 2)

    # --- Tests for Code Formatting Helpers ---
    def test_remove_fenced_code(self):
        text = (
            "Line 1\n"
            "```python\n"
            "code line\n"
            "another code line\n"
            "```\n"
            "Line 2"
        )
        result = remove_fenced_code(text)
        self.assertNotIn("code line", result)
        self.assertIn("Line 1", result)
        self.assertIn("Line 2", result)

    def test_remove_indented_code(self):
        text = (
            "Line 1\n"
            "    indented code\n"
            "Line 2"
        )
        result = remove_indented_code(text)
        self.assertNotIn("indented code", result)
        self.assertIn("Line 1", result)
        self.assertIn("Line 2", result)

    def test_remove_inline_code(self):
        text = "This is a `code snippet` in a sentence."
        result = remove_inline_code(text)
        self.assertNotIn("code snippet", result)
        self.assertIn("This is a", result)

    def test_clean_text(self):
        text = (
            "Intro\n"
            "    indented code\n"
            "```lang\n"
            "fenced code\n"
            "```\n"
            "Some `inline code` here\n"
            "Conclusion"
        )
        result = clean_text(text)
        self.assertIn("Intro", result)
        self.assertIn("Conclusion", result)
        self.assertNotIn("indented code", result)
        self.assertNotIn("fenced code", result)
        self.assertNotIn("inline code", result)

    def test_is_code_line(self):
        self.assertTrue(is_code_line("#include <stdio.h>"))
        self.assertTrue(is_code_line("void main() {"))
        self.assertTrue(is_code_line("for (int i = 0; i < 10; i++) {"))
        self.assertFalse(is_code_line("This is not code."))

    def test_has_unformatted_code(self):
        text = (
            "#include <stdio.h>\n"
            "#include <stdlib.h>\n"
            "#include <string.h>\n"
            "Some extra text."
        )
        self.assertTrue(has_unformatted_code(text))
        text2 = (
            "```cpp\n"
            "#include <stdio.h>\n"
            "#include <stdlib.h>\n"
            "#include <string.h>\n"
            "```\n"
            "Some explanation."
        )
        self.assertFalse(has_unformatted_code(text2))

    # --- Tests for Output Functions ---
    def test_print_markdown(self):
        final_output = {
            "results": {
                "testsub": {
                    "summary": {"total_posts_checked": 10, "new_posts_retrieved": 2},
                    "report": {
                        "flair_summary": {"News": 5, "None": 5},
                        "show_posts": [
                            {"title": "Post1", "author": "a", "flair": "News", "selftext": "Text1"}
                        ]
                    }
                }
            },
            "filters_applied": {"output": "markdown", "limit_report": "None"}
        }
        captured = StringIO()
        sys.stdout = captured
        print_markdown(final_output, final_output["filters_applied"])
        sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("## Subreddit: testsub", output)
        self.assertIn("**Total posts checked:** 10", output)
        self.assertIn("**Post 1:**", output)

    def test_print_human_readable(self):
        final_output = {
            "results": {
                "testsub": {
                    "summary": {"total_posts_checked": 5, "new_posts_retrieved": 1},
                    "report": {
                        "flair_summary": {"Update": 3, "None": 2},
                    }
                }
            },
            "filters_applied": {"output": "report", "limit_report": "None"}
        }
        captured = StringIO()
        sys.stdout = captured
        print_human_readable(final_output, final_output["filters_applied"])
        sys.stdout = sys.__stdout__
        output = captured.getvalue()
        self.assertIn("Subreddit: testsub", output)
        self.assertIn("Total posts checked: 5", output)
        self.assertIn("Update: 3", output)

    # --- Tests for Code Formatting Check ---
    def test_check_code_format_violations(self):
        folder = get_cache_folder("testsub")
        post = {
            "id": "violation1",
            "created_utc": 123,
            "link_flair_text": "Code",
            "title": "Test violation",
            "selftext": (
                "printf(\"Hello\");\n"
                "printf(\"World\");\n"
                "printf(\"!\");\n"
                "Some explanation."
            ),
            "author": "user"
        }
        filename = os.path.join(folder, "violation1.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(post, f)
        config_path = os.path.join("caches", "app.ini")
        if os.path.exists(config_path):
            os.remove(config_path)
        os.environ["TEST_NONINTERACTIVE"] = "1"
        captured = StringIO()
        sys.stdout = captured
        with patch("reddit_cache_v2.fetch_posts", return_value=[post]):
            violations = check_code_format_violations("testsub")
        sys.stdout = sys.__stdout__
        del os.environ["TEST_NONINTERACTIVE"]
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["id"], "violation1")
        config = configparser.ConfigParser()
        config.read(config_path)
        self.assertEqual(config["CodeFormat"].get("violation1"), "flagged")

    # --- Tests for the Main Function ---
    def test_main_json_output(self):
        dummy_post = {
            "id": "post1",
            "title": "Dummy Post",
            "author": "tester",
            "created_utc": 1000,
            "selftext": "Dummy text",
            "link_flair_text": "Test"
        }
        with patch("reddit_cache_v2.fetch_posts", return_value=[dummy_post]), \
             patch("reddit_cache_v2.cache_post", side_effect=lambda sub, post: (post, True)), \
             patch("reddit_cache_v2.fetch_modqueue_count", return_value=5), \
             patch("reddit_cache_v2.fetch_modmail_count", return_value=3), \
             patch("reddit_cache_v2.tqdm", lambda x, **kwargs: x):
            test_args = ["reddit_cache_v2.py", "testsub", "--output", "json"]
            with patch.object(sys, 'argv', test_args):
                captured = StringIO()
                sys.stdout = captured
                main()
                sys.stdout = sys.__stdout__
                output = captured.getvalue()
                # Extract JSON block starting from the first line where left-stripped text begins with "{"
                lines = output.splitlines()
                json_lines = []
                started = False
                for line in lines:
                    if not started and line.lstrip().startswith('{'):
                        started = True
                    if started:
                        json_lines.append(line)
                if not json_lines:
                    self.fail("JSON output not found in captured output")
                output_json = "\n".join(json_lines)
                # Remove ANSI escape sequences.
                ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
                output_json = ansi_escape.sub('', output_json)
                try:
                    data = json.loads(output_json)
                except Exception as e:
                    self.fail(f"Output is not valid JSON: {e}")
                self.assertIn("results", data)
                self.assertIn("testsub", data["results"])

    def test_main_markdown_output(self):
        dummy_post = {
            "id": "post1",
            "title": "Dummy Post",
            "author": "tester",
            "created_utc": 1000,
            "selftext": "Dummy text",
            "link_flair_text": "Test"
        }
        with patch("reddit_cache_v2.fetch_posts", return_value=[dummy_post]), \
             patch("reddit_cache_v2.cache_post", side_effect=lambda sub, post: (post, True)), \
             patch("reddit_cache_v2.tqdm", lambda x, **kwargs: x):
            test_args = ["reddit_cache_v2.py", "testsub", "--output", "markdown"]
            with patch.object(sys, 'argv', test_args):
                captured = StringIO()
                sys.stdout = captured
                main()
                sys.stdout = sys.__stdout__
                output = captured.getvalue()
                self.assertIn("## Subreddit: testsub", output)

    def test_main_interactive_check_code(self):
        folder = get_cache_folder("testsub")
        post = {
            "id": "post2",
            "title": "Interactive Test",
            "author": "tester",
            "created_utc": 2000,
            "selftext": (
                "printf(\"Line1\");\n"
                "printf(\"Line2\");\n"
                "printf(\"Line3\");\n"
                "Extra text."
            ),
            "link_flair_text": "Code"
        }
        filename = os.path.join(folder, "post2.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(post, f)
        config_path = os.path.join("caches", "app.ini")
        if os.path.exists(config_path):
            os.remove(config_path)
        with patch("reddit_cache_v2.fetch_posts", return_value=[post]), \
             patch("builtins.input", return_value="n"), \
             patch("reddit_cache_v2.tqdm", lambda x, **kwargs: x):
            test_args = ["reddit_cache_v2.py", "testsub", "--check-code-format", "--output", "json"]
            with patch.object(sys, 'argv', test_args):
                captured = StringIO()
                sys.stdout = captured
                main()
                sys.stdout = sys.__stdout__
        config = configparser.ConfigParser()
        config.read(config_path)
        self.assertEqual(config["CodeFormat"].get("post2"), "n")

    def test_main_no_valid_subreddits(self):
        with patch("reddit_cache_v2.fetch_posts", return_value=[]), \
             patch("reddit_cache_v2.tqdm", lambda x, **kwargs: x):
            test_args = ["reddit_cache_v2.py", "nosub"]
            with patch.object(sys, 'argv', test_args):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)

    def test_main_modqueue_modmail(self):
        dummy_post = {
            "id": "post3",
            "title": "Mod Test",
            "author": "tester",
            "created_utc": 3000,
            "selftext": "Some text",
            "link_flair_text": "Info"
        }
        with patch("reddit_cache_v2.fetch_posts", return_value=[dummy_post]), \
             patch("reddit_cache_v2.cache_post", side_effect=lambda sub, post: (post, True)), \
             patch("reddit_cache_v2.fetch_modqueue_count", return_value=7), \
             patch("reddit_cache_v2.fetch_modmail_count", return_value=4), \
             patch("reddit_cache_v2.tqdm", lambda x, **kwargs: x):
            test_args = ["reddit_cache_v2.py", "testsub", "--modqueue", "--modmail", "--output", "json"]
            with patch.object(sys, 'argv', test_args):
                captured = StringIO()
                sys.stdout = captured
                main()
                sys.stdout = sys.__stdout__
                output = captured.getvalue()
                # Extract JSON block starting from first line where left-stripped text begins with "{"
                lines = output.splitlines()
                json_lines = []
                started = False
                for line in lines:
                    if not started and line.lstrip().startswith('{'):
                        started = True
                    if started:
                        json_lines.append(line)
                if not json_lines:
                    self.fail("JSON output not found in captured output")
                output_json = "\n".join(json_lines)
                ansi_escape = re.compile(r'\x1B[@-_][0-?]*[ -/]*[@-~]')
                output_json = ansi_escape.sub('', output_json)
                try:
                    data = json.loads(output_json)
                except Exception as e:
                    self.fail(f"Output is not valid JSON: {e}")
                result = data["results"]["testsub"]
                self.assertEqual(result.get("modqueue_count"), 7)
                self.assertEqual(result.get("modmail_count"), 4)

    def test_main_report_flair(self):
        folder = get_cache_folder("testsub")
        post = {
            "id": "post4",
            "title": "Flair Test",
            "author": "tester",
            "created_utc": 4000,
            "selftext": "Text",
            "link_flair_text": "News"
        }
        filename = os.path.join(folder, "post4.json")
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(post, f)
        with patch("reddit_cache_v2.fetch_posts", return_value=[post]), \
             patch("reddit_cache_v2.tqdm", lambda x, **kwargs: x):
            test_args = ["reddit_cache_v2.py", "testsub", "-r", "flair", "--output", "report"]
            with patch.object(sys, 'argv', test_args):
                captured = StringIO()
                sys.stdout = captured
                try:
                    main()
                except SystemExit:
                    pass
                sys.stdout = sys.__stdout__
                output = captured.getvalue()
                self.assertIn("Flair Report", output)
                self.assertIn("News: 1", output)

if __name__ == '__main__':
    unittest.main()

