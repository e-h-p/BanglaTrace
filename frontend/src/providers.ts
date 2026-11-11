import type { Provider } from "./types";

export const providers: Record<
  Provider,
  { name: string; keyUrl: string; modelHint: string }
> = {
  openrouter: {
    name: "OpenRouter",
    keyUrl: "https://openrouter.ai/settings/keys",
    modelHint:
      "Enter an OpenRouter route such as provider/model-name, or load the catalog.",
  },
  openai: {
    name: "OpenAI / ChatGPT",
    keyUrl: "https://platform.openai.com/api-keys",
    modelHint:
      "Use your OpenAI API key and a GPT text model ID available to your account.",
  },
  anthropic: {
    name: "Claude / Anthropic",
    keyUrl: "https://platform.claude.com/settings/keys",
    modelHint:
      "Use your Anthropic API key and a Claude model ID available to your account.",
  },
};
