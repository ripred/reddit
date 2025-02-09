#!/usr/bin/env python3

"""
test_reddit_cache.py

Unit tests for reddit_cache.py

This file tests the following functions:
  - fetch_posts: Verifies correct behavior when a successful API response is simulated.
  - cache_post: Checks that a post is cached on first call and that subsequent calls detect the cached file.
  - generate_flair_report: Creates dummy cached files and verifies that the flair report reflects the known flairs.
  - generate_show_report: Creates dummy cached files and verifies that the report returns the expected number of posts.
  - generate_monthly_digest_report: Creates dummy cached files (one of which has a title matching the digest pattern)
      and verifies that the digest report picks it up.

Run these tests using a command like:
    python -m unittest test_reddit_cache.py
"""

import os
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Import the functions to test from reddit_cache.py.
# It is assumed that reddit_cache.py and test_reddit_cache.py are in the same directory.
from reddit_cache import (
    fetch_posts,
    cache_post,
    generate_flair_report,
    generate_show_report,
    generate_monthly_digest_report
)

class TestRedditCache(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory and switch into it to simulate a clean environment.
        self.temp_dir = tempfile.TemporaryDirectory()
        self.orig_cwd = os.getcwd()
        os.chdir(self.temp_dir.name)
        # Create sample post data.
        self.post_data_1 = {
            "id": "test1",
            "title": "Test Post 1",
            "selftext": "Content of test post 1",
            "author": "user1",
            "link_flair_text": "Flair1",
            "created_utc": 1000
        }
        self.post_data_2 = {
            "id": "test2",
            "title": "Monthly Digest: January 2024",
            "selftext": "Digest content for January 2024",
            "author": "user2",
            "link_flair_text": "Digest",
            "created_utc": 2000
        }

    def tearDown(self):
        # Return to original working directory and clean up temporary directory.
        os.chdir(self.orig_cwd)
        self.temp_dir.cleanup()

    @patch('reddit_cache.requests.get')
    def test_fetch_posts_success(self, mock_get):
        # Simulate a successful API call with two posts.
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "data": {
                "children": [{"data": self.post_data_1}, {"data": self.post_data_2}]
            }
        }
        mock_get.return_value = fake_response

        posts = fetch_posts("testsub")
        self.assertIsNotNone(posts)
        self.assertEqual(len(posts), 2)
        # Check that the first post's id matches.
        self.assertEqual(posts[0]["data"]["id"], "test1")

    def test_cache_post_creates_file(self):
        # Test that cache_post creates a file and returns is_new True on first call.
        subreddit = "testsub"
        data, is_new = cache_post(subreddit, self.post_data_1)
        self.assertTrue(is_new)
        # Check that file exists.
        filename = os.path.join(subreddit, "test1.json")
        self.assertTrue(os.path.exists(filename))
        # Calling cache_post again should return is_new as False.
        data2, is_new2 = cache_post(subreddit, self.post_data_1)
        self.assertFalse(is_new2)

    def test_generate_flair_report(self):
        # Create a temporary subreddit folder with two cached posts.
        subreddit = "testsub"
        os.makedirs(subreddit, exist_ok=True)
        with open(os.path.join(subreddit, "test1.json"), "w", encoding="utf-8") as f:
            json.dump(self.post_data_1, f, indent=2)
        with open(os.path.join(subreddit, "test2.json"), "w", encoding="utf-8") as f:
            json.dump(self.post_data_2, f, indent=2)
        report = generate_flair_report(subreddit)
        self.assertIn("Flair1", report)
        self.assertIn("Digest", report)
        self.assertEqual(report["Flair1"], 1)
        self.assertEqual(report["Digest"], 1)

    def test_generate_show_report(self):
        # Create a temporary subreddit folder with two cached posts.
        subreddit = "testsub"
        os.makedirs(subreddit, exist_ok=True)
        with open(os.path.join(subreddit, "test1.json"), "w", encoding="utf-8") as f:
            json.dump(self.post_data_1, f, indent=2)
        with open(os.path.join(subreddit, "test2.json"), "w", encoding="utf-8") as f:
            json.dump(self.post_data_2, f, indent=2)
        report = generate_show_report(subreddit, 2)
        self.assertEqual(len(report), 2)
        # Since the posts are sorted by created_utc descending, the first post should be post_data_2.
        self.assertEqual(report[0]["title"], self.post_data_2["title"])

    def test_generate_monthly_digest_report(self):
        # Create a temporary subreddit folder with two cached posts, one of which is a digest.
        subreddit = "testsub"
        os.makedirs(subreddit, exist_ok=True)
        with open(os.path.join(subreddit, "test1.json"), "w", encoding="utf-8") as f:
            json.dump(self.post_data_1, f, indent=2)
        with open(os.path.join(subreddit, "test2.json"), "w", encoding="utf-8") as f:
            json.dump(self.post_data_2, f, indent=2)
        digest_report = generate_monthly_digest_report(subreddit, digest_pattern="Monthly Digest", limit=2)
        # Check that a digest report is produced.
        self.assertIn("header", digest_report)
        self.assertIn("narrative", digest_report)
        self.assertIn("digest_posts", digest_report)
        self.assertEqual(len(digest_report["digest_posts"]), 1)

if __name__ == '__main__':
    unittest.main()

