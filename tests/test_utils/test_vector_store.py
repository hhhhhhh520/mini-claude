"""Tests for vector_store module."""

import gc
import shutil
import tempfile
import pytest
from unittest.mock import patch

from mini_claude.utils.vector_store import (
    VectorStore,
    SearchResult,
    Document,
    DependencyNotFoundError,
    check_vector_store_dependencies,
    get_recommended_backend,
)


class TestSearchResult:
    """Test SearchResult dataclass."""

    def test_search_result_creation(self):
        """Test creating a SearchResult."""
        result = SearchResult(
            id="doc1",
            text="Hello world",
            score=0.95,
            metadata={"source": "test"},
        )
        assert result.id == "doc1"
        assert result.text == "Hello world"
        assert result.score == 0.95
        assert result.metadata == {"source": "test"}

    def test_search_result_to_dict(self):
        """Test converting SearchResult to dictionary."""
        result = SearchResult(
            id="doc1",
            text="Hello world",
            score=0.95,
            metadata={"source": "test"},
        )
        d = result.to_dict()
        assert d["id"] == "doc1"
        assert d["text"] == "Hello world"
        assert d["score"] == 0.95
        assert d["metadata"] == {"source": "test"}

    def test_search_result_default_metadata(self):
        """Test SearchResult with default empty metadata."""
        result = SearchResult(id="doc1", text="Test", score=0.5)
        assert result.metadata == {}


class TestDocument:
    """Test Document dataclass."""

    def test_document_creation(self):
        """Test creating a Document."""
        doc = Document(
            id="doc1",
            text="Hello world",
            metadata={"source": "test"},
        )
        assert doc.id == "doc1"
        assert doc.text == "Hello world"
        assert doc.metadata == {"source": "test"}
        assert doc.embedding is None

    def test_document_with_embedding(self):
        """Test creating a Document with pre-computed embedding."""
        embedding = [0.1, 0.2, 0.3]
        doc = Document(id="doc1", text="Test", embedding=embedding)
        assert doc.embedding == embedding


class TestDependencyCheck:
    """Test dependency checking functions."""

    def test_check_vector_store_dependencies(self):
        """Test checking vector store dependencies."""
        deps = check_vector_store_dependencies()
        assert "chromadb" in deps
        assert "faiss" in deps
        assert "sentence_transformers" in deps
        assert isinstance(deps["chromadb"], bool)
        assert isinstance(deps["faiss"], bool)
        assert isinstance(deps["sentence_transformers"], bool)

    def test_get_recommended_backend(self):
        """Test getting recommended backend."""
        # Should return a valid backend or raise
        try:
            backend = get_recommended_backend()
            assert backend in ("chroma", "faiss")
        except DependencyNotFoundError:
            pytest.skip("No vector store backend available")


