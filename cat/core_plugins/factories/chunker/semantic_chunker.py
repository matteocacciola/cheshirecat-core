from collections import defaultdict
from typing import List, Dict, Any
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


class SemanticChunker:
    def __init__(self, model_name, max_tokens, cluster_threshold, similarity_threshold):
        self.device = (
            "cuda" if torch.cuda.is_available() else
            "mps" if torch.backends.mps.is_available() else
            "cpu"
        )
        self.model = SentenceTransformer(model_name, device=self.device)
        self.max_tokens = max_tokens
        self.cluster_threshold = cluster_threshold
        self.similarity_threshold = similarity_threshold
        self.tokenizer = self.model.tokenizer if hasattr(self.model, "tokenizer") else None

    def chunk(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def find(x: int):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int):
            parent[find(x)] = find(y)

        # calculate embeddings
        if not chunks:
            embeddings = np.array([])
        else:
            texts = [chunk["text"] for chunk in chunks]
            embeddings = np.array(self.model.encode(texts, show_progress_bar=False))

        # compute similarity
        similarity_matrix = np.zeros((0, 0)) if embeddings.size == 0 else cosine_similarity(embeddings)

        # calculate clusters
        n = similarity_matrix.shape[0]
        parent = list(range(n))

        for i in range(n):
            for j in range(i + 1, n):
                if similarity_matrix[i, j] >= self.cluster_threshold:
                    union(i, j)

        clusters = [find(i) for i in range(n)]
        cluster_map = {cid: idx for idx, cid in enumerate(sorted(set(clusters)))}
        clusters = [cluster_map[c] for c in clusters]

        # merge chunks
        if not chunks or not clusters:
            return []

        cluster_map = defaultdict(list)
        for idx, cluster_id in enumerate(clusters):
            cluster_map[cluster_id].append(chunks[idx])

        merged_chunks = []
        for chunk_list in cluster_map.values():
            current_text = ""
            current_meta = []

            for chunk in chunk_list:
                next_text = (current_text + " " + chunk["text"]).strip()
                num_tokens = len(self.tokenizer.encode(next_text)) if self.tokenizer else len(next_text.split())

                if current_text and num_tokens > self.max_tokens:
                    merged_chunks.append({
                        "text": current_text,
                        "metadata": current_meta
                    })
                    current_text = chunk["text"]
                    current_meta = [chunk]
                else:
                    current_text = next_text
                    current_meta.append(chunk)

            if current_text:
                merged_chunks.append({
                    "text": current_text,
                    "metadata": current_meta
                })

        return merged_chunks
