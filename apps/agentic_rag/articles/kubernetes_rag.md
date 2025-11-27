# Agentic RAG: Enterprise-Scale Multi-Agent AI System on Oracle Cloud Infrastructure

## Introduction

<img src="../img/architecture.png" width="100%">

Agentic RAG is an advanced Retrieval-Augmented Generation system that employs a multi-agent architecture with Chain-of-Thought reasoning, designed for enterprise-scale deployment on Oracle Cloud Infrastructure (OCI).

The system leverages specialized AI agents for complex document analysis and query processing, while taking advantage of OCI's managed Kubernetes service and security features for production-grade deployment.

With this article, we want to show you how you can get started in a few steps to install and deploy this multi-agent RAG system using Oracle Kubernetes Engine (OKE) and OCI.

## Features

This Agentic RAG system is based on the following technologies:

- Oracle Kubernetes Engine (OKE)
- Oracle Cloud Infrastructure (OCI)
- `ollama` as the inference server for most Large Language Models (LLMs) available in the solution (`llama3`, `phi3`, `qwen2`) 
- `Mistral-7B` language model, with an optional multi-agent Chain of Thought reasoning
- `ChromaDB` as vector store and retrieval system
- `Trafilatura`, `docling` and `gitingest` to extract the content from PDFs and web pages, and have them ready to be used by the RAG system
- Multi-agent architecture with specialized agents:
  - Planner Agent: Strategic decomposition of complex queries
  - Research Agent: Intelligent information retrieval (from vector database)
  - Reasoning Agent: Logical analysis and conclusion drawing
  - Synthesis Agent: Comprehensive response generation
- Support for both cloud-based (OpenAI) and local (Mistral-7B) language models
- Step-by-step reasoning visualization
- `Gradio` web interface for easy interaction with the RAG system

There are several benefits to using Containerized LLMs over running the LLMs directly on the cloud instances. For example:

- **Scalability**: you can easily scale the LLM workloads across Kubernetes clusters. In our case, we're deploying the solution with 4 agents in the same cluster, but you could deploy each agent in a different cluster if you wanted to accelerate the Chain-of-Thought reasoning processing time (horizontal scaling). You could also use vertical scaling by adding more resources to the same agent. 
- **Resource Optimization**: you can efficiently allocate GPU and memory resources for each agent
- **Isolation**: Each agent runs in its own container for better resource management
- **Version Control**: easily update and rollback LLM versions and configurations
- **Reproducibility**: have a consistent environment across development and production, which is crucial when you're working with complex LLM applications
- **Cost Efficiency**: you pay only for the resources you need, and when you're doen with your work, you can simply stop the Kubernetes cluster and you won't be charged for the resources anymore.
- **Integration**: you can easily integrate the RAG system with other programming languages or frameworks, as we also made available a REST-based API to interact with the system, apart from the standard web interface.

In conclusion, it's really easy to scale your system up and down with Kubernetes, without having to worry about the underlying infrastructure, installation, configuration, etc.

Note that the way we've planned the infrastructure is important because it allows us to:
1. Scale the `chromadb` vector store system independently
2. The LLM container can be shared across agents, meaning only deploying the LLM container once, and then using it across all the agents
3. The `Research Agent` can be scaled separately for parallel document processing, if needed
4. Memory and GPU resources can be optimized, since there's only one LLM instance running

## Deployment in Kubernetes

We have devised two different ways to deploy in Kubernetes: either through a local or distributed system, each offering its own advantages.

### Local Deployment

This method is the easiest way to implement and deploy. We call it local because every resource is deployed in the same pod. The advantages are the following:

