from typing import List, Dict, Any
import json
import argparse
from sentence_transformers import SentenceTransformer
import array
import oracledb
import yaml
from pathlib import Path


class OraDBVectorStore:
    def __init__(self, persist_directory: str = "embeddings"):
        """Initialize Oracle DB Vector Store
        
        Args:
            persist_directory: Not used for Oracle DB connection but kept for compatibility
        """
        # Load Oracle DB credentials from config.yaml
        credentials = self._load_config()
        
        username = credentials.get("ORACLE_DB_USERNAME", "ADMIN")
        password = credentials.get("ORACLE_DB_PASSWORD", "")
        dsn = credentials.get("ORACLE_DB_DSN", "")
        wallet_path = credentials.get("ORACLE_DB_WALLET_LOCATION")
        wallet_password = credentials.get("ORACLE_DB_WALLET_PASSWORD")
        
        if not password or not dsn:
            raise ValueError("Oracle DB credentials not found in config.yaml. Please set ORACLE_DB_USERNAME, ORACLE_DB_PASSWORD, and ORACLE_DB_DSN.")

        # Connect to the database
        try:
            if not wallet_path:
                print(f'Connecting (no wallet) to dsn {dsn} and user {username}')
                conn23c = oracledb.connect(user=username, password=password, dsn=dsn)
            else:
                print(f'Connecting (with wallet) to dsn {dsn} and user {username}')
                conn23c = oracledb.connect(user=username, password=password, dsn=dsn, 
                                           config_dir=wallet_path, wallet_location=wallet_path, wallet_password=wallet_password)
            print("Oracle DB Connection successful!")
        except Exception as e:
            print("Oracle DB Connection failed!", e)
            raise

        # Create a table to store the data
        cursor = conn23c.cursor()

        self.connection = conn23c
        self.cursor = cursor

        sql = """CREATE TABLE IF NOT EXISTS PDFCollection (
                           id VARCHAR2(4000 BYTE) PRIMARY KEY,
                           text VARCHAR2(4000 BYTE),
                           metadata VARCHAR2(4000 BYTE),
                           embedding VECTOR
                       )"""

        cursor.execute(sql)

        sql = """CREATE TABLE IF NOT EXISTS WebCollection (
                           id VARCHAR2(4000 BYTE) PRIMARY KEY,
                           text VARCHAR2(4000 BYTE),
                           metadata VARCHAR2(4000 BYTE),
                           embedding VECTOR
                       )"""

        cursor.execute(sql)

        sql = """CREATE TABLE IF NOT EXISTS RepoCollection (
                           id VARCHAR2(4000 BYTE) PRIMARY KEY,
                           text VARCHAR2(4000 BYTE),
                           metadata VARCHAR2(4000 BYTE),
                           embedding VECTOR
                       )"""

        cursor.execute(sql)


        sql = """CREATE TABLE IF NOT EXISTS GeneralCollection (
                           id VARCHAR2(4000 BYTE) PRIMARY KEY,
                           text VARCHAR2(4000 BYTE),
                           metadata VARCHAR2(4000 BYTE),
                           embedding VECTOR
                       )"""

        cursor.execute(sql)

        self.encoder = SentenceTransformer('all-MiniLM-L12-v2')

    
    def _load_config(self) -> Dict[str, str]:
        """Load configuration from config.yaml"""
        try:
            config_path = Path("config.yaml")
            if not config_path.exists():
                print("Warning: config.yaml not found. Using empty configuration.")
                return {}
                
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            return config if config else {}
        except Exception as e:
            print(f"Warning: Error loading config: {str(e)}")
            return {}
    
    def _sanitize_metadata(self, metadata: Dict) -> Dict:
        """Sanitize metadata to ensure all values are valid types for Oracle DB"""
        sanitized = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            elif isinstance(value, list):
                # Convert list to string representation
                sanitized[key] = str(value)
            elif value is None:
                # Replace None with empty string
                sanitized[key] = ""
            else:
                # Convert any other type to string
                sanitized[key] = str(value)
        return sanitized
    
    def add_pdf_chunks(self, chunks: List[Dict[str, Any]], document_id: str):
        """Add chunks from a PDF document to the vector store"""
        if not chunks:
            return
        
        # Prepare data for Oracle DB
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [self._sanitize_metadata(chunk["metadata"]) for chunk in chunks]
        ids = [f"{document_id}_{i}" for i in range(len(chunks))]

        # Encode all texts in a batch
        embeddings = self.encoder.encode(texts, batch_size=32, show_progress_bar=True)

        table_name = "PDFCollection"
        # Truncate the table
        self.cursor.execute(f"truncate table {table_name}")

        # Insert embeddings into Oracle
        for i, (docid, text, metadata, embedding) in enumerate(zip(ids, texts, metadatas, embeddings), start=1):
            json_metadata = json.dumps(metadata)  # Convert to JSON string
            vector = array.array("f", embedding)

            self.cursor.execute(
                "INSERT INTO PDFCollection (id, text, metadata, embedding) VALUES (:1, :2, :3, :4)",
                (docid, text, json_metadata, vector)
            )

        self.connection.commit()
    
    def add_web_chunks(self, chunks: List[Dict[str, Any]], source_id: str):
        """Add chunks from web content to the vector store"""
        if not chunks:
            return
        
        # Prepare data for Oracle DB
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [self._sanitize_metadata(chunk["metadata"]) for chunk in chunks]
        ids = [f"{source_id}_{i}" for i in range(len(chunks))]

        # Encode all texts in a batch
        embeddings = self.encoder.encode(texts, batch_size=32, show_progress_bar=True)

        # No truncation for web chunks, just append new ones

        # Insert embeddings into Oracle
        for i, (docid, text, metadata, embedding) in enumerate(zip(ids, texts, metadatas, embeddings), start=1):
            json_metadata = json.dumps(metadata)  # Convert to JSON string
            vector = array.array("f", embedding)

            self.cursor.execute(
                "INSERT INTO WebCollection (id, text, metadata, embedding) VALUES (:1, :2, :3, :4)",
                (docid, text, json_metadata, vector)
            )

        self.connection.commit()
    
    def add_general_knowledge(self, chunks: List[Dict[str, Any]], source_id: str):
        """Add general knowledge chunks to the vector store"""
        if not chunks:
            return
        
        # Prepare data for Oracle DB
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [self._sanitize_metadata(chunk["metadata"]) for chunk in chunks]
        ids = [f"{source_id}_{i}" for i in range(len(chunks))]
        
        # Encode all texts in a batch
        embeddings = self.encoder.encode(texts, batch_size=32, show_progress_bar=True)

        # Insert embeddings into Oracle
        for i, (docid, text, metadata, embedding) in enumerate(zip(ids, texts, metadatas, embeddings), start=1):
            json_metadata = json.dumps(metadata)  # Convert to JSON string
            vector = array.array("f", embedding)

            self.cursor.execute(
                "INSERT INTO GeneralCollection (id, text, metadata, embedding) VALUES (:1, :2, :3, :4)",
                (docid, text, json_metadata, vector)
            )

        self.connection.commit()
    
    def add_repo_chunks(self, chunks: List[Dict[str, Any]], document_id: str):
        """Add chunks from a repository to the vector store"""
        if not chunks:
            return
        
        # Prepare data for Oracle DB
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [self._sanitize_metadata(chunk["metadata"]) for chunk in chunks]
        ids = [f"{document_id}_{i}" for i in range(len(chunks))]
        
        # Encode all texts in a batch
        embeddings = self.encoder.encode(texts, batch_size=32, show_progress_bar=True)

        # Insert embeddings into Oracle
        for i, (docid, text, metadata, embedding) in enumerate(zip(ids, texts, metadatas, embeddings), start=1):
            json_metadata = json.dumps(metadata)  # Convert to JSON string
            vector = array.array("f", embedding)

            self.cursor.execute(
                "INSERT INTO RepoCollection (id, text, metadata, embedding) VALUES (:1, :2, :3, :4)",
                (docid, text, json_metadata, vector)
            )

        self.connection.commit()
    
    def query_pdf_collection(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Query the PDF documents collection"""
        print("🔍 [Oracle DB] Querying PDF Collection")
        # Generate Embeddings
        embeddings = self.encoder.encode(query, batch_size=32, show_progress_bar=True)
        new_vector = array.array("f", embeddings)

        sql = """
            SELECT Id, Text, MetaData, Embedding
            FROM PDFCOLLECTION
            ORDER BY VECTOR_DISTANCE(EMBEDDING, :nv, EUCLIDEAN) 
            FETCH FIRST 10 ROWS ONLY
            """

        self.cursor.execute(sql, {"nv": new_vector})

        # Fetch all rows
        rows = self.cursor.fetchall()
        
        # Format results
        formatted_results = []
        for row in rows:
            result = {
                "content": row[1],
                "metadata": json.loads(row[2]) if isinstance(row[2], str) else row[2]
            }
            formatted_results.append(result)
        
        print(f"🔍 [Oracle DB] Retrieved {len(formatted_results)} chunks from PDF Collection")
        return formatted_results
    
    def query_web_collection(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Query the web documents collection"""
        print("🔍 [Oracle DB] Querying Web Collection")
        # Generate Embeddings
        embeddings = self.encoder.encode(query, batch_size=32, show_progress_bar=True)
        new_vector = array.array("f", embeddings)

        sql = """
            SELECT Id, Text, MetaData, Embedding
            FROM WebCOLLECTION
            ORDER BY VECTOR_DISTANCE(EMBEDDING, :nv, EUCLIDEAN) 
            FETCH FIRST 10 ROWS ONLY
            """

        self.cursor.execute(sql, {"nv": new_vector})

        # Fetch all rows
        rows = self.cursor.fetchall()

        # Format results
        formatted_results = []
        for row in rows:
            result = {
                "content": row[1],
                "metadata": json.loads(row[2]) if isinstance(row[2], str) else row[2]
            }
            formatted_results.append(result)
        
        print(f"🔍 [Oracle DB] Retrieved {len(formatted_results)} chunks from Web Collection")
        return formatted_results
    
    def query_general_collection(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Query the general knowledge collection"""
        print("🔍 [Oracle DB] Querying General Knowledge Collection")
        # Generate Embeddings
        embeddings = self.encoder.encode(query, batch_size=32, show_progress_bar=True)
        new_vector = array.array("f", embeddings)

        sql = """
            SELECT Id, Text, MetaData, Embedding
            FROM GeneralCollection
            ORDER BY VECTOR_DISTANCE(EMBEDDING, :nv, EUCLIDEAN) 
            FETCH FIRST 10 ROWS ONLY
            """

        self.cursor.execute(sql, {"nv": new_vector})

        # Fetch all rows
        rows = self.cursor.fetchall()

        # Format results
        formatted_results = []
        for row in rows:
            result = {
                "content": row[1],
                "metadata": json.loads(row[2]) if isinstance(row[2], str) else row[2]
            }
            formatted_results.append(result)
        
        print(f"🔍 [Oracle DB] Retrieved {len(formatted_results)} chunks from General Knowledge Collection")
        return formatted_results
    
    def query_repo_collection(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Query the repository documents collection"""
        print("🔍 [Oracle DB] Querying Repository Collection")
        # Generate Embeddings
        embeddings = self.encoder.encode(query, batch_size=32, show_progress_bar=True)
        new_vector = array.array("f", embeddings)

        sql = """
            SELECT Id, Text, MetaData, Embedding
            FROM RepoCOLLECTION
            ORDER BY VECTOR_DISTANCE(EMBEDDING, :nv, EUCLIDEAN) 
            FETCH FIRST 10 ROWS ONLY
            """

        self.cursor.execute(sql, {"nv": new_vector})

        # Fetch all rows
        rows = self.cursor.fetchall()
        
        # Format results
        formatted_results = []
        for row in rows:
            result = {
                "content": row[1],
                "metadata": json.loads(row[2]) if isinstance(row[2], str) else row[2]
            }
            formatted_results.append(result)
        
        print(f"🔍 [Oracle DB] Retrieved {len(formatted_results)} chunks from Repository Collection")
        return formatted_results
        
    def get_collection_count(self, collection_name: str) -> int:
        """Get the total number of chunks in a collection
        
        Args:
            collection_name: Name of the collection (pdf_documents, web_documents, repository_documents, general_knowledge)
            
        Returns:
            Number of chunks in the collection
        """
        # Map collection names to table names
        collection_map = {
            "pdf_documents": "PDFCollection",
            "web_documents": "WebCollection",
            "repository_documents": "RepoCollection", 
            "general_knowledge": "GeneralCollection"
        }
        
        table_name = collection_map.get(collection_name)
        if not table_name:
            raise ValueError(f"Unknown collection name: {collection_name}")
        
        # Count the rows in the table
        sql = f"SELECT COUNT(*) FROM {table_name}"
        self.cursor.execute(sql)
        count = self.cursor.fetchone()[0]
        
        return count
    
    def get_latest_chunk(self, collection_name: str) -> Dict[str, Any]:
        """Get the most recently inserted chunk from a collection
        
        Args:
            collection_name: Name of the collection (pdf_documents, web_documents, repository_documents, general_knowledge)
            
        Returns:
            Dictionary containing the content and metadata of the latest chunk
        """
        # Map collection names to table names
        collection_map = {
            "pdf_documents": "PDFCollection",
            "web_documents": "WebCollection",
            "repository_documents": "RepoCollection", 
            "general_knowledge": "GeneralCollection"
        }
        
        table_name = collection_map.get(collection_name)
        if not table_name:
            raise ValueError(f"Unknown collection name: {collection_name}")
        
        # Get the most recently inserted row (using ID as a proxy for insertion time)
        # This assumes IDs are assigned sequentially or have a timestamp component
        sql = f"SELECT Id, Text, MetaData FROM {table_name} ORDER BY ROWID DESC FETCH FIRST 1 ROW ONLY"
        self.cursor.execute(sql)
        row = self.cursor.fetchone()
        
        if not row:
            raise ValueError(f"No chunks found in collection: {collection_name}")
        
        result = {
            "id": row[0],
            "content": row[1],
            "metadata": json.loads(row[2]) if isinstance(row[2], str) else row[2]
        }
        
        return result

def main():
    parser = argparse.ArgumentParser(description="Manage Oracle DB vector store")
    parser.add_argument("--add", help="JSON file containing chunks to add")
    parser.add_argument("--add-web", help="JSON file containing web chunks to add")
    parser.add_argument("--query", help="Query to search for")
    
    args = parser.parse_args()
    store = OraDBVectorStore()
    
    if args.add:
        with open(args.add, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        store.add_pdf_chunks(chunks, document_id=args.add)
        print(f"✓ Added {len(chunks)} PDF chunks to Oracle DB vector store")
    
    if args.add_web:
        with open(args.add_web, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        store.add_web_chunks(chunks, source_id=args.add_web)
        print(f"✓ Added {len(chunks)} web chunks to Oracle DB vector store")
    
    if args.query:
        # Query both collections
        pdf_results = store.query_pdf_collection(args.query)
        web_results = store.query_web_collection(args.query)
        
        print("\nPDF Results:")
        print("-" * 50)
        for result in pdf_results:
            print(f"Content: {result['content'][:200]}...")
            print(f"Source: {result['metadata'].get('source', 'Unknown')}")
            print(f"Pages: {result['metadata'].get('page_numbers', [])}")
            print("-" * 50)
        
        print("\nWeb Results:")
        print("-" * 50)
        for result in web_results:
            print(f"Content: {result['content'][:200]}...")
            print(f"Source: {result['metadata'].get('source', 'Unknown')}")
            print(f"Title: {result['metadata'].get('title', 'Unknown')}")
            print("-" * 50)

if __name__ == "__main__":
    main() 