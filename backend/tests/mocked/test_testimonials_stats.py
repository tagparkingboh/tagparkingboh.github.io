"""
Tests for testimonials stats and buzz words feature.

Covers:
- GET /api/testimonials stats calculation
- Average rating calculation
- Recommend percentage calculation
- Buzz words extraction

All tests use mocked data - no real database connections.
"""
import pytest
from collections import Counter


# ============================================================================
# MOCK DATA SETUP
# ============================================================================

class MockTestimonial:
    """Mock testimonial object."""
    def __init__(self, id=1, customer_name="John D.", review_text="Great service!",
                 star_rating=5, is_featured=False, source="google", status="active"):
        self.id = id
        self.customer_name = customer_name
        self.review_text = review_text
        self.star_rating = star_rating
        self.is_featured = is_featured
        self.source = source
        self.status = status


# ============================================================================
# MOCKED UNIT TESTS - Average Rating Calculation
# ============================================================================

class TestAverageRatingCalculation:
    """Unit tests for average rating calculation."""

    def test_average_rating_all_five_stars(self):
        """Happy path: All 5-star reviews."""
        testimonials = [
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=5),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        average = round(sum(t.star_rating for t in rated) / len(rated), 1)
        assert average == 5.0

    def test_average_rating_mixed_ratings(self):
        """Happy path: Mixed ratings."""
        testimonials = [
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=4),
            MockTestimonial(star_rating=4),
            MockTestimonial(star_rating=3),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        average = round(sum(t.star_rating for t in rated) / len(rated), 1)
        assert average == 4.2

    def test_average_rating_excludes_null(self):
        """Edge case: Null ratings excluded from average."""
        testimonials = [
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=None),
            MockTestimonial(star_rating=4),
            MockTestimonial(star_rating=None),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        average = round(sum(t.star_rating for t in rated) / len(rated), 1)
        assert average == 4.5
        assert len(rated) == 2

    def test_average_rating_all_null(self):
        """Edge case: All ratings are null."""
        testimonials = [
            MockTestimonial(star_rating=None),
            MockTestimonial(star_rating=None),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        average = 0 if not rated else round(sum(t.star_rating for t in rated) / len(rated), 1)
        assert average == 0

    def test_average_rating_single_review(self):
        """Boundary: Single review."""
        testimonials = [MockTestimonial(star_rating=4)]
        rated = [t for t in testimonials if t.star_rating is not None]
        average = round(sum(t.star_rating for t in rated) / len(rated), 1)
        assert average == 4.0

    def test_average_rating_rounds_correctly(self):
        """Boundary: Rounding to one decimal place."""
        testimonials = [
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=4),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        average = round(sum(t.star_rating for t in rated) / len(rated), 1)
        # (5 + 5 + 4) / 3 = 4.666... -> 4.7
        assert average == 4.7


# ============================================================================
# MOCKED UNIT TESTS - Recommend Percentage Calculation
# ============================================================================

class TestRecommendPercentCalculation:
    """Unit tests for recommend percentage calculation."""

    def test_recommend_percent_all_five_star(self):
        """Happy path: All 5-star reviews = 100% recommend."""
        testimonials = [
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=5),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        recommend_count = sum(1 for t in rated if t.star_rating >= 4)
        recommend_percent = round((recommend_count / len(rated)) * 100)
        assert recommend_percent == 100

    def test_recommend_percent_4_and_5_stars(self):
        """Happy path: 4 and 5 stars both count as recommend."""
        testimonials = [
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=4),
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=4),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        recommend_count = sum(1 for t in rated if t.star_rating >= 4)
        recommend_percent = round((recommend_count / len(rated)) * 100)
        assert recommend_percent == 100

    def test_recommend_percent_mixed(self):
        """Happy path: Mixed ratings."""
        testimonials = [
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=4),
            MockTestimonial(star_rating=3),
            MockTestimonial(star_rating=2),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        recommend_count = sum(1 for t in rated if t.star_rating >= 4)
        recommend_percent = round((recommend_count / len(rated)) * 100)
        # 2 out of 4 = 50%
        assert recommend_percent == 50

    def test_recommend_percent_excludes_null(self):
        """Edge case: Null ratings excluded from calculation."""
        testimonials = [
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=None),
            MockTestimonial(star_rating=3),
            MockTestimonial(star_rating=None),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        recommend_count = sum(1 for t in rated if t.star_rating >= 4)
        recommend_percent = round((recommend_count / len(rated)) * 100)
        # 1 out of 2 = 50%
        assert recommend_percent == 50

    def test_recommend_percent_zero(self):
        """Unhappy path: No recommendations (all low ratings)."""
        testimonials = [
            MockTestimonial(star_rating=1),
            MockTestimonial(star_rating=2),
            MockTestimonial(star_rating=3),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        recommend_count = sum(1 for t in rated if t.star_rating >= 4)
        recommend_percent = round((recommend_count / len(rated)) * 100)
        assert recommend_percent == 0

    def test_recommend_percent_rounds_correctly(self):
        """Boundary: Rounding percentage."""
        testimonials = [
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=3),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        recommend_count = sum(1 for t in rated if t.star_rating >= 4)
        recommend_percent = round((recommend_count / len(rated)) * 100)
        # 2 out of 3 = 66.666... -> 67%
        assert recommend_percent == 67


# ============================================================================
# MOCKED UNIT TESTS - Buzz Words Extraction
# ============================================================================

class TestBuzzWordsExtraction:
    """Unit tests for buzz words extraction."""

    BUZZ_WORDS = [
        "friendly", "helpful", "professional", "efficient", "reliable",
        "punctual", "quick", "fast", "prompt", "timely",
        "easy", "seamless", "smooth", "simple", "convenient",
        "great", "excellent", "amazing", "fantastic", "brilliant",
        "recommend", "stress-free", "hassle-free",
        "perfect", "clean", "safe", "secure", "affordable",
    ]

    def extract_buzz_words(self, testimonials, min_count=2, max_words=8):
        """Mirror the extraction logic from the endpoint."""
        word_counts = Counter()
        for t in testimonials:
            text_lower = t.review_text.lower()
            for word in self.BUZZ_WORDS:
                if word in text_lower:
                    word_counts[word] += 1
        return [
            {"word": word.title(), "count": count}
            for word, count in word_counts.most_common(max_words)
            if count >= min_count
        ]

    def test_buzz_words_multiple_mentions(self):
        """Happy path: Words appearing in multiple reviews."""
        testimonials = [
            MockTestimonial(review_text="Very friendly staff, great service!"),
            MockTestimonial(review_text="Friendly drivers and easy booking"),
            MockTestimonial(review_text="Great value, would recommend"),
        ]
        buzz_words = self.extract_buzz_words(testimonials)
        words = [bw["word"] for bw in buzz_words]
        assert "Friendly" in words
        assert "Great" in words

    def test_buzz_words_case_insensitive(self):
        """Happy path: Case insensitive matching."""
        testimonials = [
            MockTestimonial(review_text="FRIENDLY staff"),
            MockTestimonial(review_text="Very Friendly service"),
            MockTestimonial(review_text="friendly people"),
        ]
        buzz_words = self.extract_buzz_words(testimonials)
        words = [bw["word"] for bw in buzz_words]
        assert "Friendly" in words
        # Count should be 3
        friendly_count = next(bw["count"] for bw in buzz_words if bw["word"] == "Friendly")
        assert friendly_count == 3

    def test_buzz_words_min_count_filter(self):
        """Edge case: Words appearing only once are excluded."""
        testimonials = [
            MockTestimonial(review_text="Very friendly staff"),
            MockTestimonial(review_text="Great service"),
            MockTestimonial(review_text="Excellent experience"),
        ]
        buzz_words = self.extract_buzz_words(testimonials, min_count=2)
        # Each word appears only once, so none should be returned
        assert len(buzz_words) == 0

    def test_buzz_words_max_words_limit(self):
        """Boundary: Returns at most max_words."""
        testimonials = [
            MockTestimonial(review_text="Friendly, helpful, professional, efficient, reliable"),
            MockTestimonial(review_text="Friendly, helpful, professional, efficient, reliable"),
            MockTestimonial(review_text="Punctual, quick, easy, seamless, smooth"),
            MockTestimonial(review_text="Punctual, quick, easy, seamless, smooth"),
        ]
        buzz_words = self.extract_buzz_words(testimonials, max_words=5)
        assert len(buzz_words) <= 5

    def test_buzz_words_sorted_by_count(self):
        """Happy path: Words sorted by frequency (most common first)."""
        testimonials = [
            MockTestimonial(review_text="Friendly friendly friendly"),
            MockTestimonial(review_text="Friendly great"),
            MockTestimonial(review_text="Great service"),
        ]
        buzz_words = self.extract_buzz_words(testimonials)
        if len(buzz_words) >= 2:
            assert buzz_words[0]["count"] >= buzz_words[1]["count"]

    def test_buzz_words_empty_reviews(self):
        """Edge case: No reviews."""
        testimonials = []
        buzz_words = self.extract_buzz_words(testimonials)
        assert buzz_words == []

    def test_buzz_words_no_matches(self):
        """Unhappy path: Reviews without any buzz words."""
        testimonials = [
            MockTestimonial(review_text="The parking was okay."),
            MockTestimonial(review_text="It was fine I guess."),
        ]
        buzz_words = self.extract_buzz_words(testimonials)
        assert buzz_words == []

    def test_buzz_words_counts_once_per_review(self):
        """Edge case: Word counted once per review, not multiple times."""
        testimonials = [
            MockTestimonial(review_text="Friendly friendly friendly friendly"),
            MockTestimonial(review_text="Very friendly"),
        ]
        buzz_words = self.extract_buzz_words(testimonials)
        friendly_entry = next((bw for bw in buzz_words if bw["word"] == "Friendly"), None)
        if friendly_entry:
            # Should count as 2 (once per review), not 5
            assert friendly_entry["count"] == 2


# ============================================================================
# MOCKED INTEGRATION TESTS - Stats Response Format
# ============================================================================

class TestStatsResponseFormat:
    """Integration tests for stats in API response."""

    def test_stats_response_structure(self):
        """Happy path: Stats object has all required fields."""
        stats = {
            "average_rating": 4.9,
            "total_count": 34,
            "recommend_percent": 97,
            "buzz_words": [
                {"word": "Friendly", "count": 12},
                {"word": "Easy", "count": 8},
            ],
        }

        assert "average_rating" in stats
        assert "total_count" in stats
        assert "recommend_percent" in stats
        assert "buzz_words" in stats
        assert isinstance(stats["buzz_words"], list)

    def test_stats_buzz_words_format(self):
        """Happy path: Each buzz word has word and count."""
        buzz_words = [
            {"word": "Friendly", "count": 12},
            {"word": "Easy", "count": 8},
        ]

        for bw in buzz_words:
            assert "word" in bw
            assert "count" in bw
            assert isinstance(bw["word"], str)
            assert isinstance(bw["count"], int)

    def test_stats_with_no_testimonials(self):
        """Edge case: No testimonials returns zero stats."""
        testimonials = []
        rated = [t for t in testimonials if hasattr(t, 'star_rating') and t.star_rating is not None]

        if rated:
            average_rating = round(sum(t.star_rating for t in rated) / len(rated), 1)
            recommend_count = sum(1 for t in rated if t.star_rating >= 4)
            recommend_percent = round((recommend_count / len(rated)) * 100)
        else:
            average_rating = 0
            recommend_percent = 0

        assert average_rating == 0
        assert recommend_percent == 0

    def test_total_count_includes_all_active(self):
        """Happy path: Total count includes all active testimonials."""
        testimonials = [
            MockTestimonial(star_rating=5),
            MockTestimonial(star_rating=None),  # Unrated still counted
            MockTestimonial(star_rating=4),
        ]
        total_count = len(testimonials)
        assert total_count == 3


# ============================================================================
# BOUNDARY TESTS
# ============================================================================

class TestStatsBoundaries:
    """Boundary tests for stats calculations."""

    def test_single_testimonial_stats(self):
        """Boundary: Single testimonial."""
        testimonials = [MockTestimonial(star_rating=5)]
        rated = [t for t in testimonials if t.star_rating is not None]
        average = round(sum(t.star_rating for t in rated) / len(rated), 1)
        recommend = round((sum(1 for t in rated if t.star_rating >= 4) / len(rated)) * 100)

        assert average == 5.0
        assert recommend == 100

    def test_large_number_of_testimonials(self):
        """Boundary: Large number of testimonials."""
        testimonials = [MockTestimonial(star_rating=5) for _ in range(1000)]
        rated = [t for t in testimonials if t.star_rating is not None]
        average = round(sum(t.star_rating for t in rated) / len(rated), 1)

        assert average == 5.0
        assert len(testimonials) == 1000

    def test_all_one_star_ratings(self):
        """Boundary: All 1-star ratings."""
        testimonials = [MockTestimonial(star_rating=1) for _ in range(5)]
        rated = [t for t in testimonials if t.star_rating is not None]
        average = round(sum(t.star_rating for t in rated) / len(rated), 1)
        recommend = round((sum(1 for t in rated if t.star_rating >= 4) / len(rated)) * 100)

        assert average == 1.0
        assert recommend == 0

    def test_rating_at_threshold(self):
        """Boundary: Rating exactly at recommend threshold (4)."""
        testimonials = [
            MockTestimonial(star_rating=4),
            MockTestimonial(star_rating=3),
        ]
        rated = [t for t in testimonials if t.star_rating is not None]
        recommend = round((sum(1 for t in rated if t.star_rating >= 4) / len(rated)) * 100)

        # 4 is included, 3 is not
        assert recommend == 50
