export const LLM_MODELS = [
  { value: "", label: "Server Default" },
  // Google Gemini — Vertex AI
  {
    value: "vertex_ai/gemini-3-flash-preview",
    label: "Gemini 3 Flash (Vertex)",
  },
  {
    value: "vertex_ai/gemini-3.1-flash-lite-preview",
    label: "Gemini 3.1 Flash Lite (Vertex)",
  },
  { value: "vertex_ai/gemini-2.5-pro", label: "Gemini 2.5 Pro (Vertex)" },
  { value: "vertex_ai/gemini-2.5-flash", label: "Gemini 2.5 Flash (Vertex)" },
  {
    value: "vertex_ai/gemini-2.5-flash-image",
    label: "Gemini 2.5 Flash Image (Vertex)",
  },
  {
    value: "vertex_ai/gemini-2.5-flash-lite",
    label: "Gemini 2.5 Flash Lite (Vertex)",
  },
  {
    value: "vertex_ai/gemini-2.5-flash-lite-preview-09-2025",
    label: "Gemini 2.5 Flash Lite 09-2025 (Vertex)",
  },
  // Google Gemini — Firebase
  { value: "gemini-2.5-flash-fb", label: "Gemini 2.5 Flash (Firebase)" },
  { value: "gemini-2.5-pro-fb", label: "Gemini 2.5 Pro (Firebase)" },
  // Google Gemini — OpenRouter
  {
    value: "openrouter/google/gemini-3.1-pro-preview",
    label: "Gemini 3.1 Pro Preview (OpenRouter)",
  },
  {
    value: "openrouter/google/gemini-3-flash-preview",
    label: "Gemini 3 Flash Preview (OpenRouter)",
  },
  {
    value: "openrouter/google/gemini-2.5-pro",
    label: "Gemini 2.5 Pro (OpenRouter)",
  },
  {
    value: "openrouter/google/gemini-2.5-flash",
    label: "Gemini 2.5 Flash (OpenRouter)",
  },
  {
    value: "openrouter/google/gemini-2.0-flash-001",
    label: "Gemini 2.0 Flash (OpenRouter)",
  },
  // Anthropic Claude — OpenRouter
  {
    value: "openrouter/anthropic/claude-opus-4.6",
    label: "Claude Opus 4.6 (OpenRouter)",
  },
  {
    value: "openrouter/anthropic/claude-opus-4.5",
    label: "Claude Opus 4.5 (OpenRouter)",
  },
  {
    value: "openrouter/anthropic/claude-opus-4.1",
    label: "Claude Opus 4.1 (OpenRouter)",
  },
  {
    value: "openrouter/anthropic/claude-opus-4",
    label: "Claude Opus 4 (OpenRouter)",
  },
  {
    value: "openrouter/anthropic/claude-sonnet-4.6",
    label: "Claude Sonnet 4.6 (OpenRouter)",
  },
  {
    value: "openrouter/anthropic/claude-sonnet-4.5",
    label: "Claude Sonnet 4.5 (OpenRouter)",
  },
  {
    value: "openrouter/anthropic/claude-sonnet-4",
    label: "Claude Sonnet 4 (OpenRouter)",
  },
  {
    value: "openrouter/anthropic/claude-haiku-4.5",
    label: "Claude Haiku 4.5 (OpenRouter)",
  },
  {
    value: "openrouter/anthropic/claude-3.7-sonnet",
    label: "Claude 3.7 Sonnet (OpenRouter)",
  },
  {
    value: "openrouter/anthropic/claude-3.5-sonnet",
    label: "Claude 3.5 Sonnet (OpenRouter)",
  },
  {
    value: "openrouter/anthropic/claude-3-haiku",
    label: "Claude 3 Haiku (OpenRouter)",
  },
  // OpenAI — OpenRouter
  { value: "openrouter/openai/gpt-4o", label: "GPT-4o (OpenRouter)" },
  {
    value: "openrouter/openai/gpt-4o-2024-05-13",
    label: "GPT-4o 2024-05-13 (OpenRouter)",
  },
  { value: "openrouter/openai/gpt-4", label: "GPT-4 (OpenRouter)" },
  {
    value: "openrouter/openai/gpt-3.5-turbo",
    label: "GPT-3.5 Turbo (OpenRouter)",
  },
  {
    value: "openrouter/openai/gpt-3.5-turbo-16k",
    label: "GPT-3.5 Turbo 16K (OpenRouter)",
  },
  {
    value: "openrouter/openai/gpt-oss-120b",
    label: "GPT OSS 120B (OpenRouter)",
  },
  { value: "openrouter/openai/gpt-oss-20b", label: "GPT OSS 20B (OpenRouter)" },
  // xAI Grok — OpenRouter
  { value: "openrouter/x-ai/grok-4", label: "Grok 4 (OpenRouter)" },
  { value: "openrouter/x-ai/grok-4-fast", label: "Grok 4 Fast (OpenRouter)" },
  { value: "openrouter/x-ai/grok-3-mini", label: "Grok 3 Mini (OpenRouter)" },
  // DeepSeek — OpenRouter
  {
    value: "openrouter/deepseek/deepseek-r1-0528",
    label: "DeepSeek R1 0528 (OpenRouter)",
  },
  {
    value: "openrouter/deepseek/deepseek-r1",
    label: "DeepSeek R1 (OpenRouter)",
  },
  {
    value: "openrouter/deepseek/deepseek-chat-v3.1",
    label: "DeepSeek Chat V3.1 (OpenRouter)",
  },
  {
    value: "openrouter/deepseek/deepseek-chat-v3-0324",
    label: "DeepSeek Chat V3 0324 (OpenRouter)",
  },
  {
    value: "openrouter/deepseek/deepseek-chat",
    label: "DeepSeek Chat (OpenRouter)",
  },
  // Qwen — OpenRouter
  {
    value: "openrouter/qwen/qwen3.5-397b-a17b",
    label: "Qwen3.5 397B (OpenRouter)",
  },
  {
    value: "openrouter/qwen/qwen3.5-122b-a10b",
    label: "Qwen3.5 122B (OpenRouter)",
  },
  {
    value: "openrouter/qwen/qwen3.5-35b-a3b",
    label: "Qwen3.5 35B (OpenRouter)",
  },
  { value: "openrouter/qwen/qwen3.5-27b", label: "Qwen3.5 27B (OpenRouter)" },
  {
    value: "openrouter/qwen/qwen3-235b-a22b-thinking-2507",
    label: "Qwen3 235B Thinking (OpenRouter)",
  },
  {
    value: "openrouter/qwen/qwen3-235b-a22b-2507",
    label: "Qwen3 235B (OpenRouter)",
  },
  {
    value: "openrouter/qwen/qwen3-coder-plus",
    label: "Qwen3 Coder Plus (OpenRouter)",
  },
  { value: "openrouter/qwen/qwen3-coder", label: "Qwen3 Coder (OpenRouter)" },
  {
    value: "openrouter/qwen/qwen3.5-plus-02-15",
    label: "Qwen3.5 Plus (OpenRouter)",
  },
  {
    value: "openrouter/qwen/qwen3.5-flash-02-23",
    label: "Qwen3.5 Flash (OpenRouter)",
  },
  {
    value: "openrouter/qwen/qwen-2.5-coder-32b-instruct",
    label: "Qwen2.5 Coder 32B (OpenRouter)",
  },
  // Mistral — OpenRouter
  {
    value: "openrouter/mistralai/mistral-large-2512",
    label: "Mistral Large 2512 (OpenRouter)",
  },
  {
    value: "openrouter/mistralai/mistral-large",
    label: "Mistral Large (OpenRouter)",
  },
  {
    value: "openrouter/mistralai/mixtral-8x22b-instruct",
    label: "Mixtral 8x22B (OpenRouter)",
  },
  {
    value: "openrouter/mistralai/ministral-14b-2512",
    label: "Ministral 14B (OpenRouter)",
  },
  {
    value: "openrouter/mistralai/ministral-8b-2512",
    label: "Ministral 8B (OpenRouter)",
  },
  {
    value: "openrouter/mistralai/ministral-3b-2512",
    label: "Ministral 3B (OpenRouter)",
  },
  {
    value: "openrouter/mistralai/devstral-2512",
    label: "Devstral 2512 (OpenRouter)",
  },
  // Meta — OpenRouter
  {
    value: "openrouter/meta-llama/llama-3-70b-instruct",
    label: "Llama 3 70B (OpenRouter)",
  },
  // Moonshot — OpenRouter
  { value: "openrouter/moonshotai/kimi-k2.5", label: "Kimi K2.5 (OpenRouter)" },
  // MiniMax — OpenRouter
  {
    value: "openrouter/minimax/minimax-m2.5",
    label: "MiniMax M2.5 (OpenRouter)",
  },
  {
    value: "openrouter/minimax/minimax-m2.1",
    label: "MiniMax M2.1 (OpenRouter)",
  },
  { value: "openrouter/minimax/minimax-m2", label: "MiniMax M2 (OpenRouter)" },
  // GLM — OpenRouter
  { value: "openrouter/z-ai/glm-5", label: "GLM-5 (OpenRouter)" },
  { value: "openrouter/z-ai/glm-4.7", label: "GLM-4.7 (OpenRouter)" },
  {
    value: "openrouter/z-ai/glm-4.7-flash",
    label: "GLM-4.7 Flash (OpenRouter)",
  },
  { value: "openrouter/z-ai/glm-4.6", label: "GLM-4.6 (OpenRouter)" },
  // Other
  {
    value: "openrouter/xiaomi/mimo-v2-flash",
    label: "MiMo V2 Flash (OpenRouter)",
  },
  {
    value: "openrouter/bytedance/ui-tars-1.5-7b",
    label: "UI-TARS 1.5 7B (OpenRouter)",
  },
];
