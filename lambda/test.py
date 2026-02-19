import sys
import boto3
import onnxruntime as ort

print(f"--- Controllo Ambiente RAG ---")
print(f"Python versione: {sys.version}")
print(f"Boto3: {boto3.__version__}")
print(f"ONNX Runtime: {ort.get_device()}")
print(f"Tokenizers: OK")
print(f"Psycopg2: OK")
print(f"-------------------------------")
print("✅ Tutto pronto per AWS Lambda!")