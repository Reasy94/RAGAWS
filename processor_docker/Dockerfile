FROM public.ecr.aws/lambda/python:3.12

RUN dnf install -y gcc gcc-c++ 

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiamo i file mantenendo i nomi originali nella root della Lambda
COPY lambda/process_doc.py ${LAMBDA_TASK_ROOT}/
COPY lambda/seed_initialize.py ${LAMBDA_TASK_ROOT}/

# Il CMD punta al file che deve ricevere l'evento. 
# Scegliamo process_doc come handler principale.
CMD [ "process_doc.lambda_handler" ]