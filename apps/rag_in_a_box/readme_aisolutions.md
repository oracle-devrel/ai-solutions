# AI RAG in a Box

## Introduction

AI RAG in a Box is an intelligent Retrieval Augmented Generation (RAG) system that enhances traditional RAG pipelines with agentic decision-making capabilities. This solution leverages Large Language Models (LLMs) not just for response generation, but also for intelligent routing and decision making in the information retrieval process.

The solution combines several powerful features:
- Intelligent query routing between multiple knowledge bases
- Agent-based decision making for context selection
- Support for multiple data sources (internal documentation, industry knowledge)
- Fail-safe mechanisms for out-of-scope queries
- Flexible deployment options with both local and cloud-based LLMs

This agentic approach significantly improves the accuracy and relevance of responses by making intelligent decisions about which knowledge base to query based on the context of each question.

## 0. Prerequisites and setup

### Prerequisites

- Python 3.8 or higher
- Docker or Podman for containerized deployment
- Sufficient system resources for LLM operation:
  - Minimum 16GB RAM (recommended >24GB)
  - GPU with 8GB VRAM recommended for better performance
  - Will run on CPU if GPU is not available
- HuggingFace account and API token (for Llama models)
- Optional: OCI Account for cloud deployment

### Setup

1. Clone the repository and navigate to the project directory:
   ```bash
   git clone https://github.com/oracle-devrel/ai-solutions.git
   cd ai-solutions/apps/rag_in_a_box
   ```

2. Choose your deployment method:
   - For MacOS with Colima:
     Follow instructions in `install_colima_docker_macosx.md`
   - For MacOS with Podman:
     Follow instructions in `install_podman_macosx.md`
   - For Windows:
     Follow instructions in `install_win_llama3_db23ai.md`

3. Configure your environment:
   - Set up HuggingFace credentials if using Llama models
   - Configure OCI credentials if using cloud deployment
   - Prepare your knowledge bases (PDFs, documents, websites)

### Docs

- [Installation Guide for MacOS (Colima)](install_colima_docker_macosx.md)
- [Installation Guide for MacOS (Podman)](install_podman_macosx.md)
- [Installation Guide for Windows](install_win_llama3_db23ai.md)
- [Using Internal Llama3](using_internal_llama3.md)
- [Using GenAI](using_genai.md)

## 1. Getting Started

The solution can be deployed in several ways:

### 1. Using Docker/Podman Container

1. Build and run the container:
   ```bash
   docker build -t rag-in-a-box .
   docker run -p 8080:8080 rag-in-a-box
   ```

2. Access the web interface at `http://localhost:8080`

### 2. Using Local Installation

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Start the application:

   ```bash
   python app.py
   ```

### 3. Using OCI Cloud Deployment

Follow the VM deployment instructions in [`installvmragdemo.md`](installvmragdemo.md)

## 2. Usage

The system operates in three main modes:

1. **Document Processing**:
   - Upload internal documentation
   - Process industry knowledge bases
   - Index websites and external resources

2. **Query Processing**:
   - Submit natural language queries
   - System automatically routes to appropriate knowledge base
   - Receive contextually relevant responses

3. **Agent Management**:
   - Configure routing rules
   - Customize fail-safe responses
   - Monitor agent decisions

## Annex: Supported Features

### Knowledge Base Types
- PDF Documents
- Websites
- Internal Documentation
- Industry Standards
- Best Practices
- Public Resources

### LLM Options
- Local Llama Models
- Cloud-based LLMs
- Custom Model Integration

### Deployment Options
- Docker Containers
- Local Installation
- OCI Cloud Deployment
- VM-based Deployment

## Contributing

This project is open source. Please submit your contributions by forking this repository and submitting a pull request! Oracle appreciates any contributions that are made by the open source community.

## License

Copyright (c) 2024 Oracle and/or its affiliates.

Licensed under the Universal Permissive License (UPL), Version 1.0.

See [LICENSE](../LICENSE) for more details.

ORACLE AND ITS AFFILIATES DO NOT PROVIDE ANY WARRANTY WHATSOEVER, EXPRESS OR IMPLIED, FOR ANY SOFTWARE, MATERIAL OR CONTENT OF ANY KIND CONTAINED OR PRODUCED WITHIN THIS REPOSITORY, AND IN PARTICULAR SPECIFICALLY DISCLAIM ANY AND ALL IMPLIED WARRANTIES OF TITLE, NON-INFRINGEMENT, MERCHANTABILITY, AND FITNESS FOR A PARTICULAR PURPOSE. FURTHERMORE, ORACLE AND ITS AFFILIATES DO NOT REPRESENT THAT ANY CUSTOMARY SECURITY REVIEW HAS BEEN PERFORMED WITH RESPECT TO ANY SOFTWARE, MATERIAL OR CONTENT CONTAINED OR PRODUCED WITHIN THIS REPOSITORY. IN ADDITION, AND WITHOUT LIMITING THE FOREGOING, THIRD PARTIES MAY HAVE POSTED SOFTWARE, MATERIAL OR CONTENT TO THIS REPOSITORY WITHOUT ANY REVIEW. USE AT YOUR OWN RISK. 