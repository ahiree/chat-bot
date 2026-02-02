import numpy as np
from sentence_transformers import SentenceTransformer
import re
from typing import List, Dict
import pickle

# Load embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Session-based storage
session_documents = {}  # {session_id: [chunks]}
session_embeddings = {}  # {session_id: [embeddings]}
session_metadata = {}  # {session_id: [metadata]}


def process_document_text_with_storage(text, doc_id, session_id, doc_name=""):
    """
    Process document and store embeddings with session association
    """
    # Initialize session storage if needed
    if session_id not in session_documents:
        session_documents[session_id] = []
        session_embeddings[session_id] = []
        session_metadata[session_id] = []
    
    # Clean text
    text = clean_text(text)
    
    # Create chunks
    chunks = split_text_intelligent(text)
    
    for idx, chunk in enumerate(chunks):
        # Generate normalized embedding
        emb = model.encode(chunk, convert_to_numpy=True, normalize_embeddings=True)
        
        # Store in session
        session_documents[session_id].append(chunk)
        session_embeddings[session_id].append(emb)
        session_metadata[session_id].append({
            'doc_id': doc_id,
            'doc_name': doc_name,
            'chunk_id': idx,
            'char_count': len(chunk)
        })


# Keep original function for backward compatibility
def process_document_text(text, doc_name=""):
    """Original function - uses default session"""
    process_document_text_with_storage(text, "default", "default", doc_name)


def clean_text(text: str) -> str:
    """Clean and normalize text"""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    text = text.replace('ﬁ', 'fi').replace('ﬂ', 'fl')
    return text.strip()


def split_text(text, chunk_size=300):
    """Simple splitting (backward compatibility)"""
    words = text.split()
    return [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]


def split_text_intelligent(text: str, chunk_size=500, overlap=100) -> List[str]:
    """
    Advanced text splitting with semantic boundaries and overlap
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = []
    current_size = 0
    
    for sentence in sentences:
        sentence_words = sentence.split()
        sentence_size = len(sentence_words)
        
        if current_size + sentence_size > chunk_size and current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(chunk_text)
            
            overlap_words = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_words + sentence_words
            current_size = len(current_chunk)
        else:
            current_chunk.extend(sentence_words)
            current_size += sentence_size
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks


def retrieve_chunks(query, session_id=None, top_k=5):
    """
    Retrieve relevant chunks for a specific session
    """
    # Use default session if none provided
    if session_id is None:
        session_id = "default"
    
    # Check if session has documents
    if session_id not in session_embeddings or not session_embeddings[session_id]:
        return ["No document uploaded yet."]
    
    # Generate query embedding
    query_emb = model.encode(query, convert_to_numpy=True, normalize_embeddings=True)
    
    # Calculate similarities for this session
    embeddings = session_embeddings[session_id]
    similarities = np.array([np.dot(query_emb, emb) for emb in embeddings])
    
    # Get top candidates
    num_candidates = min(top_k * 2, len(similarities))
    top_indices = np.argsort(similarities)[-num_candidates:][::-1]
    
    # Re-rank with diversity
    selected_indices = rerank_with_diversity(
        top_indices,
        similarities,
        embeddings,
        top_k
    )
    
    # Return chunks from this session
    documents = session_documents[session_id]
    return [documents[i] for i in selected_indices]


def rerank_with_diversity(
    candidate_indices: np.ndarray,
    similarities: np.ndarray,
    embeddings: List[np.ndarray],
    top_k: int,
    diversity_weight: float = 0.3
) -> List[int]:
    """
    Re-rank results to balance relevance and diversity
    """
    if len(candidate_indices) <= top_k:
        return candidate_indices.tolist()
    
    selected = [candidate_indices[0]]
    remaining = list(candidate_indices[1:])
    
    while len(selected) < top_k and remaining:
        best_idx = None
        best_score = -float('inf')
        
        for idx in remaining:
            relevance = similarities[idx]
            diversity = min([
                1 - np.dot(embeddings[idx], embeddings[sel_idx])
                for sel_idx in selected
            ])
            combined_score = (1 - diversity_weight) * relevance + diversity_weight * diversity
            
            if combined_score > best_score:
                best_score = combined_score
                best_idx = idx
        
        selected.append(best_idx)
        remaining.remove(best_idx)
    
    return selected


def clear_session_documents(session_id):
    """
    Clear all documents and embeddings for a specific session
    """
    if session_id in session_documents:
        del session_documents[session_id]
    if session_id in session_embeddings:
        del session_embeddings[session_id]
    if session_id in session_metadata:
        del session_metadata[session_id]


def clear_document_store():
    """
    Clear all stored documents (all sessions)
    """
    global session_documents, session_embeddings, session_metadata
    session_documents.clear()
    session_embeddings.clear()
    session_metadata.clear()


def get_session_stats(session_id=None):
    """
    Get statistics for a specific session or all sessions
    """
    if session_id:
        if session_id not in session_documents:
            return {
                'session_id': session_id,
                'total_chunks': 0,
                'unique_documents': 0
            }
        
        return {
            'session_id': session_id,
            'total_chunks': len(session_documents[session_id]),
            'unique_documents': len(set(m['doc_id'] for m in session_metadata[session_id]))
        }
    else:
        # Stats for all sessions
        return {
            'total_sessions': len(session_documents),
            'total_chunks': sum(len(chunks) for chunks in session_documents.values()),
            'sessions': list(session_documents.keys())
        }


def get_stats():
    """
    Get overall statistics (backward compatibility)
    """
    return get_session_stats()


# Persistence functions for saving/loading embeddings to database
def serialize_embedding(embedding: np.ndarray) -> bytes:
    """Convert numpy array to bytes for database storage"""
    return pickle.dumps(embedding)


def deserialize_embedding(embedding_bytes: bytes) -> np.ndarray:
    """Convert bytes back to numpy array"""
    return pickle.loads(embedding_bytes)


def load_session_from_database(session_id, document_embeddings):
    """
    Load session data from database DocumentEmbedding objects
    
    Args:
        session_id: The session ID
        document_embeddings: QuerySet of DocumentEmbedding objects for this session
    """
    if session_id not in session_documents:
        session_documents[session_id] = []
        session_embeddings[session_id] = []
        session_metadata[session_id] = []
    
    for emb_obj in document_embeddings:
        # Load chunk text
        session_documents[session_id].append(emb_obj.chunk_text)
        
        # Deserialize embedding
        embedding = deserialize_embedding(emb_obj.embedding_vector)
        session_embeddings[session_id].append(embedding)
        
        # Load metadata
        session_metadata[session_id].append({
            'doc_id': str(emb_obj.document.id),
            'doc_name': emb_obj.document.original_filename,
            'chunk_id': emb_obj.chunk_index,
            'char_count': len(emb_obj.chunk_text)
        })