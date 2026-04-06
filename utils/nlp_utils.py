"""
Lightweight NLP helpers — no external API calls required.
Uses nltk + sklearn only.
"""
import re
import math
import string
from collections import Counter
from typing import Any

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import sent_tokenize, word_tokenize
from sklearn.feature_extraction.text import TfidfVectorizer

# Download required nltk data on first import
_NLTK_PACKAGES = {
    "punkt":     "tokenizers/punkt",
    "punkt_tab": "tokenizers/punkt_tab",
    "stopwords": "corpora/stopwords",
}
for _pkg, _path in _NLTK_PACKAGES.items():
    try:
        nltk.data.find(_path)
    except (LookupError, OSError):
        nltk.download(_pkg, quiet=True)

_STOP_WORDS = set(stopwords.words("english"))
_PUNCT = set(string.punctuation)

# ── Text cleaning ────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Lowercase, strip URLs, mentions, hashtags, and extra whitespace."""
    text = text.lower()
    text = re.sub(r"http\S+|www\.\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)   # keep hashtag word, drop #
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize_words(text: str, remove_stopwords: bool = True) -> list[str]:
    tokens = word_tokenize(clean_text(text))
    tokens = [t for t in tokens if t not in _PUNCT and t.isalpha()]
    if remove_stopwords:
        tokens = [t for t in tokens if t not in _STOP_WORDS]
    return tokens

# ── Writing style ────────────────────────────────────────────────────────────

def avg_sentence_length(text: str) -> float:
    sentences = sent_tokenize(text)
    if not sentences:
        return 0.0
    lengths = [len(word_tokenize(s)) for s in sentences]
    return round(sum(lengths) / len(lengths), 2)


def detect_tone(text: str) -> str:
    """
    Rule-based tone detection: formal / casual / promotional / informational.
    """
    cleaned = clean_text(text)
    words = tokenize_words(cleaned, remove_stopwords=False)
    total = len(words) or 1

    casual_markers = {"lol", "omg", "haha", "wow", "hey", "yeah", "gonna", "wanna", "tbh", "imo"}
    promo_markers = {"buy", "sale", "offer", "discount", "free", "deal", "limited", "exclusive", "shop", "order"}
    question_ratio = cleaned.count("?") / (len(sent_tokenize(cleaned)) or 1)

    casual_score = sum(1 for w in words if w in casual_markers) / total
    promo_score = sum(1 for w in words if w in promo_markers) / total
    avg_word_len = sum(len(w) for w in words) / total

    if promo_score > 0.03:
        return "promotional"
    if casual_score > 0.02:
        return "casual"
    if avg_word_len > 5.5 or question_ratio < 0.1:
        return "formal"
    return "informational"


def writing_style(posts: list[dict]) -> dict[str, Any]:
    texts = [p.get("text", "") for p in posts]
    combined = " ".join(texts)
    return {
        "tone": detect_tone(combined),
        "avg_sentence_length": avg_sentence_length(combined),
        "avg_post_length_words": round(
            sum(len(word_tokenize(t)) for t in texts) / (len(texts) or 1), 2
        ),
        "avg_post_length_chars": round(sum(len(t) for t in texts) / (len(texts) or 1), 2),
    }

# ── Topic / keyword extraction ───────────────────────────────────────────────

# Words that pass stopword filters but carry no topical meaning
_LOW_MEANING: set[str] = {
    "also", "use", "using", "used", "uses", "make", "makes", "made",
    "get", "gets", "got", "getting", "go", "going", "gone", "went",
    "know", "think", "want", "need", "look", "looking", "looks",
    "come", "coming", "take", "taking", "give", "giving", "say",
    "said", "says", "see", "seen", "let", "like", "just", "really",
    "way", "ways", "thing", "things", "time", "times", "day", "days",
    "year", "years", "people", "person", "lot", "lots", "bit",
    "good", "great", "new", "big", "best", "better", "well",
    "right", "sure", "even", "still", "back", "much", "many",
    "every", "always", "never", "often", "already", "ever",
    "actually", "basically", "literally", "definitely", "probably",
    "something", "anything", "everything", "nothing", "someone",
    "anyone", "everyone", "one", "two", "three", "first", "last",
    "next", "able", "mean", "means", "meant", "work", "works",
    "working", "worked", "help", "helps", "helping", "start",
    "started", "starting", "starts", "end", "ended", "ending",
    "put", "puts", "putting", "set", "sets", "setting", "run",
    "runs", "running", "ran", "keep", "keeps", "keeping", "kept",
    "show", "shows", "showing", "shown", "feel", "feels", "feeling",
    "try", "tries", "trying", "tried", "move", "moves", "moving",
    "build", "builds", "building", "built", "add", "adds", "adding",
    "added", "turn", "turns", "turning", "turned", "call", "calls",
    "calling", "called", "ask", "asks", "asking", "asked",
    "post", "posts", "share", "shares", "sharing", "shared",
    "follow", "follows", "following", "followed", "check", "checks",
    "checking", "checked", "read", "reads", "reading",
}

# Bigram/trigram pairs that are structurally noise (e.g. "last year", "every day")
_NOISE_NGRAM_WORDS: set[str] = _LOW_MEANING | _STOP_WORDS


def _is_meaningful_token(token: str) -> bool:
    """Return True if a single token is worth including in an n-gram."""
    return (
        token.isalpha()
        and len(token) > 2
        and token not in _STOP_WORDS
        and token not in _LOW_MEANING
    )


def _is_meaningful_ngram(ngram: tuple[str, ...]) -> bool:
    """All tokens in the n-gram must be meaningful."""
    return all(_is_meaningful_token(t) for t in ngram)


def _format_topic(ngram: tuple[str, ...]) -> str:
    """
    Convert a token tuple to a readable topic string.
    Preserves known acronyms/abbreviations in uppercase; lowercases the rest.
    e.g. ("RAG", "pipelines") -> "RAG pipelines"
         ("multi", "agent", "systems") -> "multi-agent systems"
    """
    _ACRONYMS = {
        "ai", "ml", "rag", "llm", "llms", "api", "apis", "nlp",
        "seo", "roi", "kpi", "b2b", "b2c", "saas", "ui", "ux",
        "gpt", "cv", "sql", "orm", "sdk", "cli",
    }
    formatted = []
    for token in ngram:
        if token.lower() in _ACRONYMS:
            formatted.append(token.upper())
        else:
            formatted.append(token.lower())
    return " ".join(formatted)


def extract_keywords(texts: list[str], top_n: int = 10) -> list[str]:
    """
    Extract top n-gram topics from a list of texts.

    Strategy
    --------
    1. Tokenize and filter stopwords + low-meaning words.
    2. Count bigrams and trigrams across all texts (min frequency = 2,
       or 1 if corpus is tiny).
    3. Re-rank by TF-IDF score when corpus is large enough.
    4. Fall back to meaningful unigrams if n-gram pool is too small.
    5. Return human-readable topic strings like "RAG pipelines".
    """
    if not texts:
        return []

    cleaned = [clean_text(t) for t in texts]
    min_freq = 2 if len(cleaned) >= 4 else 1

    # ── Step 1: tokenize each doc into meaningful tokens ─────────────────
    tokenized: list[list[str]] = [
        [t for t in word_tokenize(doc) if _is_meaningful_token(t)]
        for doc in cleaned
    ]

    # ── Step 2: count bigrams and trigrams ────────────────────────────────
    ngram_counter: Counter = Counter()
    for tokens in tokenized:
        for n in (3, 2):
            for i in range(len(tokens) - n + 1):
                gram = tuple(tokens[i : i + n])
                if _is_meaningful_ngram(gram):
                    ngram_counter[gram] += 1

    # Apply minimum frequency threshold
    qualified = {gram: cnt for gram, cnt in ngram_counter.items() if cnt >= min_freq}

    # ── Step 3: TF-IDF re-ranking when corpus is large enough ────────────
    if len(cleaned) >= 2:
        try:
            vec = TfidfVectorizer(
                stop_words=list(_STOP_WORDS | _LOW_MEANING),
                max_features=300,
                ngram_range=(2, 3),
                token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
                min_df=min_freq,
            )
            tfidf_matrix = vec.fit_transform(cleaned)
            scores = dict(zip(
                vec.get_feature_names_out(),
                tfidf_matrix.sum(axis=0).A1,
            ))
            # Boost qualified n-grams by their TF-IDF score
            ranked = sorted(
                qualified.items(),
                key=lambda item: scores.get(" ".join(item[0]), 0) * item[1],
                reverse=True,
            )
        except ValueError:
            ranked = sorted(qualified.items(), key=lambda x: x[1], reverse=True)
    else:
        ranked = sorted(qualified.items(), key=lambda x: x[1], reverse=True)

    topics = [_format_topic(gram) for gram, _ in ranked[:top_n]]

    # ── Step 4: pad with meaningful unigrams if n-gram pool is thin ───────
    if len(topics) < top_n:
        uni_counter: Counter = Counter(
            token for tokens in tokenized for token in tokens
        )
        existing_words = {w for topic in topics for w in topic.lower().split()}
        for token, _ in uni_counter.most_common(top_n * 3):
            if token not in existing_words and len(topics) < top_n:
                topics.append(_format_topic((token,)))
                existing_words.add(token)

    return topics


def topic_clusters(posts: list[dict], top_n: int = 10) -> dict[str, Any]:
    texts = [p.get("text", "") for p in posts]
    keywords = extract_keywords(texts, top_n=top_n)

    # Cluster by first meaningful word of each topic
    clusters: dict[str, list[str]] = {}
    for topic in keywords:
        words = topic.split()
        # Skip acronyms as cluster labels — use the next word if available
        label = words[0]
        if len(words) > 1 and label.isupper():
            label = words[1]
        clusters.setdefault(label, []).append(topic)

    return {
        "top_keywords": keywords,
        "clusters": clusters,
    }

# ── Engagement ───────────────────────────────────────────────────────────────

def engagement_summary(posts: list[dict]) -> dict[str, Any]:
    """
    Expects each post to optionally have: likes, comments, shares, views.
    """
    def _get(post: dict, key: str) -> float:
        return float(post.get(key, 0) or 0)

    if not posts:
        return {}

    total_likes = sum(_get(p, "likes") for p in posts)
    total_comments = sum(_get(p, "comments") for p in posts)
    total_shares = sum(_get(p, "shares") for p in posts)
    total_views = sum(_get(p, "views") for p in posts)
    n = len(posts)

    engagement_rates = []
    for p in posts:
        interactions = _get(p, "likes") + _get(p, "comments") + _get(p, "shares")
        views = _get(p, "views") or 1
        engagement_rates.append(interactions / views)

    return {
        "total_posts": n,
        "total_likes": int(total_likes),
        "total_comments": int(total_comments),
        "total_shares": int(total_shares),
        "total_views": int(total_views),
        "avg_likes": round(total_likes / n, 2),
        "avg_comments": round(total_comments / n, 2),
        "avg_shares": round(total_shares / n, 2),
        "avg_engagement_rate": round(sum(engagement_rates) / n * 100, 4),
        "top_post": max(posts, key=lambda p: _get(p, "likes") + _get(p, "comments") + _get(p, "shares"), default=None),
    }

# ── Posting frequency ────────────────────────────────────────────────────────

def posting_frequency(posts: list[dict]) -> dict[str, Any]:
    """
    Expects each post to have a 'timestamp' field (ISO 8601 string or datetime).
    """
    from dateutil import parser as dtparser
    from datetime import timezone

    if not posts:
        return {}

    timestamps = []
    for p in posts:
        ts = p.get("timestamp")
        if ts:
            try:
                dt = dtparser.parse(str(ts))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                timestamps.append(dt)
            except (ValueError, TypeError):
                pass

    if not timestamps:
        return {"note": "No valid timestamps found"}

    timestamps.sort()
    span_days = (timestamps[-1] - timestamps[0]).days or 1

    hour_dist = Counter(dt.hour for dt in timestamps)
    weekday_dist = Counter(dt.strftime("%A") for dt in timestamps)

    return {
        "total_posts": len(timestamps),
        "span_days": span_days,
        "posts_per_day": round(len(timestamps) / span_days, 2),
        "posts_per_week": round(len(timestamps) / span_days * 7, 2),
        "peak_hour_utc": max(hour_dist, key=hour_dist.get),
        "peak_weekday": max(weekday_dist, key=weekday_dist.get),
        "hour_distribution": dict(sorted(hour_dist.items())),
        "weekday_distribution": dict(weekday_dist),
    }
