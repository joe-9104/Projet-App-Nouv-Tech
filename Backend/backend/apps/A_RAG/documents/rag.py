import hashlib
import json
import math
import re

from django.conf import settings


class DocumentChunkService:
    TARGET_CHARS = 800
    MAX_CHARS = 1600

    def build_chunks(self, extracted_document):
        normalized = extracted_document.normalized_content or {}
        pages = normalized.get('pages', [])
        hierarchy = []
        sections = []
        current_section = None
        blocks_for_chunk = []
        chunk_data = []

        def flush():
            nonlocal blocks_for_chunk
            if not blocks_for_chunk:
                return
            texts = []
            block_ids = []
            figure_refs = []
            page_start = page_end = None
            for page_index, block in blocks_for_chunk:
                text = self._block_text(block)
                if text:
                    texts.append(text)
                block_id = block.get('block_id')
                if not block_id:
                    source_index = block.get('source_index', block.get('index'))
                    if source_index is not None:
                        block_id = f"blk_{page_index}_{source_index}"
                if block_id:
                    block_ids.append(block_id)
                for ref in block.get('figure_refs', []) or block.get('visual_asset_ids', []) or []:
                    if ref not in figure_refs:
                        figure_refs.append(ref)
                page_start = page_index if page_start is None else min(page_start, page_index)
                page_end = page_index if page_end is None else max(page_end, page_index)
            full_text = '\n'.join(texts).strip()
            if full_text:
                chunk_data.extend(self._split_large_text(full_text, block_ids, page_start, page_end,
                                                        current_section, figure_refs, extracted_document.document_id))
            blocks_for_chunk = []

        for page in pages:
            page_index = int(page.get('page_index', len(sections)))
            for block in page.get('blocks', []):
                block_type = str(block.get('type', '')).lower()
                content = block.get('content')
                level = block.get('level')
                if block_type in ('title', 'subtitle', 'heading'):
                    flush()
                    title = self._block_text(block)
                    if title:
                        section_level = int(level) if isinstance(level, int) else (1 if block_type == 'title' else 2)
                        while hierarchy and hierarchy[-1][0] >= section_level:
                            hierarchy.pop()
                        hierarchy.append((section_level, title))
                        current_section = title
                        sections.append(title)
                    continue
                if not self._block_text(block):
                    continue
                blocks_for_chunk.append((page_index, block))
                if sum(len(self._block_text(b)) for _, b in blocks_for_chunk) >= self.MAX_CHARS:
                    flush()
        flush()

        return chunk_data

    def _split_large_text(self, text, block_ids, page_start, page_end, section_title, figure_refs, document_id):
        text = re.sub(r'\n{3,}', '\n\n', text).strip()
        pieces = []
        start = 0
        while start < len(text):
            if len(text) - start <= self.MAX_CHARS:
                piece = text[start:].strip()
                end = len(text)
            else:
                target_end = min(start + self.TARGET_CHARS, len(text))
                limit_end = min(start + self.MAX_CHARS, len(text))
                candidate = text.rfind('\n', target_end, limit_end)
                if candidate == -1:
                    candidate = max(text.rfind('. ', target_end, limit_end),
                                    text.rfind('! ', target_end, limit_end),
                                    text.rfind('? ', target_end, limit_end))
                end = candidate + (1 if candidate >= 0 and text[candidate] == '.' else 0)
                if end <= start:
                    end = limit_end
                piece = text[start:end].strip()

            if piece:
                source = {
                    'document_id': str(document_id),
                    'page_start': page_start,
                    'page_end': page_end,
                    'section_title': section_title,
                    'block_ids': block_ids,
                    'hierarchy': [title for _, title in self._last_hierarchy(section_title)],
                    'figure_refs': figure_refs,
                }
                payload = json.dumps(source, sort_keys=True, ensure_ascii=False)
                chunk_id = 'chk_' + hashlib.sha256((payload + '\n' + piece).encode('utf-8')).hexdigest()[:24]
                pieces.append({'chunk_id': chunk_id, 'text': piece, **source})
            start = end
        return pieces

    def _last_hierarchy(self, section_title):
        return [(1, section_title)] if section_title else []

    def _block_text(self, block):
        content = block.get('content')
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return '\n'.join(str(item) for item in content if item is not None).strip()
        if isinstance(content, dict):
            return str(content.get('text') or content.get('content') or '').strip()
        return str(content).strip() if content is not None else ''


class SentenceTransformerEncoder:
    def __init__(self, model_name=None):
        self.model_name = model_name or getattr(settings, 'RAG_EMBEDDING_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2')
        self._model = None

    def encode(self, texts):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError('Le moteur d’embeddings sentence-transformers n’est pas installé.') from exc
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() if hasattr(v, 'tolist') else list(v) for v in vectors]


def get_embedding_encoder():
    import os
    model_name = getattr(settings, 'RAG_EMBEDDING_MODEL', 'paraphrase-multilingual-MiniLM-L12-v2')
    return SentenceTransformerEncoder(model_name)
