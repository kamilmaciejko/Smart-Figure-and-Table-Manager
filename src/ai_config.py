"""User-managed LiteLLM configuration for optional caption text correction."""

import json
import os
from urllib.parse import urlsplit, urlunsplit

from src.ai_prompts import FIGURE_LIST_PROMPTS, TABLE_LIST_PROMPTS

# ===============================================================================
# Use the model map bundled with LiteLLM; configuration must also work offline.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "true")
# User configuration. Keep credentials in provider environment variables.
provider = "ollama"  # E.g. "openai", "anthropic", "gemini", "ollama". Check litellm.provider_list for supported providers.
model = "qwen3.5:4b"  # E.g. "gpt-5", "claude-sonnet-4-5-20250929", "qwen3.5:4b".
base_url = "http://localhost:11434/api/chat"  # Optional for providers with a default endpoint.
api_key = None  # LiteLLM reads provider environment variables when this is None.
# ===============================================================================
# Default AI request settings.
figure_batch_size = 5
table_batch_size = 10
batch_character_limit = 5000
response_token_limit = 2000
caption_character_limit = 160
activation_timeout = 30
request_timeout = 120
# ===============================================================================

def _required_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    return value.strip()


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _normalize_base_url(value, ollama=False):
    if value is None or not str(value).strip():
        return "http://localhost:11434" if ollama else None

    parsed = urlsplit(str(value).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be a valid HTTP or HTTPS URL.")
    if parsed.query or parsed.fragment:
        raise ValueError("base_url cannot contain a query string or fragment.")

    path = parsed.path.rstrip("/")
    if ollama and path in {"/api/chat", "/api/generate", "/v1/chat/completions"}:
        path = ""
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", "")).rstrip("/")


def llm_config(
    provider, model, base_url=None, api_key=None, *, figure_batch_size=5,
    table_batch_size=10, batch_character_limit=5000, response_token_limit=2000,
    caption_character_limit=160, activation_timeout=30, request_timeout=120,
):
    """Validate user input and return keyword arguments for ``litellm.completion``."""
    import litellm

    configured_provider = _required_text(provider, "provider").lower()
    configured_model = _required_text(model, "model")
    ollama = configured_provider in {"ollama", "ollama_chat"}
    resolved_provider = "ollama_chat" if ollama else configured_provider
    known_providers = {item.value for item in litellm.provider_list}
    chat_providers = set(litellm.LITELLM_CHAT_PROVIDERS)

    if resolved_provider not in known_providers:
        raise ValueError(
            f"Unsupported LiteLLM provider: {configured_provider!r}. "
            "Use a provider name supported by the installed LiteLLM version."
        )
    if resolved_provider not in chat_providers:
        raise ValueError(
            f"LiteLLM provider {configured_provider!r} does not support chat completions."
        )

    prefix, separator, model_name = configured_model.partition("/")
    if separator and prefix in known_providers:
        if prefix not in {resolved_provider, configured_provider}:
            raise ValueError(
                f"Model prefix {prefix!r} does not match provider {configured_provider!r}."
            )
        configured_model = model_name

    qualified_model = f"{resolved_provider}/{configured_model}"
    normalized_url = _normalize_base_url(base_url, ollama=ollama)
    normalized_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
    request_settings = {
        "figure_batch_size": _positive_int(figure_batch_size, "figure_batch_size"),
        "table_batch_size": _positive_int(table_batch_size, "table_batch_size"),
        "batch_character_limit": _positive_int(batch_character_limit, "batch_character_limit"),
        "response_token_limit": _positive_int(response_token_limit, "response_token_limit"),
        "caption_character_limit": _positive_int(caption_character_limit, "caption_character_limit"),
        "activation_timeout": _positive_int(activation_timeout, "activation_timeout"),
        "request_timeout": _positive_int(request_timeout, "request_timeout"),
    }

    try:
        _, detected_provider, _, _ = litellm.get_llm_provider(
            model=qualified_model,
            custom_llm_provider=resolved_provider,
            api_base=normalized_url,
            api_key=normalized_key,
        )
        supported_params = litellm.get_supported_openai_params(
            model=qualified_model,
            custom_llm_provider=resolved_provider,
        ) or []
    except Exception as exc:
        raise ValueError(f"LiteLLM rejected the configuration: {exc}") from exc

    if detected_provider != resolved_provider:
        raise ValueError(
            f"LiteLLM resolved provider {detected_provider!r}, expected {resolved_provider!r}."
        )

    completion_kwargs = {
        "model": qualified_model,
        "custom_llm_provider": resolved_provider,
    }
    if normalized_url:
        completion_kwargs["api_base"] = normalized_url
    if normalized_key:
        completion_kwargs["api_key"] = normalized_key

    def accepts(**parameters):
        try:
            litellm.get_optional_params(
                model=qualified_model,
                custom_llm_provider=resolved_provider,
                **parameters,
            )
            return True
        except Exception:
            return False

    if "temperature" in supported_params and accepts(temperature=0.1):
        completion_kwargs["temperature"] = 0.1
    if ollama and accepts(think=False):
        completion_kwargs["think"] = False

    return {
        "provider": resolved_provider,
        "model": qualified_model,
        "api_base": normalized_url,
        "api_key_configured": normalized_key is not None,
        "supported_openai_params": tuple(supported_params),
        "completion_kwargs": completion_kwargs,
        "request_settings": request_settings,
    }

def llm_test_request(config):
    try:
        from litellm import completion

        completion(
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            **config["completion_kwargs"],
            timeout=config.get("request_settings", {}).get("activation_timeout", 30),
            max_retries=0,
        )
        return {
            'status': 'llm_active',
            'error': None,
        }
    except Exception as err:
        return {
            'status': 'llm_invalid',
            'error': str(err),
        }


def activate_configured_llm():
    """Validate the user-managed configuration and send one harmless test request."""
    try:
        config = llm_config(
            provider, model, base_url, api_key,
            figure_batch_size=figure_batch_size,
            table_batch_size=table_batch_size,
            batch_character_limit=batch_character_limit,
            response_token_limit=response_token_limit,
            caption_character_limit=caption_character_limit,
            activation_timeout=activation_timeout,
            request_timeout=request_timeout,
        )
    except Exception as err:
        return {"status": "llm_invalid", "error": str(err), "model": None, "config": None}

    result = llm_test_request(config)
    return {
        **result,
        "model": config["model"],
        "config": config if result["status"] == "llm_active" else None,
    }

def _parse_response(response):
    content = response.choices[0].message.content
    if not isinstance(content, str) or not content.strip():
        raise ValueError("The LLM returned an empty response.")

    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    parsed = json.loads(text)
    if isinstance(parsed, dict) and "items" in parsed:
        results = parsed["items"]
    elif isinstance(parsed, dict) and "id" in parsed:
        results = [parsed]
    else:
        results = parsed
    if not isinstance(results, list):
        raise ValueError("The LLM response must contain an items list.")
    return results


def _results_by_id(batch, results):
    if any(not isinstance(result, dict) for result in results):
        raise ValueError("Each LLM result must be a JSON object.")
    by_id = {str(result.get("id")): result for result in results}
    expected = {item["_key"] for item in batch}
    if len(by_id) != len(results) or set(by_id) != expected:
        raise ValueError("The LLM response contains missing, duplicated, or unexpected IDs.")
    return by_id


AI_EDIT_TYPES = {"NO_CHANGE", "REMOVE_COMMENTARY", "TEXT_CORRECTION", "UNRESOLVED"}
AI_CHANGE_TYPES = AI_EDIT_TYPES - {"NO_CHANGE"}


def _list_result_rows(batch, results, object_type):
    by_id = _results_by_id(batch, results)
    rows = []
    for item in batch:
        result = by_id[item["_key"]]
        decision = str(result.get("decision", "")).upper()
        edit_type = str(result.get("edit_type", "")).upper()
        if (
            decision not in {"KEEP", "EDIT"}
            or edit_type not in AI_EDIT_TYPES
            or (decision == "EDIT" and edit_type not in AI_CHANGE_TYPES)
        ):
            raise ValueError(f"Invalid AI decision for item {item['id']!r}.")
        if decision == "KEEP":
            edit_type = "NO_CHANGE"

        originals = item["texts"]
        if object_type == "figures":
            suggestions = result.get("suggestions") or []
            if not isinstance(suggestions, list) or any(
                not isinstance(value, dict)
                or type(value.get("position")) is not int
                or not isinstance(value.get("text"), str)
                for value in suggestions
            ):
                raise ValueError(f"Invalid figure suggestions for item {item['id']!r}.")
            by_position = {value["position"]: value["text"].strip() for value in suggestions}
            expected = set(range(1, len(originals) + 1))
            if len(by_position) != len(suggestions) or set(by_position) != expected:
                raise ValueError(f"Incomplete figure suggestions for item {item['id']!r}.")
            proposed = [by_position[position] for position in sorted(expected)]
        else:
            text = result.get("suggested_text")
            if not isinstance(text, str):
                raise ValueError(f"Invalid table suggestion for item {item['id']!r}.")
            proposed = [text.strip()]

        if decision == "KEEP" or edit_type == "UNRESOLVED":
            proposed = originals
        if item.get("shared_caption") and decision == "KEEP":
            raise ValueError(f"Shared figure caption {item['id']!r} was not reviewed.")
        if item.get("shared_caption") and edit_type != "UNRESOLVED" and (
            len(set(proposed)) != len(proposed) or originals[0] in proposed
        ):
            raise ValueError(f"Figure group {item['id']!r} was not fully split.")
        elif decision == "EDIT" and edit_type != "UNRESOLVED" and proposed == originals:
            decision, edit_type = "KEEP", "NO_CHANGE"
        # A group must be accepted or retained as a whole; never apply half a split.
        if any(len(text) > item["max_characters"] for text in proposed):
            decision, edit_type, proposed = "EDIT", "UNRESOLVED", originals
        for position, (original, proposed_text) in enumerate(zip(originals, proposed), start=1):
            if not proposed_text:
                raise ValueError(f"Empty AI suggestion for item {item['id']!r}.")
            rows.append({
                "id": item["id"], "position": position, "original_text": original,
                "suggested_text": proposed_text, "decision": decision,
                "edit_type": edit_type, "status": "success", "error": None,
            })
    return rows


def _list_error_rows(batch, error):
    return [
        {
            "id": item["id"], "position": position, "original_text": text,
            "suggested_text": text, "decision": "EDIT", "edit_type": "UNRESOLVED",
            "status": "error", "error": str(error),
        }
        for item in batch for position, text in enumerate(item["texts"], start=1)
    ]


def llm_list_request(config, object_type, items, language, batch_size=None, character_limit=None):
    """Review figure groups or table captions and return one normalized row per list entry."""
    from litellm import completion

    if object_type not in {"figures", "tables"}:
        raise ValueError("object_type must be 'figures' or 'tables'.")
    language = {"polish": "Polish", "english": "English"}.get(str(language).lower())
    if language is None:
        raise ValueError("language must be 'Polish' or 'English'.")
    if not isinstance(config, dict) or "completion_kwargs" not in config:
        raise ValueError("Active AI configuration is required.")

    prompts = FIGURE_LIST_PROMPTS if object_type == "figures" else TABLE_LIST_PROMPTS
    settings = config.get("request_settings", {})
    default_size = settings.get(
        "figure_batch_size" if object_type == "figures" else "table_batch_size",
        5 if object_type == "figures" else 10,
    )
    batch_size = default_size if batch_size is None else int(batch_size)
    character_limit = settings.get("batch_character_limit", 5000) if character_limit is None else int(character_limit)
    if batch_size < 1 or character_limit < 1:
        raise ValueError("Batch limits must be positive.")
    prepared = []
    for number, source in enumerate(items, start=1):
        source = dict(source)
        identifier = source.get("id", number)
        texts = source.get("texts", [source.get("text", "")])
        texts = [str(text).strip() for text in texts]
        if not texts or any(not text for text in texts):
            raise ValueError(f"Item {identifier!r} contains empty text.")
        prepared.append({
            "id": identifier, "_key": str(identifier), "texts": texts,
            "image_count": len(texts),
            "shared_caption": len(texts) > 1 and len(set(texts)) == 1,
            "max_characters": int(source.get("max_characters", 160)),
        })
    if len({item["_key"] for item in prepared}) != len(prepared):
        raise ValueError("AI request item identifiers must be unique.")

    def batches():
        batch, characters = [], 0
        for item in prepared:
            length = sum(map(len, item["texts"]))
            if batch and (len(batch) >= batch_size or characters + length > character_limit):
                yield batch
                batch, characters = [], 0
            batch.append(item)
            characters += length
        if batch:
            yield batch

    def run(batch, attempts):
        payload = [
            {**{key: value for key, value in item.items() if key != "_key"}, "id": item["_key"]}
            for item in batch
        ]
        last_error = None
        for _ in range(attempts):
            try:
                kwargs = dict(config["completion_kwargs"])
                if "response_format" in config.get("supported_openai_params", ()):
                    kwargs["response_format"] = {"type": "json_object"}
                if "max_tokens" in config.get("supported_openai_params", ()):
                    kwargs["max_tokens"] = min(
                        settings.get("response_token_limit", 2000),
                        160 * sum(item["image_count"] for item in batch) + 120,
                    )
                response = completion(
                    messages=[
                        {"role": "system", "content": prompts[language]},
                        {"role": "user", "content": json.dumps({"items": payload}, ensure_ascii=False)},
                    ],
                    timeout=settings.get("request_timeout", 120), max_retries=0, **kwargs,
                )
                return _list_result_rows(batch, _parse_response(response), object_type)
            except Exception as exc:
                last_error = exc
        raise last_error

    output = []
    for batch in batches():
        try:
            output.extend(run(batch, attempts=2))
        except Exception as batch_error:
            if len(batch) == 1:
                output.extend(_list_error_rows(batch, batch_error))
                continue
            for item in batch:
                try:
                    output.extend(run([item], attempts=1))
                except Exception as item_error:
                    output.extend(_list_error_rows([item], item_error))
    return output


def improve_list_rows(config, rows, object_type, language, max_characters=None):
    """Replace list text with AI proposals while preserving document metadata."""
    import pandas as pd

    result = rows.copy().reset_index(drop=True)
    if result.empty:
        return result
    if max_characters is None:
        max_characters = config.get("request_settings", {}).get("caption_character_limit", 160)
    result["original_text"] = result["text"]

    groups = []
    if object_type == "figures" and "_ai_group_id" in result:
        keys = [
            value if pd.notna(value) and str(value) else f"single-{index}"
            for index, value in enumerate(result["_ai_group_id"])
        ]
    else:
        keys = [f"{object_type}-{index}" for index in range(len(result))]
    positions_by_id = {}
    for index, key in enumerate(keys):
        positions_by_id.setdefault(str(key), []).append(index)
    for key, positions in positions_by_id.items():
        groups.append({
            "id": str(key), "positions": positions,
            "texts": [
                "" if pd.isna(value) else str(value).strip()
                for value in result.iloc[positions]["text"].tolist()
            ],
            "max_characters": max_characters,
        })

    request_items = [
        {key: value for key, value in group.items() if key != "positions"}
        for group in groups
    ]
    ai_rows = llm_list_request(config, object_type, request_items, language)
    result["decision"] = "KEEP"
    result["edit_type"] = "NO_CHANGE"
    result["ai_error"] = None
    for ai_row in ai_rows:
        row_position = positions_by_id[str(ai_row["id"])][ai_row["position"] - 1]
        result.at[row_position, "text"] = ai_row["suggested_text"]
        result.at[row_position, "decision"] = ai_row["decision"]
        result.at[row_position, "edit_type"] = ai_row["edit_type"]
        result.at[row_position, "ai_error"] = ai_row["error"]
    return result
