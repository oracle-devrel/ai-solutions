# Building AI Agents with Model Context Protocol (MCP) and Oracle Database 26ai

## Introduction

<img src="./img/mcp-oracle-ai-flow.png" alt="MCP Oracle AI Flow" width="80%">

This solution demonstrates how to build enterprise-grade AI agents that reason over live business data using Oracle Database 26ai and Model Context Protocol (MCP). MCP serves as a secure bridge between Large Language Models (LLMs) and Oracle Database, enabling agents to access structured data in real-time with full control and traceability.

## Key Features

- **MCP Integration**: Secure tool calling between LLMs and Oracle Database
- **Real-time Data Access**: Live business data integration without ETL
- **Vector RAG**: Native vector search capabilities in Oracle Database 26ai
- **NL2SQL/Select AI**: Natural language to SQL conversion
- **AI Optimizer**: Oracle's built-in AI optimization features
- **Langflow Integration**: Visual workflow builder for AI agents

## Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Langflow     │    │   MCP Server    │    │ Oracle Database │
│   AI Agent     │◄──►│   (Oracle DB)   │◄──►│     26ai        │
│                │    │                │    │                │
│ • Tool Calling │    │ • SQL Execution │    │ • Vector RAG   │
│ • Workflow     │    │ • Data Access   │    │ • Select AI    │
│ • LLM Chain   │    │ • Security      │    │ • AI Optimizer │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Prerequisites

- Oracle Database 26ai (cloud or container)
- Python 3.9+
- Langflow
- Oracle SQL Developer VS Code extension or SQLcl
- MCP server configuration

## Quick Start

### 1. Install Langflow

```bash
python -m venv langflowenv
.\langflowenv\Scripts\activate  # Windows
source langflowenv/bin/activate  # Linux/Mac
python -m pip install --upgrade pip
uv pip install langflow --no-cache-dir
langflow run --host 0.0.0.0 --port 7860
```

### 2. Configure Oracle MCP Server

Install Oracle SQL Developer VS Code extension and create a connection to your Oracle Database 26ai instance.

### 3. Set Up MCP Tools in Langflow

1. Create a new flow in Langflow
2. Add an "Agent" component
3. Add "MCP Tools" component
4. Configure Oracle MCP server connection

### 4. Create Your First AI Agent

Configure the agent with instructions like:

```
If a question is asked about stock or portfolio, use only the stock symbols 
and portfolio information found in the database via the run-sql functionality 
of the oracledb_mcp mcp-server services and not use or include external, 
realworld information like AAPL, etc. Use the PORTFOLIO_STOCKS view whenever 
possible for portfolio-related queries.
```

## Use Cases

### Financial Advisor Agent
- Portfolio analysis and recommendations
- Stock purchase/sale decisions
- Risk assessment based on live data
- Performance tracking and reporting

### Customer Service Agent
- Real-time customer data access
- Order status and history
- Personalized recommendations
- Issue resolution with context

### Business Intelligence Agent
- Data analysis and insights
- Report generation
- Trend identification
- Performance metrics

## Advanced Features

### Vector RAG Integration
- Store and search document embeddings
- Semantic similarity search
- Context-aware responses
- Multi-modal data support

### Select AI Integration
- Natural language queries
- Domain-specific insights
- Automated data exploration
- Business intelligence automation

### AI Optimizer
- Query performance optimization
- Automatic indexing
- Resource utilization
- Cost optimization

## Configuration

### MCP Server Configuration

```json
{
  "mcpServers": {
    "oracledb-mcp": {
      "command": "C:\\Users\\username\\sqlcl\\bin\\sql",
      "args": ["-mcp"],
      "env": {
        "TNS_ADMIN": "C:\\Users\\username\\wallet_local"
      }
    }
  }
}
```

### Environment Variables

```bash
export ORACLE_HOME=/path/to/oracle
export TNS_ADMIN=/path/to/wallet
export ORACLE_SID=your_sid
```

## Deployment Options

### Local Development
- Langflow on local machine
- Oracle Database 26ai container
- Local MCP server

### Cloud Deployment
- Oracle Cloud Infrastructure (OCI)
- Oracle Autonomous AI Database
- Containerized Langflow
- Kubernetes deployment

### Production Considerations
- Security and authentication
- Performance monitoring
- Scalability planning
- Backup and recovery

## Troubleshooting

### Common Issues

1. **MCP Connection Failed**
   - Verify Oracle Database connectivity
   - Check MCP server configuration
   - Validate credentials and permissions

2. **Tool Calling Errors**
   - Review agent instructions
   - Check tool availability
   - Verify data access permissions

3. **Performance Issues**
   - Monitor database performance
   - Optimize queries
   - Use AI Optimizer features

## Contributing

This project is open source. Please submit your contributions by forking this repository and submitting a pull request! Oracle appreciates any contributions that are made by the open source community.

## License

Copyright (c) 2024 Oracle and/or its affiliates.

Licensed under the Universal Permissive License (UPL), Version 1.0.

See [LICENSE](../LICENSE) for more details.

## Resources

- [Medium Article: Develop Agentic AI Workflows with Langflow and Oracle Database MCP](https://medium.com/oracledevs/develop-agentic-ai-workflows-with-langflow-and-oracle-database-mcp-vector-rag-nl2sql-select-ai-f9958b4481e8)
- [Oracle Database 26ai Documentation](https://docs.oracle.com/en/database/oracle/oracle-database/)
- [Model Context Protocol (MCP) Documentation](https://modelcontextprotocol.io/)
- [Langflow Documentation](https://docs.langflow.org/)
- [Oracle MCP Server](https://github.com/oracle/mcp/tree/main/src/dbtools-mcp-server)
