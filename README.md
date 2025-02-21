# Project Analyzer

This tool analyzes a project directory using Claude 3.5 Sonnet via OpenRouter API to generate a comprehensive project analysis report.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your OpenRouter API key:
```
OPENROUTER_API_KEY=your_api_key_here
```

3. Run the analyzer:
```bash
python project_analyzer.py
```

## Features

- Recursively analyzes all files in the target directory
- Generates a detailed markdown report including:
  - Complete project file listing
  - Function analysis
  - Dependency relationships
  - Project structure patterns
  - Comprehensive project interpretation

## Output

The analysis report will be saved as `project_analysis_TIMESTAMP.md` in the current directory.