- **Simplicity**: All components run in a single pod, making deployment and management straightforward
- **Easier debugging**: Troubleshooting is simpler when all logs and components are in one place (we're looking to expand the standard logging mechanism that we have right now with `fluentd`)
- **Quick setup**: Ideal for testing, development, or smaller-scale deployments
- **Lower complexity**: No need to configure inter-service communication or network policies like port forwarding or such mechanisms.

### Distributed System Deployment

By decoupling the `ollama` LLM inference system to another pod, we could easily ready our system for **vertical scaling**: if we're ever running out of resources or we need to use a bigger model, we don't have to worry about the other solution components not having enough resources for processing and logging: we can simply scale up our inference pod and connect it via a FastAPI or similar system to allow the Gradio interface to make calls to the model, following a distributed system architecture.

The advantages are:

- **Independent Scaling**: Each component can be scaled according to its specific resource needs
- **Resource Optimization**: Dedicated resources for compute-intensive LLM inference separate from other components
- **High Availability**: System remains operational even if individual components fail, and we can have multiple pods running failover LLMs to help us with disaster recovery.
- **Flexible Model Deployment**: Easily swap or upgrade LLM models without affecting the rest of the system (also, with virtually zero downtime!)
- **Load Balancing**: Distribute inference requests across multiple LLM pods for better performance, thus allowing concurrent users in our Gradio interface.
- **Isolation**: Performance issues on the LLM side won't impact the interface
- **Cost Efficiency**: Allocate expensive GPU resources only where needed (inference) while using cheaper CPU resources for other components (e.g. we use GPU for Chain of Thought reasoning, while keeping a quantized CPU LLM for standard chatting).

## Quick Start

For this solution, we have currently implemented the local system deployment, which is what we'll cover in this section.

First, we need to create a GPU OKE cluster with `zx` and Terraform. For this, you can follow the steps in [this repository](https://github.com/vmleon/oci-oke-gpu), or reuse your own Kubernetes cluster if you happen to already have one.

Then, we can start setting up the solution in our cluster by following these steps.

1. Clone the repository containing the Kubernetes manifests:

  ```bash
  git clone https://github.com/oracle-devrel/ai-solutions.git
  cd ai-solutions/apps/agentic_rag/k8s
  ```

2. Create a namespace:

  ```bash
  kubectl create namespace agentic-rag
  ```

3. Create a ConfigMap:

  This step will help our deployment for several reasons:

  1. **Externalized Configuration**: It separates configuration from application code, following best practices for containerized applications
  2. **Environment-specific Settings**: Allows us to maintain different configurations for development, testing, and production environments
  3. **Credential Management**: Provides a way to inject API tokens (like Hugging Face) without hardcoding them in the image
  4. **Runtime Configuration**: Enables changing configuration without rebuilding or redeploying the application container
  5. **Consistency**: Ensures all pods use the same configuration when scaled horizontally

  In our specific case, the ConfigMap stores the Hugging Face Hub token for accessing (and downloading) the `mistral-7b` model (and CPU-quantized variants)
  - Optionally, OpenAI API keys if using those models
  - Any other environment-specific variables needed by the application, in case we want to make further development and increase the capabilities of the system with external API keys, authentication tokens... etc.

  Let's run the following command to create the config map:

  ```bash
  # With a Hugging Face token
  cat <<EOF | kubectl apply -n agentic-rag -f -
  apiVersion: v1
  kind: ConfigMap
  metadata:
    name: agentic-rag-config
  data:
    config.yaml: |
      HUGGING_FACE_HUB_TOKEN: "your-huggingface-token"
  EOF

  # Or without a Hugging Face token
  cat <<EOF | kubectl apply -n agentic-rag -f -
  apiVersion: v1
  kind: ConfigMap
  metadata:
    name: agentic-rag-config
  data:
    config.yaml: |
      # No Hugging Face token provided
      # You can still use Ollama models
  EOF
  ```

  This approach makes our deployment more flexible, secure, and maintainable compared to hardcoding configuration values.

4. Apply the manifests:

  ```bash
  kubectl apply -n agentic-rag -f local-deployment/pvcs.yaml
  kubectl apply -n agentic-rag -f local-deployment/deployment.yaml
  kubectl apply -n agentic-rag -f local-deployment/service.yaml
  ```

  If for some reason, after applying these, there's a `NoSchedule` policy being triggered, you can untaint the nodes and try again:

  ```bash
  kubectl taint nodes -l node.kubernetes.io/instance-type=VM.GPU.A10.1 nvidia.com/gpu:NoSchedule-
  # make sure to select your own instance shape if you're using a different type than A10 GPU.
  ```

5. Monitor the Deployment

  With the following commands, we can check the status of our pod:

  ```bash
  kubectl get pods -n agentic-rag
  ```

  And view the internal logs of the pod:

  ```bash
  kubectl logs -f deployment/agentic-rag -n agentic-rag
  ```

6. Access the Application

Get the external IP address of the service:

```bash
kubectl get service agentic-rag -n agentic-rag
```

Access the application in your browser at `http://<EXTERNAL-IP>`.

## Resource Requirements

The deployment of this solution requires the following minimum resources:

- **CPU**: 4+ cores
- **Memory**: 16GB+ RAM
- **Storage**: 50GB+
- **GPU**: recommended for faster inference. In theory, you can use `mistral-7b` CPU-quantized models, but it will be sub-optimal.

## Conclusion

You can check out the full AI solution and the deployment options we mention in this article in [the official GitHub repository](https://github.com/oracle-devrel/ai-solutions/tree/main/apps/agentic_rag).