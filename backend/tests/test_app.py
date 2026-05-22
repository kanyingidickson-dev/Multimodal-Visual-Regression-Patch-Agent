import pytest
from fastapi.testclient import TestClient
import os
import sys

# Add backend to path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "model" in data

def test_review_endpoint_no_files():
    # Should fail if no files are uploaded
    response = client.post("/api/review", data={"context": "test"})
    assert response.status_code == 400
    assert "No files or images uploaded" in response.json()["detail"]

def test_unauthorized_access():
    # Set API_KEY temporarily to test auth
    os.environ["API_KEY"] = "test-secret"
    try:
        response = client.post("/api/review", data={"context": "test"})
        # Should fail due to missing API key
        assert response.status_code == 401
    finally:
        del os.environ["API_KEY"]

def test_serve_frontend():
    response = client.get("/")
    assert response.status_code == 200
    assert "html" in response.headers.get("content-type", "").lower()
    # Check for basic index.html elements
    assert "id=\"root\"" in response.text or "<script" in response.text

def test_serve_examples():
    response = client.get("/examples/sample-output.json")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
