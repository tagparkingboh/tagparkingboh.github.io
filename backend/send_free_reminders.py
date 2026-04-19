#!/usr/bin/env python3
"""Send FREE promo reminder emails in batches."""
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from email_service import send_promo_free_reminder_email
from datetime import datetime

# Production DB from environment variable
db_url = os.getenv("DATABASE_URL") or os.getenv("PRODUCTION_DATABASE_URL")
if not db_url:
    print("Error: DATABASE_URL or PRODUCTION_DATABASE_URL environment variable not set")
    sys.exit(1)
engine = create_engine(db_url)
Session = sessionmaker(bind=engine)

def send_batch(batch_ids, batch_num):
    print(f'\nSending FREE promo reminders - Batch {batch_num}: {batch_ids}')
    print('-' * 60)

    with Session() as session:
        for sub_id in batch_ids:
            result = session.execute(text('''
                SELECT id, first_name, email, promo_free_code
                FROM marketing_subscribers
                WHERE id = :id
            '''), {'id': sub_id})
            row = result.fetchone()

            if row:
                success = send_promo_free_reminder_email(
                    email=row[2],
                    first_name=row[1] or 'there',
                    promo_code=row[3]
                )
                if success:
                    session.execute(text('''
                        UPDATE marketing_subscribers
                        SET promo_free_reminder_sent = true,
                            promo_free_reminder_sent_at = :now
                        WHERE id = :id
                    '''), {'id': sub_id, 'now': datetime.utcnow()})
                    session.commit()
                    print(f'✓ ID {sub_id}: Sent to {row[2]}')
                else:
                    print(f'✗ ID {sub_id}: Failed to send to {row[2]}')
            else:
                print(f'✗ ID {sub_id}: Not found')

    print(f'Batch {batch_num} complete!')

if __name__ == '__main__':
    batch_num = int(sys.argv[1]) if len(sys.argv) > 1 else 1

    batches = {
        1: [67, 60, 56, 50, 49],
        2: [47, 45, 44, 39, 35],
        3: [27, 26, 23, 20, 18],
        4: [15, 14, 6, 2],
    }

    if batch_num in batches:
        send_batch(batches[batch_num], batch_num)
    else:
        print(f'Invalid batch number. Use 1-4')
