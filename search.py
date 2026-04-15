"""Hybrid search functionality (semantic + keyword + reranking)."""
import re
import os
import logging
from pathlib import Path
from typing import Optional
from functools import lru_cache

from google import genai
from openai import OpenAI

from config import (
    OPENAI_API_KEY,
    GEMINI_API_KEY,
    EMBEDDING_PROVIDER,
    OPENAI_EMBEDDING_MODEL,
    GEMINI_EMBEDDING_MODEL,
    VAULT_PATH,
    GPT_MODEL,
    RERANKER_MODEL,
    USE_RERANKER
)
from embeddings import get_chroma_client, get_collection, get_gemini_client

# Lazy load reranker to avoid slow startup
_reranker = None
_reranker_loading = False

# Cache for query embeddings (max 100 recent queries)
@lru_cache(maxsize=100)
def _cached_query_embedding(query: str, provider: str) -> tuple:
    """Cache query embeddings to avoid redundant API calls."""
    return tuple(create_query_embedding_uncached(query))


def get_reranker(show_status: bool = True):
    """Get cross-encoder reranker (lazy loaded)."""
    global _reranker, _reranker_loading
    if _reranker is None and USE_RERANKER and not _reranker_loading:
        _reranker_loading = True
        try:
            # Suppress verbose HF/transformers output
            logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
            logging.getLogger("transformers").setLevel(logging.WARNING)
            os.environ["TOKENIZERS_PARALLELISM"] = "false"

            if show_status:
                from rich.console import Console
                console = Console()
                with console.status("[dim]Loading reranker model...[/dim]", spinner="dots"):
                    from sentence_transformers import CrossEncoder
                    _reranker = CrossEncoder(RERANKER_MODEL, trust_remote_code=True)
            else:
                from sentence_transformers import CrossEncoder
                _reranker = CrossEncoder(RERANKER_MODEL, trust_remote_code=True)
        except Exception as e:
            print(f"Warning: Could not load reranker: {e}")
            return None
        finally:
            _reranker_loading = False
    return _reranker


def rerank_results(query: str, results: list[dict], top_k: int = None) -> list[dict]:
    """
    Rerank results using a cross-encoder for better accuracy.

    Cross-encoders are more accurate than bi-encoders (embeddings) because
    they see query and document together.
    """
    reranker = get_reranker()
    if reranker is None or not results:
        return results

    # Prepare pairs for cross-encoder
    pairs = [(query, r["content"]) for r in results]

    # Get scores
    scores = reranker.predict(pairs)

    # Attach scores and sort
    for i, score in enumerate(scores):
        results[i]["rerank_score"] = float(score)

    reranked = sorted(results, key=lambda x: x.get("rerank_score", 0), reverse=True)

    # Normalize scores
    if reranked:
        max_score = max(r.get("rerank_score", 0) for r in reranked)
        min_score = min(r.get("rerank_score", 0) for r in reranked)
        score_range = max_score - min_score if max_score != min_score else 1
        for r in reranked:
            r["score"] = (r.get("rerank_score", 0) - min_score) / score_range

    if top_k:
        return reranked[:top_k]
    return reranked


def create_query_embedding_uncached(query: str) -> list[float]:
    """Create embedding for a query (uncached version)."""
    if EMBEDDING_PROVIDER == "openai":
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.embeddings.create(
            model=OPENAI_EMBEDDING_MODEL,
            input=query
        )
        return response.data[0].embedding
    else:
        client = get_gemini_client()
        result = client.models.embed_content(
            model=GEMINI_EMBEDDING_MODEL,
            contents=query,
        )
        return result.embeddings[0].values


def create_query_embedding(query: str) -> list[float]:
    """Create embedding for a query using configured provider (cached)."""
    # Use cached version - converts tuple back to list
    return list(_cached_query_embedding(query, EMBEDDING_PROVIDER))


def extract_keywords(query: str) -> list[str]:
    """Extract important keywords from a query for keyword search."""
    # Remove common words
    stopwords = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "must", "shall", "can", "need", "dare",
        "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by",
        "from", "as", "into", "through", "during", "before", "after", "above",
        "below", "between", "under", "again", "further", "then", "once", "here",
        "there", "when", "where", "why", "how", "all", "each", "few", "more",
        "most", "other", "some", "such", "no", "nor", "not", "only", "own",
        "same", "so", "than", "too", "very", "just", "and", "but", "if", "or",
        "because", "until", "while", "about", "against", "between", "into",
        "through", "during", "before", "after", "above", "below", "up", "down",
        "out", "off", "over", "under", "again", "further", "then", "once",
        "what", "which", "who", "whom", "this", "that", "these", "those", "am",
        "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
        "your", "yours", "yourself", "yourselves", "he", "him", "his", "himself",
        "she", "her", "hers", "herself", "it", "its", "itself", "they", "them",
        "their", "theirs", "themselves", "tell", "know", "find", "give", "get"
    }

    # Extract words, keep proper nouns (capitalized) and longer words
    words = re.findall(r'\b[A-Za-z]+\b', query)
    keywords = []

    for word in words:
        lower = word.lower()
        # Keep if: not a stopword AND (capitalized OR longer than 3 chars)
        if lower not in stopwords and (word[0].isupper() or len(word) > 3):
            keywords.append(word)

    return keywords


