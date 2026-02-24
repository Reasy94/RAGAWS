import json
import boto3

from shared.config import TITAN_MODEL_ID, MAX_INPUT_CHARS

_bedrock = None


def _get_bedrock():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime")
    return _bedrock


def get_embedding(text: str) -> list[float]:
    response = _get_bedrock().invoke_model(
        modelId     = TITAN_MODEL_ID,
        contentType = "application/json",
        accept      = "application/json",
        body        = json.dumps({"inputText": text[:MAX_INPUT_CHARS]}),
    )
    body = json.loads(response["body"].read())
    return body["embedding"]
