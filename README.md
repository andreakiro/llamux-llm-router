[![GitHub stars](https://img.shields.io/github/stars/andreakiro/llamux-llm-router?style=social)](https://github.com/andreakiro/llamux-llm-router/stargazers)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://img.shields.io/pypi/v/llamux)](https://pypi.org/project/llamux/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

# llamux 🦙

A simple router to rotate across your configured LLM endpoints, balancing load and avoiding rate limits. The router selects your preferred provider-model pair based on an implicit preference list, ensuring token and request limits (day/hour/minute) aren't crossed. State persists across sessions, with quotas stored in local cache.

# Install

Requires Python 3.11+

```bash
pip install llamux
```

# Usage

You need first to set the list of endpoints you want to allow routing on;

```markdown
$ > endpoints.csv

| provider | model                   | rpm | tpm   | rph   | tph     | rpd   | tpd     |
| -------- | ----------------------- | --- | ----- | ----- | ------- | ----- | ------- |
| cerebras | llama3.3-70b            | 30  | 60000 | 900   | 1000000 | 14400 | 1000000 |
| groq     | llama-3.3-70b-versatile | 30  | 6000  | 14400 |         | 14400 |         |
```

where rpm, tpm are requests and tokens limits per minutes, and the same follows for hours and days. **Important note 🔊** Your implicit preference list is given by the ordering of the endpoints in this table. In the above, we'll always prefer Cerebras over Groq, as long as the quota limits are not exceeded.

## Use it as a standalone router;

```python
from llamux import Router

os.environ["CEREBRAS_API_KEY"] = "sk-..."
os.environ["GROQ_API_KEY"] = "sk-..."

router = Router.from_csv("endpoints.csv")
messages = [{"role": "user", "content": "Hello, how are you?"}]

provider, model, id, props = router.query(messages)
# provider: cerebras, model: llama3.3-70b
```

## Or use it directly as a completion endpoint;

```python
from llamux import Router

router = Router.from_csv("endpoints.csv")
messages = [{"role": "user", "content": "hey" * 59999}]

response = router.completion(messages) # calls cerebras
response = router.completion(messages) # calls groq (cerebras quota is out!)
```

The above builds upon [litellm](https://github.com/BerriAI/litellm) llm proxy

## More features

Contributions are welcome :)

- [ ] Add support for speed and cost routing preferences
- [ ] Add other routing strategies (now preferencial ordering only)
- [ ] Avoid getting preference listing from table ordering
