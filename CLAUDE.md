# CLAUDE.md

## Repository Overview

The **anthropic-cookbook** is Anthropic's official collection of code examples and guides for building with the Claude API. It provides copy-able code snippets and interactive tutorials (primarily Jupyter notebooks) organized around Claude's core capabilities.

- **License:** Apache 2.0
- **Primary Language:** Python
- **Content Format:** Jupyter notebooks (`.ipynb`), Python scripts, Markdown docs
- **Target Audience:** Developers integrating Claude into their applications

## Directory Structure

```
anthropic-cookbook/
├── skills/                  # In-depth skill guides with evaluations
│   ├── citations/           # Source attribution techniques
│   ├── classification/      # Text/data classification
│   ├── contextual-embeddings/ # Contextual RAG embeddings
│   ├── retrieval_augmented_generation/ # Full RAG pipeline
│   ├── summarization/       # Multi-document summarization
│   └── text_to_sql/         # Natural language to SQL
├── misc/                    # Standalone technique notebooks
├── multimodal/              # Vision and multimodal capabilities
├── tool_use/                # Tool use and function calling
├── third_party/             # External service integrations
│   ├── Brave/               # Web search
│   ├── Deepgram/            # Speech-to-text
│   ├── LlamaIndex/          # RAG framework
│   ├── MongoDB/             # Vector database
│   ├── Pinecone/            # Vector database
│   ├── VoyageAI/            # Text embeddings
│   ├── Wikipedia/           # Knowledge base search
│   └── WolframAlpha/        # Mathematical computation
├── finetuning/              # Fine-tuning examples (AWS Bedrock)
├── images/                  # Supporting images for notebooks
├── README.md                # Main documentation with recipe table
└── .gitignore               # Python-focused exclusions
```

## Skills Directory Pattern

Each skill follows a consistent structure:

```
skill_name/
├── guide.ipynb              # Main interactive tutorial
├── data/                    # Sample datasets (PDF, JSON, TXT, CSV, SQLite)
└── evaluation/
    ├── README.md            # Evaluation methodology docs
    ├── promptfooconfig.yaml # PromptFoo test configuration
    ├── dataset.csv          # Test dataset
    ├── prompts.py           # Prompt definitions for evaluation
    ├── transform.py         # Output transformation scripts
    └── vectordb.py          # Vector DB utilities (where applicable)
```

## Conventions and Patterns

### Notebook Style
- Notebooks are self-contained tutorials with explanatory markdown cells
- Each notebook includes its own dependency installation cells (`!pip install ...`)
- API keys are expected via environment variables (typically `ANTHROPIC_API_KEY`)
- Notebooks demonstrate complete workflows from setup to results

### Python Code
- No centralized `requirements.txt` or `pyproject.toml` -- dependencies are managed per-notebook
- Uses the `anthropic` Python SDK for API calls
- Common libraries: `pandas`, `numpy`, `scikit-learn`, `voyageai`, `pinecone-client`
- No formal linting or formatting configuration in the repo

### Evaluation Framework
- Uses **PromptFoo** (YAML-based LLM evaluation framework) for standardized testing
- Evaluation configs compare multiple Claude models (Haiku, Sonnet, Opus)
- Temperature is typically set to 0 for reproducible evaluations
- Custom Python scripts handle output transformation and scoring
- Metrics include BLEU, ROUGE, and LLM-based evaluation (Claude-as-judge)
- Test datasets stored as CSV files

### API Usage Patterns
- Messages API is the primary interface (not legacy completions)
- `max_tokens` is always explicitly set
- Prompts use system messages for role/context and user messages for tasks
- Tool use follows the standard Anthropic tool definition schema
- Vision examples use base64-encoded images or URLs in message content

## Development Workflow

### Adding a New Skill Guide
1. Create a new directory under `skills/` with the skill name
2. Add a `guide.ipynb` with comprehensive tutorial content
3. Include sample data in a `data/` subdirectory
4. Create an `evaluation/` directory with:
   - `promptfooconfig.yaml` for test definitions
   - `dataset.csv` with test cases
   - `prompts.py` with evaluation prompts
   - `README.md` explaining the evaluation approach

### Adding a Misc Tutorial
- Create a standalone `.ipynb` file in `misc/`
- Include pip install cells for any dependencies
- Add an entry to the root `README.md` table of recipes

### Adding a Third-Party Integration
- Create a directory under `third_party/` named after the service
- Include one or more notebooks demonstrating the integration
- Provide clear setup instructions for API keys and dependencies

### Running Evaluations
```bash
# Install PromptFoo
npm install -g promptfoo

# Run evaluation for a specific skill
cd skills/<skill_name>/evaluation
promptfoo eval
```

## Key Technical Details

### Claude Models Referenced
- `claude-3-haiku-20240307` (fast, cost-effective)
- `claude-3-5-sonnet-20240620` (balanced)
- `claude-3-opus-20240229` (most capable)

### Environment Variables
- `ANTHROPIC_API_KEY` -- required for all examples
- Service-specific keys for third-party integrations (e.g., `PINECONE_API_KEY`, `BRAVE_API_KEY`, `VOYAGE_API_KEY`)

### Data Files
- PDFs, text files, and JSON documents serve as source material for RAG examples
- Pre-computed pickle files (`.pkl`) contain vector databases for quick demo usage
- SQLite database used for text-to-SQL examples
- JSONL files used for fine-tuning datasets

## Important Notes for Contributors

- This is an educational/cookbook repository -- clarity and readability are prioritized over DRY principles
- Each notebook should be independently runnable without external setup beyond API keys
- Examples should demonstrate real-world, production-relevant patterns
- Include both basic and advanced usage in skill guides
- Update the root `README.md` when adding new content
- Keep notebooks focused on a single concept or workflow
- Avoid committing large binary files or credentials
- The `.gitignore` excludes `.env` files, Jupyter checkpoints, and compiled Python files
