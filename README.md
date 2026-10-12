# 🤖 Autonomous Multi-Agent Python Coder & Self-Healing RAG System

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-orange)](https://www.langchain.com/langgraph)
[![Gemini API](https://img.shields.io/badge/Gemini%20API-Flash-green)](https://ai.google.dev/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Interactive%20UI-FF4B4B)](https://streamlit.io/)

A cyclic multi-agent Python development system featuring autonomous code generation, secure code verification in an isolated sandbox environment, and self-healing RAG memory.

## 🏗️ Architecture & Workflow

The system consists of 4 autonomous agents interconnected using LangGraph. If the code fails during the testing phase, past error logs and resolution patterns are retrieved from ChromaDB and fed back to the Coder agent to iteratively fix the code.

## 🚀 Getting Started

1. Clone the Repository
git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git
cd YOUR_REPOSITORY_NAME

2. Create a Virtual Environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS / Linux:
source venv/bin/activate

3. Install Dependencies
pip install streamlit langchain-core langchain-google-genai langchain-chroma langgraph python-dotenv

4. Set Up Environment Variables (.env)
Create a .env file in the root directory and add your Google Gemini API key:
GOOGLE_API_KEY=your_gemini_api_key_here

5. Run the Application
* Via Streamlit Web Interface: streamlit run app.py
* Via Terminal (CLI) Mode: python Multi_agents_fixed.py

## 🛠️ Tech Stack

* Orchestration: LangGraph, LangChain
* Artificial Intelligence: Google Gemini API (gemini-1.5-flash)
* Vector Database: ChromaDB (RAG Error Memory)
* Frontend / UI: Streamlit
