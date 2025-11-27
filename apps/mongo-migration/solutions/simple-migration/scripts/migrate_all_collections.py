#!/usr/bin/env python3

import os
import subprocess
import configparser
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='log/multi_collection_migration.log'
)
logger = logging.getLogger(__name__)

def get_collections(mongo_url, db_name):
    """Get list of collections from MongoDB"""
    from pymongo import MongoClient
    client = MongoClient(mongo_url)
    db = client[db_name]
    return db.list_collection_names()

def update_config(config_file, collection_name):
    """Update config.ini with new collection name"""
    config = configparser.ConfigParser()
    config.read(config_file)
    config['mongodb']['collection'] = collection_name
    with open(config_file, 'w') as f:
        config.write(f)

def migrate_collection(collection_name):
    """Migrate a single collection"""
    logger.info(f"Starting migration of collection: {collection_name}")
    try:
        # Update config with collection name
        update_config('config/config.ini', collection_name)
        
        # Run migration script
        result = subprocess.run(
            ['python', 'mongo2ora_data.py'],
            capture_output=True,
            text=True,
            check=True
        )
        
        logger.info(f"Successfully migrated collection: {collection_name}")
        logger.debug(f"Migration output: {result.stdout}")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to migrate collection {collection_name}: {e}")
        logger.error(f"Error output: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during migration of {collection_name}: {e}")
        raise

def main():
    # Read MongoDB connection details from config
    config = configparser.ConfigParser()
    config.read('config/config.ini')
    
    mongo_user = config['mongodb']['userid']
    mongo_password = config['mongodb']['password']
    mongo_host = config['mongodb']['hostname']
    mongo_port = config['mongodb']['port']
    mongo_db = config['mongodb']['sourcedb']
    
    # Construct MongoDB URL
    mongo_url = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}:{mongo_port}/{mongo_db}"
    
    try:
        # Get list of collections
        collections = get_collections(mongo_url, mongo_db)
        logger.info(f"Found {len(collections)} collections to migrate")
        
        # Migrate each collection
        for collection in collections:
            logger.info(f"Processing collection: {collection}")
            migrate_collection(collection)
            
        logger.info("All collections migrated successfully")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

if __name__ == "__main__":
    main() 