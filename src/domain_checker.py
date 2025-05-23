"""Domain checking functionality."""

import datetime
import time
import logging
import random
import whois
import dns.resolver
from typing import Tuple, List
from .domain_info import DomainInfo
from .config import Config

logger = logging.getLogger('domain_monitor.checker')

# Constants
CONCERNING_STATUSES = {
    'autoRenewPeriod',
    'renewPeriod',
    'redemptionPeriod',
    'inactive',
    'pendingDelete',
    'pendingTransfer',
    'clientHold',
    'serverHold',
    'serverRenewProhibited',
    'clientRenewProhibited'
}


def check_domain(domain: str, config: Config, force_check: bool = False) -> DomainInfo:
    """Check a domain for expiration date, status, and nameservers with rate limiting."""
    info = DomainInfo(domain)

    # Get configuration parameters
    query_delay = config.data['general']['query_delay']
    query_jitter = config.data['general']['query_jitter']
    max_retries = config.data['general']['max_retries']
    cache_hours = config.data['general'].get('cache_hours', 24)

    # Check if we should use cached data (unless force_check is True)
    if not force_check and not config.db.should_check_domain(domain, cache_hours):
        cached_data = config.db.get_cached_domain_info(domain)
        if cached_data:
            logger.info(f"Using cached data for {domain} (last checked: {cached_data['last_checked']})")

            # Populate DomainInfo from cached data
            info.expiration_date = cached_data['expiration_date']
            info.status = cached_data['status'] or []
            info.days_until_expiration = cached_data['days_until_expiration']
            info.is_expired = cached_data['is_expired']
            info.has_concerning_status = cached_data['has_concerning_status']
            info.error = cached_data['error']

            # Get cached nameservers to populate info object
            info.nameservers = config.db.get_current_nameservers(domain)

            return info

    logger.info(f"Performing WHOIS lookup for {domain}")

    for attempt in range(max_retries):
        try:
            # Get WHOIS information
            w = whois.whois(domain)

            # Extract expiration date
            exp_date = w.expiration_date
            if isinstance(exp_date, list):
                # Handle mixed timezone-aware and naive datetimes in list
                normalized_dates = []
                for date in exp_date:
                    if date.tzinfo:
                        # Convert timezone-aware to naive
                        normalized_dates.append(date.replace(tzinfo=None))
                    else:
                        normalized_dates.append(date)
                exp_date = min(normalized_dates)  # Use earliest date if multiple

            if exp_date:
                # Convert timezone-aware expiration date to naive for consistent comparison
                if exp_date.tzinfo:
                    exp_date = exp_date.replace(tzinfo=None)

                info.expiration_date = exp_date
                now = datetime.datetime.now()
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

            # Store domain WHOIS data in database
            whois_changed, whois_changes = config.db.update_domain_whois(
                domain, info.expiration_date, info.status, info.has_concerning_status,
                info.is_expired, info.days_until_expiration, info.error
            )

            if whois_changed:
                logger.info(f"Domain WHOIS changes detected for {domain}: {whois_changes}")

            # Check resolution for apex and www domains
            _check_resolution_changes(domain, info, config)

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

    # Store error result in database if we have an error
    if info.error:
        config.db.update_domain_whois(
            domain, info.expiration_date, info.status, info.has_concerning_status,
            info.is_expired, info.days_until_expiration, info.error
        )

    # Apply rate limiting delay before next query (with jitter to avoid thundering herd)
    jitter = random.random() * query_jitter
    time.sleep(query_delay + jitter)

    return info


def _get_nameservers_only(domain: str, config: Config) -> List[str]:
    """Get nameservers for a domain using DNS lookup only (lighter than WHOIS)."""
    try:
        ns_records = dns.resolver.resolve(domain, 'NS')
        nameservers = [ns.target.to_text().rstrip('.') for ns in ns_records]
        return nameservers
    except Exception as e:
        logger.warning(f"Failed to get nameservers for {domain} via DNS: {e}")
        return []


