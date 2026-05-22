from fastapi.testclient import TestClient
from weather_server import app

client = TestClient(app)

def test_cors_headers_allowed_origin():
    response = client.options("/api/weather", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

def test_cors_headers_disallowed_origin():
    response = client.options("/api/weather", headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "GET"})
    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None # origin is not in the allowed list
