import hashlib
import json

from django.conf import settings
from django.db import transaction
from pgvector.django import CosineDistance

from .models import DocumentChunk, FigurePassageAssociation
from .rag import DocumentChunkService, get_embedding_encoder


class IndexingError(RuntimeError):
    pass


class DocumentIndexingService:
    def __init__(self, encoder=None):
        self.encoder = encoder or get_embedding_encoder()

    def index_document(self, extracted_document):
        chunks = DocumentChunkService().build_chunks(extracted_document)
        if not chunks:
            raise IndexingError('Aucun passage exploitable n’a pu être produit.')

        model_name = getattr(settings, 'RAG_EMBEDDING_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2')
        payload = json.dumps({
            'document_id': str(extracted_document.document_id),
            'extraction_id': extracted_document.id,
            'model': model_name,
            'chunks': chunks,
        }, sort_keys=True, ensure_ascii=False)
        generation = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]

        try:
            vectors = self.encoder.encode([chunk['text'] for chunk in chunks])
        except Exception as exc:
            raise IndexingError(str(exc)) from exc

        expected = getattr(settings, 'RAG_EMBEDDING_DIMENSIONS', 384)
        if len(vectors) != len(chunks) or any(len(vector) != expected for vector in vectors):
            raise IndexingError('La dimension ou le nombre des embeddings est invalide.')

        try:
            with transaction.atomic():
                DocumentChunk.objects.filter(document=extracted_document.document).delete()
                for chunk, vector in zip(chunks, vectors):
                    DocumentChunk.objects.create(
                        id=chunk['chunk_id'],
                        extracted_document=extracted_document,
                        document=extracted_document.document,
                        text=chunk['text'],
                        page_start=chunk['page_start'],
                        page_end=chunk['page_end'],
                        section_title=chunk['section_title'],
                        block_ids=chunk['block_ids'],
                        hierarchy=chunk['hierarchy'],
                        figure_refs=chunk['figure_refs'],
                        embedding=vector,
                        embedding_model=model_name,
                        generation=generation,
                    )
        except Exception as exc:
            raise IndexingError('Impossible de persister les passages indexés.') from exc

        return generation, len(chunks)


class DocumentSearchService:
    def __init__(self, encoder=None):
        self.encoder = encoder or get_embedding_encoder()

    def search(self, document, query, page_range=None, top_k=5):
        model_name = getattr(settings, 'RAG_EMBEDDING_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2')
        chunks = DocumentChunk.objects.filter(document=document, embedding_model=model_name)
        if not chunks.exists():
            return {'status': 'not_indexed', 'results': []}

        if page_range:
            start = page_range.get('start')
            end = page_range.get('end')
            if start is not None:
                chunks = chunks.filter(page_end__gte=start)
            if end is not None:
                chunks = chunks.filter(page_start__lte=end)

        try:
            query_vector = self.encoder.encode([query])[0]
        except Exception as exc:
            raise IndexingError(str(exc)) from exc

        chunks = list(chunks)
        if not chunks:
            return {'status': 'no_results', 'results': []}

        if getattr(settings, 'DATABASES', {}).get('default', {}).get('ENGINE', '').endswith('postgresql'):
            qs = DocumentChunk.objects.filter(document=document, embedding_model=model_name)
            if page_range:
                start, end = page_range.get('start'), page_range.get('end')
                if start is not None:
                    qs = qs.filter(page_end__gte=start)
                if end is not None:
                    qs = qs.filter(page_start__lte=end)
            ranked = list(qs.annotate(distance=CosineDistance('embedding', query_vector)).order_by('distance')[:top_k])
            for chunk in ranked:
                chunk.relevance_score = max(0.0, min(1.0, 1.0 - float(chunk.distance)))
        else:
            ranked = []
            for chunk in chunks:
                vector = list(chunk.embedding) if not isinstance(chunk.embedding, str) else json.loads(chunk.embedding)
                score = self._cosine(query_vector, vector)
                ranked.append((chunk, score))
            ranked = [item for item in sorted(ranked, key=lambda item: item[1], reverse=True)[:top_k]]
            for chunk, score in ranked:
                chunk.relevance_score = score
            ranked = [chunk for chunk, _ in ranked]

        threshold = getattr(settings, 'RAG_RELEVANCE_THRESHOLD', 0.20)
        relevant = [chunk for chunk in ranked if chunk.relevance_score >= threshold]
        status = 'ok' if relevant else 'insufficient_results'
        return {'status': status, 'results': relevant}

    @staticmethod
    def _cosine(left, right):
        if not left or not right or len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = sum(a * a for a in left) ** 0.5
        right_norm = sum(b * b for b in right) ** 0.5
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)


def build_visual_assets(chunk):
    extracted = chunk.extracted_document
    block_ids = set(chunk.block_ids)
    associations = (FigurePassageAssociation.objects
                    .filter(extracted_document=extracted, passage_block_id__in=block_ids)
                    .exclude(confidence=FigurePassageAssociation.Confidence.LOW)
                    .select_related('figure'))

    assets = []
    seen = set()
    for association in associations:
        figure = association.figure
        if figure.id in seen:
            continue
        seen.add(figure.id)
        assets.append({
            'asset_id': str(figure.id),
            'page': figure.page_index,
            'caption': figure.caption,
            'access_path': f'/api/documents/{chunk.document_id}/assets/{figure.id}',
        })
    return assets
