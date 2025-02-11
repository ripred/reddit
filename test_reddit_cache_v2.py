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

# Import functions from reddit_cache_v2.py
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
)

# Dummy classes for simulating PRAW submissions and conversations.
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
        # Create a temporary directory and switch to it so that "caches" is created here.
        self.original_dir = os.getcwd()
        self.temp_dir = tempfile.mkdtemp()
        os.chdir(self.temp_dir)

    def tearDown(self):
        # Return to the original directory and remove the temporary one.
        os.chdir(self.original_dir)
        shutil.rmtree(self.temp_dir)

    def test_get_cache_folder(self):
        folder = get_cache_folder("testsub")
        self.assertTrue(os.path.isdir(folder))
        self.assertIn("caches", folder)
        self.assertIn("testsub", folder)

    def test_get_config_and_save_config(self):
        # Ensure the caches folder exists
        os.makedirs("caches", exist_ok=True)
        # When no app.ini exists, get_config should create a default "CodeFormat" section.
        config, config_path = get_config()
        self.assertIn("CodeFormat", config)
        # Modify the config and save it.
        config["CodeFormat"]["dummy"] = "value"
        save_config(config, config_path)
        # Now read the file back.
        new_config = configparser.ConfigParser()
        new_config.read(config_path)
        self.assertIn("dummy", new_config["CodeFormat"])
        self.assertEqual(new_config["CodeFormat"]["dummy"], "value")

    def test_load_cached_posts(self):
        # Create a cache folder for a test subreddit and write some JSON files.
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
        # Should be sorted by created_utc descending.
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0]["id"], "b")
        self.assertEqual(loaded[1]["id"], "a")
        self.assertEqual(loaded[2]["id"], "c")

    def test_submission_to_dict(self):
        # Create a dummy submission.
        author = DummyAuthor("dummy_user")
        submission = DummySubmission(
            id="xyz",
            title="Test Submission",
            author=author,
            created_utc=1234567890,
            selftext="Submission text",
            link_flair_text="Flair"
        )
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
        # Test with no author.
        submission.author = None
        result = submission_to_dict(submission)
        self.assertEqual(result["author"], "None")

    @patch("reddit_cache_v2.reddit")
    def test_fetch_posts(self, mock_reddit):
        # Create dummy submissions.
        dummy_sub1 = DummySubmission("id1", "Title 1", DummyAuthor("user1"), 111, "Text 1", "News")
        dummy_sub2 = DummySubmission("id2", "Title 2", DummyAuthor("user2"), 222, "Text 2", None)
        # Simulate reddit.subreddit(...).new(limit=100) returns an iterable.
        fake_subreddit = MagicMock()
        fake_subreddit.new.return_value = [dummy_sub1, dummy_sub2]
        mock_reddit.subreddit.return_value = fake_subreddit

        posts = fetch_posts("testsub")
        self.assertIsNotNone(posts)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["id"], "id1")
        self.assertEqual(posts[1]["link_flair_text"], None)

    def test_cache_post(self):
        # Create a dummy post_data.
        post_data = {"id": "abc123", "title": "Test Post", "created_utc": 123, "selftext": "Some text", "author": "user", "link_flair_text": "Info"}
        # Ensure the cache folder is created.
        folder = get_cache_folder("testsub")
        filename = os.path.join(folder, "abc123.json")
        # First call should create the file and mark as new.
        cached, is_new = cache_post("testsub", post_data)
        self.assertTrue(is_new)
        self.assertTrue(os.path.exists(filename))
        # Call again; should return existing data.
        cached2, is_new2 = cache_post("testsub", post_data)
        self.assertFalse(is_new2)

    @patch("reddit_cache_v2.reddit")
    def test_fetch_modqueue_count(self, mock_reddit):
        # Simulate modqueue returning a list.
        fake_subreddit = MagicMock()
        fake_mod = MagicMock()
        fake_mod.modqueue.return_value = [1, 2, 3]
        fake_subreddit.mod = fake_mod
        mock_reddit.subreddit.return_value = fake_subreddit

        count = fetch_modqueue_count("testsub")
        self.assertEqual(count, 3)

    @patch("reddit_cache_v2.reddit")
    def test_fetch_modmail_count(self, mock_reddit):
        # Simulate modmail conversations with various states.
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

    def test_generate_flair_report(self):
        # Create cache files with various flairs.
        folder = get_cache_folder("testsub")
        posts = [
            {"id": "1", "created_utc": 100, "link_flair_text": "News", "title": "A", "selftext": "", "author": "a"},
            {"id": "2", "created_utc": 200, "link_flair_text": None, "title": "B", "selftext": "", "author": "b"},
            {"id": "3", "created_utc": 300, "link_flair_text": "News", "title": "C", "selftext": "", "author": "c"},
        ]
        for post in posts:
            filename = os.path.join(folder, f"{post['id']}.json")
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(post, f)
        report = generate_flair_report("testsub")
        self.assertEqual(report.get("News"), 2)
        self.assertEqual(report.get("None"), 1)

    def test_generate_show_report(self):
        # Create cache files.
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
        self.assertEqual(show[0]["title"], "Post2")  # because posts are sorted descending

    def test_generate_monthly_digest_report(self):
        # Create cache files with and without "Monthly Digest" in title.
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
        # Only two posts should be in the digest.
        self.assertEqual(len(digest["digest_posts"]), 2)

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
        # Test text that should be flagged using #include lines.
        text = (
            "#include <stdio.h>\n"
            "#include <stdlib.h>\n"
            "#include <string.h>\n"
            "Some extra text."
        )
        self.assertTrue(has_unformatted_code(text))
        # Test text that should not be flagged (properly formatted code blocks removed).
        text2 = (
            "```cpp\n"
            "#include <stdio.h>\n"
            "#include <stdlib.h>\n"
            "#include <string.h>\n"
            "```\n"
            "Some explanation."
        )
        self.assertFalse(has_unformatted_code(text2))

    def test_print_markdown(self):
        # Prepare a minimal final_output dictionary.
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
            }
        }
        filters_applied = {"output": "markdown", "limit_report": "None"}
        captured_output = StringIO()
        sys.stdout = captured_output
        print_markdown(final_output, filters_applied)
        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()
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
            }
        }
        filters_applied = {"output": "report", "limit_report": "None"}
        captured_output = StringIO()
        sys.stdout = captured_output
        print_human_readable(final_output, filters_applied)
        sys.stdout = sys.__stdout__
        output = captured_output.getvalue()
        self.assertIn("Subreddit: testsub", output)
        self.assertIn("Total posts checked: 5", output)
        self.assertIn("Update: 3", output)

    def test_check_code_format_violations(self):
        # Create a cache file that contains unformatted code.
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
        # Ensure configuration file does not have this post flagged.
        config_path = os.path.join("caches", "app.ini")
        if os.path.exists(config_path):
            os.remove(config_path)
        # Set TEST_NONINTERACTIVE so that the response is automatically "y".
        os.environ["TEST_NONINTERACTIVE"] = "1"
        # Capture printed output.
        captured_output = StringIO()
        sys.stdout = captured_output
        violations = check_code_format_violations("testsub")
        sys.stdout = sys.__stdout__
        # Remove the environment variable for cleanliness.
        del os.environ["TEST_NONINTERACTIVE"]
        # Check that the violation is returned.
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["id"], "violation1")
        # Also, the configuration file should now record that violation.
        config = configparser.ConfigParser()
        config.read(config_path)
        self.assertEqual(config["CodeFormat"].get("violation1"), "flagged")

if __name__ == '__main__':
    unittest.main()

