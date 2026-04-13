<p align="center">
  <img src="docs/images/hero.png" width="100%" alt="Anki-Maxxing Hero">
</p>

# ⚡ ANKI-MAXXING

> **Knowledge optimization at the speed of light.**

Anki-Maxxing is a tool that helps you get the most out of anki decks you make or download. Using AI to review decks and make semantically similar variations to prevent you from pattern recognizing the card structure instead of the content.

---

## ✨ Features

- **Semantic Rewriting**: Automatically generate semantically equivalent variations of your cards to ensure you understand the *concept*, not just the *wording*.
- **Spaced Repetition Preservation**: Enhances your workflow without breaking your cards scheduling.
- **Deep Integration**: Connects to deck using AnkiConnect.
- **Modern Dashboard**: Web-interface for easy use.

---

## 🚀 Getting Started

### 1. Install Python Dependencies
Ensure you have Python 3.12+ installed.
```bash
uv pip install -r requirements.txt
```

### 2. Install Frontend Dependencies
```bash
cd frontend && npm install
cd ..
```

### 3. Configure Environment
```bash
cp .env.example .env
```
then edit the .env file to match your setup


### 4. Running the App
Make sure **Anki** is running with the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on installed (code: `2055492159`).

Then run:
```bash
./start.sh
```

- **Frontend**: [http://localhost:3000](http://localhost:3000)
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

<p align="center">
  <img src="docs/images/logo.png" width="200" alt="Anki-Maxxing Logo">
  <br>
  <i>good luck studying ~</i>
</p>