def _check_domain_resolution(domain: str, subdomain: str = '') -> Tuple[List[str], bool]:
    """
    Check where a domain/subdomain resolves to.

    Args:
        domain: The domain name
        subdomain: The subdomain ('' for apex, 'www' for www)

    Returns:
        Tuple containing:
            - List of IP addresses
            - Boolean indicating if domain doesn't exist (NXDOMAIN)
    """
    query_domain = f"{subdomain}.{domain}" if subdomain else domain

    try:
        # Try A record lookup
        a_records = dns.resolver.resolve(query_domain, 'A')
        ips = [str(record) for record in a_records]
        return ips, False
    except dns.resolver.NXDOMAIN:
        # Domain doesn't exist
        return [], True
    except Exception as e:
        # Other DNS errors (timeout, servfail, etc.)
        logger.warning(f"Failed to resolve {query_domain}: {e}")
        return [], False


def _check_resolution_changes(domain: str, info: DomainInfo, config: Config) -> None:
    """Check for resolution changes in both apex and www domains."""

    # Check apex domain resolution
    apex_ips, apex_nxdomain = _check_domain_resolution(domain, '')
    info.apex_ips = apex_ips
    if apex_nxdomain:
        info.domain_not_exist = True
        logger.warning(f"Domain {domain} does not exist (NXDOMAIN)")

    # Track apex resolution changes
    apex_changed, apex_added, apex_removed, apex_became_nxdomain = config.db.update_domain_resolution(
        domain, '', apex_ips, apex_nxdomain
    )
    if apex_changed:
        info.apex_changed = True
        info.apex_added_ips = apex_added
        info.apex_removed_ips = apex_removed
        logger.warning(f"Apex resolution change detected for {domain}")
        if apex_added:
            logger.warning(f"  Added IPs: {', '.join(apex_added)}")
        if apex_removed:
            logger.warning(f"  Removed IPs: {', '.join(apex_removed)}")
        if apex_became_nxdomain:
            logger.warning(f"  Domain became NXDOMAIN")

    # Check www subdomain resolution (only if apex domain exists)
    if not apex_nxdomain:
        www_ips, www_nxdomain = _check_domain_resolution(domain, 'www')
        info.www_ips = www_ips

        # Track www resolution changes
        www_changed, www_added, www_removed, www_became_nxdomain = config.db.update_domain_resolution(
            domain, 'www', www_ips, www_nxdomain
        )
        if www_changed:
            info.www_changed = True
            info.www_added_ips = www_added
            info.www_removed_ips = www_removed
            logger.warning(f"WWW resolution change detected for {domain}")
            if www_added:
                logger.warning(f"  Added IPs: {', '.join(www_added)}")
            if www_removed:
                logger.warning(f"  Removed IPs: {', '.join(www_removed)}")
            if www_became_nxdomain:
                logger.warning(f"  WWW subdomain became NXDOMAIN")


def needs_alert(domain_info: DomainInfo, alert_threshold: int) -> Tuple[bool, str]:
    """Determine if an alert should be sent for this domain."""

    if domain_info.error:
        return True, f"Error checking domain: {domain_info.error}"

    reasons = []

    # Check if domain doesn't exist
    if domain_info.domain_not_exist:
        reasons.append("Domain does not exist (NXDOMAIN)")

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

    # Check for apex resolution changes
    if domain_info.apex_changed:
        changes = []
        if domain_info.apex_added_ips:
            changes.append(f"added: {', '.join(domain_info.apex_added_ips)}")
        if domain_info.apex_removed_ips:
            changes.append(f"removed: {', '.join(domain_info.apex_removed_ips)}")

        if changes:
            reasons.append(f"Apex resolution changes detected ({'; '.join(changes)})")
        else:
            reasons.append("Apex resolution changes detected")

    # Check for www resolution changes
    if domain_info.www_changed:
        changes = []
        if domain_info.www_added_ips:
            changes.append(f"added: {', '.join(domain_info.www_added_ips)}")
        if domain_info.www_removed_ips:
            changes.append(f"removed: {', '.join(domain_info.www_removed_ips)}")

        if changes:
            reasons.append(f"WWW resolution changes detected ({'; '.join(changes)})")
        else:
            reasons.append("WWW resolution changes detected")

    return bool(reasons), ", ".join(reasons)
