"""Domain checking functionality."""

import datetime
import time
import logging
import random
import whois
import dns.resolver
from typing import Tuple
from .domain_info import DomainInfo
from .config import Config

logger = logging.getLogger('domain_monitor.checker')

# Constants
CONCERNING_STATUSES = {
    'redemptionPeriod', 
    'pendingDelete', 
    'pendingTransfer', 
    'clientHold',
    'serverHold'
}


def check_domain(domain: str, config: Config) -> DomainInfo:
    """Check a domain for expiration date, status, and nameservers with rate limiting."""
    info = DomainInfo(domain)
    
    # Get rate limiting parameters
    query_delay = config.data['general']['query_delay']
    query_jitter = config.data['general']['query_jitter']
    max_retries = config.data['general']['max_retries']
    
    for attempt in range(max_retries):
        try:
            # Get WHOIS information
            w = whois.whois(domain)
            
            # Extract expiration date
            exp_date = w.expiration_date
            if isinstance(exp_date, list):
                exp_date = min(exp_date)  # Use earliest date if multiple
            
            if exp_date:
                info.expiration_date = exp_date
                # Handle timezone aware datetime by using replace for comparison
                now = datetime.datetime.now()
                if exp_date.tzinfo:
                    # If expiration date has timezone info, make now timezone-aware too
                    now = datetime.datetime.now(exp_date.tzinfo)
                info.days_until_expiration = (exp_date - now).days
                info.is_expired = info.days_until_expiration <= 0
            
            # Extract status
            status = w.status
            if status:
                if isinstance(status, list):
                    info.status = [s.strip() for s in status]
                else:
                    info.status = [s.strip() for s in status.split()]
                
                # Check for concerning statuses
                info.has_concerning_status = any(
                    any(concerning in s.lower() for concerning in CONCERNING_STATUSES)
                    for s in info.status
                )
            
            # Try to get nameservers from WHOIS data
            if w.nameservers:
                if isinstance(w.nameservers, list):
                    info.nameservers = [ns.rstrip('.') for ns in w.nameservers]
                else:
                    info.nameservers = [w.nameservers.rstrip('.')]
            
            # If nameservers are not available from WHOIS, use DNS lookup
            if not info.nameservers:
                try:
                    ns_records = dns.resolver.resolve(domain, 'NS')
                    info.nameservers = [ns.target.to_text().rstrip('.') for ns in ns_records]
                except Exception as dns_err:
                    logger.warning(f"Failed to get nameservers for {domain} via DNS: {dns_err}")
                    # Don't set error here as we still have other useful info
            
            # Check for nameserver changes if we have nameservers
            if info.nameservers:
                # Track nameserver changes in the database
                changed, added, removed = config.db.update_nameservers(domain, info.nameservers)
                if changed:
                    info.nameservers_changed = True
                    info.added_nameservers = added
                    info.removed_nameservers = removed
                    logger.warning(f"Nameserver change detected for {domain}")
                    if added:
                        logger.warning(f"  Added: {', '.join(added)}")
                    if removed:
                        logger.warning(f"  Removed: {', '.join(removed)}")
            
            # Success, exit the retry loop
            break
            
        except Exception as e:
            # Check if this is a rate limiting error
            rate_limit_indicators = ['rate limit', 'too many requests', 'throttle']
            
            if any(indicator in str(e).lower() for indicator in rate_limit_indicators) and attempt < max_retries - 1:
                # Exponential backoff with jitter
                backoff_time = (query_delay * (2 ** attempt)) + (random.random() * query_jitter)
                logger.warning(f"Rate limit detected for {domain}, backing off for {backoff_time:.2f}s (attempt {attempt+1}/{max_retries})")
                time.sleep(backoff_time)
            else:
                # Not a rate limiting error or final attempt
                info.error = str(e)
                logger.error(f"Error checking domain {domain}: {e}")
                break
    
    # Apply rate limiting delay before next query (with jitter to avoid thundering herd)
    jitter = random.random() * query_jitter
    time.sleep(query_delay + jitter)
    
    return info


def needs_alert(domain_info: DomainInfo, alert_threshold: int) -> Tuple[bool, str]:
    """Determine if an alert should be sent for this domain."""
    
    if domain_info.error:
        return True, f"Error checking domain: {domain_info.error}"
    
    reasons = []
    
    # Check expiration
    if domain_info.is_expired:
        reasons.append(f"EXPIRED ({domain_info.days_until_expiration} days ago)")
    elif domain_info.days_until_expiration is not None and domain_info.days_until_expiration <= alert_threshold:
        reasons.append(f"Expiring soon ({domain_info.days_until_expiration} days remaining)")
    
    # Check concerning statuses
    concerning = []
    for status in domain_info.status:
        for concern in CONCERNING_STATUSES:
            if concern.lower() in status.lower():
                concerning.append(status)
    
    if concerning:
        reasons.append(f"Concerning status: {', '.join(concerning)}")
    
    # Check for nameserver changes
    if domain_info.nameservers_changed:
        changes = []
        if domain_info.added_nameservers:
            changes.append(f"added: {', '.join(domain_info.added_nameservers)}")
        if domain_info.removed_nameservers:
            changes.append(f"removed: {', '.join(domain_info.removed_nameservers)}")
        
        if changes:
            reasons.append(f"Nameserver changes detected ({'; '.join(changes)})")
        else:
            reasons.append("Nameserver changes detected")
    
    return bool(reasons), ", ".join(reasons)