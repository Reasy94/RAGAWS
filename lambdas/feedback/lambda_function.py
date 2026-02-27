import json
import logging
from shared.config import URL_FRONTEND
from shared.db import get_conn, put_conn

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': URL_FRONTEND,
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': ''
        }
    
    conn = None
    try:
        body = json.loads(event['body'])
        query_id = body['messageId']
        feedback_type = body['type']
        feedback_bool = True if feedback_type == 'up' else False

        conn = get_conn()
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE queries_history 
            SET feedback = %s 
            WHERE id = %s
        """, (feedback_bool, query_id))
        
        conn.commit()
        cur.close()
        
        logger.info(f"Feedback saved: query_id={query_id}, feedback={feedback_bool}")
        
        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': URL_FRONTEND},
            'body': json.dumps({'status': 'ok'})
        }
        
    except Exception as e:
        logger.error(f"Errore feedback: {str(e)}")
        if conn:
            conn.rollback()
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': URL_FRONTEND},
            'body': json.dumps({'error': str(e)})
        }
    finally:
        if conn:
            put_conn(conn)