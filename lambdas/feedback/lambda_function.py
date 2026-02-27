import json
import psycopg2
import os

from shared.config import (URL_FRONTEND)

def lambda_handler(event, context):
    
    # Gestione CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'POST, OPTIONS'
            },
            'body': ''
        }
    
    try:
        body = json.loads(event['body'])
        query_id = body['messageId']
        feedback_type = body['type']  # 'up' o 'down'
        
        # Conversione in boolean
        feedback_bool = True if feedback_type == 'up' else False
        
        conn = psycopg2.connect(os.environ['DB_URL'])
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE queries_history 
            SET feedback = %s 
            WHERE id = %s
        """, (feedback_bool, query_id))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'status': 'ok'})
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }