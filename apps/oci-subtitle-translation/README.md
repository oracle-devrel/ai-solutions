# OCI Subtitle Translation

Automatically transcribe audio files and translate subtitles into multiple languages using Oracle Cloud Infrastructure (OCI) AI services.

## Overview

This solution combines two powerful OCI AI services to create multilingual subtitles:
- **OCI Speech**: Transcribes audio files to SRT subtitle format
- **OCI Language**: Translates subtitles into 30+ target languages

Perfect for making video content accessible to global audiences with minimal manual effort.

## Features

- 🎧 **Flexible Input**: Local audio files or files in OCI Object Storage
- 📄 **Multiple Formats**: Generates industry-standard SRT subtitle files
- 🌍 **30+ Languages**: Translate to major world languages
- ⚡ **Batch Processing**: Efficient translation for multiple languages
- 🔧 **Configurable**: Customize storage, languages, and processing methods
- 📦 **Complete Workflow**: Single command for transcription + translation

## Quick Start

### Prerequisites

- Python 3.8+
- OCI account with Speech and Language services enabled
- OCI CLI configured (`oci setup config`)
- Object Storage bucket for audio/subtitle files

### Installation

1. **Clone and install dependencies:**
   ```bash
   git clone https://github.com/oracle-devrel/ai-solutions.git
   cd ai-solutions/apps/oci-subtitle-translation
   pip install -r requirements.txt
   ```

2. **Configure your settings:**
   ```bash
   cp config_example.yaml config.yaml
   # Edit config.yaml with your OCI details (see Configuration section)
   ```

3. **Run the workflow:**
   ```bash
   # Transcribe local file and translate to Spanish
   python workflow.py --audio-source audio.mp3 --target-language es
   
   # Transcribe Object Storage file and translate to multiple languages
   python workflow.py --audio-source "audio/recording.mp3" --target-languages es fr de
   ```

## Audio Input Methods

### Method 1: Local Audio Files

For audio files on your local machine:

```bash
# Single language translation
python workflow.py --audio-source /path/to/audio.mp3 --target-language es

# Multiple languages
python workflow.py --audio-source audio.wav --target-languages es fr de pt

# Transcription only (no translation)
python workflow.py --transcribe-only --audio-source audio.mp3
```

**How it works:**
- Script uploads your local file to Object Storage
- Transcribes using OCI Speech
- Downloads and translates the generated SRT files

### Method 2: Object Storage Audio Files

For audio files already in your configured Object Storage bucket:

```bash
# File in bucket root
python workflow.py --audio-source "myfile.mp3" --target-language es

# File in subfolder
python workflow.py --audio-source "audio/recordings/interview.mp3" --target-languages es fr

# Complex path (from OCI Speech job output)
python workflow.py --audio-source "transcriptions/audio.mp3/job-abc123/audio.mp3" --target-language es
```