def keyword_search(
    keywords: list[str],
    collection,
    n_results: int = 20,
    file_filter: Optional[str] = None
) -> list[dict]:
    """Search using keyword matching."""
    if not keywords:
        return []

    results = []
    seen_ids = set()

    # Search for each keyword
    for keyword in keywords[:5]:  # Limit to top 5 keywords
        try:
            where_doc = {"$contains": keyword}
            where_meta = {"file_path": {"$contains": file_filter}} if file_filter else None

            keyword_results = collection.get(
                where_document=where_doc,
                where=where_meta,
                include=["documents", "metadatas"],
                limit=n_results
            )

            if keyword_results["ids"]:
                for i, id_ in enumerate(keyword_results["ids"]):
                    if id_ not in seen_ids:
                        seen_ids.add(id_)
                        # Score based on keyword frequency in document
                        doc = keyword_results["documents"][i]
                        freq = doc.lower().count(keyword.lower())
                        score = min(freq * 0.1, 1.0)  # Cap at 1.0

                        results.append({
                            "id": id_,
                            "content": doc,
                            "file_path": keyword_results["metadatas"][i].get("file_path", ""),
                            "file_name": keyword_results["metadatas"][i].get("file_name", ""),
                            "header": keyword_results["metadatas"][i].get("header", ""),
                            "score": score,
                            "match_type": "keyword"
                        })
        except Exception:
            continue

    return results


def semantic_search(
    query: str,
    collection,
    n_results: int = 20,
    file_filter: Optional[str] = None
) -> list[dict]:
    """Search using semantic similarity."""
    query_embedding = create_query_embedding(query)

    where_filter = None
    if file_filter:
        where_filter = {"file_path": {"$contains": file_filter}}

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where=where_filter,
        include=["documents", "metadatas", "distances"]
    )

    formatted = []
    if results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            score = 1 - results["distances"][0][i]
            formatted.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "file_path": results["metadatas"][0][i].get("file_path", ""),
                "file_name": results["metadatas"][0][i].get("file_name", ""),
                "header": results["metadatas"][0][i].get("header", ""),
                "score": score,
                "match_type": "semantic"
            })

    return formatted


def reciprocal_rank_fusion(
    result_lists: list[list[dict]],
    k: int = 60
) -> list[dict]:
    """
    Combine multiple result lists using Reciprocal Rank Fusion.

    RRF score = sum(1 / (k + rank)) for each list the doc appears in
    """
    scores = {}
    docs = {}

    for results in result_lists:
        for rank, doc in enumerate(results):
            doc_id = doc["id"]
            if doc_id not in scores:
                scores[doc_id] = 0
                docs[doc_id] = doc
            scores[doc_id] += 1 / (k + rank + 1)

    # Sort by RRF score
    sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

    # Return merged results with combined score
    merged = []
    for doc_id in sorted_ids:
        doc = docs[doc_id].copy()
        doc["score"] = scores[doc_id]
        merged.append(doc)

    return merged


def search(
    query: str,
    n_results: int = 10,
    file_filter: Optional[str] = None,
    hybrid: bool = True,
    rerank: bool = True
) -> list[dict]:
    """
    Hybrid search combining semantic and keyword search with optional reranking.

    Args:
        query: Search query
        n_results: Number of results to return
        file_filter: Optional filter for file paths (partial match)
        hybrid: Use hybrid search (semantic + keyword). Set False for semantic only.
        rerank: Use cross-encoder reranking for better accuracy.

    Returns:
        List of search results with content and metadata
    """
    chroma_client = get_chroma_client()
    collection = get_collection(chroma_client)

    # Fetch more candidates if we're going to rerank
    fetch_multiplier = 3 if (rerank and USE_RERANKER) else 2

    # Semantic search (always do this)
    semantic_results = semantic_search(
        query, collection, n_results=n_results * fetch_multiplier, file_filter=file_filter
    )

    if not hybrid:
        results = semantic_results
    else:
        # Keyword search
        keywords = extract_keywords(query)
        keyword_results = keyword_search(
            keywords, collection, n_results=n_results * fetch_multiplier, file_filter=file_filter
        )

        # Combine with RRF
        if keyword_results:
            merged = reciprocal_rank_fusion([semantic_results, keyword_results])
            # Normalize scores to 0-1 range
            if merged:
                max_score = merged[0]["score"]
                for doc in merged:
                    doc["score"] = doc["score"] / max_score
            results = merged
        else:
            results = semantic_results

    # Rerank with cross-encoder for better accuracy
    if rerank and USE_RERANKER and results:
        results = rerank_results(query, results[:n_results * 2], top_k=n_results)
    else:
        results = results[:n_results]

    return results


def get_full_note(file_path: str) -> Optional[str]:
    """Get the full content of a note."""
    full_path = VAULT_PATH / file_path
    if full_path.exists():
        return full_path.read_text(encoding="utf-8")
    return None


def find_related(file_path: str, n_results: int = 5) -> list[dict]:
    """Find notes related to a given note."""
    content = get_full_note(file_path)
    if not content:
        return []

    # Use first 1000 chars as query
    query = content[:1000]

    results = search(query, n_results=n_results + 1)

    # Filter out the source file
    return [r for r in results if r["file_path"] != file_path][:n_results]
