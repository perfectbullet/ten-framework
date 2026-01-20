#
# Performance benchmarks for Speaker Recognition SDK
#

import time
import numpy as np
import pytest

from speaker_recognition.config import MatcherConfig
from speaker_recognition.matcher import SimilarityMatcher


@pytest.mark.benchmark
class TestMatcherPerformance:
    """Performance benchmarks for similarity matching."""

    def test_similarity_calculation_speed(self):
        """Test speed of single similarity calculation."""
        matcher = SimilarityMatcher()

        # Create 192-dim embeddings
        np.random.seed(42)
        a = np.random.randn(192).astype(np.float32)
        b = np.random.randn(192).astype(np.float32)

        # Warmup
        for _ in range(100):
            matcher.cosine_similarity(a, b)

        # Benchmark
        iterations = 10000
        start = time.time()
        for _ in range(iterations):
            matcher.cosine_similarity(a, b)
        elapsed = time.time() - start

        avg_time_ms = (elapsed / iterations) * 1000

        print(f"\n  Single similarity calculation: {avg_time_ms:.3f}ms")
        print(f"  Throughput: {iterations/elapsed:.0f} calculations/second")

        # Should be very fast (< 1ms per calculation)
        assert avg_time_ms < 1.0

    def test_find_best_match_speed(self, sample_embeddings):
        """Test speed of finding best match."""
        matcher = SimilarityMatcher()

        # Create query embedding
        np.random.seed(42)
        query = np.random.randn(192).astype(np.float32)

        # Warmup
        for _ in range(100):
            matcher.find_best_match(query, sample_embeddings)

        # Benchmark
        iterations = 1000
        start = time.time()
        for _ in range(iterations):
            matcher.find_best_match(query, sample_embeddings)
        elapsed = time.time() - start

        avg_time_ms = (elapsed / iterations) * 1000

        print(f"\n  Find best match ({len(sample_embeddings)} speakers): {avg_time_ms:.3f}ms")
        print(f"  Throughput: {iterations/elapsed:.0f} matches/second")

        # Should be fast (< 50ms for 100 speakers)
        assert avg_time_ms < 50.0

    def test_find_best_match_scalability(self):
        """Test scalability with increasing number of speakers."""
        matcher = SimilarityMatcher()

        np.random.seed(42)
        query = np.random.randn(192).astype(np.float32)

        speaker_counts = [10, 50, 100, 500, 1000]
        times = []

        for count in speaker_counts:
            # Create candidates
            candidates = {
                f"spk_{i:04d}": (f"Speaker_{i}", np.random.randn(192).astype(np.float32))
                for i in range(count)
            }

            # Warmup
            matcher.find_best_match(query, candidates)

            # Benchmark
            iterations = max(100 // (count // 10), 10)
            start = time.time()
            for _ in range(iterations):
                matcher.find_best_match(query, candidates)
            elapsed = time.time() - start

            avg_time_ms = (elapsed / iterations) * 1000
            times.append(avg_time_ms)

            print(f"  {count:4d} speakers: {avg_time_ms:6.3f}ms")

        # Check that time scales roughly linearly
        # 100x speakers should take less than 100x time (due to optimizations)
        ratio = times[-1] / times[0]
        print(f"  Scalability ratio: {ratio:.2f}x")

        # Should be reasonable (not exponential)
        assert ratio < speaker_counts[-1] / speaker_counts[0]

    def test_batch_match_speed(self):
        """Test speed of batch matching."""
        matcher = SimilarityMatcher()

        # Create candidates
        np.random.seed(42)
        candidates = {
            f"spk_{i:04d}": (f"Speaker_{i}", np.random.randn(192).astype(np.float32))
            for i in range(100)
        }

        # Create queries
        queries = [np.random.randn(192).astype(np.float32) for _ in range(10)]

        # Benchmark
        start = time.time()
        results = matcher.batch_match(queries, candidates)
        elapsed = time.time() - start

        avg_time_ms = (elapsed / len(queries)) * 1000

        print(f"\n  Batch match (10 queries, 100 speakers): {elapsed*1000:.1f}ms total")
        print(f"  Average per query: {avg_time_ms:.1f}ms")

        assert len(results) == len(queries)


@pytest.mark.benchmark
class TestEmbeddingOperations:
    """Performance benchmarks for embedding operations."""

    def test_aggregation_speed(self):
        """Test speed of embedding aggregation."""
        from speaker_recognition.utils import AudioUtils

        # Create embeddings
        np.random.seed(42)
        embeddings = [np.random.randn(192).astype(np.float32) for _ in range(10)]

        # Warmup
        for _ in range(1000):
            AudioUtils.aggregate_embeddings(embeddings, method="mean")

        # Benchmark
        iterations = 10000
        start = time.time()
        for _ in range(iterations):
            AudioUtils.aggregate_embeddings(embeddings, method="mean")
        elapsed = time.time() - start

        avg_time_ms = (elapsed / iterations) * 1000

        print(f"\n  Aggregate {len(embeddings)} embeddings: {avg_time_ms:.3f}ms")
        print(f"  Throughput: {iterations/elapsed:.0f} aggregations/second")

        # Should be very fast
        assert avg_time_ms < 1.0

    def test_segmentation_speed(self):
        """Test speed of audio segmentation."""
        from speaker_recognition.utils import AudioUtils

        # Create 10 seconds of audio at 16kHz
        audio = np.random.randn(160000).astype(np.float32)

        # Warmup
        for _ in range(100):
            AudioUtils.segment_audio(audio, 16000, segment_length=3.0, overlap=0.5)

        # Benchmark
        iterations = 1000
        start = time.time()
        for _ in range(iterations):
            AudioUtils.segment_audio(audio, 16000, segment_length=3.0, overlap=0.5)
        elapsed = time.time() - start

        avg_time_ms = (elapsed / iterations) * 1000

        segments = AudioUtils.segment_audio(audio, 16000, segment_length=3.0, overlap=0.5)

        print(f"\n  Segment 10s audio: {avg_time_ms:.3f}ms")
        print(f"  Produced {len(segments)} segments")

        # Should be fast
        assert avg_time_ms < 10.0


@pytest.mark.benchmark
class TestIDGeneration:
    """Performance benchmarks for ID generation."""

    def test_id_generation_speed(self):
        """Test speed of speaker ID generation."""
        from speaker_recognition.utils import SpeakerIdGenerator

        # Warmup
        for _ in range(1000):
            SpeakerIdGenerator.generate()

        # Benchmark
        iterations = 100000
        start = time.time()
        ids = [SpeakerIdGenerator.generate() for _ in range(iterations)]
        elapsed = time.time() - start

        avg_time_us = (elapsed / iterations) * 1000000

        print(f"\n  Generate ID: {avg_time_us:.3f}μs")
        print(f"  Throughput: {iterations/elapsed:.0f} IDs/second")

        # All IDs should be unique
        assert len(set(ids)) == iterations

        # Should be very fast
        assert avg_time_us < 100  # Less than 100 microseconds


if __name__ == "__main__":
    # Run benchmarks directly
    pytest.main([__file__, "-v", "-s"])
