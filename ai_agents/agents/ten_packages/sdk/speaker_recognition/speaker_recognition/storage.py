#
# MongoDB storage backend for speaker recognition
#

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field

from speaker_recognition.config import MongoDBConfig

logger = logging.getLogger(__name__)


class SpeakerProfile(BaseModel):
    """Speaker profile data model."""

    speaker_id: str = Field(alias="_id")
    speaker_name: str
    embedding: List[float]  # 192-dim embedding vector
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class SpeakerStorage:
    """MongoDB storage for speaker profiles."""

    def __init__(self, config: Optional[MongoDBConfig] = None):
        """
        Initialize MongoDB storage.

        Args:
            config: MongoDB configuration
        """
        self.config = config or MongoDBConfig()
        self.client = None
        self.db = None
        self.collection = None
        self._connect()

    def _connect(self):
        """Establish MongoDB connection."""
        try:
            from pymongo import MongoClient
            from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

            self.client = MongoClient(
                self.config.uri,
                serverSelectionTimeoutMS=self.config.timeout_ms,
            )

            # Test connection
            self.client.admin.command("ping")

            self.db = self.client[self.config.database]
            self.collection = self.db[self.config.collection]

            # Create indexes
            self._create_indexes()

            logger.info(
                f"Connected to MongoDB: {self.config.database}.{self.config.collection}"
            )

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
        except ImportError as e:
            raise ImportError(
                "pymongo is not installed. Please install it with: pip install pymongo"
            ) from e

    def _create_indexes(self):
        """Create database indexes for performance."""
        try:
            # Create unique index on speaker_id
            self.collection.create_index("_id", unique=True)

            # Create index on speaker_name for lookups
            self.collection.create_index("speaker_name")

            # Create index on created_at for sorting
            self.collection.create_index("created_at", -1)

            logger.debug("MongoDB indexes created")

        except Exception as e:
            logger.warning(f"Failed to create indexes: {e}")

    def register_speaker(
        self,
        speaker_id: str,
        speaker_name: str,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SpeakerProfile:
        """
        Register a new speaker.

        Args:
            speaker_id: Unique speaker ID
            speaker_name: Speaker display name
            embedding: 192-dim embedding vector
            metadata: Optional metadata dictionary

        Returns:
            SpeakerProfile

        Raises:
            ValueError: If speaker_id already exists
        """
        # Check if speaker already exists
        if self.collection.find_one({"_id": speaker_id}):
            raise ValueError(f"Speaker with ID '{speaker_id}' already exists")

        now = datetime.utcnow()

        document = {
            "_id": speaker_id,
            "speaker_name": speaker_name,
            "embedding": embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
        }

        try:
            self.collection.insert_one(document)
            logger.info(f"Registered speaker: {speaker_id} ({speaker_name})")
            return SpeakerProfile(**document)

        except Exception as e:
            logger.error(f"Failed to register speaker: {e}")
            raise

    def get_speaker(self, speaker_id: str) -> Optional[SpeakerProfile]:
        """
        Get speaker profile by ID.

        Args:
            speaker_id: Speaker ID

        Returns:
            SpeakerProfile or None if not found
        """
        doc = self.collection.find_one({"_id": speaker_id})
        if doc:
            return SpeakerProfile(**doc)
        return None

    def get_speaker_by_name(self, speaker_name: str) -> List[SpeakerProfile]:
        """
        Get speakers by name (may return multiple).

        Args:
            speaker_name: Speaker name to search for

        Returns:
            List of SpeakerProfile objects
        """
        docs = self.collection.find({"speaker_name": speaker_name})
        return [SpeakerProfile(**doc) for doc in docs]

    def update_embedding(
        self,
        speaker_id: str,
        embedding: np.ndarray,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Update speaker embedding (for re-enrollment).

        Args:
            speaker_id: Speaker ID
            embedding: New 192-dim embedding vector
            metadata: Optional metadata to update

        Returns:
            True if updated, False if speaker not found
        """
        update_doc = {
            "embedding": embedding.tolist() if isinstance(embedding, np.ndarray) else embedding,
            "updated_at": datetime.utcnow(),
        }

        if metadata:
            update_doc["metadata"] = metadata

        result = self.collection.update_one(
            {"_id": speaker_id}, {"$set": update_doc}
        )

        if result.modified_count > 0:
            logger.info(f"Updated embedding for speaker: {speaker_id}")
            return True

        return False

    def delete_speaker(self, speaker_id: str) -> bool:
        """
        Delete speaker profile.

        Args:
            speaker_id: Speaker ID to delete

        Returns:
            True if deleted, False if not found
        """
        result = self.collection.delete_one({"_id": speaker_id})

        if result.deleted_count > 0:
            logger.info(f"Deleted speaker: {speaker_id}")
            return True

        return False

    def list_speakers(
        self, skip: int = 0, limit: int = 100, sort_by: str = "created_at"
    ) -> List[SpeakerProfile]:
        """
        List all speakers with pagination.

        Args:
            skip: Number of documents to skip
            limit: Maximum number of documents to return
            sort_by: Field to sort by (default: created_at)

        Returns:
            List of SpeakerProfile objects
        """
        sort_order = -1 if sort_by == "created_at" else 1

        docs = (
            self.collection.find()
            .sort(sort_by, sort_order)
            .skip(skip)
            .limit(limit)
        )

        return [SpeakerProfile(**doc) for doc in docs]

    def count_speakers(self) -> int:
        """
        Get total count of registered speakers.

        Returns:
            Number of speakers
        """
        return self.collection.count_documents({})

    def get_all_embeddings(self) -> Dict[str, tuple]:
        """
        Get all speaker embeddings for batch matching.

        Returns:
            Dictionary mapping speaker_id to (speaker_name, embedding_array)
        """
        docs = self.collection.find({}, {"_id": 1, "speaker_name": 1, "embedding": 1})

        result = {}
        for doc in docs:
            speaker_id = doc["_id"]
            speaker_name = doc["speaker_name"]
            embedding = np.array(doc["embedding"], dtype=np.float32)
            result[speaker_id] = (speaker_name, embedding)

        return result

    def search_by_metadata(
        self, metadata_query: Dict[str, Any], skip: int = 0, limit: int = 100
    ) -> List[SpeakerProfile]:
        """
        Search speakers by metadata.

        Args:
            metadata_query: Metadata key-value pairs to match
            skip: Number of documents to skip
            limit: Maximum number of documents to return

        Returns:
            List of matching SpeakerProfile objects
        """
        query = {f"metadata.{k}": v for k, v in metadata_query.items()}

        docs = self.collection.find(query).skip(skip).limit(limit)

        return [SpeakerProfile(**doc) for doc in docs]

    def speaker_exists(self, speaker_id: str) -> bool:
        """
        Check if speaker exists.

        Args:
            speaker_id: Speaker ID to check

        Returns:
            True if speaker exists
        """
        return self.collection.find_one({"_id": speaker_id}) is not None

    def close(self):
        """Close database connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def create_storage(
    uri: Optional[str] = None,
    database: Optional[str] = None,
    collection: Optional[str] = None,
) -> SpeakerStorage:
    """
    Convenience function to create speaker storage.

    Args:
        uri: MongoDB connection URI
        database: Database name
        collection: Collection name

    Returns:
        SpeakerStorage instance
    """
    config = MongoDBConfig(
        uri=uri or MongoDBConfig.__fields__["uri"].default,
        database=database or MongoDBConfig.__fields__["database"].default,
        collection=collection or MongoDBConfig.__fields__["collection"].default,
    )
    return SpeakerStorage(config)
