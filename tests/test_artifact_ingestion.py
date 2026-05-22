"""Tests for artifact ingestion with body size validation."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.api.server import create_app
from src.orchestrator.artifact_service import ArtifactService
from src.api.routes import MAX_ARTIFACT_SIZE


class TestArtifactIngestion:
    """Test artifact ingestion with body size validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.app = create_app()
        self.client = TestClient(self.app)
    
    def test_upload_artifact_authorized_valid_size(self):
        """Test authorized upload with valid body size."""
        response = self.client.post(
            "/api/v2/artifacts?name=test",
            content=b"small content",
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/octet-stream"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "artifact_id" in data
        assert data["status"] == "uploaded"
    
    def test_upload_artifact_unauthorized(self):
        """Test unauthorized upload returns 401."""
        response = self.client.post(
            "/api/v2/artifacts?name=test",
            content=b"small content",
            headers={"Content-Type": "application/octet-stream"}
        )
        assert response.status_code == 401
    
    def test_upload_artifact_malformed_body_size_exceeded(self):
        """Test malformed request with body size exceeding max returns 413."""
        # Create content larger than MAX_ARTIFACT_SIZE (10MB)
        large_content = b"x" * (MAX_ARTIFACT_SIZE + 1)
        response = self.client.post(
            "/api/v2/artifacts?name=test",
            content=large_content,
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/octet-stream"}
        )
        assert response.status_code == 413
        data = response.json()
        assert "Payload too large" in data["detail"]
    
    def test_update_artifact_authorized_valid_size(self):
        """Test authorized update with valid body size."""
        # First create an artifact
        create_response = self.client.post(
            "/api/v2/artifacts?name=test",
            content=b"small content",
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/octet-stream"}
        )
        artifact_id = create_response.json()["artifact_id"]
        
        # Update it
        response = self.client.put(
            f"/api/v2/artifacts/{artifact_id}?name=updated",
            content=b"updated content",
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/octet-stream"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "updated"
    
    def test_update_artifact_not_found(self):
        """Test update with non-existent artifact returns 404."""
        response = self.client.put(
            "/api/v2/artifacts/nonexistent-id?name=test",
            content=b"small content",
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/octet-stream"}
        )
        assert response.status_code == 404
    
    def test_update_artifact_body_size_exceeded(self):
        """Test update with body size exceeding max returns 413."""
        large_content = b"x" * (MAX_ARTIFACT_SIZE + 1)
        response = self.client.put(
            "/api/v2/artifacts/test-id?name=test",
            content=large_content,
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/octet-stream"}
        )
        assert response.status_code == 413
    
    def test_get_artifact_authorized(self):
        """Test authorized get artifact."""
        # First create an artifact
        create_response = self.client.post(
            "/api/v2/artifacts?name=test",
            content=b"test content",
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/octet-stream"}
        )
        artifact_id = create_response.json()["artifact_id"]
        
        # Get it
        response = self.client.get(
            f"/api/v2/artifacts/{artifact_id}",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        assert response.json()["id"] == artifact_id
    
    def test_get_artifact_not_found(self):
        """Test get non-existent artifact returns 404."""
        response = self.client.get(
            "/api/v2/artifacts/nonexistent-id",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 404
    
    def test_list_artifacts_authorized(self):
        """Test authorized list artifacts."""
        response = self.client.get(
            "/api/v2/artifacts",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        assert "artifacts" in response.json()
    
    def test_delete_artifact_authorized(self):
        """Test authorized delete artifact."""
        # First create an artifact
        create_response = self.client.post(
            "/api/v2/artifacts?name=test",
            content=b"test content",
            headers={"Authorization": "Bearer test-token", "Content-Type": "application/octet-stream"}
        )
        artifact_id = create_response.json()["artifact_id"]
        
        # Delete it
        response = self.client.delete(
            f"/api/v2/artifacts/{artifact_id}",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
    
    def test_delete_artifact_not_found(self):
        """Test delete non-existent artifact returns 404."""
        response = self.client.delete(
            "/api/v2/artifacts/nonexistent-id",
            headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 404


class TestArtifactServiceValidation:
    """Test artifact service body size validation."""
    
    def test_validate_body_size_within_limit(self):
        """Test validation passes when body size is within limit."""
        service = ArtifactService(max_body_size=100)
        is_valid, error_msg = service.validate_body_size(50)
        assert is_valid is True
        assert error_msg is None
    
    def test_validate_body_size_exceeds_limit(self):
        """Test validation fails when body size exceeds limit."""
        service = ArtifactService(max_body_size=100)
        is_valid, error_msg = service.validate_body_size(150)
        assert is_valid is False
        assert "exceeds maximum" in error_msg
    
    def test_upload_validates_before_lookup(self):
        """Test upload validates body size before performing lookup."""
        service = ArtifactService(max_body_size=10)
        
        # This should fail validation before any lookup
        with pytest.raises(ValueError, match="exceeds maximum"):
            service.upload_artifact(
                artifact_id="test-id",
                name="test",
                content=b"x" * 20,  # 20 bytes > 10 byte limit
            )
        
        # Verify no artifact was created (no mutation happened)
        assert service.get_artifact("test-id") is None
    
    def test_upload_rejects_nonexistent_artifact_id(self):
        """Test upload rejects non-existent artifact_id for update."""
        service = ArtifactService(max_body_size=100)
        
        # This should fail because artifact doesn't exist
        with pytest.raises(ValueError, match="not found"):
            service.upload_artifact(
                artifact_id="nonexistent-id",
                name="test",
                content=b"test content",
            )
    
    def test_upload_succeeds_for_existing_artifact(self):
        """Test upload succeeds for existing artifact."""
        service = ArtifactService(max_body_size=100)
        
        # Create artifact first
        artifact = service.upload_artifact(
            artifact_id=None,
            name="test",
            content=b"original",
        )
        artifact_id = artifact["id"]
        
        # Update existing artifact
        updated = service.upload_artifact(
            artifact_id=artifact_id,
            name="updated",
            content=b"updated content",
        )
        assert updated["id"] == artifact_id
        assert updated["name"] == "updated"
