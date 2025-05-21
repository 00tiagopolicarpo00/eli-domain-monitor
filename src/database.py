"""Database operations for domain monitor."""

import sqlite3
import datetime
import logging
from typing import List, Tuple, Dict, Any

logger = logging.getLogger('domain_monitor.database')


class DatabaseManager:
    """Manager for SQLite database operations."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema if it doesn't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create nameservers table if it doesn't exist
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS nameservers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            nameserver TEXT NOT NULL,
            first_seen TIMESTAMP NOT NULL,
            last_seen TIMESTAMP NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            UNIQUE(domain, nameserver)
        )
        ''')
        
        # Create nameserver_history table to track all changes
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS nameserver_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL,
            event_type TEXT NOT NULL,  -- 'add', 'remove'
            nameserver TEXT NOT NULL,
            timestamp TIMESTAMP NOT NULL
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_current_nameservers(self, domain: str) -> List[str]:
        """Get the current active nameservers for a domain."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT nameserver FROM nameservers
        WHERE domain = ? AND is_active = 1
        ORDER BY nameserver
        ''', (domain,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [row['nameserver'] for row in results]
    
    def update_nameservers(self, domain: str, current_nameservers: List[str]) -> Tuple[bool, List[str], List[str]]:
        """
        Update nameservers for a domain and detect changes.
        
        Args:
            domain: The domain name
            current_nameservers: List of current nameservers from WHOIS/DNS
            
        Returns:
            Tuple containing:
                - Boolean indicating if nameservers changed
                - List of added nameservers
                - List of removed nameservers
        """
        # Make sure nameservers are sorted for easier comparison (order doesn't matter)
        if not current_nameservers:
            return False, [], []
        
        current_nameservers = sorted([ns.lower() for ns in current_nameservers])
        previous_nameservers = sorted([ns.lower() for ns in self.get_current_nameservers(domain)])
        
        # Early exit if identical
        if current_nameservers == previous_nameservers:
            # Just update the last_seen timestamp
            self._update_last_seen(domain, current_nameservers)
            return False, [], []
        
        # Get differences
        added = [ns for ns in current_nameservers if ns not in previous_nameservers]
        removed = [ns for ns in previous_nameservers if ns not in current_nameservers]
        
        # If there's no record yet (first time checking), don't report it as a change
        is_first_check = not previous_nameservers
        
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        
        try:
            # Mark all previous nameservers as inactive
            if not is_first_check:
                cursor.execute('''
                UPDATE nameservers SET is_active = 0
                WHERE domain = ?
                ''', (domain,))
            
            # Insert or update current nameservers
            for ns in current_nameservers:
                cursor.execute('''
                INSERT INTO nameservers (domain, nameserver, first_seen, last_seen, is_active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(domain, nameserver) 
                DO UPDATE SET last_seen = ?, is_active = 1
                ''', (domain, ns, now, now, now))
            
            # Record history for added and removed nameservers (but not for first check)
            if not is_first_check:
                for ns in added:
                    cursor.execute('''
                    INSERT INTO nameserver_history (domain, event_type, nameserver, timestamp)
                    VALUES (?, 'add', ?, ?)
                    ''', (domain, ns, now))
                
                for ns in removed:
                    cursor.execute('''
                    INSERT INTO nameserver_history (domain, event_type, nameserver, timestamp)
                    VALUES (?, 'remove', ?, ?)
                    ''', (domain, ns, now))
            
            conn.commit()
        except Exception as e:
            logger.error(f"Database error updating nameservers for {domain}: {e}")
            conn.rollback()
            return False, [], []
        finally:
            conn.close()
        
        # Don't return added/removed for first check
        if is_first_check:
            return False, [], []
        else:
            return (added or removed), added, removed
    
    def _update_last_seen(self, domain: str, nameservers: List[str]) -> None:
        """Update the last_seen timestamp for nameservers."""
        conn = self._get_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        
        try:
            for ns in nameservers:
                cursor.execute('''
                UPDATE nameservers 
                SET last_seen = ?
                WHERE domain = ? AND nameserver = ?
                ''', (now, domain, ns))
            
            conn.commit()
        except Exception as e:
            logger.error(f"Database error updating last_seen for {domain}: {e}")
            conn.rollback()
        finally:
            conn.close()
    
    def get_nameserver_history(self, domain: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent nameserver history for a domain."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT event_type, nameserver, timestamp 
        FROM nameserver_history
        WHERE domain = ?
        ORDER BY timestamp DESC
        LIMIT ?
        ''', (domain, limit))
        
        results = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in results]