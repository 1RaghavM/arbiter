# Arbiter

Arbiter is a student project exploring how to route chat requests across cloud AI models based on task difficulty, expected response quality, cost, and latency. It combines a React interface with a FastAPI backend and PostgreSQL storage, using Jev for prompt analysis and models from OpenAI, Anthropic, and Google for generation. The project compares routed responses with fixed-model baselines to study whether model selection and bounded evaluation can reduce cost or response time while preserving quality.
