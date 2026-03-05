# Founder Followup Emails - Remaining 68 Customers

**Date:** 4 March 2026

## Status
- **Sent:** 47 emails
- **Remaining:** 68 emails (hit SendGrid daily limit)

## To Resume Tomorrow

Run this command from the backend directory:

```bash
cd /Users/qaorca/Downloads/Projects/Tag/backend

python3 -c "
import os
import time
from dotenv import load_dotenv
load_dotenv()

import psycopg2
from datetime import datetime
from email_service import send_founder_followup_email

conn = psycopg2.connect('postgresql://postgres:wjqOmlfMamCcuIEwydmamWeGoJKmUlJb@trolley.proxy.rlwy.net:39730/railway')
cur = conn.cursor()

exclude_ids = [1, 2, 5, 43, 75, 102, 105, 125]

cur.execute('''
    SELECT c.id, c.first_name, c.email
    FROM customers c
    LEFT JOIN bookings b ON c.id = b.customer_id
    WHERE c.created_at >= '2026-01-01' AND c.created_at < '2026-02-01'
    AND b.id IS NULL
    AND c.id NOT IN %s
    AND (c.founder_followup_sent IS NULL OR c.founder_followup_sent = false)
    ORDER BY c.id
''', (tuple(exclude_ids),))

customers = cur.fetchall()
print(f'Sending to {len(customers)} remaining customers...')

sent_count = 0
failed_count = 0

for customer_id, first_name, email in customers:
    time.sleep(1)
    success = send_founder_followup_email(email, first_name.strip())

    if success:
        cur.execute('''
            UPDATE customers
            SET founder_followup_sent = true, founder_followup_sent_at = %s
            WHERE id = %s
        ''', (datetime.utcnow(), customer_id))
        conn.commit()
        sent_count += 1
        print(f'✓ Sent to {first_name} ({email})')
    else:
        failed_count += 1
        print(f'✗ Failed: {first_name} ({email})')

print(f'Done! Sent: {sent_count}, Failed: {failed_count}')
conn.close()
"
```

## Remaining Customers (68)

| ID | Name | Email |
|----|------|-------|
| 55 | Jayne Chinnock | jaynec60@aol.com |
| 56 | Rebecca Aruwa | totallybecky@hotmail.com |
| 57 | Nicola Brunell | nicky.brunell@gmail.com |
| 58 | Mabel Clarkson | mabelclarkson27@gmail.com |
| 59 | Jackie Barnett | jackie.barnett1@btinternet.com |
| 60 | Gordon Macartney | g.t.macartney@hotmail.com |
| 61 | Stephen Southwell | sarge3535@hotmail.com |
| 62 | Emma Jane Ralph | emmaralph86@live.co.uk |
| 63 | Graham Perkins | hottriathlete@hotmail.com |
| 64 | Chris Ward | hollymandy1944@gmail.com |
| 65 | Jenny Yendole | jennyyendole@gmail.com |
| 66 | Mary Payne | mary@makingtime.co.uk |
| 67 | John Wise | john.wise976@btinternet.com |
| 68 | Si Morris Green | sijake0610@me.com |
| 69 | Krzysztof Krzyzkowski | krzys78@spoko.pl |
| 70 | John Clifford | johnclifford627@gmail.com |
| 71 | Lucy Holland | lucykeys@hotmail.com |
| 72 | Jennifer Long | jennifer678@gmail.com |
| 73 | Beverley Packwood | bev.packwood@hotmail.com |
| 74 | andrea dowson | andreadowson@hotmail.com |
| 76 | Fred Smith | fred.smith@talk21.com |
| 77 | Nicola Young | nryoung@gmail.com |
| 78 | Sonia Figueira | v_figueira34@hotmail.com |
| 79 | John Smith | jonsmith16@gmail.com |
| 80 | Jessica Wooldridge | jrwooldridge@hotmail.co.uk |
| 81 | John Welton | johnwelton88@gmail.com |
| 82 | Kerry Kemp | kempshouse1234@hotmail.com |
| 83 | Francine Wallis | fandadwallis@googlemail.com |
| 84 | Ian Caley | ljc1803@icloud.com |
| 85 | John Smith | grumpy0701@hotmail.com |
| 86 | Amber Ridgway | Hayleylucy@hotmail.co.uk |
| 87 | Rod Hobbs | rodhobbs70@gmail.com |
| 89 | Joy Hinton | jrpolson@hotmail.com |
| 90 | Tracy McGregor | tracylongnew@gmail.com |
| 91 | Andrew Greening | andrewgreening@gmail.com |
| 92 | Brenda Saunders | brendasaunders50@gmail.com |
| 93 | James Young | young_jr19@hotmail.com |
| 94 | Katie Oly | katieeoly@icloud.com |
| 95 | John Penney | stokenbrand@testing.com |
| 96 | Ruth Loader | rootp83@gmail.com |
| 97 | Sally Anne McDonald | sallymcdonald62@gmail.com |
| 98 | gillian foster | gillianafoster1@gmail.com |
| 99 | Barry House | susanhouse797@yahoo.com |
| 100 | Ian Blanchard | ianpblanchard2@gmail.com |
| 101 | Philip Phillips | phphillips@ntlworld.com |
| 103 | Vince Earley | vince-earley@msn.com |
| 104 | David Thomson | dave.45cdo@yahoo.co.uk |
| 106 | Darren Hollis | darrenhollis@mac.com |
| 107 | Anne Parker | gazannie23@gmail.com |
| 108 | Sue Winston | sueflint21@hotmail.com |
| 109 | Michele Moutray | micheleyogi61@outlook.com |
| 110 | Richard Cooper | rf.cooper44@gmail.com |
| 111 | Lui Hollomby | luihollomby@gmail.com |
| 112 | Nichola Walker | nicholajgreen23@gmail.com |
| 113 | Mel Barstow | melanie.bunker@sky.com |
| 114 | Matt Ballinger | matt.ballinger@sky.com |
| 115 | James Uncles | manfrom@aol.com |
| 116 | David Hannaford | dave.hannie@gmail.com |
| 117 | Rod Hobbs | rod211070@sky.com |
| 118 | James Tiller | outer.boost82@icloud.com |
| 119 | Nhadia Steer | markandnhadia@yahoo.co.uk |
| 121 | Sue Mewett | suemewett7@gmail.com |
| 122 | Helen Hart | helenmaryhart22@gmail.com |
| 123 | DAVID M LINNEY | annieandmark@sky.com |
| 124 | DAVID M LINNEY | markanniejob22@outlook.com |
| 126 | Gareth Gosling | gooze22@hotmail.com |
| 127 | Deborah Boros | debboros69@icloud.com |
| 128 | Karen Hack | magic12111@hotmail.com |
| 129 | June Hardy | junehardy@sky.com |
| 130 | Joanna Maranga | jojonm@hotmail.co.uk |
| 131 | Penelope May | penny.may@btinternet.com |
| 132 | Simon Chase | si.chase@outlook.com |

## Notes
- SendGrid free tier limit is ~100 emails/day
- Script uses 1 second delay between emails to avoid rate limiting
- Customers are automatically marked as `founder_followup_sent = true` in database when successful
