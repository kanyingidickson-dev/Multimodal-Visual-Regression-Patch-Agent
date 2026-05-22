import pytest
from fastapi.testclient import TestClient
import os
import sys

# Add root directory to path so we can import api.index
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Ensure MOCK_MODE is set before importing so GemmaClient doesn't raise
os.environ.setdefault("MOCK_MODE", "true")

from api.index import app

client = TestClient(app)

def test_api_index_health_check():
    """GET /api/health should return 200 with status:healthy"""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "model" in data
    assert "mock_mode" in data

def test_api_index_review_endpoint_no_files():
    """POST /api/review with no files should return 400"""
    response = client.post("/api/review", data={"context": "test"})
    assert response.status_code == 400
    assert "No files or images uploaded" in response.json()["detail"]

def test_api_index_review_endpoint_with_file():
    """POST /api/review with a code file in MOCK_MODE should return 200 with analysis"""
    import io
    file_content = b"def add(a, b):\n    return a + b\n"
    file_obj = io.BytesIO(file_content)
    files = {"files": ("add.py", file_obj, "text/x-python")}

    response = client.post("/api/review", files=files, data={"context": "Check for bugs"})
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "root_cause" in data
    assert "fix_plan" in data
    assert "patch" in data
    assert "confidence" in data

def test_api_index_old_routes_return_404():
    """Routes without /api prefix should NOT exist (would cause Vercel path mismatch)"""
    assert client.get("/health").status_code == 404
    assert client.post("/review").status_code in (404, 405)