class TestVectorStoreChroma:
    """Test VectorStore with ChromaDB backend."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for vector store."""
        # Use a persistent temp dir that we manually clean up
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        # Force garbage collection to release file handles
        gc.collect()
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    @pytest.fixture
    def chroma_store(self, temp_dir):
        """Create a ChromaDB vector store for testing."""
        # Skip if chromadb not available
        try:
            store = VectorStore(
                db_type="chroma",
                path=temp_dir,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                collection_name="test_collection",
            )
            yield store
            # Clear before cleanup
            try:
                store.clear()
            except Exception:
                pass
            # Release backend reference
            store._backend = None
            store._collection = None
            gc.collect()
        except DependencyNotFoundError as e:
            pytest.skip(str(e))

    def test_chroma_init(self, chroma_store):
        """Test ChromaDB store initialization."""
        assert chroma_store.db_type == "chroma"
        assert chroma_store.count() == 0

    def test_chroma_add_embedding(self, chroma_store):
        """Test adding an embedding to ChromaDB."""
        result = chroma_store.add_embedding(
            "doc1",
            "Hello world",
            {"source": "test"},
        )
        assert result is True
        assert chroma_store.count() == 1

    def test_chroma_add_embedding_empty_text(self, chroma_store):
        """Test adding empty text raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            chroma_store.add_embedding("doc1", "")

    def test_chroma_search_similar(self, chroma_store):
        """Test searching for similar texts in ChromaDB."""
        # Add some documents
        chroma_store.add_embedding("doc1", "Hello world")
        chroma_store.add_embedding("doc2", "Goodbye world")
        chroma_store.add_embedding("doc3", "Python programming")

        # Search for similar to "Hello"
        results = chroma_store.search_similar("Hello", k=2)

        assert len(results) <= 2
        assert all(isinstance(r, SearchResult) for r in results)
        # First result should be "Hello world"
        assert results[0].id == "doc1"

    def test_chroma_search_with_filter(self, chroma_store):
        """Test searching with metadata filter in ChromaDB."""
        chroma_store.add_embedding("doc1", "Python code", {"language": "python"})
        chroma_store.add_embedding("doc2", "Java code", {"language": "java"})

        results = chroma_store.search_similar(
            "code",
            k=5,
            filter={"language": "python"},
        )

        assert len(results) == 1
        assert results[0].metadata["language"] == "python"

    def test_chroma_get_by_id(self, chroma_store):
        """Test getting document by ID from ChromaDB."""
        chroma_store.add_embedding("doc1", "Hello world", {"source": "test"})

        doc = chroma_store.get_by_id("doc1")

        assert doc is not None
        assert doc.id == "doc1"
        assert doc.text == "Hello world"
        assert doc.metadata["source"] == "test"

    def test_chroma_get_by_id_not_found(self, chroma_store):
        """Test getting non-existent document returns None."""
        doc = chroma_store.get_by_id("nonexistent")
        assert doc is None

    def test_chroma_delete_by_id(self, chroma_store):
        """Test deleting document from ChromaDB."""
        chroma_store.add_embedding("doc1", "Hello world")

        result = chroma_store.delete_by_id("doc1")

        assert result is True
        assert chroma_store.count() == 0

    def test_chroma_delete_by_id_not_found(self, chroma_store):
        """Test deleting non-existent document returns False."""
        result = chroma_store.delete_by_id("nonexistent")
        assert result is False

    def test_chroma_clear(self, chroma_store):
        """Test clearing all documents from ChromaDB."""
        chroma_store.add_embedding("doc1", "Hello")
        chroma_store.add_embedding("doc2", "World")

        result = chroma_store.clear()

        assert result is True
        assert chroma_store.count() == 0

    def test_chroma_add_batch(self, chroma_store):
        """Test adding batch of documents to ChromaDB."""
        ids = ["doc1", "doc2", "doc3"]
        texts = ["Hello", "World", "Python"]
        metadatas = [{"idx": 1}, {"idx": 2}, {"idx": 3}]

        result = chroma_store.add_batch(ids, texts, metadatas)

        assert result is True
        assert chroma_store.count() == 3

    def test_chroma_add_batch_mismatched_lengths(self, chroma_store):
        """Test batch add with mismatched lengths raises error."""
        with pytest.raises(ValueError, match="same length"):
            chroma_store.add_batch(["doc1", "doc2"], ["Hello"])

    def test_chroma_update_existing(self, chroma_store):
        """Test updating existing document in ChromaDB."""
        chroma_store.add_embedding("doc1", "Hello world")
        chroma_store.add_embedding("doc1", "Updated text")

        doc = chroma_store.get_by_id("doc1")
        assert doc.text == "Updated text"

    def test_chroma_search_empty_query(self, chroma_store):
        """Test searching with empty query raises error."""
        with pytest.raises(ValueError, match="cannot be empty"):
            chroma_store.search_similar("")

    def test_chroma_get_stats(self, chroma_store):
        """Test getting statistics from ChromaDB store."""
        chroma_store.add_embedding("doc1", "Hello")

        stats = chroma_store.get_stats()

        assert stats["db_type"] == "chroma"
        assert stats["document_count"] == 1
        assert stats["embedding_dim"] > 0
        assert "all-MiniLM-L6-v2" in stats["embedding_model"]

    def test_chroma_len(self, chroma_store):
        """Test __len__ method."""
        chroma_store.add_embedding("doc1", "Hello")
        chroma_store.add_embedding("doc2", "World")

        assert len(chroma_store) == 2

    def test_chroma_repr(self, chroma_store):
        """Test __repr__ method."""
        repr_str = repr(chroma_store)
        assert "VectorStore" in repr_str
        assert "chroma" in repr_str


class TestVectorStoreFAISS:
    """Test VectorStore with FAISS backend."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for vector store."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        gc.collect()
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    @pytest.fixture
    def faiss_store(self, temp_dir):
        """Create a FAISS vector store for testing."""
        # Skip if faiss not available
        try:
            store = VectorStore(
                db_type="faiss",
                path=temp_dir,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                collection_name="test_faiss",
            )
            yield store
            try:
                store.clear()
            except Exception:
                pass
            store._backend = None
            gc.collect()
        except DependencyNotFoundError:
            store = VectorStore(
                db_type="faiss",
                path=temp_dir,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                collection_name="test_faiss",
            )
            yield store
            store.clear()
        except DependencyNotFoundError as e:
            pytest.skip(str(e))

    def test_faiss_init(self, faiss_store):
        """Test FAISS store initialization."""
        assert faiss_store.db_type == "faiss"
        assert faiss_store.count() == 0

    def test_faiss_add_embedding(self, faiss_store):
        """Test adding an embedding to FAISS."""
        result = faiss_store.add_embedding(
            "doc1",
            "Hello world",
            {"source": "test"},
        )
        assert result is True
        assert faiss_store.count() == 1

    def test_faiss_search_similar(self, faiss_store):
        """Test searching for similar texts in FAISS."""
        faiss_store.add_embedding("doc1", "Hello world")
        faiss_store.add_embedding("doc2", "Goodbye world")
        faiss_store.add_embedding("doc3", "Python programming")

        results = faiss_store.search_similar("Hello", k=2)

        assert len(results) <= 2
        assert all(isinstance(r, SearchResult) for r in results)

    def test_faiss_get_by_id(self, faiss_store):
        """Test getting document by ID from FAISS."""
        faiss_store.add_embedding("doc1", "Hello world", {"source": "test"})

        doc = faiss_store.get_by_id("doc1")

        assert doc is not None
        assert doc.id == "doc1"
        assert doc.text == "Hello world"

    def test_faiss_delete_by_id(self, faiss_store):
        """Test deleting document from FAISS."""
        faiss_store.add_embedding("doc1", "Hello world")

        result = faiss_store.delete_by_id("doc1")

        assert result is True
        assert faiss_store.count() == 0

    def test_faiss_clear(self, faiss_store):
        """Test clearing all documents from FAISS."""
        faiss_store.add_embedding("doc1", "Hello")
        faiss_store.add_embedding("doc2", "World")

        result = faiss_store.clear()

        assert result is True
        assert faiss_store.count() == 0

    def test_faiss_add_batch(self, faiss_store):
        """Test adding batch of documents to FAISS."""
        ids = ["doc1", "doc2", "doc3"]
        texts = ["Hello", "World", "Python"]

        result = faiss_store.add_batch(ids, texts)

        assert result is True
        assert faiss_store.count() == 3

    def test_faiss_search_with_filter(self, faiss_store):
        """Test searching with metadata filter in FAISS."""
        faiss_store.add_embedding("doc1", "Python code", {"language": "python"})
        faiss_store.add_embedding("doc2", "Java code", {"language": "java"})

        results = faiss_store.search_similar(
            "code",
            k=5,
            filter={"language": "python"},
        )

        assert len(results) == 1
        assert results[0].metadata["language"] == "python"

    def test_faiss_persistence(self, temp_dir):
        """Test FAISS data persistence."""
        # Create store and add document
        store1 = VectorStore(
            db_type="faiss",
            path=temp_dir,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            collection_name="persist_test",
        )
        store1.add_embedding("doc1", "Hello world")
        store1_count = store1.count()

        # Create new store with same path
        store2 = VectorStore(
            db_type="faiss",
            path=temp_dir,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            collection_name="persist_test",
        )

        # Should have loaded existing data
        assert store2.count() == store1_count

        # Clean up
        store2.clear()

    def test_faiss_get_stats(self, faiss_store):
        """Test getting statistics from FAISS store."""
        faiss_store.add_embedding("doc1", "Hello")

        stats = faiss_store.get_stats()

        assert stats["db_type"] == "faiss"
        assert stats["document_count"] == 1
        assert stats["embedding_dim"] > 0
        assert "index_size" in stats


