"""Configuration management for domain monitor."""

import os
import logging
import yaml
from typing import List
from .database import DatabaseManager

# Configure logging
logger = logging.getLogger('domain_monitor.config')

# Constants
DEFAULT_CONFIG_PATH = 'config.yaml'
DEFAULT_DB_PATH = 'domain_monitor.db'
DEFAULT_ALERT_THRESHOLD = 30  # days
DEFAULT_QUERY_DELAY = 2.0  # seconds between WHOIS queries
DEFAULT_JITTER = 1.0  # random jitter added to delay
MAX_RETRIES = 3  # max retries for rate-limited queries


class Config:
    """Configuration manager for domain monitor."""
    
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.data = {
            'general': {
                'alert_days': DEFAULT_ALERT_THRESHOLD,
                'log_file': None,
                'query_delay': DEFAULT_QUERY_DELAY,
                'query_jitter': DEFAULT_JITTER,
                'max_retries': MAX_RETRIES,
                'db_path': DEFAULT_DB_PATH,
                'domains_file': None,
            },
            'email': {
                'enabled': False,
                'smtp_server': None,
                'smtp_port': 587,
                'username': None,
                'password': None,
                'from_address': None,
                'to_addresses': [],
                'subject_prefix': '[Domain Monitor]',
            }
        }
        self.load()
        self.db = DatabaseManager(self.get_db_path())
    
    def load(self) -> None:
        """Load configuration from file."""
        if not os.path.exists(self.config_path):
            logger.warning(f"Config file {self.config_path} not found, using defaults")
            return
        
        try:
            with open(self.config_path, 'r') as f:
                config_data = yaml.safe_load(f) or {}
            
            # Update config with loaded data
            for section in self.data:
                if section in config_data:
                    self.data[section].update(config_data[section])
            
            # Set up logging file if specified
            if self.data['general'].get('log_file'):
                file_handler = logging.FileHandler(self.data['general']['log_file'])
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                ))
                logger.addHandler(file_handler)
                
            logger.info(f"Loaded configuration from {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
    
    def get_domains(self, domains_file: str = None) -> List[str]:
        """Get domains from domains file."""
        domains = []
        seen_domains = set()
        
        # Use specified domains file or one from config
        domains_file = domains_file or self.data['general'].get('domains_file')
        
        # Return empty list if no domains file is specified
        if not domains_file:
            return domains
            
        # Read domains from file if it exists
        if os.path.exists(domains_file):
            try:
                with open(domains_file, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        domain = line.strip().lower()  # Normalize to lowercase
                        if domain and not domain.startswith('#'):
                            if domain in seen_domains:
                                logger.info(f"Skipping duplicate domain '{domain}' on line {line_num} in {domains_file}")
                            else:
                                seen_domains.add(domain)
                                domains.append(domain)
            except Exception as e:
                logger.error(f"Failed to read domains file {domains_file}: {e}")
        else:
            logger.warning(f"Domains file {domains_file} not found")
        
        return domains
    
    def get_alert_days(self) -> int:
        """Get alert threshold in days."""
        return self.data['general']['alert_days']
    
    def get_db_path(self) -> str:
        """Get database file path."""
        return self.data['general']['db_path']
    
    def is_email_enabled(self) -> bool:
        """Check if email notifications are enabled."""
        email_config = self.data['email']
        return (
            email_config['enabled'] and
            email_config['smtp_server'] and
            email_config['from_address'] and
            email_config['to_addresses']
        )