"""
Hierarchical Text Chunker Plugin for CheshireCat Core

This plugin implements a sophisticated hierarchical chunking strategy that:
1. Preserves document structure (sections, paragraphs, sentences)
2. Maintains semantic coherence within chunks
3. Optimizes for retrieval effectiveness
4. Handles multiple document types intelligently
"""

from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import re
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents.base import Document


def _extract_sections(text: str) -> List[Dict[str, Any]]:
    """
    Extract document sections based on structural markers.
    Handles markdown headers, numbered sections, and visual separators.
    """
    sections = []
    current_section = {
        "title": None,
        "content": [],
        "level": 0,
        "hierarchy": []
    }

    lines = text.split("\n")
    heading_stack = []

    for line in lines:
        # Check for markdown headers
        header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if header_match:
            # Save previous section if it has content
            if current_section["content"]:
                sections.append({
                    **current_section,
                    "content": "\n".join(current_section["content"])
                })

            level = len(header_match.group(1))
            title = header_match.group(2).strip()

            # Maintain heading hierarchy stack
            while heading_stack and heading_stack[-1]["level"] >= level:
                heading_stack.pop()

            heading_stack.append({"level": level, "title": title})

            current_section = {
                "title": title,
                "content": [],
                "level": level,
                "hierarchy": [h["title"] for h in heading_stack]
            }
        else:
            current_section["content"].append(line)

    # Add final section
    if current_section["content"]:
        sections.append({
            **current_section,
            "content": "\n".join(current_section["content"])
        })

    # If no sections found, treat entire text as one section
    if not sections:
        sections = [{
            "title": None,
            "content": text,
            "level": 0,
            "hierarchy": []
        }]

    return sections


class ChunkLevel(Enum):
    """Hierarchy levels for document chunking"""
    DOCUMENT = "document"
    SECTION = "section"
    PARAGRAPH = "paragraph"
    FORMULA = "formula"
    SENTENCE = "sentence"


@dataclass
class ChunkMetadata:
    """Metadata for hierarchical chunks"""
    level: ChunkLevel
    parent_id: str | None = None
    section_title: str | None = None
    position: int = 0
    total_siblings: int = 0
    heading_hierarchy: List[str] = None
    has_formula: bool = False
    formula_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_level": self.level.value,
            "parent_id": self.parent_id,
            "section_title": self.section_title,
            "position": self.position,
            "total_siblings": self.total_siblings,
            "heading_hierarchy": self.heading_hierarchy or [],
            "has_formula": self.has_formula,
            "formula_count": self.formula_count,
        }


