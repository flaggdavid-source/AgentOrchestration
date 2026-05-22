"""Artifact Service - Manages artifact storage and retrieval."""

import time
import uuid
from typing import Any, Dict, Optional


class ArtifactService:
    """Service for managing artifact uploads with body size validation."""
    
    def __init__(self, max_body_size: int = 10 * 1024 * 1024):  # 10MB default
        self.max_body_size = max_body_size
        self._artifacts: Dict[str, Dict[str, Any]] = {}

    def validate_body_size(self, body_size: int) -> tuple[bool, Optional[str]]:
        """Validate body size before any processing.
        
        Returns:
            tuple: (is_valid, error_message)
        """
        if body_size > self.max_body_size:
            return False, f"Body size {body_size} exceeds maximum allowed size {self.max_body_size}"
        return True, None

    def upload_artifact(
        self,
        artifact_id: Optional[str],
        name: str,
        content: bytes,
        content_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload an artifact with body size validation.
        
        This method validates body size BEFORE any lookup or mutation.
        
        Args:
            artifact_id: Optional existing artifact ID for updates
            name: Artifact name
            content: Artifact content bytes
            content_type: Optional content type
            
        Returns:
            Dict containing artifact details
            
        Raises:
            ValueError: If body size exceeds maximum
        """
        # Validate body size BEFORE any lookup or mutation
        is_valid, error_msg = self.validate_body_size(len(content))
        if not is_valid:
            raise ValueError(error_msg)
        
        # If artifact_id provided, check if it exists (lookup)
        if artifact_id:
            existing = self._artifacts.get(artifact_id)
            if existing is None:
                raise ValueError(f"Artifact {artifact_id} not found")
        
        # Now safe to mutate
        artifact_uuid = artifact_id or str(uuid.uuid4())
        timestamp = time.time()
        
        self._artifacts[artifact_uuid] = {
            "id": artifact_uuid,
            "name": name,
            "content": content,
            "content_type": content_type or "application/octet-stream",
            "size": len(content),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        
        return self._artifacts[artifact_uuid]

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        """Get an artifact by ID."""
        return self._artifacts.get(artifact_id)

    def list_artifacts(self) -> list[Dict[str, Any]]:
        """List all artifacts."""
        return list(self._artifacts.values())

    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact by ID."""
        if artifact_id in self._artifacts:
            del self._artifacts[artifact_id]
            return True
        return False


# Global artifact service instance
artifact_service = ArtifactService()
