#!/usr/bin/env python3
import os
import tempfile
import shutil
import unittest

# Import the functions to be tested from your reddit_cache module.
from reddit_cache import (
    remove_fenced_code,
    remove_indented_code,
    clean_text,
    is_code_line,
    has_unformatted_code,
    get_cache_folder
)

class TestRedditCache(unittest.TestCase):
    def test_remove_fenced_code(self):
        text = (
            "This is a test.\n"
            "```python\n"
            "#include <stdio.h>\n"
            "void main() {}\n"
            "```\n"
            "End of test."
        )
        expected = "This is a test.\nEnd of test."
        result = remove_fenced_code(text)
        self.assertEqual(result.strip(), expected.strip())

    def test_remove_indented_code(self):
        text = (
            "This is a test.\n"
            "    #include <stdio.h>\n"
            "    void main() {}\n"
            "End of test."
        )
        expected = "This is a test.\nEnd of test."
        result = remove_indented_code(text)
        self.assertEqual(result.strip(), expected.strip())

    def test_clean_text_removes_both(self):
        text = (
            "Intro text\n"
            "    #include <stdio.h>\n"
            "    void main() {}\n"
            "More text\n"
            "```\n"
            "def foo():\n"
            "    pass\n"
            "```\n"
            "Conclusion"
        )
        expected = "Intro text\nMore text\nConclusion"
        result = clean_text(text)
        self.assertEqual(result.strip(), expected.strip())

    def test_is_code_line_positive(self):
        # These lines should be recognized as code.
        self.assertTrue(is_code_line("#include <stdio.h>"))
        self.assertTrue(is_code_line("void main() {"))
        self.assertTrue(is_code_line("for (int i = 0; i < 10; i++) {"))
        # Test the printf pattern:
        self.assertTrue(is_code_line("printf(\"Hello\");"))

    def test_is_code_line_negative(self):
        self.assertFalse(is_code_line("This is just a regular sentence."))

    def test_has_unformatted_code_does_not_flag_properly_formatted(self):
        # Code that is properly indented should not trigger a violation.
        text = (
            "#include <stdio.h>\n"
            "void main() {\n"
            "    printf(\"Hello\");\n"  # properly indented
            "}\n"
            "Some extra text."
        )
        self.assertFalse(has_unformatted_code(text))

    def test_has_unformatted_code_flags_unformatted_code(self):
        # Block of unformatted code (no indentation or fences) should trigger a violation.
        text = (
            "#include <stdio.h>\n"
            "void main() {\n"
            "printf(\"Hello\");\n"
            "}\n"
            "Extra text here."
        )
        self.assertTrue(has_unformatted_code(text))

    def test_get_cache_folder_creates_directory(self):
        temp_dir = tempfile.mkdtemp()
        original_dir = os.getcwd()
        os.chdir(temp_dir)
        try:
            folder = get_cache_folder("testsub")
            self.assertTrue(os.path.isdir(folder))
        finally:
            os.chdir(original_dir)
            shutil.rmtree(temp_dir)

if __name__ == '__main__':
    unittest.main()

