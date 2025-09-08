from typing import Iterator
from pytube import extract
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter
from langchain_core.documents.base import Document, Blob
from langchain.document_loaders.base import BaseBlobParser


class YoutubeParser(BaseBlobParser):
    def __init__(self):
        self.formatter = TextFormatter()

    def lazy_parse(self, blob: Blob) -> Iterator[Document]:
        video_id = extract.video_id(blob.source)

        transcript = YouTubeTranscriptApi.get_transcripts([video_id], languages=["en", "it"], preserve_formatting=True)
        text = self.formatter.format_transcript(transcript[0][video_id])

        yield Document(page_content=text, metadata={})
