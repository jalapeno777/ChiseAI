# LLM Provider Configuration

## Provider Fallback Chain

The system uses a prioritized fallback chain for LLM providers:

1. **KIMI 2.5 (k2p5)** - Primary provider
   - Endpoint: https://api.kimi.com/coding/v1
   - Model: k2p5
   - Env var: KIMI_API_KEY
   - Enabled by default

2. **GLM-5 (Z.ai)** - Secondary provider
   - Endpoint: https://api.z.ai/api/paas/v4/chat/completions
   - Model: glm-5
   - Env var: ZAI_API_KEY or ZHIPU_API_KEY

3. **GLM-4.7 (Zhipu)** - Tertiary provider
   - Endpoint: https://api.z.ai/api/paas/v4/chat/completions
   - Model: glm-4.7
   - Env var: ZHIPU_API_KEY

4. **MiniMax 2.5** - Quaternary provider (disabled by default)
   - Endpoint: https://api.minimax.io/v1/text/chatcompletion_v2
   - Model: MiniMax-M2.5
   - Env var: MINIMAX_API_KEY
   - **Requires explicit enable**: MINIMAX_ENABLED=true

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| KIMI_API_KEY | Yes | - | KIMI API key |
| KIMI_MODEL | No | k2p5 | Model ID (k2p5 or k2p5_think) |
| KIMI_ENABLED | No | true | Enable KIMI provider |
| ZAI_API_KEY | No | - | Z.ai API key (alternative to ZHIPU_API_KEY) |
| ZHIPU_API_KEY | No | - | Zhipu API key |
| MINIMAX_API_KEY | No | - | MiniMax API key |
| MINIMAX_ENABLED | No | false | Enable MiniMax provider |

## Configuration Examples

### Primary: KIMI only
```bash
KIMI_API_KEY=your_key_here
```

### With MiniMax fallback enabled
```bash
KIMI_API_KEY=your_kimi_key
ZHIPU_API_KEY=your_zhipu_key
MINIMAX_API_KEY=your_minimax_key
MINIMAX_ENABLED=true
```

## Agent Model Assignments

The Opencode agent swarm uses the following model assignments:

| Agent | Model | Temperature | Purpose |
|-------|-------|-------------|---------|
| jarvis | zai-coding-plan/glm-4.7-thinking | 0.2 | Planning and assessment |
| dev | kimi-for-coding/k2p5 | 0.2 | General development |
| senior-dev | kimi-for-coding/k2p5 | 0.15 | Complex development tasks |
| quickdev | minimax/MiniMax-M2.5 | 0.35 | Fast execution tasks |
| research | - | - | Repo docs and forensics (no edits) |
| web-research | - | - | Online search and citations (no edits) |
| critic | - | - | Adversarial review (no edits) |

## See Also

- [Product Requirements Document](./prd.md)
- [Architecture Overview](./architecture.md)
