FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p ${LAMBDA_TASK_ROOT}/models
COPY models/model.onnx ${LAMBDA_TASK_ROOT}/models/
COPY models/tokenizer.json ${LAMBDA_TASK_ROOT}/models/

COPY lambda/process_doc.py ${LAMBDA_TASK_ROOT}/
COPY lambda/seed_initialize.py ${LAMBDA_TASK_ROOT}/

ENV PYTHONPATH=${LAMBDA_TASK_ROOT}

CMD [ "process_doc.lambda_handler" ]