# 🤖 Autonomous Multi-Agent Python Coder & Self-Healing RAG System

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Multi--Agent-orange)](https://www.langchain.com/langgraph)
[![Gemini API](https://img.shields.io/badge/Gemini%20API-Flash-green)](https://ai.google.dev/)
[![Streamlit](https://img.shields.io/badge/Streamlit-Interactive%20UI-FF4B4B)](https://streamlit.io/)

Otonom kod üretimi, izole bir sandbox ortamında güvenli kod doğrulaması ve **kendi kendini düzelten (self-healing) RAG hafızası** içeren döngüsel çoklu-ajan (multi-agent) Python geliştirme sistemi.

---

## 🏗️ Mimari ve İşleyiş (Architecture Diagram)

Sistem, LangGraph kullanılarak birbirine bağlı 4 otonom ajandan oluşur. Kod test aşamasında hata verirse, ChromaDB üzerinden geçmiş hata tecrübeleri çekilerek Coder ajanına geri beslenir:

```mermaid
graph TD
    A[Kullanıcı Görevi] --> B[Planner Agent: Mimari Plan]
    B --> C[Coder Agent: Kod Üretimi]
    C --> D[Tester Agent: Sandbox Testi]
    D -- Başarısız --> E[ChromaDB: Hata Hafızası / RAG]
    E --> C
    D -- Başarılı --> F[Refactor Agent: PEP-8 & Type Hints]
    F --> G[Nihai Python Kodu]
