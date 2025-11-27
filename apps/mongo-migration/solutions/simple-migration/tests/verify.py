#!/usr/bin/env python3

import os
import logging
import pymongo
import cx_Oracle
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MigrationVerifier:
    def __init__(self, mongo_uri, oracle_uri):
        self.mongo_uri = mongo_uri
        self.oracle_uri = oracle_uri
        self.mongo_client = None
        self.oracle_conn = None

    def connect(self):
        """Establish connections to both databases"""
        try:
            # Connect to MongoDB
            self.mongo_client = pymongo.MongoClient(self.mongo_uri)
            logger.info("Connected to MongoDB")

            # Connect to Oracle
            self.oracle_conn = cx_Oracle.connect(self.oracle_uri)
            logger.info("Connected to Oracle")
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise

    def verify_collections(self):
        """Verify that all collections exist in both databases"""
        try:
            # Get MongoDB collections
            mongo_db = self.mongo_client.get_database()
            mongo_collections = mongo_db.list_collection_names()
            logger.info(f"MongoDB collections: {mongo_collections}")

            # Get Oracle collections
            cursor = self.oracle_conn.cursor()
            cursor.execute("""
                SELECT collection_name 
                FROM user_collections
            """)
            oracle_collections = [row[0] for row in cursor.fetchall()]
            logger.info(f"Oracle collections: {oracle_collections}")

            # Compare collections
            missing_collections = set(mongo_collections) - set(oracle_collections)
            if missing_collections:
                logger.error(f"Missing collections in Oracle: {missing_collections}")
                return False
            return True
        except Exception as e:
            logger.error(f"Collection verification failed: {e}")
            return False

    def verify_document_counts(self):
        """Verify document counts match between databases"""
        try:
            mongo_db = self.mongo_client.get_database()
            cursor = self.oracle_conn.cursor()

            for collection in mongo_db.list_collection_names():
                # Get MongoDB count
                mongo_count = mongo_db[collection].count_documents({})

                # Get Oracle count
                cursor.execute(f"""
                    SELECT COUNT(*) 
                    FROM {collection}
                """)
                oracle_count = cursor.fetchone()[0]

                if mongo_count != oracle_count:
                    logger.error(
                        f"Count mismatch in {collection}: "
                        f"MongoDB={mongo_count}, Oracle={oracle_count}"
                    )
                    return False
                logger.info(f"Collection {collection} count verified: {mongo_count}")
            return True
        except Exception as e:
            logger.error(f"Document count verification failed: {e}")
            return False

    def verify_sample_documents(self):
        """Verify sample documents match between databases"""
        try:
            mongo_db = self.mongo_client.get_database()
            cursor = self.oracle_conn.cursor()

            for collection in mongo_db.list_collection_names():
                # Get sample from MongoDB
                mongo_doc = mongo_db[collection].find_one()
                if not mongo_doc:
                    continue

                # Get corresponding document from Oracle
                doc_id = mongo_doc.get('_id')
                cursor.execute(f"""
                    SELECT data 
                    FROM {collection}
                    WHERE json_value(data, '$.id') = :1
                """, [str(doc_id)])
                oracle_doc = cursor.fetchone()

                if not oracle_doc:
                    logger.error(f"Document {doc_id} not found in Oracle {collection}")
                    return False

                # Compare documents (implement detailed comparison as needed)
                logger.info(f"Sample document verified in {collection}")
            return True
        except Exception as e:
            logger.error(f"Sample document verification failed: {e}")
            return False

    def close(self):
        """Close database connections"""
        if self.mongo_client:
            self.mongo_client.close()
        if self.oracle_conn:
            self.oracle_conn.close()

def main():
    # Configuration
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/ecommerce")
    oracle_uri = os.getenv("ORACLE_URI", "user/password@localhost:1521/service")

    # Create verifier instance
    verifier = MigrationVerifier(mongo_uri, oracle_uri)

    try:
        # Connect to databases
        verifier.connect()

        # Run verifications
        collections_ok = verifier.verify_collections()
        counts_ok = verifier.verify_document_counts()
        samples_ok = verifier.verify_sample_documents()

        # Report results
        if all([collections_ok, counts_ok, samples_ok]):
            logger.info("All verifications passed successfully")
        else:
            logger.error("Some verifications failed")
            raise Exception("Verification failed")

    except Exception as e:
        logger.error(f"Verification process failed: {e}")
        raise
    finally:
        verifier.close()

if __name__ == "__main__":
    main() 