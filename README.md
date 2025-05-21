# Domain Monitor

A CLI tool to monitor domains for expiration dates, status changes, and nameserver information. It can process a single domain or a list from a file and send email alerts for domains nearing expiration, concerning statuses, or when nameservers change.

## Features

- Check domain expiration dates
- Monitor domain status (e.g., redemptionPeriod, pendingDelete)
- Display nameserver information
- Track nameserver changes over time using SQLite database
- Get alerts when nameservers change
- Send email alerts for domains requiring attention
- Process single domains or bulk lists
- Configurable via YAML config file
- Designed for cron job integration
- Rate limiting protection for bulk WHOIS queries

## Installation

1. Clone this repository:
```
git clone https://github.com/yourusername/domain-monitor.git
cd domain-monitor
```

2. Install required packages:
```
pip install -r requirements.txt
```

## Project Structure

The project has been organized into a modular structure for better maintainability:

```
├── domain_monitor.py       # Main CLI entry point
├── src/                    # Source modules
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── database.py        # SQLite database operations
│   ├── domain_checker.py  # Domain checking logic
│   ├── domain_info.py     # Domain data structures
│   └── email_sender.py    # Email notification functionality
├── test/                   # Test files
│   └── test_domain_monitor.py
├── config.yaml.example     # Example configuration
├── domains.txt.example     # Example domains list
└── requirements.txt        # Python dependencies
```

3. Create a configuration file:
```
cp config.yaml.example config.yaml
```

4. Edit the configuration file to match your requirements:
```
nano config.yaml
```

## Usage

### Basic Usage

The simplest way to use the tool is to:
1. Set up your `domains_file` in config.yaml
2. Run the check command with no parameters:

```
python domain_monitor.py check
```

You can also override or specify domains in other ways:

Check a single domain:
```
python domain_monitor.py check --domain example.com
```

Check domains from a specific file (overrides config setting):
```
python domain_monitor.py check --file domains.txt
```

### Test Email Configuration

To verify that your SMTP configuration works properly:
```
python domain_monitor.py test-email
```

You can also send to a specific email address:
```
python domain_monitor.py test-email --recipient user@example.com
```

### Configuration

Copy the example configuration file:
```
cp config.yaml.example config.yaml
```

### Command-Line Options

#### Domain Check Options
```
Usage: domain_monitor.py check [OPTIONS]

  Check domains for expiration dates and status.

Options:
  -d, --domain TEXT              Single domain to check
  -f, --file TEXT                File containing list of domains (overrides domains_file in config)
  -c, --config TEXT              Path to config file
  -a, --alert-days INTEGER       Days threshold for expiration alerts
  -q, --quiet                    Suppress output except for errors
  --send-email / --no-email      Override config email setting
  --delay FLOAT                  Delay between WHOIS queries (seconds)
  --db-path TEXT                 Override database path for nameserver tracking
  --help                         Show this message and exit
```

#### Email Test Options
```
Usage: domain_monitor.py test-email [OPTIONS]

  Send a test email to verify SMTP configuration.

Options:
  -c, --config TEXT      Path to config file
  -r, --recipient TEXT   Override recipient email address
  --help                 Show this message and exit
```

## Cron Job Integration

Add the script to your crontab to run automatically:

```
# Run domain check daily at 2 AM
0 2 * * * cd /path/to/domain-monitor && python domain_monitor.py check --quiet >> /var/log/domain-monitor.log 2>&1
```

## Alert Conditions

The script will generate alerts for domains under the following conditions:

- Domain expires within the configured threshold (default: 30 days)
- Domain has a concerning status (redemptionPeriod, pendingDelete, pendingTransfer, clientHold, serverHold)
- Nameservers have changed since the last check
- Error occurs while checking domain information

## Nameserver Change Detection

The script tracks nameserver changes over time using an SQLite database:

- Each domain's nameservers are recorded in the database
- When nameservers change, alerts are generated
- Changes are tracked regardless of the order of nameservers
- History of nameserver changes is maintained

### Viewing Nameserver History

You can view the nameserver history for a domain:

```
python domain_monitor.py ns-history example.com
```

Options:
```
Usage: domain_monitor.py ns-history [OPTIONS] DOMAIN

  View nameserver history for a specific domain.

Options:
  -c, --config TEXT     Path to config file
  --db-path TEXT        Override database path
  -l, --limit INTEGER   Maximum number of history entries to show
  --help                Show this message and exit
```

## Rate Limiting

The script includes protection against WHOIS rate limiting:

- Configurable delay between queries
- Random jitter to prevent synchronized requests
- Exponential backoff for rate-limited queries
- Configurable maximum retry attempts

## Development

### Running Tests

```bash
# Run all tests
pytest test/

# Run specific test
pytest test/test_domain_monitor.py::test_domain_info_initialization -v

# Run tests with coverage
pytest --cov=src test/
```

### Code Structure

The application is organized into separate modules:

- **config.py**: Handles YAML configuration loading and database initialization
- **database.py**: Manages SQLite operations for nameserver tracking
- **domain_checker.py**: Core domain checking logic with rate limiting
- **domain_info.py**: Data structures for domain information
- **email_sender.py**: SMTP email functionality for alerts
- **domain_monitor.py**: Main CLI interface using Click

## License

MIT