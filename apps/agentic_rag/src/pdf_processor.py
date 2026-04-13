from pathlib import Path
from typing import List, Dict, Any
import json
import argparse
from docling.document_converter import DocumentConverter
from urllib.parse import urlparse
import warnings
import uuid
import os
from langchain_oracledb.document_loaders.oracleai import OracleTextSplitter
from .db_utils import get_db_connection

os.environ['HF_HUB_DISABLE_XET'] = '1'

# Suppress the token length warning
warnings.filterwarnings('ignore', category=UserWarning, module='transformers.generation.utils')

def is_url(string: str) -> bool:
    """Check if a string is a valid URL"""
    try:
        result = urlparse(string)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

class PDFProcessor:
    def __init__(self, tokenizer: str = "BAAI/bge-small-en-v1.5"):
        """Initialize PDF processor with Docling converter and OracleTextSplitter"""
        # Suppress CUDA compilation warnings
        warnings.filterwarnings('ignore', category=UserWarning, module='torch.utils.cpp_extension')
        # Suppress token length warnings
        warnings.filterwarnings('ignore', category=UserWarning, module='transformers.generation.utils')
        warnings.filterwarnings('ignore', category=UserWarning, module='transformers.modeling_utils')

        self.converter = DocumentConverter()
        self.tokenizer = tokenizer

        # Initialize Oracle connection and splitter
        self.oracle_available = False
        try:
            self.connection = get_db_connection()
            self.splitter_params = {"normalize": "all"}
            self.splitter = OracleTextSplitter(conn=self.connection, params=self.splitter_params)
            self.oracle_available = True
            print("Successfully initialized OracleTextSplitter")
        except Exception as e:
            print(f"OracleTextSplitter unavailable ({e}), using fallback text splitter")
            self.connection = None
            self.splitter = None

    def _split_text_fallback(self, text: str, chunk_size: int = 1000) -> List[str]:
        """Simple fallback text splitter when Oracle is unavailable"""
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        chunks = []
        current_chunk = []
        current_length = 0
        for sentence in sentences:
            sentence = sentence + '.'
            if current_length + len(sentence) > chunk_size and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_length = 0
            current_chunk.append(sentence)
            current_length += len(sentence)
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        return chunks

    def _split_text_with_oracle(self, text: str) -> List[str]:
        """Split text using OracleTextSplitter, with fallback"""
        if not self.oracle_available:
            return self._split_text_fallback(text)
        try:
            return self.splitter.split_text(text)
        except Exception as e:
            print(f"Warning: OracleTextSplitter failed: {str(e)}, using fallback")
            return self._split_text_fallback(text)

    def process_pdf(self, file_path: str | Path) -> List[Dict[str, Any]]:
        """Process a PDF file and return chunks of text with metadata"""
        try:
            # Generate a unique document ID
            document_id = str(uuid.uuid4())

            # Convert PDF using Docling
            conv_result = self.converter.convert(file_path)
            if not conv_result or not conv_result.document:
                raise ValueError(f"Failed to convert PDF: {file_path}")

            # Export to markdown text for splitting
            text_content = conv_result.document.export_to_markdown()

            # Split using OracleTextSplitter
            chunks = self._split_text_with_oracle(text_content)

            if not chunks:
                raise ValueError("Failed to chunk document: no text content extracted")

            # Process chunks into a standardized format
            processed_chunks = []
            for i, chunk_text in enumerate(chunks):
                # Basic metadata since we are splitting raw text
                # We lose granular per-chunk metadata from docling, but this is expected with text splitting
                metadata = {
                    "source": str(file_path),
                    "document_id": document_id,
                    "chunk_index": i
                }

                processed_chunk = {
                    "text": chunk_text,
                    "metadata": metadata
                }
                processed_chunks.append(processed_chunk)

            return processed_chunks, document_id

        except Exception as e:
            raise Exception(f"Error processing PDF {file_path}: {str(e)}")

    def process_pdf_url(self, url: str) -> List[Dict[str, Any]]:
        """Process a PDF file from a URL and return chunks of text with metadata"""
        try:
            # Convert PDF using Docling's built-in URL support
            conv_result = self.converter.convert(url)
            if not conv_result or not conv_result.document:
                raise ValueError(f"Failed to convert PDF from URL: {url}")

            # Generate a unique document ID
            document_id = str(uuid.uuid4())

             # Export to markdown text for splitting
            text_content = conv_result.document.export_to_markdown()

            # Split using OracleTextSplitter
            chunks = self._split_text_with_oracle(text_content)

            if not chunks:
                raise ValueError("Failed to chunk document: no text content extracted")

            # Process chunks into a standardized format
            processed_chunks = []
            for i, chunk_text in enumerate(chunks):
                metadata = {
                    "source": url,
                    "document_id": document_id,
                    "chunk_index": i
                }

                processed_chunk = {
                    "text": chunk_text,
                    "metadata": metadata
                }
                processed_chunks.append(processed_chunk)

            return processed_chunks, document_id

        except Exception as e:
            raise Exception(f"Error processing PDF from URL {url}: {str(e)}")

    def process_directory(self, directory: str | Path) -> List[Dict[str, Any]]:
        """Process all PDF files in a directory"""
        directory = Path(directory)
        all_chunks = []
        document_ids = []

        for pdf_file in directory.glob("**/*.pdf"):
            try:
                chunks, doc_id = self.process_pdf(pdf_file)
                all_chunks.extend(chunks)
                document_ids.append(doc_id)
                print(f"✓ Processed {pdf_file} (ID: {doc_id})")
            except Exception as e:
                print(f"✗ Failed to process {pdf_file}: {str(e)}")

        return all_chunks, document_ids

def main():
    parser = argparse.ArgumentParser(description="Process PDF files and extract text chunks")
    parser.add_argument("--input", required=True,
                       help="Input PDF file, directory, or URL (http/https URLs supported)")
    parser.add_argument("--output", required=True, help="Output JSON file for chunks")
    parser.add_argument("--tokenizer", default="BAAI/bge-small-en-v1.5", help="Ignored (using OracleTextSplitter)")

    args = parser.parse_args()

    try:
        # Create output directory if it doesn't exist
        output_dir = Path(args.output).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        processor = PDFProcessor()

        if is_url(args.input):
            print(f"\nProcessing PDF from URL: {args.input}")
            print("=" * 50)
            chunks, doc_id = processor.process_pdf_url(args.input)
            print(f"Document ID: {doc_id}")
        elif Path(args.input).is_dir():
            print(f"\nProcessing directory: {args.input}")
            print("=" * 50)
            chunks, doc_ids = processor.process_directory(args.input)
            print(f"Document IDs: {', '.join(doc_ids)}")
        else:
            print(f"\nProcessing file: {args.input}")
            print("=" * 50)
            chunks, doc_id = processor.process_pdf(args.input)
            print(f"Document ID: {doc_id}")

        # Save chunks to JSON
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

        print("\nSummary:")
        print(f"✓ Processed {len(chunks)} chunks")
        print(f"✓ Saved to {args.output}")

    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main()
