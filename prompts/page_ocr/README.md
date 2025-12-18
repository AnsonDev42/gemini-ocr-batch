# Page OCR Prompt Templates

This directory contains Jinja2 templates for generating prompts used in the Gemini batch inference pipeline.

## Template: `v1.jinja`

The initial version of the page OCR prompt template, extracted from `Curricular-Gemini.py`.

### Variables

- `previous_context` (optional): Context string from the previous page containing:
  - Last 500 characters of text from previous page
  - Last 3 courses with their metadata (department, level, term)

### Usage

```python
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('prompts/page_ocr'))
template = env.get_template('v1.jinja')

# Without context (first page)
prompt = template.render(previous_context=None)

# With context (subsequent pages)
prompt = template.render(previous_context=context_string)
```

### Template Features

- **Conditional context section**: Only includes previous page context if provided
- **Raw JSON examples**: Uses `{% raw %}` blocks to preserve JSON examples with `{{` and `}}` syntax
- **Two-part structure**: 
  1. Raw OCR text recognition with boundary detection
  2. Course information parsing from extracted text

### Version History

- **v1**: Initial extraction from `Curricular-Gemini.py` (2024)