class TestVectorStoreErrors:
    """Test error handling in VectorStore."""

    def test_invalid_db_type(self):
        """Test invalid db_type raises error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Unsupported db_type"):
                VectorStore(db_type="invalid", path=tmpdir)

    def test_unsupported_db_type_missing_dependency(self):
        """Test that missing dependency raises friendly error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "mini_claude.utils.vector_store.CHROMA_AVAILABLE", False
            ):
                with patch(
                    "mini_claude.utils.vector_store.FAISS_AVAILABLE", False
                ):
                    with pytest.raises(DependencyNotFoundError):
                        VectorStore(db_type="chroma", path=tmpdir)


class TestVectorStoreEdgeCases:
    """Test edge cases in VectorStore."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for vector store."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        gc.collect()
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    @pytest.fixture
    def store(self, temp_dir):
        """Create a vector store for testing."""
        try:
            store = VectorStore(
                db_type="chroma",
                path=temp_dir,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            )
            yield store
            try:
                store.clear()
            except Exception:
                pass
            store._backend = None
            store._collection = None
            gc.collect()
        except DependencyNotFoundError as e:
            pytest.skip(str(e))

    def test_search_empty_store(self, store):
        """Test searching in empty store returns empty list."""
        results = store.search_similar("Hello", k=5)
        assert results == []

    def test_unicode_text(self, store):
        """Test handling of unicode text."""
        store.add_embedding("doc1", "Hello world")
        store.add_embedding("doc2", "Hello world")

        results = store.search_similar("Hello world", k=5)
        assert len(results) >= 1

    def test_long_text(self, store):
        """Test handling of long text."""
        long_text = "A" * 10000
        result = store.add_embedding("doc1", long_text)
        assert result is True

    def test_special_characters_in_metadata(self, store):
        """Test metadata with special characters."""
        # ChromaDB only supports str, int, float, bool values (not nested dicts)
        metadata = {
            "key_with_special": "value:with:colons",
            "nested_key": "{'key': 'value'}",  # JSON string instead of dict
        }
        result = store.add_embedding("doc1", "Test", metadata)
        assert result is True

        doc = store.get_by_id("doc1")
        assert doc.metadata["key_with_special"] == "value:with:colons"

    def test_add_batch_empty_list(self, store):
        """Test adding empty batch."""
        result = store.add_batch([], [])
        assert result is True

    def test_search_k_larger_than_count(self, store):
        """Test searching with k larger than document count."""
        store.add_embedding("doc1", "Hello")
        results = store.search_similar("Hello", k=100)
        assert len(results) == 1


class TestVectorStoreIntegration:
    """Integration tests for VectorStore."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for vector store."""
        tmpdir = tempfile.mkdtemp()
        yield tmpdir
        gc.collect()
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    def test_semantic_similarity(self, temp_dir):
        """Test that semantically similar texts are found."""
        try:
            store = VectorStore(
                db_type="chroma",
                path=temp_dir,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            )
        except DependencyNotFoundError as e:
            pytest.skip(str(e))

        # Add documents on different topics
        store.add_embedding("python1", "Python is a programming language")
        store.add_embedding("python2", "I love coding in Python")
        store.add_embedding("food1", "Pizza is delicious")
        store.add_embedding("food2", "I enjoy eating Italian food")

        # Search for programming-related content
        results = store.search_similar("coding and programming", k=2)

        # Should find Python-related documents
        assert len(results) > 0
        python_ids = ["python1", "python2"]
        assert any(r.id in python_ids for r in results)

        store.clear()

    def test_different_queries_same_results(self, temp_dir):
        """Test that similar queries return similar results."""
        try:
            store = VectorStore(
                db_type="chroma",
                path=temp_dir,
                embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            )
        except DependencyNotFoundError as e:
            pytest.skip(str(e))

        store.add_embedding("doc1", "Machine learning is fascinating")

        # Different ways to ask about the same topic
        results1 = store.search_similar("AI and ML", k=1)
        results2 = store.search_similar("artificial intelligence", k=1)

        # Both should find the same document
        if results1 and results2:
            assert results1[0].id == results2[0].id

        store.clear()
