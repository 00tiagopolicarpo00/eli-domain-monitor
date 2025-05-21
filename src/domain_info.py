"""Domain information data structures and utilities."""

import datetime
from typing import List, Any


class DomainInfo:
    """Class to store domain information and status."""
    
    def __init__(self, domain: str):
        self.domain = domain
        self.expiration_date = None
        self.days_until_expiration = None
        self.status = []
        self.nameservers = []
        self.is_expired = False
        self.has_concerning_status = False
        self.nameservers_changed = False
        self.added_nameservers = []
        self.removed_nameservers = []
        self.error = None
    
    def __str__(self) -> str:
        if self.error:
            return f"{self.domain}: ERROR - {self.error}"
        
        expiry_str = (f"expires in {self.days_until_expiration} days "
                      f"({self.expiration_date.strftime('%Y-%m-%d')})")
        status_str = f"status: {', '.join(self.status)}"
        ns_str = f"nameservers: {', '.join(self.nameservers)}"
        
        ns_change_str = ""
        if self.nameservers_changed:
            added_str = f"ADDED: {', '.join(self.added_nameservers)}" if self.added_nameservers else ""
            removed_str = f"REMOVED: {', '.join(self.removed_nameservers)}" if self.removed_nameservers else ""
            ns_change_parts = [p for p in [added_str, removed_str] if p]
            ns_change_str = f" [NS CHANGED: {'; '.join(ns_change_parts)}]" if ns_change_parts else " [NS CHANGED]"
        
        return f"{self.domain}: {expiry_str}, {status_str}, {ns_str}{ns_change_str}"