class HierarchicalChunker:
    """
    Advanced hierarchical text chunker that maintains document structure
    while optimizing for semantic coherence and retrieval.
    """
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
        max_chunk_size: int = 2000,
        preserve_structure: bool = True
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.preserve_structure = preserve_structure

        # Hierarchical separators ordered by priority
        self.separators = {
            ChunkLevel.SECTION: [
                r"\n#{1,6}\s+.+\n",  # Markdown headers
                r"\n={3,}\n",  # Section dividers
                r"\n-{3,}\n",
                r"\n\s*(?:Chapter|Section|Part)\s+\d+",  # Numbered sections
            ],
            ChunkLevel.PARAGRAPH: [
                "\n\n\n",  # Multiple newlines
                "\n\n",  # Paragraph breaks
            ],
            ChunkLevel.SENTENCE: [
                ". ",
                "! ",
                "? ",
                "。",  # Chinese/Japanese period
                "！",
                "？",
            ]
        }

    def chunk_document(self, text: str, metadata: Dict | None = None) -> List[Document]:
        """
        Main entry point for hierarchical chunking.

        Args:
            text: Input text to chunk
            metadata: Optional metadata to include in chunks

        Returns:
            List of Document objects with hierarchical metadata
        """
        if not text or len(text.strip()) == 0:
            return []

        metadata = metadata or {}
        chunks = []

        # Level 1: Extract document structure
        sections = _extract_sections(text)

        # Level 2: Process each section hierarchically
        for section_idx, section in enumerate(sections):
            section_chunks = self._process_section(
                section,
                section_idx,
                len(sections),
                metadata,
            )
            chunks.extend(section_chunks)

        return chunks

    def _process_section(
        self,
        section: Dict[str, Any],
        section_idx: int,
        total_sections: int,
        base_metadata: Dict,
        formula_map: Dict[str, str] | None = None
    ) -> List[Document]:
        """
        Process a section into optimally sized chunks while preserving context.
        """
        content = section["content"]

        # If section is small enough, keep as single chunk
        if len(content) <= self.max_chunk_size:
            metadata = ChunkMetadata(
                level=ChunkLevel.SECTION,
                section_title=section["title"],
                position=section_idx,
                total_siblings=total_sections,
                heading_hierarchy=section["hierarchy"]
            )

            doc = Document(
                page_content=content,
                metadata={**base_metadata, **metadata.to_dict()}
            )
            return [doc]

        # Split large sections into paragraphs
        paragraphs = self._split_by_paragraphs(content)

        # Recursively chunk paragraphs
        para_chunks = []
        for para_idx, paragraph in enumerate(paragraphs):
            para_chunks.extend(
                self._process_paragraph(
                    paragraph,
                    para_idx,
                    len(paragraphs),
                    section,
                    section_idx,
                    base_metadata
                )
            )

        return para_chunks

    def _split_by_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs while preserving meaningful breaks."""
        # Split on double newlines but preserve some context
        paragraphs = re.split(r"\n\n+", text)

        # Filter out empty paragraphs and strip whitespace
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        return paragraphs

    def _process_paragraph(
        self,
        paragraph: str,
        para_idx: int,
        total_paras: int,
        section: Dict[str, Any],
        section_idx: int,
        base_metadata: Dict
    ) -> List[Document]:
        """
        Process a paragraph, potentially splitting it further if needed.
        """
        # If paragraph is within limits, return as single chunk
        if self.min_chunk_size <= len(paragraph) <= self.max_chunk_size:
            metadata = ChunkMetadata(
                level=ChunkLevel.PARAGRAPH,
                parent_id=f"section_{section_idx}",
                section_title=section["title"],
                position=para_idx,
                total_siblings=total_paras,
                heading_hierarchy=section["hierarchy"]
            )

            # Add section context to paragraph if available
            content = paragraph
            if section["title"] and self.preserve_structure:
                content = f"[Section: {section['title']}]\n\n{paragraph}"

            doc = Document(
                page_content=content,
                metadata={**base_metadata, **metadata.to_dict()}
            )
            return [doc]

        # For very large paragraphs, use recursive splitting
        if len(paragraph) > self.max_chunk_size:
            return self._recursive_split(
                paragraph,
                section,
                section_idx,
                para_idx,
                base_metadata
            )

        # Paragraph is too small, will be merged in post-processing
        return []

    def _recursive_split(
        self,
        text: str,
        section: Dict[str, Any],
        section_idx: int,
        para_idx: int,
        base_metadata: Dict
    ) -> List[Document]:
        """
        Use recursive character splitting for large chunks while maintaining context.
        """
        # Custom recursive splitter with overlap for context preservation
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

        splits = splitter.split_text(text)
        documents = []

        for idx, split in enumerate(splits):
            metadata = ChunkMetadata(
                level=ChunkLevel.SENTENCE,
                parent_id=f"section_{section_idx}_para_{para_idx}",
                section_title=section["title"],
                position=idx,
                total_siblings=len(splits),
                heading_hierarchy=section["hierarchy"]
            )

            # Add hierarchical context
            content = split
            if section["title"] and self.preserve_structure:
                context_prefix = f"[Section: {section['title']}]\n\n"
                content = context_prefix + split

            doc = Document(
                page_content=content,
                metadata={**base_metadata, **metadata.to_dict()}
            )
            documents.append(doc)

        return documents


class MathAwareHierarchicalChunker:
    """
    Math-aware hierarchical chunker that:
    1. Detects and preserves mathematical formulas
    2. Maintains document structure
    3. Keeps formulas with surrounding context
    4. Handles multimodal content
    """
    # Formula patterns
    DISPLAY_FORMULA = r"\$\$(.*?)\$\$"
    INLINE_FORMULA = r"(?<!\$)\$(?!\$)(.*?)\$(?!\$)"
    LATEX_ENV = r"\\begin\{(equation|align|gather|multiline)\*?\}(.*?)\\end\{\1\*?\}"

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
        max_chunk_size: int = 2000,
        formula_context_window: int = 300,
        preserve_structure: bool = True
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.formula_context_window = formula_context_window
        self.preserve_structure = preserve_structure

    def chunk_document(
        self,
        text: str,
        metadata: Dict | None = None
    ) -> List[Document]:
        """Main entry point for math-aware chunking"""
        if not text or len(text.strip()) == 0:
            return []

        metadata = metadata or {}

        # Detect and protect formulas
        protected_text, formula_map = self._protect_formulas(text)

        # Extract document structure
        sections = _extract_sections(protected_text)

        # Process each section
        chunks = []
        for section_idx, section in enumerate(sections):
            section_chunks = self._process_section(
                section,
                section_idx,
                len(sections),
                metadata,
                formula_map,
            )
            chunks.extend(section_chunks)

        return chunks

    def _protect_formulas(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Replace formulas with placeholders to prevent splitting.
        Returns (protected_text, formula_map)
        """
        formula_map = {}
        protected = text
        counter = 0

        # Protect display formulas
        for match in re.finditer(self.DISPLAY_FORMULA, text, re.DOTALL):
            formula = match.group(0)
            placeholder = f"__FORMULA_{counter}__"
            formula_map[placeholder] = formula
            protected = protected.replace(formula, placeholder, 1)
            counter += 1

        # Protect LaTeX environments
        for match in re.finditer(self.LATEX_ENV, text, re.DOTALL):
            formula = match.group(0)
            placeholder = f"__FORMULA_{counter}__"
            formula_map[placeholder] = formula
            protected = protected.replace(formula, placeholder, 1)
            counter += 1

        # Protect inline formulas
        for match in re.finditer(self.INLINE_FORMULA, text):
            formula = match.group(0)
            placeholder = f"__FORMULA_{counter}__"
            formula_map[placeholder] = formula
            protected = protected.replace(formula, placeholder, 1)
            counter += 1

        return protected, formula_map

    def _restore_formulas(self, text: str, formula_map: Dict[str, str]) -> str:
        """Restore formulas from placeholders"""
        restored = text
        for placeholder, formula in formula_map.items():
            restored = restored.replace(placeholder, formula)
        return restored

    def _process_section(
        self,
        section: Dict[str, Any],
        section_idx: int,
        total_sections: int,
        base_metadata: Dict,
        formula_map: Dict[str, str] | None = None
    ) -> List[Document]:
        """Process section with formula awareness"""
        content = section["content"]

        # Count formulas in section
        formula_count = sum(1 for key in formula_map.keys() if key in content)
        has_formula = formula_count > 0

        # If section is small enough, keep as single chunk
        if len(content) <= self.max_chunk_size:
            restored_content = self._restore_formulas(content, formula_map)

            metadata = ChunkMetadata(
                level=ChunkLevel.SECTION,
                section_title=section["title"],
                position=section_idx,
                total_siblings=total_sections,
                heading_hierarchy=section["hierarchy"],
                has_formula=has_formula,
                formula_count=formula_count
            )

            if section["title"] and self.preserve_structure:
                restored_content = f"# {section['title']}\n\n{restored_content}"

            doc = Document(
                page_content=restored_content,
                metadata={**base_metadata, **metadata.to_dict()}
            )
            return [doc]

        # Split large sections with formula awareness
        return self._split_with_formula_awareness(
            content,
            section,
            section_idx,
            base_metadata,
            formula_map
        )

    def _split_with_formula_awareness(
        self,
        text: str,
        section: Dict[str, Any],
        section_idx: int,
        base_metadata: Dict,
        formula_map: Dict[str, str]
    ) -> List[Document]:
        """
        Split text while keeping formulas with context.
        Ensures formulas are never split and have surrounding context.
        """
        chunks = []

        # Find formula positions
        formula_positions = []
        for placeholder in formula_map.keys():
            pos = text.find(placeholder)
            if pos != -1:
                formula_positions.append({
                    "start": pos,
                    "end": pos + len(placeholder),
                    "placeholder": placeholder
                })

        formula_positions.sort(key=lambda x: x["start"])

        if not formula_positions:
            # No formulas, use standard splitting
            return self._standard_split(
                text, section, section_idx, base_metadata, formula_map
            )

        # Split around formulas with context
        current_pos = 0

        for formula_pos in formula_positions:
            # Get context before formula
            context_start = max(0, formula_pos["start"] - self.formula_context_window)

            # Create chunk with context + formula + context
            chunk_start = context_start
            chunk_end = min(
                len(text),
                formula_pos["end"] + self.formula_context_window
            )

            chunk_text = text[chunk_start:chunk_end]
            restored_chunk = self._restore_formulas(chunk_text, formula_map)

            formula_count = sum(
                1 for key in formula_map.keys() if key in chunk_text
            )

            metadata = ChunkMetadata(
                level=ChunkLevel.FORMULA,
                parent_id=f"section_{section_idx}",
                section_title=section["title"],
                position=len(chunks),
                heading_hierarchy=section["hierarchy"],
                has_formula=True,
                formula_count=formula_count
            )

            if section["title"] and self.preserve_structure:
                restored_chunk = f"[{section['title']}]\n\n{restored_chunk}"

            doc = Document(
                page_content=restored_chunk,
                metadata={**base_metadata, **metadata.to_dict()}
            )
            chunks.append(doc)

        return chunks

    def _standard_split(
        self,
        text: str,
        section: Dict[str, Any],
        section_idx: int,
        base_metadata: Dict,
        formula_map: Dict[str, str]
    ) -> List[Document]:
        """Standard recursive splitting when no formulas present"""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
        )

        splits = splitter.split_text(text)
        documents = []

        for idx, split in enumerate(splits):
            restored_split = self._restore_formulas(split, formula_map)

            metadata = ChunkMetadata(
                level=ChunkLevel.PARAGRAPH,
                parent_id=f"section_{section_idx}",
                section_title=section["title"],
                position=idx,
                total_siblings=len(splits),
                heading_hierarchy=section["hierarchy"]
            )

            if section["title"] and self.preserve_structure:
                restored_split = f"[{section['title']}]\n\n{restored_split}"

            doc = Document(
                page_content=restored_split,
                metadata={**base_metadata, **metadata.to_dict()}
            )
            documents.append(doc)

        return documents
