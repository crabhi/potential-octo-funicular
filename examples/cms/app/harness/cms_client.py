"""Thin HTTP client for the demo CMS server, shared by the test modules.

Points at CMS_BASE_URL (default http://127.0.0.1:3100). No mocks: every
call in the test suite is a real HTTP request against a really running
axum process.
"""
import os

import requests

BASE_URL = os.environ.get("CMS_BASE_URL", "http://127.0.0.1:3100")

USERS = ["alice", "bob", "eve", "root"]
ROLE_OF = {"alice": "author", "bob": "author", "eve": "editor", "root": "admin"}
ARTICLE_IDS = [1, 2, 3, 4]  # published, draft, in_review, archived (seeded)
STATE_OF = {1: "published", 2: "draft", 3: "in_review", 4: "archived"}


def login(user: str) -> str:
    r = requests.post(f"{BASE_URL}/login", json={"user": user}, timeout=5)
    r.raise_for_status()
    return r.json()["token"]


def get_article(article_id: int, token: str | None = None):
    params = {"token": token} if token else {}
    return requests.get(f"{BASE_URL}/articles/{article_id}", params=params, timeout=5)


def create_article(token: str, title="t", body="b"):
    return requests.post(
        f"{BASE_URL}/articles",
        json={"title": title, "body": body},
        headers={"Authorization": f"Bearer {token}"},
        timeout=5,
    )


def edit_article(article_id: int, token: str, title=None, body=None):
    payload = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    return requests.put(
        f"{BASE_URL}/articles/{article_id}",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=5,
    )


def submit_article(article_id: int, token: str):
    return requests.post(
        f"{BASE_URL}/articles/{article_id}/submit",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5,
    )


def publish_article(article_id: int, token: str):
    return requests.post(
        f"{BASE_URL}/articles/{article_id}/publish",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5,
    )


def deactivate(user: str, admin_token: str):
    return requests.post(
        f"{BASE_URL}/admin/deactivate/{user}",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=5,
    )


def demote(user: str, admin_token: str):
    return requests.post(
        f"{BASE_URL}/admin/demote/{user}",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=5,
    )


def health() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False


def violated_rule(response) -> str | None:
    """Return the inv_* rule name a 403 response names, else None."""
    if response.status_code != 403:
        return None
    try:
        return response.json().get("error")
    except ValueError:
        return None
