# Laix RAG Service

## About the Project
The **Laix RAG Service** is an AI-powered document retrieval and analysis system utilizing Retrieval-Augmented Generation (RAG). It is specifically designed to handle and process large volumes of jurisprudence and legal documents.

## Document and Jurisprudence Structure
The system is built to ingest, index, and retrieve insights from a vast corpus of legal documents (currently managing an extensive collection of over 25GB of PDFs and legal texts). The pipeline extracts text, generates contextual embeddings, and stores them in a vector database, enabling highly accurate semantic search. This allows legal professionals and users to instantly query case law, rulings, and statutes, getting accurate, AI-summarized responses backed by specific document citations.

## System Architecture
The service is built on a modern, robust, and scalable stack:
- **FastAPI (Python):** Serves as the core backend, providing high-performance RESTful APIs to handle ingestion and query requests.
- **PostgreSQL with pgvector:** Acts as the primary database, specifically optimized to store and perform similarity searches over high-dimensional vector embeddings generated from the documents.
- **Redis & Celery:** Used for asynchronous task management. The heavy lifting of parsing PDFs, generating embeddings (e.g., using multilingual mpnet), and indexing them is offloaded to background workers to ensure the main API remains highly responsive.
- **Docker & Containerization:** The entire architecture (API, workers, databases) is fully containerized, ensuring consistency across environments and seamless scalability.

## GitHub Actions & CI/CD
Continuous Integration and Continuous Deployment (CI/CD) pipelines are orchestrated through **GitHub Actions**. This automation guarantees:
- **Reliable Deployments:** Every push to the main branch triggers automated testing and deployment pipelines, minimizing human error.
- **Environment Management:** Secrets and environment variables (such as SMTP credentials and Model secrets) are securely managed and injected during the build process.
- **Quality Assurance:** Code quality is continuously monitored, ensuring that new features or optimizations do not break the existing RAG pipeline before reaching production.

## Impact on the CRM
The Laix RAG Service acts as the cognitive engine for the company's CRM platform:
- **Instant Legal Insights:** Sales or support agents using the CRM can query complex legal topics directly within their workflow, receiving AI-generated answers with exact citations from the jurisprudence database.
- **Efficiency & Automation:** By automating the legal research phase, the service dramatically reduces the time spent looking up precedents, allowing agents to close cases and resolve inquiries much faster.
- **Seamless Integration:** The RESTful architecture allows the CRM to seamlessly consume the RAG API, essentially transforming a traditional CRM into an intelligent, AI-assisted legal workspace.

## AI in Development
This project was developed with the substantial assistance of Artificial Intelligence.

### Advantages of using AI
- **Rapid Prototyping:** AI accelerated the setup of complex pipelines (e.g., Docker environments, vector databases, and API integrations).
- **Code Optimization:** Assisting in identifying bottlenecks, improving file ingestion handling, and gracefully managing corrupted documents.
- **Architectural Guidance:** Providing best practices for RAG systems, embedding models, and database selection.

### My Role as a Developer
As the developer, my role focuses on orchestrating the architecture, defining the business logic, reviewing and refining AI-generated solutions, and ensuring the final product strictly adheres to security, robustness, and performance standards. AI serves as a powerful pair-programmer, while I maintain the strategic direction, problem solving, and quality assurance of the service.
