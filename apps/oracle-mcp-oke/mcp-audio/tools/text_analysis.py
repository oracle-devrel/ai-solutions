import os
import threading

import oci
from oci.ai_language.models import TextDocument, BatchDetectLanguageKeyPhrasesDetails
from oci.retry import DEFAULT_RETRY_STRATEGY
from tools.oci_auth import load_runtime_oci_config_and_signer
from tools.logger_util import get_logger

logger = get_logger(__name__)

_CLIENT_LOCK = threading.Lock()
_LANGUAGE_CLIENT: oci.ai_language.AIServiceLanguageClient | None = None
_LANGUAGE_CLIENT_CTX: tuple[str, str, str, str] | None = None


def _client_context() -> tuple[str, str, str, str]:
    environment = os.environ.get("ENVIRONMENT", "").strip().lower()
    oci_config_file = os.path.expanduser(os.environ.get("OCI_CONFIG_FILE", "~/.oci/config"))
    region = os.environ.get("OCI_REGION", "")
    profile = os.environ.get("OCI_CONFIG_PROFILE", "").strip()
    return environment, oci_config_file, region, profile


def _build_ai_client() -> oci.ai_language.AIServiceLanguageClient:
    config, signer, auth_mode = load_runtime_oci_config_and_signer(
        logger=logger,
        connection_timeout=10.0,
        read_timeout=240.0,
    )
    logger.info("Language client auth mode=%s region=%s", auth_mode, config.get("region"))
    client_kwargs = {"config": config}
    if signer is not None:
        client_kwargs["signer"] = signer
    return oci.ai_language.AIServiceLanguageClient(**client_kwargs)


def create_ai_client() -> oci.ai_language.AIServiceLanguageClient:
    """Initialize and return OCI AI Language client with speech-like auth fallback."""
    global _LANGUAGE_CLIENT, _LANGUAGE_CLIENT_CTX
    ctx = _client_context()
    with _CLIENT_LOCK:
        if _LANGUAGE_CLIENT is None or _LANGUAGE_CLIENT_CTX != ctx:
            _LANGUAGE_CLIENT = _build_ai_client()
            _LANGUAGE_CLIENT_CTX = ctx
    return _LANGUAGE_CLIENT

def analyze_text(text: str) -> dict:
    logger.info(f"Starting text analysis for input: {text[:50]}...")  # Log first 50 chars
    try:
        ai_client = create_ai_client()
        compartment_id = os.environ.get("COMPARTMENT_ID")
        if not compartment_id:
            logger.error("COMPARTMENT_ID is not set for AI Language request")
            return {"error": "COMPARTMENT_ID environment variable is required for sentiment analysis"}

        logger.info(f"Using COMPARTMENT_ID={compartment_id[:18]}... for AI Language requests")

        logger.info("Preparing text document")
        text_document = TextDocument(key="input_text", text=text, language_code="en")

        logger.info("Performing text classification")
        text_classification = ai_client.batch_detect_language_text_classification(
            batch_detect_language_text_classification_details=oci.ai_language.models.BatchDetectLanguageTextClassificationDetails(
                compartment_id=compartment_id,
                documents=[text_document]
            )
        )
        logger.info(f"Text classification received: {text_classification.data}")
               
        
        logger.info("Performing key phrase extraction")
        key_phrase_details = BatchDetectLanguageKeyPhrasesDetails(
            compartment_id=compartment_id,
            documents=[text_document]
        )
        key_phrase_response = ai_client.batch_detect_language_key_phrases(key_phrase_details, retry_strategy=DEFAULT_RETRY_STRATEGY)
        logger.info(f"Key phrase response received: {key_phrase_response.data}")
        
        result = {
            "text_classification": {
                "label": text_classification.data.documents[0].text_classification[0].label,
                "score": text_classification.data.documents[0].text_classification[0].score
            },
            "key_phrases": [kp.text for kp in key_phrase_response.data.documents[0].key_phrases]
        }
        logger.info("Text analysis completed successfully")
        return result
    except oci.exceptions.ServiceError as e:
        logger.error(f"Service error: {e.message}, Status: {e.status}, Code: {e.code}")
        return {"error": f"Service error: {e.message}"}
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {"error": f"An error occurred: {str(e)}"}
