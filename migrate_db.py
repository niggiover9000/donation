import sqlite3

def migrate():
    conn = sqlite3.connect('donation.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute("ALTER TABLE settings ADD COLUMN org1 VARCHAR DEFAULT ''")
    except sqlite3.OperationalError:
        pass # Column already exists
    
    try:
        cursor.execute("ALTER TABLE settings ADD COLUMN org2 VARCHAR DEFAULT ''")
    except sqlite3.OperationalError:
        pass
        
    try:
        cursor.execute("ALTER TABLE settings ADD COLUMN org3 VARCHAR DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE bids ADD COLUMN organization VARCHAR DEFAULT ''")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE settings ADD COLUMN paypal_link VARCHAR DEFAULT 'https://paypal.me/'")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    print("Migration successful")

if __name__ == '__main__':
    migrate()
