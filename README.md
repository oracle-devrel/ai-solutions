# AI Solutions

Welcome to the AI Solutions repository, a collection of deployable apps, workshops and tools built with Oracle technologies, some of them featured in [oracle.ai](https://oracle.ai). This repository contains practical implementations, demos, and guides for various AI use cases.

## Repository Structure

- `apps/`: Deployable applications, automation scripts, and infrastructure-as-code projects.
- `workshops/`: Step-by-step guides, LiveLabs content, and educational materials.
- `notebooks/`: Reserved for notebook-driven explorations and tutorials (currently minimal).

## 🚀 New AI Solutions (2026)

### 1. [OCI GenAI Routing Profile Lab](./apps/oci-genai-routing-profile/)
**Validate OCI Generative AI Routing Profiles Across Multiple Agent Workflows**

- **Routing-Profile Validation**: Confirm selected inference regions comply with the profile's allowed-region policy
- **OpenAI-Compatible API**: Use the routing-profile OCID directly as the model with the OpenAI Python SDK
- **Agent Workflows**: Run equivalent LangChain chat-agent and OpenAI Agents SDK experiments
- **Response Verification**: Capture `x-genai-selected-region` response headers for every live request
- **Terraform Automation**: Provision a routing profile and compartment-scoped API-key policy

### 2. [OCI GenAI Sandbox Lab](./apps/oci-sandbox-demo/)
**Interactive Lab for OCI Generative AI Sandboxes and the OpenAI-Compatible Responses API**

- **Sandbox Tutorials**: Executable tutorials for OCI Generative AI Sandboxes
- **OpenAI-Compatible API**: Build with OCI's OpenAI-compatible Responses API
- **Live Execution**: View API calls, commands, output, and sandbox lifecycle events
- **Agent Workflows**: Examples for OpenAI Agents SDK and LangGraph workflows
- **Use Cases**: Secure experimentation, agent development, web research, and model evaluation

### 3. [MCP Audio on OKE](./apps/oracle-mcp-oke/)
**Deploy an MCP Audio Server and Client on Oracle Kubernetes Engine (OKE)**

- **MCP Audio Server**: Audio transcription and text-analysis workflows exposed through MCP
- **OKE Deployment**: Deploy server and Gradio client applications on Oracle Kubernetes Engine
- **Terraform Automation**: Provision networking, OKE, OCIR repositories, and storage resources
- **OCIR Integration**: Build and publish container images to Oracle Cloud Infrastructure Registry
- **Use Cases**: Audio transcription, sentiment analysis, and MCP-enabled AI applications

### 4. [Oracle MCP AI Agents](./apps/oracle-mcp-ai-agents/)
**Building AI Agents with Model Context Protocol (MCP) and Oracle AI Database**

- **MCP Integration**: Secure tool calling between LLMs and Oracle Database
- **Real-time Data Access**: Live business data integration without ETL
- **Vector RAG**: Native vector search capabilities
- **Langflow Integration**: Visual workflow builder for AI agents
- **Use Cases**: Financial advisor, customer service, business intelligence

### 5. [Oracle Select AI Insights](./apps/oracle-select-ai-insights/)
**Talk with Industry-Specific Domain Data and Gain Insights Using Select AI**

- **Natural Language Queries**: Ask questions in plain English
- **Domain-Specific Knowledge**: Industry-tailored insights and analysis
- **No SQL Required**: Democratized data access for business users
- **Multi-Industry Support**: Finance, healthcare, retail, manufacturing
- **Use Cases**: Business intelligence, compliance, operational analytics

## 🔧 Existing Solutions

### AI & Machine Learning
- [Agentic RAG](./apps/agentic_rag/) - AI RAG in a BOX Demo using Oracle AI Database and Local LLMs
- [PlaneLLM](./apps/planeLLM/) - Generate bite-sized educational podcasts using OCI Generative AI
- [LangGraph Agent with GenAI](./apps/langgraph_agent_with_genai/) - File indexing and conversational search using LangGraph and Oracle Generative AI
- [Neural Networks Hero](./workshops/neural_networks_hero/) - Neural network implementations and tutorials

### Computer Vision
- [OCI Vision AI](./apps/OJET%20(VDOM)%20-%20OCI%20Vision/) - Oracle JET application with OCI Vision integration for image analysis
- [Mask Detection](./workshops/mask_detection_training/) - Training and labeling for mask detection models

### Language & Translation
- [OCI Language Translation](./apps/oci-language-translation/) - Multi-language translation services
- [OCI Subtitle Translation](./apps/oci-subtitle-translation/) - Automated subtitle translation
- [OCI CSV-JSON Translation](./apps/oci-csv-json-translation/) - Data format conversion tools
- [OCI Language Multiple Translation](./apps/oci-language-multiple-translation/) - Bulk document translation using OCI Language

### DevOps & OKE
- [NVIDIA NIM on OKE](./apps/nvidia-nim-oke/) - NVIDIA Inference Microservices on Oracle Container Engine
- [Holoscan](./apps/holoscan/) - Holoscan applications and deployments
- [MCP Audio on OKE](./apps/oracle-mcp-oke/) - MCP audio server and client deployment on Oracle Kubernetes Engine

### Data & Analytics
- [Data in AI Revolution](./workshops/data-in-ai-revolution/) - Data-driven AI solutions and insights
- [RAG in a Box](./apps/rag_in_a_box/) - Retrieval-Augmented Generation solutions
- [Oracle Select AI Insights](./apps/oracle-select-ai-insights/) - Natural language insights for industry-specific domain data

## 📁 Directory Contents

### Apps Directory (`apps/`)

- **[agentic_rag](./apps/agentic_rag/)** - Multi-agent RAG system with Chain-of-Thought reasoning using Oracle AI Database and local LLMs
- **[holoscan](./apps/holoscan/)** - Terraform stack for deploying NVIDIA Holoscan on Oracle Linux A10 GPU instances
- **[langflow-agentic-ai-oracle-mcp-vector-nl2sql](./apps/langflow-agentic-ai-oracle-mcp-vector-nl2sql/)** - Agentic AI workflows with Langflow, Oracle Database MCP, Vector RAG, and NL2SQL
- **[langgraph_agent_with_genai](./apps/langgraph_agent_with_genai/)** - File indexing and conversational search using LangGraph and Oracle Generative AI
- **[mongo-migration](./apps/mongo-migration/)** - Migration tools and solutions for moving MongoDB applications to Oracle Database
- **[nvidia-nim-oke](./apps/nvidia-nim-oke/)** - Deploying NVIDIA Inference Microservices on Oracle Kubernetes Engine with GPU support
- **[oci-csv-json-translation](./apps/oci-csv-json-translation/)** - Translate specific columns in CSV files or keys in JSON documents using OCI Language
- **[oci-genai-routing-profile](./apps/oci-genai-routing-profile/)** - Local lab for validating OCI Generative AI routing profiles with OpenAI SDK, LangChain, and OpenAI Agents SDK workflows
- **[oci-language-multiple-translation](./apps/oci-language-multiple-translation/)** - Bulk translation of multiple documents from OCI Object Storage buckets
- **[oci-language-translation](./apps/oci-language-translation/)** - Multi-language translation services for documents and text using OCI Language
- **[oci-sandbox-demo](./apps/oci-sandbox-demo/)** - Interactive Streamlit lab for OCI Generative AI Sandboxes and the OpenAI-compatible Responses API
- **[oci-subtitle-translation](./apps/oci-subtitle-translation/)** - Transcribe audio files and translate subtitles using OCI Speech and Language services
- **[OJET (VDOM) - OCI Vision](./apps/OJET%20(VDOM)%20-%20OCI%20Vision/)** - Oracle JET Virtual DOM application with OCI Vision integration for image analysis
- **[oracle-mcp-ai-agents](./apps/oracle-mcp-ai-agents/)** - Building AI agents with Model Context Protocol (MCP) and Oracle AI Database
- **[oracle-mcp-oke](./apps/oracle-mcp-oke/)** - Deploy MCP audio server and Gradio client applications on Oracle Kubernetes Engine
- **[oracle-select-ai-insights](./apps/oracle-select-ai-insights/)** - Natural language queries for industry-specific domain data using Oracle Select AI
- **[planeLLM](./apps/planeLLM/)** - Generate bite-sized educational podcasts on any topic using OCI GenAI service
- **[rag_in_a_box](./apps/rag_in_a_box/)** - Containerized RAG system with Oracle AI Database and local LLMs deployable via Podman

### Workshops Directory (`workshops/`)

- **[ai-meetings](./workshops/ai-meetings/)** - Build web applications using Visual Builder Cloud Service with AI-powered meeting transcription, summarization, and sentiment analysis
- **[data-in-ai-revolution](./workshops/data-in-ai-revolution/)** - Educational workshop on data types, structures, and processing techniques in AI and machine learning
- **[mask_detection_labeling](./workshops/mask_detection_labeling/)** - Step-by-step guide for creating and labeling a computer vision model to detect mask-wearing states using RoboFlow
- **[mask_detection_training](./workshops/mask_detection_training/)** - Training and improving YOLO-based object detection models for mask detection on Oracle Cloud Infrastructure
- **[neural_networks_hero](./workshops/neural_networks_hero/)** - Comprehensive workshop on neural network implementations, training, and inference for computer vision tasks

### Notebooks Directory (`notebooks/`)

- Currently empty - Reserved for notebook-driven explorations and tutorials

## 🚀 Getting Started

Each solution includes:
- Comprehensive README with architecture overview
- Quick start guides and prerequisites
- Configuration examples and deployment options
- Use cases and best practices
- Troubleshooting guides

## 📚 Resources

- [Oracle AI Database](https://www.oracle.com/database/ai-native-database-26ai/)
- [Oracle Cloud Infrastructure](https://www.oracle.com/cloud/)

## 🤝 Contributing

We welcome contributions! Please see individual solution directories for contribution guidelines.

## 📄 License

Copyright (c) 2024 Oracle and/or its affiliates.

Licensed under the Universal Permissive License (UPL), Version 1.0.

See [LICENSE](./LICENSE) for more details.

---

*Built with ❤️ by the Oracle DevRel team*
