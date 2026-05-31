from fastapi.testclient import TestClient

from main import app


def test_robots_txt_returns_plain_text_policy():
    response = TestClient(app).get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "User-agent: *" in response.text
    assert "Allow: /" in response.text
    assert "Sitemap: https://tagparking.co.uk/sitemap.xml" in response.text
