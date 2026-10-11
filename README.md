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
🚀 Çalıştırma Adımları (Getting Started)
1. Repoyu Klonlayın
Bash
git clone https://github.com/KULLANICI_ADIN/REPOSUN_ADI.git
cd REPOSUN_ADI
2. Sanal Ortam (Virtual Environment) Oluşturun
Bash
python -m venv venv
# Windows için:
venv\Scripts\activate
# macOS / Linux için:
source venv/bin/activate
3. Bağımlılıkları Yükleyin
Proje dizininde gerekli kütüphaneleri yükleyin:

Bash
pip install streamlit langchain-core langchain-google-genai langchain-chroma langgraph python-dotenv
4. Çevre Değişkenlerini (.env) Ayarlayın
Projenin ana dizininde bir .env dosyası oluşturun ve Gemini API anahtarınızı ekleyin:

Code snippet
GOOGLE_API_KEY=senin_gemini_api_anahtarin_buraya
5. Uygulamayı Başlatın
Streamlit Web Arayüzü ile:

Bash
streamlit run app.py
Terminal (CLI) Modunda:

Bash
python Multi_agents_fixed.py
🛠️ Kullanılan Teknolojiler
Orkestrasyon: LangGraph, LangChain

Yapay Zeka: Google Gemini API (gemini-1.5-flash)

Vektör Veritabanı: ChromaDB (RAG Error Memory)

Arayüz: Streamlit
