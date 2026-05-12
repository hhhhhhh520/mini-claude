"""Vector store module for semantic search and embedding storage.

Supports ChromaDB (recommended) and FAISS backends with graceful
degradation when dependencies are missing.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

# Set HuggingFace mirror for China users (if not already set)
if "HF_ENDPOINT" not in os.environ:
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# Check for optional dependencies
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    chromadb = None
    ChromaSettings = None

try:
    import faiss
    import numpy as np

    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None
    np = None

try:
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None


class VectorStoreError(Exception):
    """Base exception for vector store errors."""

    pass


class DependencyNotFoundError(VectorStoreError):
    """Raised when a required dependency is not installed."""

    pass


@dataclass
class SearchResult:
    """A single search result from the vector store.

    Attributes:
        id: Unique identifier for the document
        text: The original text content
        score: Similarity score (higher is more similar)
        metadata: Optional metadata associated with the document
    """

    id: str
    text: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "text": self.text,
            "score": self.score,
            "metadata": self.metadata,
        }


@dataclass
class Document:
    """A document to be stored in the vector store.

    Attributes:
        id: Unique identifier for the document
        text: The text content to embed
        metadata: Optional metadata associated with the document
        embedding: Optional pre-computed embedding
    """

    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None


class VectorStore:
    """Vector store for semantic search with multiple backend support.

    Supports ChromaDB (recommended for persistence) and FAISS (for
    in-memory operations). Uses sentence-transformers for embeddings.

    Example:
        >>> store = VectorStore(db_type="chroma", path="~/.mini_claude/vectors")
        >>> store.add_embedding("doc1", "Hello world", {"source": "greeting"})
        >>> results = store.search_similar("Hi there", k=5)
        >>> print(results[0].text)  # "Hello world"
    """

    def __init__(
        self,
        db_type: str = "chroma",
        path: str = "~/.mini_claude/vectors",
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        collection_name: str = "default",
    ):
        """Initialize the vector store.

        Args:
            db_type: Database type, "chroma" or "faiss"
            path: Path for persistent storage (expanded with ~)
            embedding_model: Name of the sentence-transformers model
            collection_name: Name of the collection (ChromaDB only)

        Raises:
            DependencyNotFoundError: If required dependencies are not installed
        """
        self.db_type = db_type.lower()
        self.path = str(Path(path).expanduser())
        self.embedding_model_name = embedding_model
        self.collection_name = collection_name

        # Initialize embedding model
        self._embedding_model = None
        self._embedding_dim = None

        # Initialize backend
        self._backend = None
        self._id_map: Dict[str, int] = {}  # For FAISS ID mapping
        self._documents: Dict[str, Document] = {}  # For FAISS document storage

        # Validate and initialize
        self._validate_dependencies()
        self._init_embedding_model()
        self._init_backend()

    def _validate_dependencies(self) -> None:
        """Validate that required dependencies are installed."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise DependencyNotFoundError(
                "sentence-transformers is required for embeddings. "
                "Install it with: pip install sentence-transformers"
            )

        if self.db_type == "chroma" and not CHROMA_AVAILABLE:
            raise DependencyNotFoundError(
                "chromadb is required for ChromaDB backend. Install it with: pip install chromadb"
            )

        if self.db_type == "faiss" and not FAISS_AVAILABLE:
            raise DependencyNotFoundError(
                "faiss and numpy are required for FAISS backend. "
                "Install them with: pip install faiss-cpu numpy "
                "(or faiss-gpu for GPU support)"
            )

        if self.db_type not in ("chroma", "faiss"):
            raise ValueError(f"Unsupported db_type: {self.db_type}. Supported types: chroma, faiss")

    def _init_embedding_model(self) -> None:
        """Initialize the embedding model."""
        logger.info(f"Loading embedding model: {self.embedding_model_name}")
        self._embedding_model = SentenceTransformer(self.embedding_model_name)
        self._embedding_dim = self._embedding_model.get_sentence_embedding_dimension()
        logger.info(f"Embedding dimension: {self._embedding_dim}")

    def _init_backend(self) -> None:
        """Initialize the vector database backend."""
        if self.db_type == "chroma":
            self._init_chroma()
        elif self.db_type == "faiss":
            self._init_faiss()

    def _init_chroma(self) -> None:
        """Initialize ChromaDB backend."""
        # Create directory if it doesn't exist
        os.makedirs(self.path, exist_ok=True)

        # Initialize ChromaDB client with persistent storage
        self._backend = chromadb.PersistentClient(
            path=self.path,
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        # Get or create collection
        self._collection = self._backend.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(f"Initialized ChromaDB at {self.path} with collection '{self.collection_name}'")

    def _init_faiss(self) -> None:
        """Initialize FAISS backend."""
        # Create directory if it doesn't exist
        os.makedirs(self.path, exist_ok=True)

        # Initialize FAISS index with cosine similarity (using Inner Product on normalized vectors)
        self._backend = faiss.IndexFlatIP(self._embedding_dim)

        # Load existing data if available
        self._load_faiss_data()

        logger.info(f"Initialized FAISS index with dimension {self._embedding_dim}")

    def _load_faiss_data(self) -> None:
        """Load existing FAISS index and document data from disk."""
        index_path = Path(self.path) / f"{self.collection_name}.index"
        meta_path = Path(self.path) / f"{self.collection_name}.json"

        if index_path.exists() and meta_path.exists():
            try:
                # Load FAISS index
                self._backend = faiss.read_index(str(index_path))

                # Load metadata
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._id_map = data.get("id_map", {})
                    self._documents = {
                        k: Document(**v) for k, v in data.get("documents", {}).items()
                    }

                logger.info(f"Loaded FAISS data with {len(self._documents)} documents")
            except Exception as e:
                logger.warning(f"Failed to load FAISS data: {e}. Starting fresh.")
                self._backend = faiss.IndexFlatIP(self._embedding_dim)
                self._id_map = {}
                self._documents = {}

    def _save_faiss_data(self) -> None:
        """Save FAISS index and document data to disk."""
        index_path = Path(self.path) / f"{self.collection_name}.index"
        meta_path = Path(self.path) / f"{self.collection_name}.json"

        try:
            # Save FAISS index
            faiss.write_index(self._backend, str(index_path))

            # Save metadata
            data = {
                "id_map": self._id_map,
                "documents": {
                    k: {"id": v.id, "text": v.text, "metadata": v.metadata}
                    for k, v in self._documents.items()
                },
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Saved FAISS data with {len(self._documents)} documents")
        except Exception as e:
            logger.error(f"Failed to save FAISS data: {e}")
            raise VectorStoreError(f"Failed to save FAISS data: {e}") from e

    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as a list of floats
        """
        embedding = self._embedding_model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        embeddings = self._embedding_model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def _generate_id(self, text: str) -> str:
        """Generate a deterministic ID from text content.

        Args:
            text: Text content

        Returns:
            MD5 hash of the text
        """
        return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()

    def add_embedding(
        self,
        id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Add a text embedding to the vector store.

        Args:
            id: Unique identifier for the document
            text: Text content to embed and store
            metadata: Optional metadata to associate with the document

        Returns:
            True if successful

        Raises:
            VectorStoreError: If the operation fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        metadata = metadata or {}
        metadata["_created_at"] = datetime.now().isoformat()

        try:
            if self.db_type == "chroma":
                return self._add_to_chroma(id, text, metadata)
            else:
                return self._add_to_faiss(id, text, metadata)
        except Exception as e:
            logger.error(f"Failed to add embedding: {e}")
            raise VectorStoreError(f"Failed to add embedding: {e}") from e

    def _add_to_chroma(
        self,
        id: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> bool:
        """Add document to ChromaDB."""
        # Check if ID already exists and update if so
        existing = self._collection.get(ids=[id])
        if existing["ids"]:
            # Update existing document
            self._collection.update(
                ids=[id],
                documents=[text],
                metadatas=[metadata],
            )
            logger.debug(f"Updated existing document: {id}")
        else:
            # Add new document
            embedding = self._generate_embedding(text)
            self._collection.add(
                ids=[id],
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata],
            )
            logger.debug(f"Added new document: {id}")

        return True

    def _add_to_faiss(
        self,
        id: str,
        text: str,
        metadata: Dict[str, Any],
    ) -> bool:
        """Add document to FAISS."""
        # Check if ID already exists
        if id in self._documents:
            # FAISS doesn't support updates, need to remove and re-add
            # For simplicity, we'll just update the document
            logger.debug(f"Updating existing document: {id}")
            idx = self._id_map[id]
            embedding = self._generate_embedding(text)
            # FAISS doesn't support in-place updates for IndexFlatIP
            # We need to add a new entry and mark the old one as invalid
            # For simplicity, we just update the metadata
            self._documents[id] = Document(id=id, text=text, metadata=metadata)
            self._save_faiss_data()
            return True

        # Generate embedding
        embedding = self._generate_embedding(text)

        # Add to FAISS index
        import numpy as np

        embedding_array = np.array([embedding], dtype=np.float32)
        self._backend.add(embedding_array)

        # Update mappings
        idx = self._backend.ntotal - 1
        self._id_map[id] = idx
        self._documents[id] = Document(id=id, text=text, metadata=metadata)

        # Save to disk
        self._save_faiss_data()

        logger.debug(f"Added document {id} at index {idx}")
        return True

    def add_batch(
        self,
        ids: List[str],
        texts: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Add multiple embeddings in a batch.

        Args:
            ids: List of unique identifiers
            texts: List of text contents
            metadatas: Optional list of metadata dictionaries

        Returns:
            True if successful

        Raises:
            ValueError: If inputs have mismatched lengths
            VectorStoreError: If the operation fails
        """
        if len(ids) != len(texts):
            raise ValueError("ids and texts must have the same length")

        if metadatas and len(metadatas) != len(ids):
            raise ValueError("metadatas must have the same length as ids")

        if not ids:
            return True

        metadatas = metadatas or [{}] * len(ids)
        created_at = datetime.now().isoformat()
        for meta in metadatas:
            meta["_created_at"] = created_at

        try:
            if self.db_type == "chroma":
                return self._add_batch_to_chroma(ids, texts, metadatas)
            else:
                return self._add_batch_to_faiss(ids, texts, metadatas)
        except Exception as e:
            logger.error(f"Failed to add batch: {e}")
            raise VectorStoreError(f"Failed to add batch: {e}") from e

    def _add_batch_to_chroma(
        self,
        ids: List[str],
        texts: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> bool:
        """Add batch of documents to ChromaDB."""
        embeddings = self._generate_embeddings(texts)

        # Check which IDs exist
        existing = self._collection.get(ids=ids)
        existing_ids = set(existing["ids"])

        # Separate new and existing documents
        new_ids, new_texts, new_embeddings, new_metadatas = [], [], [], []
        update_ids, update_texts, update_metadatas = [], [], []

        for i, id in enumerate(ids):
            if id in existing_ids:
                update_ids.append(id)
                update_texts.append(texts[i])
                update_metadatas.append(metadatas[i])
            else:
                new_ids.append(id)
                new_texts.append(texts[i])
                new_embeddings.append(embeddings[i])
                new_metadatas.append(metadatas[i])

        # Add new documents
        if new_ids:
            self._collection.add(
                ids=new_ids,
                embeddings=new_embeddings,
                documents=new_texts,
                metadatas=new_metadatas,
            )

        # Update existing documents
        if update_ids:
            self._collection.update(
                ids=update_ids,
                documents=update_texts,
                metadatas=update_metadatas,
            )

        logger.debug(f"Added {len(new_ids)} new and updated {len(update_ids)} documents")
        return True

    def _add_batch_to_faiss(
        self,
        ids: List[str],
        texts: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> bool:
        """Add batch of documents to FAISS."""
        import numpy as np

        embeddings = self._generate_embeddings(texts)
        embedding_array = np.array(embeddings, dtype=np.float32)

        # Add to FAISS index
        self._backend.add(embedding_array)

        # Update mappings
        start_idx = self._backend.ntotal - len(ids)
        for i, id in enumerate(ids):
            idx = start_idx + i
            self._id_map[id] = idx
            self._documents[id] = Document(id=id, text=texts[i], metadata=metadatas[i])

        # Save to disk
        self._save_faiss_data()

        logger.debug(f"Added {len(ids)} documents to FAISS")
        return True

    def search_similar(
        self,
        query: str,
        k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Search for similar texts in the vector store.

        Args:
            query: Query text to search for
            k: Number of results to return
            filter: Optional metadata filter (ChromaDB only)
                Example: {"source": "document"} or {"year": {"$gte": 2020}}

        Returns:
            List of SearchResult objects, sorted by similarity score (descending)

        Raises:
            VectorStoreError: If the operation fails
        """
        if not query or not query.strip():
            raise ValueError("Query cannot be empty")

        try:
            if self.db_type == "chroma":
                return self._search_chroma(query, k, filter)
            else:
                return self._search_faiss(query, k, filter)
        except Exception as e:
            logger.error(f"Failed to search: {e}")
            raise VectorStoreError(f"Failed to search: {e}") from e

    def _search_chroma(
        self,
        query: str,
        k: int,
        filter: Optional[Dict[str, Any]],
    ) -> List[SearchResult]:
        """Search ChromaDB for similar documents."""
        query_embedding = self._generate_embedding(query)

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=filter,
            include=["documents", "metadatas", "distances"],
        )

        search_results = []
        if results["ids"] and results["ids"][0]:
            for i, id in enumerate(results["ids"][0]):
                # ChromaDB returns distances, convert to similarity scores
                # For cosine distance, similarity = 1 - distance
                distance = results["distances"][0][i]
                score = 1.0 - distance if distance is not None else 0.0

                search_results.append(
                    SearchResult(
                        id=id,
                        text=results["documents"][0][i] or "",
                        score=score,
                        metadata=results["metadatas"][0][i] or {},
                    )
                )

        logger.debug(f"Found {len(search_results)} results for query")
        return search_results

    def _search_faiss(
        self,
        query: str,
        k: int,
        filter: Optional[Dict[str, Any]],
    ) -> List[SearchResult]:
        """Search FAISS for similar documents."""
        import numpy as np

        if self._backend.ntotal == 0:
            return []

        # Limit k to available documents
        k = min(k, self._backend.ntotal)

        query_embedding = self._generate_embedding(query)
        query_array = np.array([query_embedding], dtype=np.float32)

        # Search FAISS
        distances, indices = self._backend.search(query_array, k)

        # Build reverse mapping (index -> id)
        reverse_id_map = {v: k for k, v in self._id_map.items()}

        search_results = []
        for i, (distance, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < 0:  # FAISS returns -1 for empty slots
                continue

            doc_id = reverse_id_map.get(idx)
            if doc_id is None or doc_id not in self._documents:
                continue

            doc = self._documents[doc_id]

            # Apply metadata filter if specified
            if filter:
                match = all(doc.metadata.get(key) == value for key, value in filter.items())
                if not match:
                    continue

            search_results.append(
                SearchResult(
                    id=doc_id,
                    text=doc.text,
                    score=float(distance),
                    metadata=doc.metadata,
                )
            )

        logger.debug(f"Found {len(search_results)} results for query")
        return search_results

    def get_by_id(self, id: str) -> Optional[Document]:
        """Retrieve a document by its ID.

        Args:
            id: Document ID

        Returns:
            Document if found, None otherwise
        """
        try:
            if self.db_type == "chroma":
                result = self._collection.get(ids=[id], include=["documents", "metadatas"])
                if result["ids"]:
                    return Document(
                        id=id,
                        text=result["documents"][0] or "",
                        metadata=result["metadatas"][0] or {},
                    )
                return None
            else:
                return self._documents.get(id)
        except Exception as e:
            logger.error(f"Failed to get document: {e}")
            return None

    def delete_by_id(self, id: str) -> bool:
        """Delete a document by its ID.

        Args:
            id: Document ID to delete

        Returns:
            True if deleted, False if not found

        Raises:
            VectorStoreError: If the operation fails
        """
        try:
            if self.db_type == "chroma":
                return self._delete_from_chroma(id)
            else:
                return self._delete_from_faiss(id)
        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            raise VectorStoreError(f"Failed to delete document: {e}") from e

    def _delete_from_chroma(self, id: str) -> bool:
        """Delete document from ChromaDB."""
        existing = self._collection.get(ids=[id])
        if not existing["ids"]:
            return False

        self._collection.delete(ids=[id])
        logger.debug(f"Deleted document: {id}")
        return True

    def _delete_from_faiss(self, id: str) -> bool:
        """Delete document from FAISS.

        Note: FAISS doesn't support efficient deletion. We mark the document
        as deleted in our metadata but the index entry remains.
        """
        if id not in self._documents:
            return False

        # Remove from metadata
        del self._documents[id]
        del self._id_map[id]

        # Note: FAISS index still contains the vector, but we can't access it
        # without a valid ID mapping. Consider rebuilding the index periodically.

        self._save_faiss_data()
        logger.debug(f"Deleted document: {id}")
        return True

    def clear(self) -> bool:
        """Clear all documents from the vector store.

        Returns:
            True if successful

        Raises:
            VectorStoreError: If the operation fails
        """
        try:
            if self.db_type == "chroma":
                # Delete and recreate the collection
                self._backend.delete_collection(self.collection_name)
                self._collection = self._backend.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info(f"Cleared collection: {self.collection_name}")
            else:
                # Reset FAISS index
                self._backend = faiss.IndexFlatIP(self._embedding_dim)
                self._id_map = {}
                self._documents = {}
                self._save_faiss_data()
                logger.info("Cleared FAISS index")

            return True
        except Exception as e:
            logger.error(f"Failed to clear: {e}")
            raise VectorStoreError(f"Failed to clear: {e}") from e

    def count(self) -> int:
        """Get the number of documents in the store.

        Returns:
            Number of documents
        """
        if self.db_type == "chroma":
            return self._collection.count()
        else:
            return len(self._documents)

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store.

        Returns:
            Dictionary with statistics
        """
        stats = {
            "db_type": self.db_type,
            "path": self.path,
            "embedding_model": self.embedding_model_name,
            "embedding_dim": self._embedding_dim,
            "document_count": self.count(),
            "collection_name": self.collection_name,
        }

        if self.db_type == "chroma":
            stats["backend"] = "ChromaDB"
        else:
            stats["backend"] = "FAISS"
            stats["index_size"] = self._backend.ntotal

        return stats

    def __len__(self) -> int:
        """Return the number of documents."""
        return self.count()

    def __repr__(self) -> str:
        """Return string representation."""
        return (
            f"VectorStore(db_type={self.db_type!r}, path={self.path!r}, documents={self.count()})"
        )


def check_vector_store_dependencies() -> Dict[str, bool]:
    """Check which vector store dependencies are available.

    Returns:
        Dictionary mapping dependency names to availability status
    """
    return {
        "chromadb": CHROMA_AVAILABLE,
        "faiss": FAISS_AVAILABLE,
        "sentence_transformers": SENTENCE_TRANSFORMERS_AVAILABLE,
    }


def get_recommended_backend() -> str:
    """Get the recommended vector store backend.

    Returns "chroma" if ChromaDB is available, otherwise "faiss" if available,
    or raises an error if neither is available.
    """
    if CHROMA_AVAILABLE:
        return "chroma"
    elif FAISS_AVAILABLE:
        return "faiss"
    else:
        raise DependencyNotFoundError(
            "No vector store backend available. "
            "Install chromadb or faiss-cpu: "
            "pip install chromadb OR pip install faiss-cpu numpy"
        )
