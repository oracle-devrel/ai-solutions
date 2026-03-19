import asyncio
import json
import os
import time
from pathlib import Path

import oci
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient


def load_client_env() -> None:
    load_dotenv('/Users/<alias>/Bitbucket/selfhosted-mcp-oke/mcp-client/.env')


def upload_local_file(namespace: str, bucket: str, local_file: Path) -> str:
    profile = os.getenv('OCI_PROFILE') or os.getenv('AUTH_PROFILE') or 'DEFAULT'
    config_file = os.path.expanduser(os.getenv('OCI_CONFIG_FILE', '~/.oci/config'))
    config = oci.config.from_file(file_location=config_file, profile_name=profile)

    object_name = f"uploads/{int(time.time())}_{local_file.name}"
    obj = oci.object_storage.ObjectStorageClient(config)
    with local_file.open('rb') as f:
        obj.put_object(
            namespace_name=namespace,
            bucket_name=bucket,
            object_name=object_name,
            put_object_body=f,
        )
    return object_name


async def main() -> None:
    load_client_env()

    mcp_url = os.getenv('MCP_URL', 'http://0.0.0.0:8080/mcp/')
    compartment_id = os.getenv('SPEECH_COMPARTMENT_OCID') or os.getenv('COMPARTMENT_ID')
    namespace = os.getenv('OCI_NAMESPACE')
    bucket = os.getenv('SPEECH_BUCKET')
    local_file = Path(os.getenv('LOCAL_SPEECH_FILE', '/Users/<alias>/Downloads/sample-9.mp3'))

    if not compartment_id:
        raise ValueError('Missing SPEECH_COMPARTMENT_OCID/COMPARTMENT_ID in mcp-client/.env')
    if not namespace or not bucket:
        raise ValueError('Missing OCI_NAMESPACE/SPEECH_BUCKET in mcp-client/.env')
    if not local_file.exists():
        raise FileNotFoundError(f'Local file not found: {local_file}')

    print('Uploading local file to Object Storage...')
    object_name = upload_local_file(namespace, bucket, local_file)
    print(f'Uploaded as: {object_name}')

    payload = {
        'compartment_id': compartment_id,
        'namespace': namespace,
        'bucket_name': bucket,
        'file_names': [object_name],
        'job_name': f'CustomerCallTranscription-temp-{int(time.time())}',
        'model_type': os.getenv('SPEECH_MODEL_TYPE', 'WHISPER_LARGE_V3T'),
        'language_code': os.getenv('SPEECH_LANGUAGE_CODE', 'auto'),
        'whisper_prompt': os.getenv('SPEECH_WHISPER_PROMPT', 'This is a customer support conversation.'),
        'diarization_enabled': str(os.getenv('SPEECH_DIARIZATION_ENABLED', 'true')).lower() in {'1', 'true', 'yes', 'y'},
    }

    print('Payload sent to MCP tool:')
    print(json.dumps(payload, indent=2))

    client = MultiServerMCPClient(
        {
            'tools_server': {
                'transport': 'streamable_http',
                'url': mcp_url,
                'timeout': 30.0,
            }
        }
    )

    async with client.session('tools_server') as session:
        result = await session.call_tool('create_speech_transcription_job', {'payload': json.dumps(payload)})

    raw_text = result.content[0].text if getattr(result, 'content', None) else ''
    parsed = json.loads(raw_text) if raw_text else {'raw': str(result)}

    print('MCP response:')
    print(json.dumps(parsed, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
