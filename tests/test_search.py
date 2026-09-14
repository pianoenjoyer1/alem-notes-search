import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

from search import Passage, SearchIndex, read_passages, tokenize
from server import make_handler


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.index = SearchIndex([Passage("a.md", 1, "retrieval context search"),
                                  Passage("b.md", 3, "Python tests"),
                                  Passage("c.md", 5, "Деректер сапасы")])

    def test_expected_source_ranks_first(self):
        self.assertEqual(self.index.search("retrieval search")[0]["source"], "a.md")

    def test_unicode_and_case(self):
        self.assertEqual(self.index.search("ДЕРЕКТЕР")[0]["source"], "c.md")
        self.assertEqual(tokenize("Ｃａｆｅ́"), ["café"])

    def test_empty_and_unknown_queries(self):
        for query in ["", "!!!", "astronaut"]:
            self.assertEqual(self.index.search(query), [])

    def test_empty_index(self):
        self.assertEqual(SearchIndex([]).search("test"), [])

    def test_query_constraints(self):
        for limit in [0, 51, -1]:
            with self.assertRaises(ValueError):
                self.index.search("tests", limit)
        with self.assertRaises(ValueError):
            self.index.search("x" * 1001)

    def test_cosine_bounds_and_limit(self):
        hits = self.index.search("retrieval tests", 1)
        self.assertEqual(len(hits), 1)
        self.assertTrue(0 < hits[0]["score"] <= 1)

    def test_sources_and_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "note.md").write_text("first\nline\n\nsecond", encoding="utf-8")
            Path(folder, "skip.py").write_text("ignored")
            passages = read_passages(folder)
            self.assertEqual([(p.line, p.text) for p in passages], [(1, "first line"), (4, "second")])

    def test_invalid_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                read_passages(Path(folder, "missing"))

    def test_http_api_and_no_arbitrary_file_access(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.index))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:{}".format(server.server_port)
        try:
            with urlopen(base + "/api/search?q=retrieval", timeout=3) as response:
                self.assertEqual(json.load(response)["hits"][0]["source"], "a.md")
            with urlopen(base, timeout=3) as response:
                self.assertIn(b"ALEM / NOTES", response.read())
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "/search.py", timeout=3)
            self.assertEqual(error.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
