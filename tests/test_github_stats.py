import unittest
from unittest.mock import AsyncMock

from github_stats import Queries, Stats


class LanguageTreeTests(unittest.IsolatedAsyncioTestCase):
    def make_stats(self, exclude_paths=None, exclude_langs=None):
        stats = Stats(
            "test-user",
            "example-token",
            session=None,
            exclude_paths=exclude_paths,
            exclude_langs=exclude_langs,
        )
        stats._languages = {}
        return stats

    async def test_language_tree_exclusions_and_extension_totals(self):
        stats = self.make_stats(
            exclude_paths={"generated/*.py", "private"},
        )
        stats.queries.query_rest = AsyncMock(
            return_value={
                "truncated": False,
                "tree": [
                    {"path": "src/main.py", "type": "blob", "size": 120},
                    {"path": "src/app.js", "type": "blob", "size": 30},
                    {"path": "node_modules/pkg/index.js", "type": "blob", "size": 900},
                    {"path": "vendor/dependency.py", "type": "blob", "size": 800},
                    {"path": "generated/output.py", "type": "blob", "size": 700},
                    {"path": "private/key.js", "type": "blob", "size": 600},
                    {"path": "notes.unknown", "type": "blob", "size": 500},
                    {"path": "src", "type": "tree"},
                ],
            }
        )

        await stats._add_repo_languages("owner/repo", "main", "main-oid", set())

        self.assertEqual(stats._languages["Python"]["size"], 120)
        self.assertEqual(stats._languages["JavaScript"]["size"], 30)
        self.assertEqual(stats._languages["Python"]["color"], "#3572A5")
        self.assertEqual(stats._languages["JavaScript"]["color"], "#f1e05a")
        stats.queries.query_rest.assert_awaited_once_with(
            "/repos/owner/repo/git/trees/main-oid", params={"recursive": "1"}
        )

    async def test_excluded_languages_are_not_counted(self):
        stats = self.make_stats(exclude_langs={"python"})
        stats.queries.query_rest = AsyncMock(
            return_value={
                "truncated": False,
                "tree": [{"path": "main.py", "type": "blob", "size": 12}],
            }
        )

        await stats._add_repo_languages("owner/repo", "main", "main-oid", {"python"})

        self.assertEqual(stats._languages, {})

    async def test_repository_present_in_both_connections_is_scanned_once(self):
        stats = self.make_stats()
        repo = {
            "nameWithOwner": "owner/repo",
            "stargazers": {"totalCount": 1},
            "forkCount": 2,
            "defaultBranchRef": {
                "name": "main",
                "target": {"oid": "main-oid"},
            },
        }
        stats.queries.query = AsyncMock(
            return_value={
                "data": {
                    "viewer": {
                        "login": "test-user",
                        "repositories": {
                            "nodes": [repo],
                            "pageInfo": {"hasNextPage": False},
                        },
                        "repositoriesContributedTo": {
                            "nodes": [repo],
                            "pageInfo": {"hasNextPage": False},
                        },
                    }
                }
            }
        )
        stats.queries.query_rest = AsyncMock(
            return_value={
                "truncated": False,
                "tree": [{"path": "main.py", "type": "blob", "size": 10}],
            }
        )

        await stats.get_stats()

        self.assertEqual(stats._repos, {"owner/repo"})
        self.assertEqual(stats._languages["Python"]["prop"], 100)
        stats.queries.query_rest.assert_awaited_once()

    async def test_repository_query_does_not_exclusively_filter_public_repositories(self):
        query = Queries.repos_overview()

        self.assertNotIn("isPublic: PUBLIC", query)
        self.assertNotIn("is: PUBLIC", query)

    async def test_graphql_query_uses_the_supplied_access_token(self):
        class FakeResponse:
            async def json(self):
                return {"data": {}}

        class FakeSession:
            def __init__(self):
                self.headers = None

            async def post(self, url, headers, json):
                self.headers = headers
                return FakeResponse()

        session = FakeSession()
        queries = Queries("test-user", "example-token", session)

        await queries.query("query { viewer { login } }")

        self.assertEqual(
            session.headers["Authorization"], "bearer example-token"
        )

    async def test_truncated_tree_fails_instead_of_returning_partial_totals(self):
        stats = self.make_stats()
        stats.queries.query_rest = AsyncMock(
            return_value={
                "truncated": True,
                "tree": [{"path": "main.py", "type": "blob", "size": 10}],
            }
        )

        with self.assertRaisesRegex(RuntimeError, "truncated"):
            await stats._add_repo_languages("owner/repo", "main", "main-oid", set())

        self.assertEqual(stats._languages, {})


if __name__ == "__main__":
    unittest.main()