**Important:** 
- Use the **object path within your bucket** (don't include bucket name)
- Bucket name and namespace come from your `config.yaml`
- If path doesn't exist locally, it's treated as an Object Storage path

## Configuration

Edit `config.yaml` with your OCI details:

```yaml
# OCI Profile (from ~/.oci/config)
profile: "DEFAULT"

# Speech Service Settings
speech:
  compartment_id: "ocid1.compartment.oc1..your-compartment-id"
  bucket_name: "your-bucket-name"
  namespace: "your-namespace"
  language_code: "en-US"  # Default transcription language

# Output Settings
output:
  storage_type: "both"  # "local", "object_storage", or "both"
  local_directory: "./output"

# Translation Settings
translation:
  target_languages: ["es", "fr", "de"]  # Default languages
  method: "batch"  # "batch" or "sync"
```

### Finding Your OCI Details

- **Compartment ID**: OCI Console → Identity → Compartments
- **Namespace**: OCI Console → Object Storage → Bucket Details
- **Bucket Name**: The bucket you created for audio/subtitle files
- **Profile**: Your OCI CLI profile name (usually "DEFAULT")

## Usage Examples

### Complete Workflow

```bash
# Local file → transcribe → translate to Spanish and French
python workflow.py --audio-source interview.mp3 --target-languages es fr

# Object Storage file → transcribe → translate to German
python workflow.py --audio-source "recordings/meeting.wav" --target-language de

# Custom output location
python workflow.py --audio-source audio.mp3 --target-language es --output-type local
```

### Individual Operations

**Transcription only:**
```bash
# Local file
python generate_srt_from_audio.py --input-file audio.mp3

# Object Storage file
python generate_srt_from_audio.py --input-file "audio/recording.mp3"

# Specify language and output
python generate_srt_from_audio.py --input-file audio.mp3 --language es-ES --output-type local
```

**Translation only:**
```bash
# Translate existing SRT file
python translate_srt.py --input-file subtitles.srt --target-languages es fr de

# Translate SRT file in Object Storage
python translate_srt.py --input-file "srt/subtitles.srt" --target-language es --method sync
```

## Supported Languages

### Audio Transcription
| Language | Code | | Language | Code |
|----------|------|---|----------|------|
| English (US) | en-US | | Portuguese (Brazil) | pt-BR |
| English (UK) | en-GB | | Hindi (India) | hi-IN |
| English (Australia) | en-AU | | French (France) | fr-FR |
| English (India) | en-IN | | German (Germany) | de-DE |
| Spanish (Spain) | es-ES | | Italian (Italy) | it-IT |

### Translation (30+ languages)
| Language | Code | | Language | Code | | Language | Code |
|----------|------|---|----------|------|---|----------|------|
| Spanish | es | | French | fr | | German | de |
| Portuguese | pt | | Italian | it | | Dutch | nl |
| Russian | ru | | Japanese | ja | | Korean | ko |
| Chinese (Simplified) | zh-CN | | Chinese (Traditional) | zh-TW | | Arabic | ar |
| Hebrew | he | | Hindi | hi | | Thai | th |

[View complete list](https://docs.oracle.com/en-us/iaas/language/using/translate.htm#supported-langs)

## Command Reference

### workflow.py

| Option | Description | Example |
|--------|-------------|---------|
| `--audio-source` | Audio file (local or Object Storage path) | `--audio-source "audio/file.mp3"` |
| `--target-language` | Single target language | `--target-language es` |
| `--target-languages` | Multiple target languages | `--target-languages es fr de` |
| `--transcribe-only` | Only transcribe (no translation) | `--transcribe-only` |
| `--translate-only` | Only translate existing SRT | `--translate-only --srt-file file.srt` |
| `--speech-language` | Override transcription language | `--speech-language es-ES` |
| `--output-type` | Where to store output | `--output-type local` |
| `--config` | Custom config file | `--config my-config.yaml` |

### Output Storage Options

| Value | Description | Files Saved To |
|-------|-------------|----------------|
| `local` | Local filesystem only | `./output/` directory |
| `object_storage` | Object Storage only | Your configured bucket |
| `both` | Both locations (default) | Local directory + Object Storage |

## Translation Methods

### Batch Translation (Recommended)
- **Best for**: Multiple languages, larger files
- **Limit**: 20MB per file
- **Speed**: Faster for multiple languages
- **Usage**: `--method batch` (default)

### Synchronous Translation
- **Best for**: Single language, smaller files
- **Limit**: No file size limit
- **Speed**: Slower for multiple languages
- **Usage**: `--method sync`

## Troubleshooting

### Common Issues

**"BucketNotFound" Error:**
- Verify bucket name and namespace in `config.yaml`
- Ensure bucket exists in the correct region
- Check IAM permissions for Object Storage

**"ObjectNotFound" Error:**
- Verify the object path in your bucket
- Check if file was uploaded successfully
- Ensure correct spelling and case

**Authentication Issues:**
```bash
# Test OCI CLI configuration
oci iam user get --user-id $(oci iam user list --query 'data[0].id' --raw-output)

# Reconfigure if needed
oci setup config
```

**Large File Handling:**
- Audio files: No limit for OCI Speech
- SRT files: 20MB limit for batch translation
- Large files automatically use sync translation

### Debug Mode

Add verbose logging:
```bash
# Set environment variable for detailed logs
export OCI_CLI_PROFILE=your-profile
python workflow.py --audio-source audio.mp3 --target-language es
```

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Audio File    │ ──▶│   OCI Speech     │ ──▶│   SRT File      │
│ (Local/Storage) │    │   Transcription  │    │   Generated     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                        │
                                                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Translated SRT  │ ◀──│  OCI Language    │ ◀──│   SRT File      │
│   Files (es,    │    │   Translation    │    │   Original      │
│   fr, de, etc.) │    └──────────────────┘    └─────────────────┘
└─────────────────┘
```

## Contributing

This project is open source. Please submit your contributions by forking this repository and submitting a pull request! Oracle appreciates any contributions that are made by the open source community.

## License

Copyright (c) 2025 Oracle and/or its affiliates.

Licensed under the Universal Permissive License (UPL), Version 1.0.

See [LICENSE](../LICENSE) for more details.

ORACLE AND ITS AFFILIATES DO NOT PROVIDE ANY WARRANTY WHATSOEVER, EXPRESS OR IMPLIED, FOR ANY SOFTWARE, MATERIAL OR CONTENT OF ANY KIND CONTAINED OR PRODUCED WITHIN THIS REPOSITORY, AND IN PARTICULAR SPECIFICALLY DISCLAIM ANY AND ALL IMPLIED WARRANTIES OF TITLE, NON-INFRINGEMENT, MERCHANTABILITY, AND FITNESS FOR A PARTICULAR PURPOSE. FURTHERMORE, ORACLE AND ITS AFFILIATES DO NOT REPRESENT THAT ANY CUSTOMARY SECURITY REVIEW HAS BEEN PERFORMED WITH RESPECT TO ANY SOFTWARE, MATERIAL OR CONTENT CONTAINED OR PRODUCED WITHIN THIS REPOSITORY. IN ADDITION, AND WITHOUT LIMITING THE FOREGOING, THIRD PARTIES MAY HAVE POSTED SOFTWARE, MATERIAL OR CONTENT TO THIS REPOSITORY WITHOUT ANY REVIEW. USE AT YOUR OWN RISK. 
