"""Hooks to modify the RabbitHole's documents ingestion.

Here is a collection of methods to hook into the RabbitHole execution pipeline.

These hooks allow to intercept the uploaded documents at different places before they are saved into memory.

"""
from typing import List, Dict
from langchain_community.document_loaders.parsers.audio import FasterWhisperParser
from langchain_community.document_loaders.parsers.html.bs4 import BS4HTMLParser
from langchain_community.document_loaders.parsers.language.language_parser import LanguageParser
from langchain_community.document_loaders.parsers.msword import MsWordParser
from langchain_community.document_loaders.parsers.pdf import PyMuPDFParser
from langchain_community.document_loaders.parsers.txt import TextParser
from langchain_core.documents import Document

from cat.core_plugins.base_plugin.parsers import YoutubeParser, TableParser, JSONParser, PowerPointParser
from cat.mad_hatter.decorators import hook
from cat.memory.utils import PointStruct


@hook(priority=999)
def rabbithole_instantiates_parsers(file_handlers: Dict, cat) -> Dict:
    """Hook the available parsers for ingesting files in the declarative memory.

    Allows replacing or extending existing supported mime types and related parsers to customize the file ingestion.

    Args:
        file_handlers: Dict
            Keys are the supported mime types and values are the related parsers.
        cat: CheshireCat
            Cheshire Cat instance.

    Returns:
        file_handlers: Dict
            Edited dictionary of supported mime types and related parsers.
    """
    return file_handlers | {
        "application/json": JSONParser(),
        "application/msword": MsWordParser(),
        "application/vnd.ms-powerpoint": PowerPointParser(),
        "application/pdf": PyMuPDFParser(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": TableParser(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": MsWordParser(),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": PowerPointParser(),
        "text/csv": TableParser(),
        "text/html": BS4HTMLParser(),
        "text/javascript": LanguageParser(language="js"),
        "text/markdown": TextParser(),
        "text/plain": TextParser(),
        "text/x-python": LanguageParser(language="python"),
        "video/mp4": YoutubeParser(),
        "audio/mpeg": FasterWhisperParser(),
        "audio/mp3": FasterWhisperParser(),
        "audio/ogg": FasterWhisperParser(),
        "audio/wav": FasterWhisperParser(),
        "audio/webm": FasterWhisperParser(),
    }


# Hook called just before of inserting a document in vector memory
@hook(priority=0)
def before_rabbithole_insert_memory(doc: Document, cat) -> Document:
    """Hook the `Document` before is inserted in the vector memory.

    Allows editing and enhancing a single `Document` before the *RabbitHole* add it to the declarative vector memory.

    Args:
        doc: Document
            Langchain `Document` to be inserted in memory.
        cat: StrayCat
            Stray Cat instance.

    Returns:
        doc: Document
            Langchain `Document` that is added in the declarative vector memory.

    Notes
    -----
    The `Document` has two properties::

        `page_content`: the string with the text to save in memory;
        `metadata`: a dictionary with at least two keys:
            `source`: where the text comes from;
            `when`: timestamp to track when it's been uploaded.
    """
    return doc


# Hook called just before rabbithole splits text. Input is whole Document
@hook(priority=0)
def before_rabbithole_splits_text(docs: List[Document], cat) -> List[Document]:
    """Hook the `Documents` before they are split into chunks.

    Allows editing the uploaded document main Document(s) before the *RabbitHole* recursively splits it in shorter ones.
    Please note that this is a list because parsers can output one or more Document, that are afterwards splitted.

    For instance, the hook allows to change the text or edit/add metadata.

    Args:
        docs: List[Document]
            Langchain `Document`s resulted after parsing the file uploaded in the *RabbitHole*.
        cat: StrayCat
            Stray Cat instance.

    Returns:
        docs: List[Document]
            Edited Langchain `Document`s.
    """
    return docs


# Hook called when a list of Document is going to be inserted in memory from the rabbit hole.
# Here you can edit/summarize the documents before inserting them in memory
# Should return a list of documents (each is a langchain Document)
@hook(priority=0)
def before_rabbithole_stores_documents(docs: List[Document], cat) -> List[Document]:
    """Hook into the memory insertion pipeline.

    Allows modifying how the list of `Document` is inserted in the vector memory.

    For example, this hook is a good point to summarize the incoming documents and save both original and
    summarized contents.

    Args:
        docs: List[Document]
            List of Langchain `Document` to be edited.
        cat: StrayCat
            Stray Cat instance.

    Returns:
        docs: List[Document]
            List of edited Langchain documents.
    """
    return docs


@hook(priority=0)
def after_rabbithole_stored_documents(source, stored_points: List[PointStruct], cat) -> None:
    """Hook the Document after is inserted in the vector memory.

    Allows editing and enhancing the list of Document after is inserted in the vector memory.

    Args:
        source: str
            Name of ingested file/url
        stored_points: List[PointStruct]
            List of PointStruct just inserted into the db.
        cat: StrayCat
            Stray Cat instance.
    """
    pass
